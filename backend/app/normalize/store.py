"""원문 1건 → 후보 → resolve → 사실 테이블 upsert + field_provenance + change_event (한 트랜잭션).

``store_raw_document(session, raw)``:
1. raw_document 행 확인(없으면 sha256 기준으로 넣는다 — 수집기가 이미 넣었으면 그 행).
2. source_kind별 파서로 후보를 만든다(notice_pdf·applyhome_*·rtms·stats).
3. 후보의 entity_key를 행 id로 묶는다: complex = 주택관리번호(applyhome_id; 임의공급·무순위 공고는 최초 번호),
   complex_type = 단지 + 타입(청약홈의 문자 없는 주택형 '84.9582'는 전용면적이 같은 약식 타입과 같은 행),
   payment_terms = 단지 + 공고번호, competition = 단지 + 공급형태·순위·타입,
   rtms_trade·unsold = 같은 거래·같은 달.
   없는 행은 만든다(단지 행은 raw.region_id가 있어야 한다).
4. 같은 행·필드에 이미 다른 원문 출처가 있으면 그 출처 행(field_provenance: value_norm·observed_on·rank·라벨)
   으로 후보를 되살려 합친다 — 옛 원문을 다시 읽거나 파싱하지 않는다(계약 2026-10-09.2).
   우선순위 판정(resolve)은 항상 그 필드의 모든 출처를 함께 본다
   (T5: 청약홈 1,573 vs 공고문 1,769는 저장 순서와 무관하게 청약홈 채택).
   value_norm 이 없는 옛 행(0001 시절)만 그 원문을 다시 파싱한다(호환 읽기).
   다시 쓰면서 value_norm 이 채워진다.
   payment_terms 의 'price_by_type.<type>.<항목>' 후보는 payment_terms.price_by_type json 에 쓴다.
   공식 홈페이지(official_site)의 intake_status 문구 후보는 분류 전이라 사실 테이블·출처 행에 쓰지 않고
   ``StoreResult.candidates``·``skipped`` 로 넘긴다(분류는 판정기·사람).
5. chosen 값을 행에 쓰고, 바뀐 값은 change_event로 남긴다(새 공고 = critical, 계약금 10%→5% = critical, T9).
6. 단지 주소가 정해지면 법정동·생활권을 배정한다(지역 밖이면 '범위 경계', D2-6).

트랜잭션: ``session.begin_nested()`` 안에서 한다 — 중간에 실패하면 이 원문의 쓰기가 전부 되돌려진다.
commit은 호출자(잡 러너)가 한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate, ResolvedFields
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import (
    ChangeEvent,
    Competition,
    Complex,
    ComplexType,
    FieldProvenance,
    PaymentTerms,
    RawDocument,
    RtmsTrade,
    Unsold,
)
from app.normalize import changes
from app.normalize.applyhome_parser import ApplyhomeParser
from app.normalize.extract_request import ExtractRequest, build_extract_requests
from app.normalize.fields import (
    DECIMAL_FIELDS,
    INT_FIELDS,
    JSON_FIELDS,
    PRIMARY_SOURCES,
    split_price_by_type,
    value_from_norm,
)
from app.normalize.living_area import assign_complex_area
from app.normalize.notice_parser import NoticeParser
from app.normalize.official_site_parser import ComplexKey, OfficialSiteParser
from app.normalize.provenance import upsert_provenance
from app.normalize.resolver import resolve
from app.normalize.rtms_parser import RtmsParser
from app.normalize.stats_parser import StatsParser

__all__ = ["StoreError", "StoreResult", "parser_for", "raw_dto", "store_raw_document"]


class _Parser(Protocol):
    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]: ...


class StoreError(RuntimeError):
    """저장할 수 없는 원문(지역을 모르는 새 단지 등)."""


@dataclass
class StoreResult:
    raw_document_id: int
    candidates: list[FieldCandidate]
    resolved: ResolvedFields
    provenance_ids: list[int]
    change_events: list[ChangeEvent]
    complex_ids: list[int]
    extract_requests: list[ExtractRequest]
    skipped: list[FieldCandidate] = field(default_factory=list)


def parser_for(
    source_kind: str, *, raw_dir: Path | None = None, complex_key: ComplexKey | None = None
) -> _Parser | None:
    """source_kind → 파서.

    ``complex_key``(complex_id → 주택관리번호)는 공식 홈페이지 후보의 단지 키에 쓴다.
    """
    if source_kind == "official_site":
        return OfficialSiteParser(raw_dir=raw_dir, complex_key=complex_key)
    if source_kind == "notice_pdf":
        return NoticeParser(raw_dir=raw_dir)
    if source_kind in ("applyhome_list", "applyhome_detail"):
        return ApplyhomeParser(raw_dir=raw_dir)
    if source_kind == "rtms":
        return RtmsParser(raw_dir=raw_dir)
    if source_kind == "stats":
        return StatsParser(raw_dir=raw_dir)
    return None


def raw_dto(row: RawDocument) -> RawDocumentDTO:
    return RawDocumentDTO(
        id=row.id,
        source_kind=row.source_kind,
        url=row.url,
        fetched_at=row.fetched_at,
        http_status=row.http_status,
        sha256=row.sha256,
        path=row.path,
        content_type=row.content_type,
        text_path=row.text_path,
        table_path=row.table_path,
        complex_id=row.complex_id,
        region_id=row.region_id,
        error_text=row.error_text,
        image_hash=row.image_hash,
        meta=row.meta,
    )


def _ensure_raw_row(session: Session, raw: RawDocumentDTO | RawDocument) -> RawDocument:
    if isinstance(raw, RawDocument):
        return raw
    if raw.id is not None:
        row = session.get(RawDocument, raw.id)
        if row is not None:
            return row
    row = session.scalars(select(RawDocument).where(RawDocument.sha256 == raw.sha256)).first()
    if row is not None:
        return row
    row = RawDocument(
        source_kind=raw.source_kind,
        url=raw.url,
        fetched_at=raw.fetched_at,
        http_status=raw.http_status,
        sha256=raw.sha256,
        path=raw.path,
        content_type=raw.content_type,
        text_path=raw.text_path,
        table_path=raw.table_path,
        complex_id=raw.complex_id,
        region_id=raw.region_id,
        error_text=raw.error_text,
        image_hash=raw.image_hash,
        meta=raw.meta,
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------- 키 → 행


class _Binder:
    """entity_key → 행 id. create=True면 없는 행을 만든다(이번 원문의 후보), False면 찾기만(다시 파싱한 옛
    후보)."""

    def __init__(self, session: Session, *, snapshot_id: int | None, detected_at: str) -> None:
        self.s = session
        self.snapshot_id = snapshot_id
        self.detected_at = detected_at
        self.events: list[ChangeEvent] = []
        self.created: set[tuple[str, int]] = set()
        self.new_terms: list[PaymentTerms] = []
        self._complex: dict[str, Complex] = {}

    # -- complex
    def complex_for(
        self, key: str, raw: RawDocumentDTO, batch: list[FieldCandidate], *, create: bool
    ) -> Complex | None:
        if key in self._complex:
            return self._complex[key]
        cx = self.s.scalars(select(Complex).where(Complex.applyhome_id == key)).first()
        if cx is None and raw.complex_id is not None:
            cand = self.s.get(Complex, raw.complex_id)
            if cand is not None and cand.applyhome_id in (None, key):
                cx = cand
                if create and cx.applyhome_id is None:
                    cx.applyhome_id = key
        if cx is None and create:
            region_id = raw.region_id
            if region_id is None:
                raise StoreError(f"새 단지({key})를 만들려면 raw.region_id가 필요하다")
            name = next(
                (
                    str(c.value)
                    for c in batch
                    if c.entity == "complex" and c.entity_key == key and c.field == "name"
                ),
                key,
            )
            cx = Complex(
                region_id=region_id,
                applyhome_id=key,
                name=name,
                former_names=[],
                apply_dates=[],
                contract_dates=[],
                inclusion_class="미분류",
            )
            self.s.add(cx)
            self.s.flush()
            self.created.add(("complex", cx.id))
            self.events.append(
                changes.new_notice_event(
                    field="applyhome_id",
                    new_text=f"{key} {name}",
                    entity_id=cx.id,
                    snapshot_id=self.snapshot_id,
                    complex_id=cx.id,
                    detected_at=self.detected_at,
                )
            )
        if cx is not None:
            self._complex[key] = cx
        return cx

    # -- complex_type
    def type_for(self, cx: Complex, tcode: str, area: float | None, *, create: bool) -> ComplexType | None:
        types = list(self.s.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id)))
        exact = next((t for t in types if t.type_code == tcode), None)
        if exact is not None:
            return exact
        dec = Decimal(str(area)).quantize(Decimal("0.01")) if area is not None else None
        if dec is not None:
            same_area = [
                t
                for t in types
                if t.area_m2 is not None and Decimal(t.area_m2).quantize(Decimal("0.01")) == dec
            ]
            if "." in tcode and len(same_area) == 1:
                return same_area[0]
            dotted = [t for t in same_area if "." in t.type_code]
            if "." not in tcode and len(dotted) == 1:
                dotted[0].type_code = tcode  # 청약홈 주택형 → 공고문 약식 표기로 이름을 맞춘다
                return dotted[0]
        if not create:
            return None
        t = ComplexType(complex_id=cx.id, type_code=tcode)
        self.s.add(t)
        self.s.flush()
        self.created.add(("complex_type", t.id))
        return t

    # -- payment_terms
    def terms_for(
        self, cx: Complex, notice_no: str, batch: list[FieldCandidate], key: str, *, create: bool
    ) -> PaymentTerms | None:
        row = self.s.scalars(
            select(PaymentTerms).where(PaymentTerms.complex_id == cx.id, PaymentTerms.notice_no == notice_no)
        ).first()
        if row is not None or not create:
            return row
        eff = next(
            (
                c.value
                for c in batch
                if c.entity == "payment_terms"
                and c.entity_key == key
                and c.field == "effective_from"
                and c.value
            ),
            None,
        )
        if not isinstance(eff, str):
            return None
        kind = next(
            (
                str(c.value)
                for c in batch
                if c.entity == "payment_terms"
                and c.entity_key == key
                and c.field == "notice_kind"
                and c.value
            ),
            None,
        )
        had_terms = (
            self.s.scalars(select(PaymentTerms.id).where(PaymentTerms.complex_id == cx.id)).first()
            is not None
        )
        row = PaymentTerms(
            complex_id=cx.id,
            notice_no=notice_no,
            effective_from=eff,
            interim_schedule=[],
            notice_kind=kind,
            price_by_type={},
        )
        self.s.add(row)
        self.s.flush()
        self.created.add(("payment_terms", row.id))
        self.new_terms.append(row)
        if had_terms:
            self.events.append(
                changes.new_notice_event(
                    field="notice_no",
                    new_text=f"{notice_no} {kind or ''}".strip(),
                    entity_id=row.id,
                    snapshot_id=self.snapshot_id,
                    complex_id=cx.id,
                    detected_at=self.detected_at,
                )
            )
        return row

    # -- competition
    def competition_for(
        self, cx: Complex, kind: str, rnd: str, tcode: str, *, create: bool
    ) -> Competition | None:
        row = self.s.scalars(
            select(Competition).where(
                Competition.complex_id == cx.id,
                Competition.kind == kind,
                Competition.round == rnd,
                Competition.type_code == tcode,
            )
        ).first()
        if row is not None or not create:
            return row
        row = Competition(complex_id=cx.id, kind=kind, round=rnd, type_code=tcode)
        self.s.add(row)
        self.s.flush()
        self.created.add(("competition", row.id))
        return row

    # -- rtms_trade / unsold (값으로 식별, 재수집해도 같은 행)
    def trade_for(self, raw: RawDocumentDTO, vals: dict[str, Any], *, create: bool) -> RtmsTrade | None:
        if raw.region_id is None:
            return None
        floor = vals.get("floor")
        row = self.s.scalars(
            select(RtmsTrade).where(
                RtmsTrade.region_id == raw.region_id,
                RtmsTrade.apt_name == vals.get("apt_name"),
                RtmsTrade.deal_date == vals.get("deal_date"),
                RtmsTrade.price_won == int(vals.get("price_won") or 0),
                RtmsTrade.floor.is_(None) if floor is None else RtmsTrade.floor == int(floor),
                RtmsTrade.area_m2 == Decimal(str(vals.get("area_m2"))),
                RtmsTrade.source == vals.get("source"),
            )
        ).first()
        if row is not None or not create:
            return row
        row = RtmsTrade(
            region_id=raw.region_id,
            apt_name=str(vals["apt_name"]),
            area_m2=Decimal(str(vals["area_m2"])),
            price_won=int(vals["price_won"]),
            deal_date=str(vals["deal_date"]),
            source=str(vals["source"]),
            raw_document_id=raw.id,
        )
        self.s.add(row)
        self.s.flush()
        self.created.add(("rtms_trade", row.id))
        return row

    def unsold_for(self, raw: RawDocumentDTO, vals: dict[str, Any], *, create: bool) -> Unsold | None:
        if raw.region_id is None:
            return None
        code = vals.get("scope_code")
        name = vals.get("scope_name")
        stmt = select(Unsold).where(Unsold.region_id == raw.region_id, Unsold.ym == vals.get("ym"))
        stmt = stmt.where(Unsold.scope_code == code) if code else stmt.where(Unsold.scope_name == name)
        row = self.s.scalars(stmt).first()
        if row is not None or not create:
            return row
        row = Unsold(
            region_id=raw.region_id, ym=str(vals["ym"]), source_label="확인됨", raw_document_id=raw.id
        )
        self.s.add(row)
        self.s.flush()
        self.created.add(("unsold", row.id))
        return row

    # -- 묶기
    def bind(
        self, cands: list[FieldCandidate], raw: RawDocumentDTO, *, create: bool
    ) -> tuple[list[FieldCandidate], list[FieldCandidate]]:
        bound: list[FieldCandidate] = []
        skipped: list[FieldCandidate] = []
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for c in cands:
            by_key.setdefault((c.entity, c.entity_key or ""), {})[c.field] = c.value
        ids: dict[tuple[str, str], int | None] = {}
        for c in cands:
            k = (c.entity, c.entity_key or "")
            if k not in ids:
                ids[k] = self._id_for(c.entity, c.entity_key or "", by_key[k], cands, raw, create=create)
            eid = ids[k]
            if eid is None:
                skipped.append(c)
                continue
            bound.append(c.model_copy(update={"entity_id": eid}))
        return bound, skipped

    def _id_for(
        self,
        entity: str,
        key: str,
        vals: dict[str, Any],
        batch: list[FieldCandidate],
        raw: RawDocumentDTO,
        *,
        create: bool,
    ) -> int | None:
        if entity == "complex":
            cx = self.complex_for(key, raw, batch, create=create) if key else None
            return cx.id if cx else None
        if entity in ("complex_type", "payment_terms", "competition"):
            parts = key.split(":")
            cx = self.complex_for(parts[0], raw, batch, create=create) if parts and parts[0] else None
            if cx is None:
                return None
            if entity == "complex_type" and len(parts) == 2:
                area = vals.get("area_m2")
                t = self.type_for(
                    cx, parts[1], float(area) if isinstance(area, (int, float)) else None, create=create
                )
                return t.id if t else None
            if entity == "payment_terms" and len(parts) == 2:
                pt = self.terms_for(cx, parts[1], batch, key, create=create)
                return pt.id if pt else None
            if entity == "competition" and len(parts) == 4:
                comp = self.competition_for(cx, parts[1], parts[2], parts[3], create=create)
                return comp.id if comp else None
            return None
        if entity == "rtms_trade":
            if not {"apt_name", "deal_date", "price_won", "area_m2", "source"} <= vals.keys():
                return None
            tr = self.trade_for(raw, vals, create=create)
            return tr.id if tr else None
        if entity == "unsold":
            un = self.unsold_for(raw, vals, create=create)
            return un.id if un else None
        return None


_MODELS: dict[str, Any] = {
    "complex": Complex,
    "complex_type": ComplexType,
    "payment_terms": PaymentTerms,
    "competition": Competition,
    "rtms_trade": RtmsTrade,
    "unsold": Unsold,
}
_DECIMAL_FIELDS = DECIMAL_FIELDS


def _coerce(field_name: str, v: Any) -> Any:
    if v is None:
        return None
    pbt = split_price_by_type(field_name)
    if pbt is not None:
        return int(v) if pbt[1] in ("max_price_won", "floor_sample_price_won", "units") else str(v)
    if field_name in JSON_FIELDS:
        return json.loads(v) if isinstance(v, str) else v
    if isinstance(v, bool):
        return v
    if field_name in INT_FIELDS or field_name in {
        "floor",
        "completed_year",
        "total",
        "post_completion",
        "price_won",
    }:
        return int(v)
    if field_name in _DECIMAL_FIELDS:
        return Decimal(str(v))
    return v


def _set_price_by_type(
    obj: PaymentTerms,
    c: FieldCandidate,
    pbt: tuple[str, str],
    *,
    initial: bool,
    snapshot_id: int | None,
    detected_at: str,
) -> ChangeEvent | None:
    """payment_terms.price_by_type[type][항목] = 값. json 은 새 dict 로 바꿔 넣어야 변경이 잡힌다.
    값이 바뀌면 change_event(가격 항목은 critical — changes.severity_for)."""
    type_code, item = pbt
    new = _coerce(c.field, c.value)
    cur = dict(obj.price_by_type or {})
    entry = dict(cur.get(type_code) or {})
    had = item in entry
    old_v = entry.get(item)
    if had and changes.fmt_value(old_v) == changes.fmt_value(new):
        return None
    entry[item] = new
    cur[type_code] = entry
    obj.price_by_type = cur
    return changes.value_change_event(
        entity="payment_terms",
        entity_id=obj.id,
        field=c.field,
        old=old_v,
        new=new,
        snapshot_id=snapshot_id,
        complex_id=obj.complex_id,
        detected_at=detected_at,
        initial=initial or not had,
    )


def _candidate_from_row(fp: FieldProvenance, source_kind: str | None) -> FieldCandidate:
    """저장된 출처 행 → 후보(옛 원문을 다시 파싱하지 않는다). primary 는 출처 종류로 되살린다
    (실거래는 rank 1 = Open API 1차, 그 밖 rank = 재가공 2차 — rtms_parser 와 같은 규칙)."""
    primary = (source_kind in PRIMARY_SOURCES) if source_kind is not None else True
    if source_kind == "rtms":
        primary = fp.source_rank == 1
    return FieldCandidate.model_validate(
        {
            "entity": fp.entity,
            "entity_id": fp.entity_id,
            "entity_key": fp.entity_key,
            "field": fp.field,
            "value_text": fp.value_text,
            "value": value_from_norm(fp.field, fp.value_norm),
            "source_rank": fp.source_rank,
            "source_kind": source_kind,
            "primary": primary,
            "label": fp.label,
            "reason": fp.reason,
            "excerpt": fp.excerpt or fp.value_text or fp.field,
            "excerpt_start": fp.excerpt_start,
            "excerpt_end": fp.excerpt_end,
            "raw_document_id": fp.raw_document_id,
            "url": fp.url,
            "checked_at": fp.checked_at,
            "observed_on": fp.observed_on,
            "needs_extract": False,
        }
    )


def _is_legacy(fp: FieldProvenance) -> bool:
    """value_norm 없이 값이 있던 옛 행(0001 시절) — 값 형을 알 수 없어 원문을 다시 파싱한다."""
    return fp.value_norm is None and fp.value_text is not None and fp.label != "확인 불가"


def _reparse_existing(
    session: Session,
    binder: _Binder,
    bound: list[FieldCandidate],
    exclude_raw_id: int,
    raw_dir: Path | None,
    parser_factory: Callable[[str], _Parser | None],
) -> list[FieldCandidate]:
    """같은 (entity, entity_id, field)의 다른 원문 출처 → 후보.

    출처 행(value_norm)에서 되살리고, value_norm 이
    없는 옛 행의 원문만 다시 파싱한다(호환)."""
    del raw_dir
    groups = {(c.entity, c.entity_id, c.field) for c in bound}
    if not groups:
        return []
    pairs = {(e, i) for e, i, _ in groups}
    rows: list[FieldProvenance] = []
    for e, i in sorted(pairs, key=lambda p: (p[0], p[1] or 0)):
        for fp in session.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.entity == e, FieldProvenance.entity_id == i)
            .order_by(FieldProvenance.id)
        ):
            if (
                fp.raw_document_id is not None
                and fp.raw_document_id != exclude_raw_id
                and (fp.entity, fp.entity_id, fp.field) in groups
            ):
                rows.append(fp)
    legacy_raw = {fp.raw_document_id for fp in rows if _is_legacy(fp) and fp.raw_document_id is not None}
    kinds: dict[int, str | None] = {}
    out: list[FieldCandidate] = []
    for fp in sorted(rows, key=lambda r: (r.raw_document_id or 0, r.id)):
        rid = fp.raw_document_id
        if rid is None or rid in legacy_raw:
            continue
        if rid not in kinds:
            raw_row = session.get(RawDocument, rid)
            kinds[rid] = raw_row.source_kind if raw_row is not None else None
        out.append(_candidate_from_row(fp, kinds[rid]))
    for rid in sorted(legacy_raw):
        row = session.get(RawDocument, rid)
        if row is None:
            continue
        dto = raw_dto(row)
        p = parser_factory(dto.source_kind)
        if p is None:
            continue
        old_cands, _ = binder.bind(p.parse(dto), dto, create=False)
        out.extend(c for c in old_cands if (c.entity, c.entity_id, c.field) in groups)
    return out


def store_raw_document(
    session: Session,
    raw: RawDocumentDTO | RawDocument,
    *,
    snapshot_id: int | None = None,
    raw_dir: Path | None = None,
    parser: _Parser | None = None,
    now: datetime | None = None,
) -> StoreResult:
    """원문 1건을 정규화해 저장한다(한 트랜잭션 — SAVEPOINT). commit은 호출자."""
    detected_at = changes.detected_now(now)

    def complex_key(complex_id: int) -> str | None:
        cx = session.get(Complex, complex_id)
        return cx.applyhome_id if cx is not None else None

    def factory(kind: str) -> _Parser | None:
        return parser_for(kind, raw_dir=raw_dir, complex_key=complex_key)

    with session.begin_nested():
        row = _ensure_raw_row(session, raw)
        dto = raw_dto(row)
        p = parser or factory(dto.source_kind)
        cands = p.parse(dto) if p is not None else []
        binder = _Binder(session, snapshot_id=snapshot_id, detected_at=detected_at)
        bound, skipped = binder.bind(cands, dto, create=True)
        old = _reparse_existing(session, binder, bound, row.id, raw_dir, factory)
        resolved = resolve(bound + old)
        fps = upsert_provenance(session, resolved.provenance)
        events = list(binder.events)
        touched_complex: set[int] = set()
        for c in resolved.chosen:
            model = _MODELS.get(c.entity)
            if model is None or c.entity_id is None or c.value is None or c.label == "확인 불가":
                continue
            obj = session.get(model, c.entity_id)
            if obj is None:
                continue
            pbt = split_price_by_type(c.field) if c.entity == "payment_terms" else None
            if pbt is not None:
                ev_pbt = _set_price_by_type(
                    obj,
                    c,
                    pbt,
                    initial=(c.entity, c.entity_id) in binder.created,
                    snapshot_id=snapshot_id,
                    detected_at=detected_at,
                )
                if ev_pbt is not None:
                    events.append(ev_pbt)
                continue
            if not hasattr(model, c.field) or c.field == "id":
                continue
            new = _coerce(c.field, c.value)
            old_v = getattr(obj, c.field)
            if changes.fmt_value(old_v) == changes.fmt_value(new):
                continue
            initial = (c.entity, c.entity_id) in binder.created
            if c.entity == "complex" and c.field == "name" and old_v and not initial:
                names = list(obj.former_names or [])
                if old_v not in names:
                    obj.former_names = [*names, old_v]
            setattr(obj, c.field, new)
            cid = obj.id if c.entity == "complex" else getattr(obj, "complex_id", None)
            ev = changes.value_change_event(
                entity=c.entity,
                entity_id=c.entity_id,
                field=c.field,
                old=old_v,
                new=new,
                snapshot_id=snapshot_id,
                complex_id=cid,
                detected_at=detected_at,
                initial=initial,
            )
            if ev is not None:
                events.append(ev)
            if c.entity == "complex" and c.field == "address":
                touched_complex.add(obj.id)
        session.flush()
        for terms in binder.new_terms:
            events.extend(
                changes.payment_change_events(
                    session, terms, snapshot_id=snapshot_id, detected_at=detected_at
                )
            )
        for cid in sorted(touched_complex):
            cx = session.get(Complex, cid)
            if cx is not None:
                assign_complex_area(session, cx)
        session.add_all(events)
        session.flush()
        cids: set[int] = set()
        for c in bound:
            if c.entity_id is None:
                continue
            if c.entity == "complex":
                cids.add(c.entity_id)
            elif c.entity in ("complex_type", "payment_terms", "competition"):
                parent = session.get(_MODELS[c.entity], c.entity_id)
                if parent is not None:
                    cids.add(parent.complex_id)
        complex_ids = sorted(cids)
    return StoreResult(
        raw_document_id=row.id,
        candidates=cands,
        resolved=resolved,
        provenance_ids=[fp.id for fp in fps],
        change_events=events,
        complex_ids=complex_ids,
        extract_requests=build_extract_requests(bound),
        skipped=skipped,
    )
