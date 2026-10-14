"""원문 1건 → 후보 → resolve → 사실 테이블 upsert + field_provenance + change_event (한 트랜잭션).

``store_raw_document(session, raw)``:
1. raw_document 행 확인(없으면 sha256 기준으로 넣는다 — 수집기가 이미 넣었으면 그 행).
2. source_kind별 파서로 후보를 만든다(notice_pdf·applyhome_*·rtms·stats).
3. 후보의 entity_key를 행 id로 묶는다: complex = 주택관리번호(applyhome_id; 임의공급·무순위 공고는 최초 번호),
   complex_type = 단지 + 타입(청약홈의 문자 없는 주택형 '84.9582'는 전용면적이 같은 약식 타입과 같은 행),
   payment_terms = 단지 + 공고번호, competition = 단지 + 공급형태·순위·**원 면적 코드**(D23-2 — 단지 주택형 대조는 읽기 시점
   표시 속성, ``normalize.competition``),
   rtms_trade·unsold = 같은 거래·같은 달.
   없는 행은 만든다(단지 행은 raw.region_id가 있어야 한다).
   단지는 **원문의 지역 안에서만** 찾는다(R3 W4): 같은 주택관리번호의 단지가 다른 지역에 있으면 그 행을
   건드리지 않는다. applyhome_id 가 전역 유일(현 스키마)이면 이 원문의 그 단지 후보는 건너뛴다(skipped,
   ``StoreResult.foreign_keys``) — (region_id, applyhome_id) 유일로 바뀌면 지역마다 자기 행을 만든다.
   같은 블록 중복(R3 W12c, D10-4): 잔여 세대(무순위·임의공급·잔여세대) 공고는 최초 주택관리번호를 싣지 않아
   다른 번호로 들어온다. **잔여 공고 원문(URL 경로 Remndr·OPT, 또는 공고 종류 무순위·임의공급·선착순·재공급)
   으로 들어온 새 번호에만**, 같은 지역에서 정규화한 단지명 + 정규화한 공급위치가 모두 같은 단지가 정확히
   1개면 그 행에 묶는다(문자열 정규화는 판단이 아니다). 이름 키는 잔여 공고의 회차·공급 구분 괄호만 떼고
   차수·단지·블록 번호('(2차)', '1단지', 'AA13-1블록')는 남긴다. 주소가 구역 표현('…일원'·'일대'·'외 n필지')
   이면 묶지 않는다. 일반 APT 공고끼리는 묶지 않는다. 둘 이상이거나 주소가 없으면 묶지 않는다.
   **D18-4(R4 C3·M1)**: 잔여·임의·무순위·재공급 공고는 원 단지(사업)의 사건이다 — 자기 번호로 단지 행을 만들기 전에
   원 단지를 찾는다(``_remnant_target``): ① 이번 수집 실행의 연결(``links`` — 앞 원문이 이 번호를 묶은 단지, 공고문
   '최초 주택관리번호' 인용 포함) ② 그 공고번호의 납부 조건·잔여 공고 이력 행이 있는 단지 ③ 같은 블록(위). 찾으면 원
   단지에 묶고(단지 단위 값은 덮지 않는다 — D11-4), 못 찾으면(원 단지를 알 수 없는 잔여 공고) 그 사업의 유일한 행으로
   자기 번호 행을 만든다. 공고문이 인용한 원 번호의 단지가 없으면 원 번호로 행을 만들되 이름은 번호(자리표시)로 두고
   잔여 공고의 단지 단위 값은 쓰지 않는다 — 원 공고는 수집 단계가 주택관리번호로 공식 API 에서 다시 받는다
   (``scheduler.collect``). 자리표시 이름은 묶인 잔여 공고(청약홈 이름, 공급 회차 괄호 뗌)로 채운다. 공식 홈페이지
   주소는 원 단지에 없을 때만 잔여 공고 값으로 채운다(같은 사업의 홈페이지 — 접수 상태 행의 근거).
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

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate, ResolvedFields
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.facts_view import is_human
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
from app.normalize._text import strip_supply_round
from app.normalize.applyhome_parser import ApplyhomeParser
from app.normalize.competition import TYPE_AMBIGUOUS
from app.normalize.extract_request import ExtractRequest, build_extract_requests
from app.normalize.fields import (
    AUDIT_FLAG_REASON,
    CONFLICT_HOLD,
    DECIMAL_FIELDS,
    EXPLICIT_NULL_FIELDS,
    EXTRACT_REASON,
    INT_FIELDS,
    JSON_FIELDS,
    PRIMARY_SOURCES,
    QUIET_FIRST_FIELDS,
    compare_mark,
    is_price_amount,
    is_superseded,
    norm_value,
    split_discount,
    split_price_by_type,
    strip_tags,
    value_from_norm,
    with_mark,
    with_superseded,
)
from app.normalize.living_area import assign_complex_area, correct_dong
from app.normalize.merge import find_duplicate, live, merge_duplicate
from app.normalize.notice_parser import NoticeParser, ScanTypes
from app.normalize.official_site_parser import ComplexKey, OfficialSiteParser
from app.normalize.provenance import upsert_provenance
from app.normalize.resolver import resolve
from app.normalize.rtms_parser import RtmsParser
from app.normalize.stats_parser import StatsParser

__all__ = [
    "TYPE_AMBIGUOUS",
    "StoreError",
    "StoreResult",
    "address_key",
    "block_name_key",
    "candidate_from_row",
    "current_rows",
    "human_superseded",
    "is_remainder_url",
    "is_zone_address",
    "parser_for",
    "raw_dto",
    "resolve_field_group",
    "retire_superseded",
    "store_raw_document",
    "write_chosen",
]


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
    foreign_keys: list[str] = field(default_factory=list)  # 다른 지역 단지라 건너뛴 주택관리번호(W4)
    first_load_folded: int = 0  # 첫 적재라 이벤트 대신 센 값 기록·덮어쓰기 수(D18-7·D21-7)
    alt_addresses: dict[int, list[str]] = field(default_factory=dict)
    """원 단지에 묶여 쓰지 않은 잔여 공고의 공급위치(단지 id → 주소들) — 원 단지 주소가 아직 없으면(원 공고 전) 수집 단계가
    실행 끝에 다시 쓴다(D22-3, ``living_area.correct_dong``)."""


def parser_for(
    source_kind: str,
    *,
    raw_dir: Path | None = None,
    complex_key: ComplexKey | None = None,
    scan_types: ScanTypes | None = None,
) -> _Parser | None:
    """source_kind → 파서.

    ``complex_key``(complex_id → 주택관리번호)는 공식 홈페이지 후보의 단지 키에 쓴다.
    ``scan_types``(주택관리번호 → 이미 있는 단지의 타입 코드, 없으면 None)는 스캔 공고문의 '확인 불가(스캔)' 후보에 쓴다
    (R5-NORM 2 — 저장 단계만 준다).
    """
    if source_kind == "official_site":
        return OfficialSiteParser(raw_dir=raw_dir, complex_key=complex_key)
    if source_kind == "notice_pdf":
        return NoticeParser(raw_dir=raw_dir, scan_types=scan_types)
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

    def __init__(
        self,
        session: Session,
        *,
        snapshot_id: int | None,
        detected_at: str,
        links: dict[str, int] | None = None,
    ) -> None:
        self.s = session
        # D18-4: 잔여 공고 번호(자기 주택관리번호·공고번호) → 원 단지 id. 수집 실행 하나가 같은 dict 를 넘겨 원문 순서와
        # 무관하게(상세 → 주택형 → 경쟁률) 같은 단지에 묶이게 한다
        self.links: dict[str, int] = links if links is not None else {}
        self.snapshot_id = snapshot_id
        self.detected_at = detected_at
        self.events: list[ChangeEvent] = []
        self.created: set[tuple[str, int]] = set()
        self.new_terms: list[PaymentTerms] = []
        self._complex: dict[str, Complex] = {}
        self.foreign: set[str] = set()
        # D11-4: 잔여·임의·무순위 공고를 다른 번호의 원 단지에 묶은 키 — 그 공고의 단지 단위
        # 후보(complex·complex_type)는
        # 원 단지 값을 덮어쓰지 않는다(payment_terms·competition·remaining_event 에만 기록)
        self.merged: set[str] = set()
        # 잔여 공고 PDF 가 '최초 주택관리번호'로 원 단지를 가리킨 키(R3 4차 M-8) — 그 공고의 단지(complex) 후보만 건너뛴다
        self.cited: set[str] = set()

    # -- complex
    def complex_for(
        self, key: str, raw: RawDocumentDTO, batch: list[FieldCandidate], *, create: bool
    ) -> Complex | None:
        if key in self._complex:
            return self._complex[key]
        if key in self.foreign:
            return None
        region_id = raw.region_id
        stmt = select(Complex).where(Complex.applyhome_id == key)
        if region_id is not None:
            stmt = stmt.where(Complex.region_id == region_id)
        cx = self.s.scalars(stmt).first()
        if cx is not None and cx.merged_into_id is not None:
            # D29-2: 원 단지에 병합된 같은 사업의 중복 행 번호 → 원 단지(잔여 공고처럼 — 단지 단위 값은 덮지 않는다, D11-4)
            target = self.s.get(Complex, cx.merged_into_id)
            if target is not None:
                cx = target
                self.merged.add(key)
                self.links.setdefault(key, target.id)
        cites = create and _cites_original(raw, batch, key)
        if cx is not None and region_id is not None and not cites and _is_remainder_notice(raw, batch, key):
            # R9-PARSE(G7 캘린더 중복): 인용을 못 읽던 때 잔여 공고 번호로 생긴 단지 행(같은 사업의 두 번째 행)이 있어도, 지금
            # 그 번호가 다른 단지(원 단지)의 납부 조건 공고번호로 묶여 있으면(D18-4 인용) 그 원 단지에 쓴다. 남은 옛 행은
            # ``absorbed_remnant_rows`` 로 체크리스트에서 빠진다
            owner = self._absorbing_original(key, region_id)
            if owner is not None:
                cx = owner
                self.merged.add(key)
                self.links.setdefault(key, owner.id)
        if cx is not None and cites:
            # R3 4차 M-8: 잔여 공고 PDF 가 '최초 주택관리번호'로 원 단지를 가리킨다 — 그 공고의 단지 단위 값(이름 '(임의공급
            # 4차)'·남은 세대수·전매·거주·규제)은 원 단지를 덮지 않는다(D11-4, payment_terms·competition 에만 기록).
            # 타입 가격 후보는 그대로 둔다(공고문 파서가 잔여 공고에서 면적·세대수는 내지 않고 가격만 낸다 — 현재 공고 가격)
            self.cited.add(key)
        if cx is None and region_id is not None and _APPLYHOME_ID_GLOBAL:
            other = self.s.scalars(select(Complex.id).where(Complex.applyhome_id == key)).first()
            if other is not None:  # 다른 지역의 단지 — 덮어쓰지 않는다(W4)
                self.foreign.add(key)
                return None
        if cx is None and raw.complex_id is not None:
            cand = self.s.get(Complex, raw.complex_id)
            if (
                cand is not None
                and cand.applyhome_id in (None, key)
                and (region_id is None or cand.region_id == region_id)
            ):
                cx = cand
                if create and cx.applyhome_id is None:
                    cx.applyhome_id = key
        if cx is None and region_id is not None and not cites and _is_remainder_notice(raw, batch, key):
            cx = self._remnant_target(key, region_id, batch, create=create)
            if cx is not None:
                self.merged.add(key)
        if (
            cx is None
            and create
            and region_id is not None
            and not cites
            and not _is_remainder_notice(raw, batch, key)
        ):
            cx = self._upcoming_row(key, region_id, batch)
        if cx is None and create:
            region_id = raw.region_id
            if region_id is None:
                raise StoreError(f"새 단지({key})를 만들려면 raw.region_id가 필요하다")
            name = (
                key  # D18-4: 인용된 원 번호 — 잔여 공고의 이름(제목)이 아니라 자리표시. 원 공고 재수집이 채운다
                if cites
                else next(
                    (
                        str(c.value)
                        for c in batch
                        if c.entity == "complex" and c.entity_key == key and c.field == "name"
                    ),
                    key,
                )
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
            if cites:
                self.cited.add(key)  # 새로 만든 원 단지에도 잔여 공고의 단지 단위 값은 쓰지 않는다(D18-4)
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
            if cites:  # 이 공고문(잔여 공고)의 공고번호 → 원 단지(뒤에 오는 그 공고의 청약홈 원문이 같은 단지에 묶이게)
                for no in sorted(_own_notice_nos(batch, key) | _url_numbers(raw.url)):
                    if no != key:
                        self.links.setdefault(no, cx.id)
                        self._merge_duplicate(no, key, cx, region_id)
        return cx

    def _merge_duplicate(self, own_no: str, cited_no: str, original: Complex, region_id: int | None) -> None:
        """D29-2: 잔여 공고문이 원 공고(``cited_no`` — 이미 있던 원 단지 행)를 인용했고, 그 공고문의 자기 번호 ``own_no`` 로 따로 생긴
        같은 지역 단지 행이 있으면 원 단지에 병합한다(``normalize.merge`` — 인용 없이는 하지 않는다). 이 원문이 원 단지 행을 새로
        만든 경우(자리표시)는 병합하지 않는다."""
        if region_id is None or ("complex", original.id) in self.created:
            return
        dup = find_duplicate(self.s, region_id, own_no, original)
        if dup is None:
            return
        ev = merge_duplicate(
            self.s,
            dup,
            original,
            cited_no=cited_no,
            snapshot_id=self.snapshot_id,
            detected_at=self.detected_at,
        )
        if ev is not None:
            self.events.append(ev)

    def _upcoming_row(self, key: str, region_id: int, batch: list[FieldCandidate]) -> Complex | None:
        """D20-2: 청약홈 새 공고 ``key`` 의 이름 키(``block_name_key``)가 트랙 (A) 공고 예정 후보 행(주택관리번호 없음)의 이름·옛
        이름 키와 **같은** 행이 정확히 1개면 그 행에 주택관리번호를 붙여 같은 단지로 합친다(새 공고 이벤트는 새 단지와 같다).
        문자열 대조(파싱)뿐이다 — 후보 행의 별칭은 판정기 compare 로 이미 모였다(``normalize.upcoming``)."""
        name = next(
            (
                str(c.value)
                for c in batch
                if c.entity == "complex" and c.entity_key == key and c.field == "name"
            ),
            None,
        )
        nk = block_name_key(name) if name else ""
        if not nk:
            return None
        hits = [
            cx
            for cx in self.s.scalars(
                select(Complex).where(
                    Complex.region_id == region_id,
                    Complex.applyhome_id.is_(None),
                    Complex.track == "A",
                    live(),
                )
            )
            if nk in {block_name_key(n) for n in (cx.name, *(cx.former_names or []))}
        ]
        if len(hits) != 1:
            return None
        cx = hits[0]
        cx.applyhome_id = key
        self.s.flush()
        self.created.add(("complex", cx.id))  # 공고 전 후보의 빈 값 → 청약홈 값은 새 공고 이벤트 1건이 대신
        self.events.append(
            changes.new_notice_event(
                field="applyhome_id",
                new_text=f"{key} {name}(공고 예정 후보와 합침)",
                entity_id=cx.id,
                snapshot_id=self.snapshot_id,
                complex_id=cx.id,
                detected_at=self.detected_at,
            )
        )
        return cx

    def _absorbing_original(self, key: str, region_id: int) -> Complex | None:
        """잔여 공고 번호 ``key`` 를 납부 조건 공고번호로 가진 같은 지역의 **다른** 단지(applyhome_id ≠ key)가 정확히 1개면 그 행
        (연결 ``links`` 가 먼저). 표 조회뿐이다(판단 아님)."""
        cid = self.links.get(key)
        cand = self.s.get(Complex, cid) if cid is not None else None
        if (
            cand is not None
            and cand.region_id == region_id
            and cand.applyhome_id != key
            and cand.merged_into_id is None
        ):
            return cand
        ids = set(
            self.s.scalars(
                select(Complex.id)
                .join(PaymentTerms, PaymentTerms.complex_id == Complex.id)
                .where(
                    PaymentTerms.notice_no == key,
                    Complex.region_id == region_id,
                    Complex.applyhome_id.is_distinct_from(key),
                    live(),
                )
            )
        )
        return self.s.get(Complex, ids.pop()) if len(ids) == 1 else None

    def _remnant_target(
        self, key: str, region_id: int, batch: list[FieldCandidate], *, create: bool
    ) -> Complex | None:
        """D18-4: 잔여 공고 번호 ``key`` 의 원 단지(없으면 None). 연결 → 납부 조건·잔여 이력의 공고번호 → 같은 블록."""
        from app.models import RemainingEvent

        nos = {key, *_own_notice_nos(batch, key)}
        hit: Complex | None = None
        for no in sorted(nos):
            cid = self.links.get(no)
            cand = self.s.get(Complex, cid) if cid is not None else None
            if (
                cand is not None
                and cand.region_id == region_id
                and cand.applyhome_id != key
                and cand.merged_into_id is None
            ):
                hit = cand
                break
        if hit is None:
            for model in (PaymentTerms, RemainingEvent):
                ids = set(
                    self.s.scalars(
                        select(Complex.id)
                        .join(model, model.complex_id == Complex.id)
                        .where(
                            model.notice_no.in_(sorted(nos)),
                            Complex.region_id == region_id,
                            Complex.applyhome_id.is_distinct_from(key),
                            live(),
                        )
                    )
                )
                if len(ids) == 1:
                    hit = self.s.get(Complex, ids.pop())
                    break
        if hit is None and create:
            hit = self._same_block(key, region_id, batch)
        if hit is None:
            return None
        for no in nos:
            self.links.setdefault(no, hit.id)
        if create and hit.name == hit.applyhome_id:
            # 자리표시 이름(인용으로 만든 원 단지) → 청약홈의 그 사업 이름(공급 회차·구분 괄호를 뗀 값). 원 공고 재수집이 덮는다
            name = next(
                (
                    str(c.value)
                    for c in batch
                    if c.entity == "complex" and c.entity_key == key and c.field == "name" and c.value
                ),
                None,
            )
            if name and strip_supply_round(name).strip():
                hit.name = strip_supply_round(name).strip()
        return hit

    def _same_block(self, key: str, region_id: int, batch: list[FieldCandidate]) -> Complex | None:
        """W12c: 같은 지역에서 정규화 단지명·공급위치가 모두 같은 단지가 정확히 1개면 그 행."""
        vals = {c.field: c.value for c in batch if c.entity == "complex" and c.entity_key == key}
        name, address = vals.get("name"), vals.get("address")
        if not isinstance(name, str) or not isinstance(address, str):
            return None
        nk, ak = block_name_key(name), address_key(address)
        if not nk or not ak or is_zone_address(address):
            return None
        hits = [
            cx
            for cx in self.s.scalars(
                select(Complex).where(Complex.region_id == region_id, Complex.address.is_not(None), live())
            )
            if cx.applyhome_id != key
            and not is_zone_address(cx.address or "")
            and address_key(cx.address or "") == ak
            and nk in {block_name_key(n) for n in (cx.name, *(cx.former_names or []))}
        ]
        return hits[0] if len(hits) == 1 else None

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
        """경쟁률 행 = (단지, 공급 구분, 회차, **원 면적 코드**) — 원문이 준 값만으로 찾는다(D23-2, R4 4차 N13). 그 시점의 단지
        주택형과 대조해 키를 바꾸면 타입 행이 생기기 전·후 재정규화가 같은 경쟁률을 다른 행으로 만든다 — 주택형 대조는 읽기
        시점 표시 속성이다(``normalize.competition.display_type_codes``)."""
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
        presale = bool(vals.get("is_presale", False))  # 분양권 거래는 같은 값의 매매와 다른 행(R3b F1a)
        row = self.s.scalars(
            select(RtmsTrade).where(
                RtmsTrade.region_id == raw.region_id,
                RtmsTrade.apt_name == vals.get("apt_name"),
                RtmsTrade.deal_date == vals.get("deal_date"),
                RtmsTrade.price_won == int(vals.get("price_won") or 0),
                RtmsTrade.floor.is_(None) if floor is None else RtmsTrade.floor == int(floor),
                RtmsTrade.area_m2 == Decimal(str(vals.get("area_m2"))),
                RtmsTrade.source == vals.get("source"),
                RtmsTrade.is_presale.is_(presale),
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
            is_presale=presale,
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
            if eid is None or self._merged_unit(c):
                skipped.append(c)
                continue
            bound.append(c.model_copy(update={"entity_id": eid}))
        return bound, skipped

    def complex_for_key(self, key: str) -> int | None:
        cx = self._complex.get(key)
        return cx.id if cx is not None else None

    def _merged_unit(self, c: FieldCandidate) -> bool:
        """원 단지에 묶인 잔여 공고의 단지 단위 후보(complex·complex_type)인가(D11-4 — 원 단지 값을 덮어쓰지 않는다).

        R3 5차 M10: 원 번호를 인용한 잔여 공고의 **입주 예정월**(``CITED_COMPLEX_FIELDS``)은 원 단지 후보로 받는다 — 이름·
        세대수·당첨일·청약 일정 같은 그 잔여 공고 자신의 값은 버리지만, 같은 단지의 입주 지연(2028-03 → 2028-09)은 정당한
        갱신이다(공고문 최신 규칙으로 resolver 가 가른다). R3 6차 minor 16: 같은 블록으로 묶인(W12c, 자기 번호) 잔여 공고도
        같다 — 타입 행은 계속 버린다."""
        if c.entity not in MERGED_UNIT_ENTITIES:
            return False
        key = (c.entity_key or "").split(":")[0]
        if key not in self.merged and not (c.entity == "complex" and key in self.cited):
            return False
        if c.entity != "complex":
            return True
        if c.field in CITED_COMPLEX_FIELDS:
            return False
        if (
            c.field in FILL_EMPTY_FIELDS
        ):  # D18-4: 원 단지에 없을 때만(같은 사업의 공식 홈페이지 — 접수 상태 근거)
            cx = self._complex.get(key)
            return cx is None or bool(getattr(cx, c.field, None))
        return True

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
                if parts[0] in self.merged:
                    return None  # 원 단지에 묶인 잔여 공고의 타입 행은 만들지 않는다(R3 4차 minor — 건너뛸 후보의 행 선생성)
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


MERGED_UNIT_ENTITIES = frozenset({"complex", "complex_type"})
"""D11-4: 원 단지에 묶인 잔여·임의·무순위 공고에서 원 단지에 쓰지 않는 단지 단위 엔티티."""
CITED_COMPLEX_FIELDS = frozenset({"move_in_ym"})
"""R3 5차 M10·6차 minor 16: 원 단지에 묶인 잔여 공고(원 번호 인용·같은 블록 병합)에서도 원 단지 후보로 받는 단지 필드 —
그 단지 전체의 일정인 입주 예정월(입주 일정 변경)뿐. 공고일·청약 일정·당첨일·계약일은 그 잔여 공급 자신의 일정이라
원 단지 값을 덮지 않는다(D11-4 — ``remaining_event``·``payment_terms`` 에 기록)."""

FILL_EMPTY_FIELDS = frozenset({"official_site_url"})
"""D18-4: 원 단지에 묶인 잔여 공고에서 원 단지 값이 **비어 있을 때만** 받는 단지 필드 — 사업의 공식 홈페이지(잔여 공고의
접수 상태가 같은 홈페이지에 올라온다). 원 단지 값이 있으면 덮지 않는다(D11-4)."""

_URL_NO_RE = re.compile(
    r"(?:houseManageNo=|pblancNo=|HOUSE_MANAGE_NO%3A%3AEQ%5D=|PBLANC_NO%3A%3AEQ%5D=)(\d{10})"
)


def _url_numbers(url: str) -> set[str]:
    """원문 주소의 주택관리번호·공고번호(청약홈 상세·공고문 첨부·API 1건 조회)."""
    return set(_URL_NO_RE.findall(url))


def _own_notice_nos(batch: list[FieldCandidate], key: str) -> set[str]:
    """이 원문이 ``key`` 단지에 대해 낸 공고번호들(납부 조건 키 '<key>:<공고번호>'의 뒤)."""
    return {
        (c.entity_key or "").split(":", 1)[1]
        for c in batch
        if c.entity == "payment_terms"
        and (c.entity_key or "").count(":") == 1
        and (c.entity_key or "").split(":", 1)[0] == key
    }


_APPLYHOME_ID_GLOBAL: bool = bool(Complex.__table__.c.applyhome_id.unique)
"""complex.applyhome_id 가 전역 유일(현 스키마)인가. (region_id, applyhome_id) 유일로 바뀌면 False."""

# 하이픈은 지우지 않는다(minor 18: 'AA1-31' 과 'AA13-1' 이 같은 키가 되던 문제) — 공백·문장부호·괄호·'번지'만
_KEY_DROP_RE = re.compile(r"[\s·,.()（）\[\]]+|번지")
# 구역 표현: '…일원'·'일대'·'외 n필지'·'1056-1외'·'AA13블록외 2'(minor 18 — 숫자·블록 바로 뒤 '외'도)
_ZONE_RE = re.compile(r"일원|일대|(?:^|\s|\d|블록|BL|bl)외(?:[\s,·;/]|\d|$)|필지")
"""구역 표현 — '1056-1외, 1056-2'(외 뒤 쉼표)도(R3 4차 minor)."""
_REMAINDER_PATHS = ("Remndr", "getOPT", "OPTLttot")
_REMAINDER_KINDS = ("무순위", "임의", "잔여", "선착순", "재공급", "계약취소")


def block_name_key(name: str) -> str:
    """단지명 비교 키: 잔여 공고의 회차·공급 구분 괄호만 떼고 공백·문장부호를 뺀다(대소문자 무시).
    차수·단지·블록 번호는 남긴다(D10-4)."""
    return _KEY_DROP_RE.sub("", strip_supply_round(name)).lower()


def is_zone_address(address: str) -> bool:
    """공급위치가 구역 표현('…일원'·'일대'·'외 n필지')인가 — 같은 블록 병합 금지(D10-4)."""
    return bool(_ZONE_RE.search(address))


def _cites_original(raw: RawDocumentDTO, batch: list[FieldCandidate], key: str) -> bool:
    """잔여 공고 원문이 자기 번호가 아닌 원 단지 번호(``key`` — 공고문 '최초 주택관리번호')로 단지를 가리키는가:
    이 원문의 납부 조건 키가 '<key>:<다른 공고번호>' 이고 공고 종류가 잔여(무순위·임의·선착순…)."""
    own = {
        (c.entity_key or "").split(":", 1)[1]
        for c in batch
        if c.entity == "payment_terms" and (c.entity_key or "").count(":") == 1
        and (c.entity_key or "").split(":", 1)[0] == key
    }  # fmt: skip
    # R4-FIX(D18-4): 공고문이 원문 주소의 자기 번호가 아닌 번호(공고문의 '최초 주택관리번호')로 단지를 가리키면 인용이다 —
    # 납부 조건 후보(공고일 줄)나 제목의 공급 구분을 못 읽어도. 그렇지 않으면 그 공고문의 단지 단위 값이 원 단지에 쓰였다
    url_own = _url_numbers(raw.url) if raw.source_kind == "notice_pdf" else set()
    if url_own and key not in url_own:
        return True
    return bool(own) and key not in own and _is_remainder_notice(raw, batch, key)


def is_remainder_url(url: str) -> bool:
    """청약홈 잔여세대·임의공급 화면·API 원문 주소인가(URL 경로 대조 — D18-4 저장 순서)."""
    path = urlsplit(url).path
    return any(p in path for p in _REMAINDER_PATHS)


def _is_remainder_notice(raw: RawDocumentDTO, batch: list[FieldCandidate], key: str) -> bool:
    """이 원문이 잔여 공고(무순위·임의공급·잔여세대·재공급)인가: URL 경로(청약홈 잔여세대·임의공급 화면·API)
    또는 같은 번호의 공고 종류 후보(공고문 제목). 문자열 대조뿐이다(판단 아님)."""
    path = urlsplit(raw.url).path
    if any(p in path for p in _REMAINDER_PATHS):
        return True
    return any(
        c.entity == "payment_terms"
        and (c.entity_key or "").split(":")[0] == key
        and c.field == "notice_kind"
        and isinstance(c.value, str)
        and any(k in c.value for k in _REMAINDER_KINDS)
        for c in batch
    )


def address_key(address: str) -> str:
    """공급위치 비교 키: 공백·문장부호·'번지'를 뺀다(구역 표현 주소는 ``is_zone_address`` 로 따로 거른다)."""
    return _KEY_DROP_RE.sub("", address).lower()


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


def _set_discount(
    obj: PaymentTerms,
    c: FieldCandidate,
    type_code: str,
    *,
    held: bool,
    initial: bool,
    snapshot_id: int | None,
    detected_at: str,
) -> ChangeEvent | None:
    """payment_terms.discount_by_type[type] = 원(계약 .8, D11-6 — 공고에 명시된 할인). 채택 보류면 그 항목을 지운다."""
    cur = dict(obj.discount_by_type or {})
    old_v = cur.get(type_code)
    new: int | None = None if held or c.value is None else int(c.value)
    if changes.fmt_value(old_v) == changes.fmt_value(new):
        return None
    if new is None:
        cur.pop(type_code, None)
    else:
        cur[type_code] = new
    obj.discount_by_type = cur
    return changes.value_change_event(
        entity="payment_terms",
        entity_id=obj.id,
        field=c.field,
        old=old_v,
        new=new,
        snapshot_id=snapshot_id,
        complex_id=obj.complex_id,
        detected_at=detected_at,
        initial=initial or old_v is None,
    )


_KEEP: Any = object()


def _held_value(model: Any, field_name: str) -> Any:
    """채택 보류 시 비운 값: NULL 가능 컬럼은 None, NOT NULL JSON 목록(일정)은 [] (값 없음).
    그 밖의 NOT NULL 컬럼(실거래 가격 등 행의 키 성격)은 비울 수 없다 → ``_KEEP``(그대로 둠)."""
    column = model.__table__.columns.get(field_name)
    if column is None or column.nullable:
        return None
    return [] if field_name in JSON_FIELDS else _KEEP


def write_chosen(
    session: Session,
    chosen: list[FieldCandidate],
    *,
    created: set[tuple[str, int]] | frozenset[tuple[str, int]] = frozenset(),
    snapshot_id: int | None,
    detected_at: str,
) -> tuple[list[ChangeEvent], set[int]]:
    """채택(chosen) 후보 값을 사실 테이블에 쓴다. 바뀐 값은 change_event(새 행이면 initial).

    값 없는 후보('확인 불가')는 건너뛴다 — 단, 같은 rank 1차·1차 상충의 채택 보류 후보(reason
    ``CONFLICT_HOLD``, R3 M1)는 사실 테이블 값을 비운다(compare 로 풀릴 때까지 점수 미사용).
    반환 = (이벤트, 주소가 바뀐 단지 id — 생활권 재배정 대상).
    ``store_raw_document`` 와 판정 결과 반영(``normalize.judged``)이 같이 쓴다.
    """
    events: list[ChangeEvent] = []
    touched_complex: set[int] = set()
    for c in chosen:
        model = _MODELS.get(c.entity)
        held = c.value is None and c.reason == CONFLICT_HOLD
        if model is None or c.entity_id is None:
            continue
        # R9-PARSE Q2: 원문이 '설명 없음'을 확인한 텍스트 필드(값 없음 + 라벨 확인됨)는 옛 값을 지운다 — '확인 불가'(못 읽음)와 다르다
        cleared = c.value is None and c.label != "확인 불가" and (c.entity, c.field) in EXPLICIT_NULL_FIELDS
        if (c.value is None or c.label == "확인 불가") and not held and not cleared:
            continue
        obj = session.get(model, c.entity_id)
        if obj is None:
            continue
        disc = split_discount(c.field) if c.entity == "payment_terms" else None
        if disc is not None:
            ev_d = _set_discount(
                obj,
                c,
                disc,
                held=held,
                initial=(c.entity, c.entity_id) in created,
                snapshot_id=snapshot_id,
                detected_at=detected_at,
            )
            if ev_d is not None:
                events.append(ev_d)
            continue
        pbt = split_price_by_type(c.field) if c.entity == "payment_terms" else None
        if pbt is not None:
            ev_pbt = _set_price_by_type(
                obj,
                c,
                pbt,
                initial=(c.entity, c.entity_id) in created,
                snapshot_id=snapshot_id,
                detected_at=detected_at,
            )
            if ev_pbt is not None:
                events.append(ev_pbt)
            continue
        if not hasattr(model, c.field) or c.field == "id":
            continue
        new = _held_value(model, c.field) if held else _coerce(c.field, c.value)
        if new is _KEEP:
            continue
        old_v = getattr(obj, c.field)
        if changes.fmt_value(old_v) == changes.fmt_value(new):
            continue
        initial = (c.entity, c.entity_id) in created or (
            old_v is None and (c.entity, c.field) in QUIET_FIRST_FIELDS
        )
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
    return events, touched_complex


def candidate_from_row(fp: FieldProvenance, source_kind: str | None) -> FieldCandidate:
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


def _own_key(session: Session, entity: str, entity_id: int | None) -> str | None:
    """단지 단위 엔티티 행(complex·complex_type)이 속한 단지의 주택관리번호. 그 밖은 None."""
    if entity_id is None or entity not in MERGED_UNIT_ENTITIES:
        return None
    if entity == "complex":
        cx = session.get(Complex, entity_id)
    else:
        t = session.get(ComplexType, entity_id)
        cx = session.get(Complex, t.complex_id) if t is not None else None
    return cx.applyhome_id if cx is not None else None


def _foreign_unit_row(fp: FieldProvenance, own_key: str | None) -> bool:
    """단지 단위 출처 행의 entity_key(파서가 단 주택관리번호)가 이 단지 번호와 다르다 = 원 단지에 묶인 잔여 공고가 쓴 행.

    R4-FIX: 원 단지가 잔여 공고에서 받는 필드(``CITED_COMPLEX_FIELDS`` — 입주 예정월)는 후보로 남긴다 — 빼면 원문마다 자기
    값만 보고 마지막에 저장한 원문이 이겨, 같은 날 다시 저장할 때 값이 오갔다(change_event 가 생김, M5)."""
    if own_key is None or not fp.entity_key or (fp.entity == "complex" and fp.field in CITED_COMPLEX_FIELDS):
        return False
    return fp.entity_key.split(":")[0] != own_key


def resolve_field_group(
    session: Session,
    entity: str,
    entity_id: int,
    field_name: str,
    extra: list[FieldCandidate],
    *,
    snapshot_id: int | None = None,
    now: datetime | None = None,
    add_events: bool = True,
) -> list[ChangeEvent]:
    """한 사실 필드 그룹(entity, entity_id, field)을 저장된 출처 행(원문·사람 확인) + ``extra`` 후보로 다시 resolve 한다
    (사람 확인 입력 — ``api.demotion.apply_human_check``). 원문을 다시 읽지 않는다. 사실 테이블·출처
    행·change_event. ``add_events=False`` 면 이벤트를 세션에 넣지 않고 돌려주기만 한다(호출자가 첫 적재 요약 등으로 거른다)."""
    detected_at = changes.detected_now(now)
    with session.begin_nested():
        own_key = _own_key(session, entity, entity_id)
        cands: list[FieldCandidate] = []
        kinds: dict[int, str | None] = {}
        group_rows = current_rows(
            session,
            list(
                session.scalars(
                    select(FieldProvenance)
                    .where(
                        FieldProvenance.entity == entity,
                        FieldProvenance.entity_id == entity_id,
                        FieldProvenance.field == field_name,
                    )
                    .order_by(FieldProvenance.id)
                )
            ),
        )
        for fp in group_rows:
            rid = fp.raw_document_id
            if rid is None:
                if is_human(fp.reason):
                    cands.append(candidate_from_row(fp, None))
                continue
            if _is_legacy(fp) or _foreign_unit_row(fp, own_key):
                continue
            if rid not in kinds:
                raw_row = session.get(RawDocument, rid)
                kinds[rid] = raw_row.source_kind if raw_row is not None else None
            cands.append(candidate_from_row(fp, kinds[rid]))
        cands += semantic_humans(session, {(entity, entity_id, field_name)}, [*extra, *cands])  # D13-2
        resolved = resolve([*extra, *cands], price_refs(session, {(entity, entity_id, field_name)}))
        upsert_provenance(session, resolved.provenance)
        events, _ = write_chosen(session, resolved.chosen, snapshot_id=snapshot_id, detected_at=detected_at)
        events += human_superseded(
            session, resolved, events, snapshot_id=snapshot_id, detected_at=detected_at
        )
        if add_events:
            session.add_all(events)
        session.flush()
    return events


HUMAN_SEMANTIC_FIELDS = frozenset({"max_price_won", "down_payment_pct", "discount"})
"""공고 행이 여럿인 사람 확인 필드(가격 — 공고문 타입 행·모든 공고 price_by_type, 계약금 — 모든 공고). 단지 필드는 행 하나."""
FILL_EMPTY_FIELDS = frozenset({"down_payment_pct", "discount"})
"""D17-4(R3i major 4): 새 공고(무순위·정정)에 그 값이 **없으면** 사람 확인 값을 그대로 적용하는 납부 조건 필드(값 없음 ≠ 다른 값).
가격은 공고문 타입 행이 늘 남아 있어 현재 구매가가 사라지지 않는다 — 공고가 싣지 않은 타입 가격을 공고 행에 만들지 않는다."""


def _empty_human_groups(session: Session, bound: list[FieldCandidate]) -> set[tuple[str, int | None, str]]:
    """D17-4: 이번 원문이 쓴 납부 조건 행마다, 같은 단지 다른 공고 행에 사람 확인이 있는 할인·계약금 필드 중 이번 원문이 값을 싣지
    않은 것 — ``semantic_humans`` 가 그 칸에 사람 확인 후보를 넣는다(값 없음 ≠ 다른 값)."""
    have = {(c.entity, c.entity_id, c.field) for c in bound}
    out: set[tuple[str, int | None, str]] = set()
    for pid in sorted(
        {c.entity_id for c in bound if c.entity == "payment_terms" and c.entity_id is not None}
    ):
        pt = session.get(PaymentTerms, pid)
        if pt is None:
            continue
        siblings = select(PaymentTerms.id).where(
            PaymentTerms.complex_id == pt.complex_id, PaymentTerms.id != pid
        )
        for f in session.scalars(
            select(FieldProvenance.field)
            .where(
                FieldProvenance.entity == "payment_terms",
                FieldProvenance.entity_id.in_(siblings),
                FieldProvenance.raw_document_id.is_(None),
            )
            .distinct()
        ):
            if fills_empty("payment_terms", f) and ("payment_terms", pid, f) not in have:
                out.add(("payment_terms", pid, f))
    return out


def fills_empty(entity: str, field_name: str) -> bool:
    """D17-4: 그 (테이블, 출처 필드)는 값 없는 공고 행에도 사람 확인 값을 적용하는가(납부 조건 할인·계약금)."""
    from app.facts_view import logical_field

    return entity == "payment_terms" and logical_field(field_name) in FILL_EMPTY_FIELDS


def semantic_humans(
    session: Session, groups: set[tuple[str, int | None, str]], present: list[FieldCandidate]
) -> list[FieldCandidate]:
    """D13-2: 사람 확인은 (단지, 의미 필드) 단위 — 그 행의 의미 묶음(``facts_view.semantic_group``) **다른 행**에 있는
    사람 확인을 이 행의 0순위 후보로 옮겨 온다(값이 있는 행만 — 그 필드를 싣지 않은 공고에는 값을 만들지 않는다).

    그래서 새 공고 행(무순위 병합 포함)이 와도 resolver 가 행마다 같은 규칙(D12-1)을 적용한다: 사람 확인 이전 관측 출처는
    지고, 이후 관측된 공식 1차 출처의 다른 값은 채택 + critical + '사람 확인 재검토'(``human_superseded``)."""
    from app.facts_view import logical_field, semantic_group
    from app.normalize.resolver import is_human_candidate

    def key(c: FieldCandidate) -> tuple[Any, ...]:
        return (c.entity, c.entity_id, c.field, norm_value(c.value), c.observed_on, c.checked_at)

    have = {key(c) for c in present if is_human_candidate(c)}
    valued = {
        (c.entity, c.entity_id, c.field) for c in present if c.value is not None and c.label != "확인 불가"
    }
    out: list[FieldCandidate] = []
    for e, i, f in sorted(groups, key=lambda g: (g[0], g[1] or 0, g[2])):
        if (
            i is None
            or e not in ("complex_type", "payment_terms")
            or logical_field(f) not in HUMAN_SEMANTIC_FIELDS
        ):
            continue
        if (e, i, f) not in valued and not fills_empty(e, f):
            continue  # 가격 등: 그 필드를 싣지 않은 행에는 값을 만들지 않는다(D17-4 는 할인·계약금만 값 없는 행에도)
        _cid, rows = semantic_group(session, e, i, f)
        for se, si, sf in rows[1:]:
            for fp in session.scalars(
                select(FieldProvenance)
                .where(
                    FieldProvenance.entity == se,
                    FieldProvenance.entity_id == si,
                    FieldProvenance.field == sf,
                    FieldProvenance.raw_document_id.is_(None),
                )
                .order_by(FieldProvenance.id)
            ):
                if not is_human(fp.reason) or fp.value_norm is None:
                    continue
                cand = candidate_from_row(fp, None).model_copy(
                    update={"entity": e, "entity_id": i, "entity_key": None, "field": f}
                )
                k = key(cand)
                if k in have:
                    continue
                have.add(k)
                out.append(cand)
    return out


HUMAN_REVIEW_TITLE = "사람 확인 재검토"
"""D12-1: 사람 확인 이후 새 공식 1차 출처가 다른 값을 내 채택됐다 — 체크리스트 '사실 재확인' 항목 제목 머리."""


def human_superseded(
    session: Session,
    resolved: ResolvedFields,
    events: list[ChangeEvent],
    *,
    snapshot_id: int | None = None,
    detected_at: str | None = None,
    created: set[tuple[str, int]] | frozenset[tuple[str, int]] = frozenset(),
) -> list[ChangeEvent]:
    """D12-1·D13-2: 사람 확인 행이 있는데 원문 출처가 채택된 필드(resolver — 사람 확인 이후 새 공식 출처의 다른 값)는
    critical·재판정 + 체크리스트 '사람 확인 재검토'(사실 재확인 — 동기화가 닫지 않는다). 행과 무관하다: 값 변경 이벤트가
    없는 **새 공고 행**(값 하나하나를 이벤트로 남기지 않는 행)이면 이 함수가 critical 이벤트를 만든다(반환 — 호출자가
    추가). 같은 내용 이벤트가 이미 있으면(재정규화) 다시 만들지 않는다."""
    from app.models import ChecklistItem

    rows: dict[tuple[str, int, str], list[Any]] = {}
    for p in resolved.provenance:
        if p.entity_id is not None:
            rows.setdefault((p.entity, p.entity_id, p.field[:64]), []).append(p)
    superseded: dict[tuple[str, int, str], Any] = {}
    for key, group in rows.items():
        human = next((p for p in group if is_human(p.reason) and not p.chosen), None)
        if human is not None and any(p.chosen and not is_human(p.reason) for p in group):
            superseded[key] = human
    if not superseded:
        return []
    from app.api.demotion import FIELD_NAMES
    from app.facts_view import logical_field

    by_key = {
        (ev.entity, ev.entity_id, (ev.field or "")[:64]): ev for ev in events if ev.entity_id is not None
    }
    extra: list[ChangeEvent] = []
    for key, human in superseded.items():
        ev = by_key.get(key)
        if ev is None and (key[0], key[1]) not in created:
            continue  # 값이 그대로(재정규화) — 이미 알렸다
        if ev is None:
            chosen = next(p for p in rows[key] if p.chosen and not is_human(p.reason))
            old_text = f"{human.value_text} (사람 확인)"[:200]
            new_text = (chosen.value_text or "")[:200]
            entity, eid, fld = key
            if session.scalars(
                select(ChangeEvent.id).where(
                    ChangeEvent.entity == entity,
                    ChangeEvent.entity_id == eid,
                    ChangeEvent.field == fld,
                    ChangeEvent.old_text == old_text,
                    ChangeEvent.new_text == new_text,
                )
            ).first():
                continue  # 재정규화 — 이미 알렸다
            model = _MODELS.get(entity)
            obj = session.get(model, eid) if model is not None else None
            cid = eid if entity == "complex" else getattr(obj, "complex_id", None)
            ev = ChangeEvent(
                snapshot_id=snapshot_id, entity=entity, entity_id=eid, field=fld, old_text=old_text,
                new_text=new_text, detected_at=detected_at or changes.detected_now(None), severity="critical",
                triggers_rejudge=True, complex_id=cid,
            )  # fmt: skip
            extra.append(ev)
        ev.severity = "critical"
        ev.triggers_rejudge = True
        logical = logical_field(human.field)
        title = f"{HUMAN_REVIEW_TITLE}: {FIELD_NAMES.get(logical, logical)}"
        note = (
            f"사람 확인 값 {human.value_text} 이후 새 공식 공고가 {ev.new_text} 를 냈다(D12-1) — 원문을 확인해 다시 사람 "
            "확인하거나 닫는다"
        )
        item = session.scalars(
            select(ChecklistItem).where(
                ChecklistItem.complex_id == ev.complex_id,
                ChecklistItem.kind == "사실 재확인",
                ChecklistItem.title == title,
            )
        ).first()
        if item is None:
            session.add(
                ChecklistItem(
                    complex_id=ev.complex_id, kind="사실 재확인", title=title, status="open", note=note
                )
            )
            session.flush()
        else:
            item.status, item.closed_by, item.note = "open", None, note
    return extra


def price_refs(
    session: Session, groups: set[tuple[str, int | None, str]]
) -> dict[tuple[str, str, str], list[FieldCandidate]]:
    """D21-1(R4 재시험 N1): 공고별 타입 가격 그룹(``payment_terms``·``price_by_type.<타입>.<최고가|대표층가>``) → 같은 단지·같은
    타입 행(``complex_type``)의 **공고문이 아닌** 1차 출처 최고가 후보(청약홈 API·웹 '만원'). resolver 가 10배 이상 다르면 그
    공고 가격을 보류한다(비교만 — 출처 행·채택 후보가 아니다). 키 = ``resolver.group_key`` 모양."""
    out: dict[tuple[str, str, str], list[FieldCandidate]] = {}
    kinds: dict[int, str | None] = {}
    for entity, eid, fname in sorted(groups, key=lambda g: (g[0], g[1] or 0, g[2])):
        if entity != "payment_terms" or eid is None or not is_price_amount(entity, fname):
            continue
        pbt = split_price_by_type(fname)
        pt = session.get(PaymentTerms, eid)
        if pbt is None or pt is None:
            continue
        ct = session.scalars(
            select(ComplexType).where(
                ComplexType.complex_id == pt.complex_id, ComplexType.type_code == pbt[0]
            )
        ).first()
        if ct is None:
            continue
        refs: list[FieldCandidate] = []
        for fp in session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == "complex_type",
                FieldProvenance.entity_id == ct.id,
                FieldProvenance.field == "max_price_won",
                FieldProvenance.raw_document_id.is_not(None),
            )
            .order_by(FieldProvenance.id)
        ):
            rid = fp.raw_document_id
            assert rid is not None
            if is_superseded(fp.reason):
                continue  # R10-FIX: 옛 파싱 행은 비교 대상도 아니다
            if rid not in kinds:
                raw_row = session.get(RawDocument, rid)
                kinds[rid] = raw_row.source_kind if raw_row is not None else None
            if kinds[rid] in (None, "notice_pdf") or fp.value_norm is None or fp.label == "확인 불가":
                continue
            refs.append(candidate_from_row(fp, kinds[rid]))
        if refs:
            out[("payment_terms", f"id:{eid}", fname)] = refs
    return out


def _price_groups_of_types(session: Session, bound: list[FieldCandidate]) -> set[tuple[str, int, str]]:
    """이번 원문이 쓴 공고문 아닌 타입 행 최고가(청약홈) → 같은 단지·타입의 공고별 타입 가격 그룹(D21-1 — 청약홈 가격이 나중에
    와도 저장 순서와 무관하게 같은 보류·해제가 되도록 다시 resolve 한다)."""
    out: set[tuple[str, int, str]] = set()
    for c in bound:
        if (
            c.entity != "complex_type"
            or c.field != "max_price_won"
            or c.entity_id is None
            or c.source_kind == "notice_pdf"
        ):
            continue
        ct = session.get(ComplexType, c.entity_id)
        if ct is None:
            continue
        for pt in session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == ct.complex_id)):
            for item in ("max_price_won", "floor_sample_price_won"):
                fname = f"price_by_type.{ct.type_code}.{item}"
                has = session.scalars(
                    select(FieldProvenance.id).where(
                        FieldProvenance.entity == "payment_terms",
                        FieldProvenance.entity_id == pt.id,
                        FieldProvenance.field == fname,
                    )
                ).first()
                if has is not None:
                    out.add(("payment_terms", pt.id, fname))
    return out


def _merged_addresses(binder: _Binder, skipped: list[FieldCandidate]) -> dict[int, list[str]]:
    """원 단지에 묶여(D11-4) 원 단지 값으로 쓰지 않은 잔여 공고의 공급위치(단지 id → 주소들)."""
    out: dict[int, list[str]] = {}
    for c in skipped:
        if (
            c.entity != "complex"
            or c.field != "address"
            or not isinstance(c.value, str)
            or not c.value.strip()
        ):
            continue
        cid = binder.complex_for_key((c.entity_key or "").split(":")[0])
        if cid is not None and c.value not in out.get(cid, []):
            out.setdefault(cid, []).append(c.value)
    return out


def _is_judged_row(fp: FieldProvenance) -> bool:
    """판정기 추출·감사로 만든 출처 행(``judged.apply_extracted`` — reason '판정기 추출 …'·'판정기 감사 flagged …')."""
    return (strip_tags(fp.reason) or "").startswith((EXTRACT_REASON, AUDIT_FLAG_REASON))


def _carry_compare_marks(session: Session, bound: list[FieldCandidate], raw_id: int) -> list[FieldCandidate]:
    """D23-3(R4 4차 N14): 같은 원문을 다시 정규화할 때, 그 원문이 같은 자리(엔티티·필드·발췌 위치)에 **같은 값**으로 남긴 출처 행의
    판정기 compare 채택·병기 표식(``COMPARE_ADOPTED``·``COMPARE_SIDE``)을 이번 후보 reason 에 다시 붙인다.

    빼면 출처 행 reason 이 파서 값으로 다시 쓰여 표식이 사라진다 — 같은 rank 1차·1차 상충은 다시 채택 보류('확인 불가'), 그 밖은
    '판정기 compare 채택' 근거가 이벤트 없이 사라지고 다음 재판정이 표식 없는 상대를 새 상충으로 보고 compare 를 다시 부른다(R4 4차
    (b) 뒤 재판정 ``tools/call`` 4). 값이 바뀌면(파서가 다른 값을 읽음) 표식을 옮기지 않는다 — compare 결과는 옛 값에 대한 것이다."""
    groups = {(c.entity, c.entity_id, c.field) for c in bound if c.entity_id is not None}
    if not groups:
        return bound
    marks: dict[tuple[str, int, str, int | None, str | None], str] = {}
    for fp in session.scalars(
        select(FieldProvenance).where(FieldProvenance.raw_document_id == raw_id).order_by(FieldProvenance.id)
    ):
        if fp.entity_id is None or (fp.entity, fp.entity_id, fp.field) not in groups or _is_judged_row(fp):
            continue
        head = compare_mark(fp.reason)
        if head is not None:
            marks.setdefault((fp.entity, fp.entity_id, fp.field, fp.excerpt_start, fp.value_norm), head)
    if not marks:
        return bound
    out: list[FieldCandidate] = []
    for c in bound:
        head = (
            marks.get((c.entity, c.entity_id, c.field, c.excerpt_start, norm_value(c.value)))
            if c.entity_id is not None and compare_mark(c.reason) is None
            else None
        )
        out.append(c if head is None else c.model_copy(update={"reason": with_mark(c.reason, head)}))
    return out


_SourceId = tuple[str, str, str, str, int | None, str]


def _source_id(
    entity: str,
    entity_key: str | None,
    field_name: str,
    value_text: str | None,
    start: int | None,
    label: str,
) -> _SourceId:
    """원문 안의 출처 자리(파싱 키·필드·값 표기·발췌 위치·라벨) — ``provenance._same_source`` 가 같은 행으로 보는 기준 + 파싱 키."""
    return (entity, entity_key or "", field_name, (value_text or "").replace("\x00", " "), start, label)


def _parser_row(fp: FieldProvenance) -> bool:
    """원문 파서가 만든 출처 행(사람 확인·판정기 추출·감사 행이 아님)."""
    return fp.raw_document_id is not None and not _is_judged_row(fp)


def _mark_superseded(fp: FieldProvenance) -> None:
    fp.reason = with_superseded(fp.reason)
    fp.chosen = False
    fp.conflict_group = None  # 상충 묶음에서 빠진다 — P5 compare 대상도 아니다


def retire_superseded(session: Session, raw_id: int, bound: list[FieldCandidate], keep: set[int]) -> int:
    """R10-FIX: 원문 ``raw_id`` 를 지금 파서로 정규화한 뒤 — 이번 후보와 같은 묶음(엔티티·행·필드)·같은 파싱 키의 그 원문 파서 행
    중 이번 출처 행 갱신(``keep``)에 들지 않은 것 = 옛 파서가 낸 행. 표식(``SUPERSEDED_REASON``)·chosen false·상충 묶음 없음.

    지우지 않는다(발행 리비전의 출처 근거). 빼지 않으면 다른 원문을 정규화할 때 ``_reparse_existing`` 이 이 행을 후보로 되살려,
    같은 출처 종류에서 원문 번호가 큰 쪽의 옛 값이 이긴다(운영 인천 스냅샷 7 ``apply_dates`` 46 단지 × 2 이벤트)."""
    keys = {(c.entity, c.entity_id, c.field, c.entity_key or "") for c in bound if c.entity_id is not None}
    if not keys:
        return 0
    n = 0
    for fp in session.scalars(
        select(FieldProvenance).where(FieldProvenance.raw_document_id == raw_id).order_by(FieldProvenance.id)
    ):
        if fp.id in keep or not _parser_row(fp) or is_superseded(fp.reason):
            continue
        if (fp.entity, fp.entity_id, fp.field, fp.entity_key or "") not in keys:
            continue
        _mark_superseded(fp)
        n += 1
    if n:
        session.flush()
    return n


def current_rows(
    session: Session,
    rows: list[FieldProvenance],
    parser_factory: Callable[[str], _Parser | None] | None = None,
) -> list[FieldProvenance]:
    """후보로 되살릴 출처 행에서 옛 파싱 행을 뺀다(R10-FIX).

    - 표식(``SUPERSEDED_REASON``)이 있는 행은 뺀다.
    - 한 원문이 같은 묶음·같은 파싱 키에 파서 행을 둘 이상 남겼으면(파서가 바뀐 뒤 그 원문을 아직 다시 정규화하지 않음 — 배포 직후
      첫 수집, 또는 한 원문이 같은 칸을 여러 자리에서 냄) 그 원문을 지금 파서로 다시 읽어, 지금 파싱이 같은 자리·같은 값으로 내는
      행만 남기고 나머지는 표식한다. 원문을 못 읽거나 지금 파싱과 같은 행이 하나도 없으면 그대로 둔다(추측하지 않는다).
    사람 확인·판정기 추출·감사 행은 건드리지 않는다."""
    rows = [fp for fp in rows if not is_superseded(fp.reason)]
    buckets: dict[tuple[int, str, int | None, str, str], list[FieldProvenance]] = {}
    for fp in rows:
        if _parser_row(fp) and fp.raw_document_id is not None:
            k = (fp.raw_document_id, fp.entity, fp.entity_id, fp.field, fp.entity_key or "")
            buckets.setdefault(k, []).append(fp)
    mixed = sorted(
        (k for k, v in buckets.items() if len(v) > 1), key=lambda k: (k[0], k[1], k[2] or 0, k[3], k[4])
    )
    if not mixed:
        return rows
    factory = parser_factory or (lambda kind: parser_for(kind))
    parsed: dict[int, set[_SourceId] | None] = {}
    stale: set[int] = set()
    for k in mixed:
        rid = k[0]
        if rid not in parsed:
            parsed[rid] = _parsed_sources(session, rid, factory)
        now = parsed[rid]
        if now is None:
            continue
        group = buckets[k]
        same = [
            fp
            for fp in group
            if _source_id(fp.entity, fp.entity_key, fp.field, fp.value_text, fp.excerpt_start, fp.label)
            in now
        ]
        if not same:
            continue
        for fp in group:
            if fp not in same:
                _mark_superseded(fp)
                stale.add(fp.id)
    if stale:
        session.flush()
    return [fp for fp in rows if fp.id not in stale]


def _parsed_sources(
    session: Session, raw_id: int, factory: Callable[[str], _Parser | None]
) -> set[_SourceId] | None:
    """원문 하나를 지금 파서로 읽은 출처 자리들. 원문 행·파서가 없거나 읽지 못하면 None(판단 보류 — 행을 그대로 둔다)."""
    row = session.get(RawDocument, raw_id)
    p = factory(row.source_kind) if row is not None else None
    if row is None or p is None:
        return None
    try:
        cands = p.parse(raw_dto(row))
    except Exception:  # 옛 행 정리는 보조 단계 — 못 읽으면 예전처럼 저장된 행을 그대로 후보로(원문 실패는 수집 단계가 행으로 남긴다)
        return None
    if not cands:
        return None
    return {
        _source_id(c.entity, c.entity_key, c.field, c.value_text, c.excerpt_start, c.label) for c in cands
    }


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
    # D22-1(R4 3차 N9): 이번 원문을 다시 파싱해도 같은 자리(엔티티·필드·발췌 위치)를 여전히 판정기에 물어야 하면(파서가 못 읽음 —
    # needs_extract), 그 원문에서 판정기 추출·감사로 만든 출처 행은 그대로 후보다(같은 원문·같은 입력 = 같은 판정 결과). 빼면
    # 파서 행('확인 불가')이 다시 chosen 이 되어 사실 값은 그대로인데 출처가 '확인 불가'로 바뀐다(발행 저장본 '출처 누락').
    # 파서가 이제 값을 읽으면(needs_extract 아님) 판정 행은 후보가 아니다 — 값이 바뀌면 resolve·write_chosen 이 이벤트를 남긴다
    asks_judge = {(c.entity, c.entity_id, c.field, c.excerpt_start) for c in bound if c.needs_extract}
    pairs = {(e, i) for e, i, _ in groups}
    rows: list[FieldProvenance] = []
    for e, i in sorted(pairs, key=lambda p: (p[0], p[1] or 0)):
        own_key = _own_key(session, e, i)
        for fp in session.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.entity == e, FieldProvenance.entity_id == i)
            .order_by(FieldProvenance.id)
        ):
            if (fp.entity, fp.entity_id, fp.field) not in groups:
                continue
            if fp.raw_document_id is None:
                if is_human(fp.reason):
                    rows.append(fp)  # 사람 확인 = resolver 0순위 후보(D11-3) — 재정규화에도 남는다(C-3)
                continue
            if fp.raw_document_id == exclude_raw_id:
                if _is_judged_row(fp) and (fp.entity, fp.entity_id, fp.field, fp.excerpt_start) in asks_judge:
                    rows.append(fp)  # D22-1: 같은 원문의 판정기 추출 행 보존
                continue  # 이번 원문(파서 행은 이번 파싱 후보가 대신한다)
            if _foreign_unit_row(fp, own_key):
                continue  # 원 단지에 묶인 잔여 공고가 D11-4 이전에 쓴 단지 단위 행(후보 아님)
            rows.append(fp)
    legacy_raw = {fp.raw_document_id for fp in rows if _is_legacy(fp) and fp.raw_document_id is not None}
    # R10-FIX: 옛 파싱 행(표식)은 후보가 아니고, 표식 전 행이 남은 다른 원문은 지금 파서로 다시 읽어 지금 파싱 행만 후보로 쓴다
    rows = [fp for fp in rows if fp.raw_document_id in legacy_raw] + current_rows(
        session, [fp for fp in rows if fp.raw_document_id not in legacy_raw], parser_factory
    )
    kinds: dict[int, str | None] = {}
    out: list[FieldCandidate] = []
    for fp in sorted(rows, key=lambda r: (r.raw_document_id or 0, r.id)):
        rid = fp.raw_document_id
        if rid is None:
            out.append(candidate_from_row(fp, None))  # 사람 확인
            continue
        if rid in legacy_raw:
            continue
        if rid not in kinds:
            raw_row = session.get(RawDocument, rid)
            kinds[rid] = raw_row.source_kind if raw_row is not None else None
        out.append(candidate_from_row(fp, kinds[rid]))
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
    links: dict[str, int] | None = None,
    first_load: bool = False,
) -> StoreResult:
    """원문 1건을 정규화해 저장한다(한 트랜잭션 — SAVEPOINT). commit은 호출자.

    ``links``: 수집 실행 하나의 잔여 공고 번호 → 원 단지 연결(D18-4). 같은 dict 를 원문마다 넘긴다(없으면 원문마다 새로).
    ``first_load``: 지역 첫 적재(bootstrap, D18-7·R4 m3) — 값 기록(빈 값 → 값, 새 공고·새 단지 포함)과 같은 적재 안의 값 →
    다른 값 덮어쓰기(D21-7·R4 재시험 m-b)는 change_event 로 남기지 않고 ``StoreResult.first_load_folded`` 로 센다(수집
    단계가 '첫 적재' 한 줄로 요약)."""
    detected_at = changes.detected_now(now)

    def complex_key(complex_id: int) -> str | None:
        cx = session.get(Complex, complex_id)
        return cx.applyhome_id if cx is not None else None

    def scan_types(key: str) -> list[str] | None:
        """R5-NORM 2: 스캔 공고문의 단지(같은 지역·주택관리번호)가 이미 있으면 그 타입 코드들, 없으면 None."""
        stmt = select(Complex.id).where(Complex.applyhome_id == key)
        if raw.region_id is not None:
            stmt = stmt.where(Complex.region_id == raw.region_id)
        cid = session.scalars(stmt.order_by(Complex.id)).first()
        if cid is None:
            return None
        return sorted(session.scalars(select(ComplexType.type_code).where(ComplexType.complex_id == cid)))

    def factory(kind: str) -> _Parser | None:
        return parser_for(kind, raw_dir=raw_dir, complex_key=complex_key, scan_types=scan_types)

    with session.begin_nested():
        row = _ensure_raw_row(session, raw)
        dto = raw_dto(row)
        p = parser or factory(dto.source_kind)
        cands = p.parse(dto) if p is not None else []
        binder = _Binder(session, snapshot_id=snapshot_id, detected_at=detected_at, links=links)
        bound, skipped = binder.bind(cands, dto, create=True)
        bound = _carry_compare_marks(session, bound, row.id)  # D23-3: 재정규화가 compare 표식을 지우지 않게
        old = _reparse_existing(session, binder, bound, row.id, raw_dir, factory)
        # D13-2: 새 행에도 그 의미 필드의 사람 확인(다른 행에 있는)을 0순위 후보로 — 행과 무관하게 같은 규칙.
        # D17-4(R3i major 4): 새 공고가 할인·계약금을 **싣지 않았으면**(값 없음) 그 칸에도 사람 확인 값을 그대로 적용한다
        groups = {(c.entity, c.entity_id, c.field) for c in bound} | _empty_human_groups(session, bound)
        old += semantic_humans(session, groups, bound + old)
        resolved = resolve(bound + old, price_refs(session, groups))
        fps = upsert_provenance(session, resolved.provenance)
        # R10-FIX: 이 원문의 옛 파서 행(이번 파싱이 다시 만들지 않음)은 표식 — 다른 원문의 정규화에서 후보로 되살아나지 않게
        retire_superseded(session, row.id, bound, {fp.id for fp in fps})
        events = list(binder.events)
        written, touched_complex = write_chosen(
            session,
            resolved.chosen,
            created=binder.created,
            snapshot_id=snapshot_id,
            detected_at=detected_at,
        )
        events.extend(written)
        events.extend(
            human_superseded(
                session,
                resolved,
                written,
                snapshot_id=snapshot_id,
                detected_at=detected_at,
                created=binder.created,
            )
        )
        session.flush()
        # D21-1: 청약홈 타입 가격이 바뀌면(나중에 와도) 같은 타입의 공고별 가격 보류·해제를 다시 본다(저장 순서와 무관)
        for e, i, f in sorted(_price_groups_of_types(session, bound) - groups):
            events.extend(
                resolve_field_group(session, e, i, f, [], snapshot_id=snapshot_id, now=now, add_events=False)
            )
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
        # D21-6(R4 재시험 N7)·D22-3: 원 단지에 묶여 쓰지 않은 잔여 공고의 공급위치 — 원 단지 주소에 동이 없으면 그 주소로 법정동을
        # 찾는다(바뀌면 change_event). 원 단지 주소가 아직 없으면(원 공고 다시 받기 전) 수집 단계가 실행 끝에 다시 쓴다
        alt = _merged_addresses(binder, skipped)
        for cid, addrs in sorted(alt.items()):
            cx = session.get(Complex, cid)
            if cx is not None:
                ev = correct_dong(session, cx, addrs, snapshot_id=snapshot_id, detected_at=detected_at)
                if ev is not None:
                    events.append(ev)
        folded = 0
        if first_load:
            # D18-7 + D21-7(R4 재시험 m-b): 지역 첫 적재 중의 값 기록은 빈 값 → 값뿐 아니라 같은 적재 안의 값 → 다른 값
            # 덮어쓰기(공고문이 차례로 같은 타입 가격·입주월을 덮음)도 이벤트 대신 요약으로 센다 — 첫날 G1 이 critical 로 차지 않게
            folded = len(events)
            events = []
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
        # 원 단지에 묶인 잔여 공고(D11-4): 단지 단위 후보는 건너뛰었어도 그 단지는 이 원문과 관련된 단지다(재판정 대상)
        cids |= {binder.complex_for_key(k) for k in binder.merged | binder.cited} - {None}  # type: ignore[arg-type]
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
        foreign_keys=sorted(binder.foreign),
        first_load_folded=folded,
        alt_addresses=alt,
    )
