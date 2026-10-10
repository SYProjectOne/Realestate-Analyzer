"""사실 읽기 단일 함수 — 강등(검증 모순) 읽기 시점 오버레이 (DECISIONS D11-3·D12-2, 계약 2026-10-09.9, R3 4차 리뷰 C-1·M-17).

강등은 사실 테이블 값을 지우지 않는다. ``fact_demotion`` 행이 (entity, entity_id, field, 모순 값 ``value_norm``)를
기록하고, 사실 값을 읽는 모든 곳 — 파이프라인 입력(``scheduler.inputs.load_facts``)·API(``api.facts.ProvIndex``·
``api.views.load_bundles``)·보고서(``reports.data``)·CSV·체크리스트 동기화 — 이 이 모듈로 같은 규칙을 적용한다.

**D12-2 — 강등은 행 id 가 아니라 (단지, 의미 필드, 모순 값)에 걸린다.** 의미 필드(``semantic_rows``):

- 가격 = 그 타입의 공고문 타입 행 ``complex_type.max_price_won`` + 그 단지 **모든 공고**의 ``price_by_type.<타입>.max_price_won``
- 납부 조건 필드(계약금 % 등) = 그 단지 모든 공고(``payment_terms``)의 같은 필드
- 단지 필드(입주·전매·거주의무) = 그 단지 행

그 묶음의 어느 행이든 chosen 출처 행 값이 모순 값이고 사람 확인이 아니면 그 행이 '확인 불가(검증 모순)'이다 — 같은 모순
가격을 실은 새 공고 행(무순위 병합 포함)이 와도 상세·목록·점수에 '추정'으로 돌아오지 않는다(C-1).

강등의 상태(``DemotionOverlay.status``)는 **지금 쓰는 행**(``current_row`` — 가격 = ``price_view.current_price`` 의 max_ref,
납부 조건 = 현재 공고, 단지 필드 = 단지 행)으로 정한다:

(a) 사람 확인(0순위 후보가 chosen) → 'human_check' — 그 의미 필드의 어느 행도 가리지 않는다(사람 확인이 이긴다).
(b) 원문의 **다른 값**(값 있는 채택) → 'new_source' — 체크리스트는 닫히지만, 모순 값을 그대로 실은 다른 행(옛 공고)은
    계속 가린다. 같은 모순 값이 다시 지금 쓰는 행이 되면(compare 재채택 등) 다시 'demoted'(쓰기 경로가 재강등 기록, M-17).
(c) 그 밖(같은 값 재수집·값 없는 행·채택 보류 대표 행) → 'demoted'.

창(window)이 없다 — 강등 기록이 생긴 순간부터 모든 읽기 경로가 같다. 여기는 읽기만 한다(DB 쓰기 없음 — GET 도 이 함수를
쓴다). 복원·재강등 기록은 쓰기 경로(``api.demotion.sync_demotions``)가 남긴다. 판단 없음 — 문자열 비교뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import FactDemotion, FieldProvenance

__all__ = [
    "DEMOTION_LABEL",
    "DEMOTION_REASON",
    "HUMAN_REASON",
    "RESTORED_HUMAN",
    "RESTORED_NEW_SOURCE",
    "STATUS_DEMOTED",
    "ChosenRef",
    "DemotionOverlay",
    "chosen_from_rows",
    "current_row",
    "is_human",
    "load_overlay",
    "logical_field",
    "overlay_applies",
    "region_catalysts",
    "semantic_group",
    "semantic_rows",
]

DEMOTION_LABEL: Final = "확인 불가"
DEMOTION_REASON: Final = "검증 모순"
HUMAN_REASON: Final = "사람 확인"
"""사람 확인 출처 행 reason 머리('사람 확인(phone)'). resolver 0순위 후보(``api.demotion.apply_human_check``)."""
STATUS_DEMOTED: Final = "demoted"
RESTORED_NEW_SOURCE: Final = "new_source"
RESTORED_HUMAN: Final = "human_check"
_CHUNK: Final = 500

RowKey = tuple[str, int, str]


def is_human(reason: str | None) -> bool:
    """사람 확인 출처 행인가(reason '사람 확인(…)' — 앞에 compare·상충 표식이 붙어 있어도)."""
    if not reason:
        return False
    from app.normalize.fields import strip_tags

    return (strip_tags(str(reason)) or "").startswith(HUMAN_REASON)


def logical_field(name: str) -> str:
    """출처 필드 경로 → 논리 필드: 'price_by_type.84A.max_price_won' → 'max_price_won', 그 밖은 그대로."""
    if name.startswith("price_by_type."):
        return name.rsplit(".", 1)[-1]
    return name


@dataclass(frozen=True, slots=True)
class ChosenRef:
    """chosen 출처 행에서 오버레이 판단에 쓰는 열."""

    id: int
    value_norm: str | None
    reason: str | None
    raw_document_id: int | None


def overlay_applies(d: FactDemotion, chosen: ChosenRef | None) -> bool:
    """강등이 **원래 행**에 지금 적용되는가(행 단위 규칙 — 같은 의미 필드의 다른 행은 ``load_overlay``). 사람 확인 복원이면
    False."""
    if d.restored_at is not None and d.restored_by != RESTORED_NEW_SOURCE:
        return False
    return _row_applies(d, chosen, original=True)


def _row_applies(d: FactDemotion, chosen: ChosenRef | None, *, original: bool) -> bool:
    """모순 값이 이 행의 chosen 값인가(D12-2: 같은 단지·같은 의미 필드의 어느 행이든)."""
    if chosen is None:
        return original  # 원래 행에 chosen 출처 행이 없다 = 값도 없다(강등 표시가 맞다). 다른 행은 값이 없으면 무관
    if is_human(chosen.reason):
        return False
    if (chosen.reason or "") == DEMOTION_REASON and chosen.raw_document_id is None:
        return original  # 0006 강등 출처 행(값을 비운 강등)이 아직 chosen
    if d.value_norm is not None and chosen.value_norm is not None:
        return chosen.value_norm == d.value_norm
    if not original:
        return False
    # 정준 값(value_norm)을 모르는 옛 출처 행(0002 이전·시드): 강등한 그 출처 행이 chosen 인 동안만
    return chosen.id == d.original_fp_id


@dataclass
class DemotionOverlay:
    """적용 중인 강등 색인. ``fields(entity, id)`` → 가려진 필드(출처 필드 경로, 예 'price_by_type.84A.max_price_won').

    ``status[d.id]`` = 강등의 지금 상태('demoted' · 'new_source' · 'human_check' — 모듈 설명), ``demotions`` = 읽은 강등."""

    active: dict[RowKey, FactDemotion] = field(default_factory=dict)
    status: dict[int, str] = field(default_factory=dict)
    current: dict[int, ChosenRef | None] = field(default_factory=dict)
    """강등 id → 지금 쓰는 행의 chosen 출처(없으면 None) — 재강등이 '모순 값이 다시 채택'인지 '채택 보류'인지 가른다(M3)."""
    demotions: list[FactDemotion] = field(default_factory=list)
    _by_row: dict[tuple[str, int], set[str]] = field(default_factory=lambda: defaultdict(set))

    def mark(self, key: RowKey, d: FactDemotion) -> None:
        self.active.setdefault(key, d)
        self._by_row[(key[0], key[1])].add(key[2])

    def state(self, d: FactDemotion) -> str:
        """강등 상태. 읽지 않은 강등은 기록 그대로(복원 기록 있으면 그 사유)."""
        st = self.status.get(d.id)
        if st is not None:
            return st
        return STATUS_DEMOTED if d.restored_at is None else str(d.restored_by or RESTORED_NEW_SOURCE)

    def fields(self, entity: str, entity_id: int | None) -> frozenset[str]:
        if entity_id is None:
            return frozenset()
        return frozenset(self._by_row.get((entity, entity_id), ()))

    def get(self, entity: str, entity_id: int | None, name: str) -> FactDemotion | None:
        if entity_id is None:
            return None
        return self.active.get((entity, entity_id, name))

    def is_demoted(self, entity: str, entity_id: int | None, name: str) -> bool:
        return self.get(entity, entity_id, name) is not None

    def complex_ids(self) -> set[int]:
        return {d.complex_id for d in self.active.values() if d.complex_id is not None}

    def __bool__(self) -> bool:
        return bool(self.active)


def _chosen_refs(session: Session, keys: Iterable[RowKey]) -> dict[RowKey, ChosenRef]:
    want: dict[str, set[int]] = defaultdict(set)
    fields: set[RowKey] = set()
    for e, i, f in keys:
        want[e].add(i)
        fields.add((e, i, f))
    out: dict[RowKey, ChosenRef] = {}
    fp = FieldProvenance
    for entity, ids in want.items():
        id_list = sorted(ids)
        names = sorted({f for (e, _i, f) in fields if e == entity})
        for start in range(0, len(id_list), _CHUNK):
            stmt = (
                select(fp.entity_id, fp.field, fp.id, fp.value_norm, fp.reason, fp.raw_document_id)
                .where(
                    fp.entity == entity,
                    fp.entity_id.in_(id_list[start : start + _CHUNK]),
                    fp.field.in_(names),
                    fp.chosen.is_(True),
                )
                .order_by(fp.id)
            )
            for eid, name, fid, vn, reason, raw in session.execute(stmt):
                if eid is None:
                    continue
                key = (entity, int(eid), str(name))
                if key in fields and key not in out:
                    out[key] = ChosenRef(int(fid), vn, reason, raw)
    return out


@dataclass
class _Rows:
    """강등이 있는 단지의 타입·납부 조건 행(의미 필드 묶음·현재 행 계산용 — 읽기만)."""

    types: dict[int, list[Any]] = field(default_factory=lambda: defaultdict(list))
    terms: dict[int, list[Any]] = field(default_factory=lambda: defaultdict(list))
    type_code: dict[int, str] = field(default_factory=dict)


def _load_rows(session: Session, complex_ids: set[int]) -> _Rows:
    from app.models import ComplexType, PaymentTerms

    out = _Rows()
    cids = sorted(complex_ids)
    for start in range(0, len(cids), _CHUNK):
        chunk = cids[start : start + _CHUNK]
        for t in session.scalars(
            select(ComplexType).where(ComplexType.complex_id.in_(chunk)).order_by(ComplexType.id)
        ):
            out.types[t.complex_id].append(t)
            out.type_code[t.id] = t.type_code
        for p in session.scalars(
            select(PaymentTerms).where(PaymentTerms.complex_id.in_(chunk)).order_by(PaymentTerms.id)
        ):
            out.terms[p.complex_id].append(p)
    return out


def _type_code_of(d: FactDemotion, rows: _Rows) -> str | None:
    from app.normalize.fields import split_price_by_type

    pbt = split_price_by_type(d.field)
    if pbt is not None:
        return pbt[0]
    if d.entity == "complex_type":
        return rows.type_code.get(d.entity_id)
    return None


def semantic_rows(d: FactDemotion, rows: _Rows) -> list[RowKey]:
    """D12-2 같은 단지·같은 의미 필드의 행들(원래 행 포함, 모듈 설명)."""
    original: RowKey = (d.entity, d.entity_id, d.field)
    cid = d.complex_id
    if cid is None or d.entity == "complex":
        return [original]
    out: list[RowKey] = [original]
    if logical_field(d.field) == "max_price_won":
        code = _type_code_of(d, rows)
        if code is None:
            return out
        out += [
            ("complex_type", t.id, "max_price_won") for t in rows.types.get(cid, []) if t.type_code == code
        ]
        out += [
            ("payment_terms", p.id, f"price_by_type.{code}.max_price_won") for p in rows.terms.get(cid, [])
        ]
    elif d.entity == "payment_terms":
        out += [("payment_terms", p.id, d.field) for p in rows.terms.get(cid, [])]
    elif d.entity == "complex_type":
        code = _type_code_of(d, rows)
        out += [("complex_type", t.id, d.field) for t in rows.types.get(cid, []) if t.type_code == code]
    return list(dict.fromkeys(out))


def current_row(d: FactDemotion, rows: _Rows) -> RowKey | None:
    """그 의미 필드에서 점수·화면이 **지금 쓰는** 행. 못 정하면(가격 미공개·납부 조건 없음) None."""
    from app.analysis.price_view import current_price, current_terms

    if d.complex_id is None or d.entity == "complex":
        return (d.entity, d.entity_id, d.field)
    cid = d.complex_id
    if logical_field(d.field) == "max_price_won":
        ref = current_price(rows.types.get(cid, []), rows.terms.get(cid, []), discount_label=None).max_ref
        return (ref.entity, ref.entity_id, ref.field) if ref is not None else None
    if d.entity == "payment_terms":
        cur = current_terms(rows.terms.get(cid, []))
        return ("payment_terms", cur.id, d.field) if cur is not None else None
    return (d.entity, d.entity_id, d.field)


def _status(d: FactDemotion, cur: ChosenRef | None, original: ChosenRef | None) -> str:
    """강등의 지금 상태(모듈 설명 (a)~(c)). 채택 보류(compare 대기) 대표 행·값 없는 행은 풀지 않는다(M-17)."""
    from app.normalize.fields import CONFLICT_HOLD, has_tag

    if d.restored_at is not None and d.restored_by == RESTORED_HUMAN:
        return RESTORED_HUMAN
    if cur is not None and is_human(cur.reason):
        return RESTORED_HUMAN
    if d.value_norm is None:  # 0006 시절 행(모순 값 모름) — 원래 행 규칙
        if _row_applies(d, original, original=True):
            return STATUS_DEMOTED
        return RESTORED_HUMAN if original is not None and is_human(original.reason) else RESTORED_NEW_SOURCE
    if (
        cur is not None
        and cur.value_norm is not None
        and cur.value_norm != d.value_norm
        and not has_tag(cur.reason, CONFLICT_HOLD)
        and not ((cur.reason or "") == DEMOTION_REASON and cur.raw_document_id is None)
    ):
        return RESTORED_NEW_SOURCE
    return STATUS_DEMOTED


def _candidates(session: Session, complex_ids: Iterable[int] | None) -> list[FactDemotion]:
    """오버레이 대상 강등: 복원 기록 없음 + 새 출처로 풀린 것(같은 모순 값이 다시 chosen 이면 다시 가린다 — M-17)."""
    stmt = select(FactDemotion).where(
        or_(FactDemotion.restored_at.is_(None), FactDemotion.restored_by == RESTORED_NEW_SOURCE)
    )
    if complex_ids is None:
        return list(session.scalars(stmt))
    cids = sorted(set(complex_ids))
    rows: list[FactDemotion] = []
    for start in range(0, len(cids), _CHUNK):
        rows.extend(session.scalars(stmt.where(FactDemotion.complex_id.in_(cids[start : start + _CHUNK]))))
    return rows


def _complexes_of(session: Session, entity: str, ids: Iterable[int]) -> set[int]:
    """행 id → 강등이 있는 단지 id(강등 표는 작다 — 강등 단지의 행만 대조)."""
    from app.models import ComplexType, PaymentTerms

    want = set(ids)
    demo_cx = {
        int(c)
        for c in session.scalars(
            select(FactDemotion.complex_id).where(FactDemotion.complex_id.is_not(None)).distinct()
        )
        if c is not None
    }
    if not want or not demo_cx:
        return set()
    if entity == "complex":
        return want & demo_cx
    model: Any = {"complex_type": ComplexType, "payment_terms": PaymentTerms}.get(entity)
    if model is None:
        return demo_cx
    hit: set[int] = set()
    cx_list = sorted(demo_cx)
    for start in range(0, len(cx_list), _CHUNK):
        for rid, cid in session.execute(
            select(model.id, model.complex_id).where(model.complex_id.in_(cx_list[start : start + _CHUNK]))
        ):
            if rid in want:
                hit.add(int(cid))
    return hit


def load_overlay(
    session: Session,
    *,
    entity: str | None = None,
    ids: Iterable[int] | None = None,
    complex_ids: Iterable[int] | None = None,
    chosen: Mapping[RowKey, ChosenRef] | None = None,
) -> DemotionOverlay:
    """강등을 읽어 오버레이를 만든다(읽기 전용). 범위: ``complex_ids``, 또는 ``entity``+``ids``(그 행들이 속한 단지),
    없으면 전부. 강등은 단지 단위로 펼친다(D12-2).

    ``chosen``: 호출자가 이미 읽은 chosen 출처 행(없는 키만 여기서 한 번 더 읽는다)."""
    if ids is not None and entity is not None:
        complex_ids = _complexes_of(session, entity, ids)
    rows = _candidates(session, complex_ids)
    out = DemotionOverlay()
    if not rows:
        return out
    # 같은 행에 강등 기록이 여럿이면(같은 사실의 두 번째 주장 등) 가장 새 것 하나
    latest: dict[RowKey, FactDemotion] = {}
    for d in sorted(rows, key=lambda r: r.id):
        latest[(d.entity, d.entity_id, d.field)] = d
    demos = list(latest.values())
    data = _load_rows(session, {d.complex_id for d in demos if d.complex_id is not None})
    groups = {d.id: semantic_rows(d, data) for d in demos}
    currents = {d.id: current_row(d, data) for d in demos}
    keys: set[RowKey] = {k for g in groups.values() for k in g}
    keys |= {c for c in currents.values() if c is not None}
    refs: dict[RowKey, ChosenRef] = {k: chosen[k] for k in keys if chosen is not None and k in chosen}
    missing = [k for k in keys if k not in refs]
    if missing:
        refs.update(_chosen_refs(session, missing))
    for d in demos:
        original: RowKey = (d.entity, d.entity_id, d.field)
        cur = currents[d.id]
        cur_ref = refs.get(cur) if cur is not None else None
        st = _status(d, cur_ref, refs.get(original))
        out.demotions.append(d)
        out.status[d.id] = st
        out.current[d.id] = cur_ref
        if st == RESTORED_HUMAN:
            continue  # 사람 확인이 이긴다 — 그 의미 필드의 어느 행도 가리지 않는다
        for k in groups[d.id]:
            if _row_applies(d, refs.get(k), original=k == original):
                out.mark(k, d)
    return out


def chosen_from_rows(rows: Iterable[Any]) -> dict[RowKey, ChosenRef]:
    """이미 읽은 FieldProvenance(ORM) chosen 행 → ChosenRef 색인."""
    out: dict[RowKey, ChosenRef] = {}
    for r in rows:
        if r.entity_id is None or not r.chosen:
            continue
        key = (str(r.entity), int(r.entity_id), str(r.field))
        out.setdefault(key, ChosenRef(int(r.id), r.value_norm, r.reason, r.raw_document_id))
    return out


def semantic_group(
    session: Session, entity: str, entity_id: int, field_name: str
) -> tuple[int | None, list[RowKey]]:
    """(단지, 의미 필드) 단위 행 묶음 — 강등(D12-2)과 사람 확인(D13-2)이 같은 키를 쓴다. 반환 (단지 id, 행들[자기 먼저]).

    - 단지 필드 → 그 단지 행 하나
    - 가격(``max_price_won``) → 그 타입 코드의 공고문 타입 행 + 그 단지 **모든 공고**의 ``price_by_type.<타입>.max_price_won``
    - 납부 조건 필드 → 그 단지 모든 공고의 같은 필드
    - 타입 행의 다른 필드 → 같은 타입 코드의 타입 행들"""
    from app.models import ComplexType, PaymentTerms
    from app.normalize.fields import split_price_by_type

    me: RowKey = (entity, entity_id, field_name)
    if entity == "complex":
        return entity_id, [me]
    code: str | None = None
    if entity == "complex_type":
        t = session.get(ComplexType, entity_id)
        if t is None:
            return None, [me]
        cid, code = t.complex_id, t.type_code
    elif entity == "payment_terms":
        p = session.get(PaymentTerms, entity_id)
        if p is None:
            return None, [me]
        cid = p.complex_id
        pbt = split_price_by_type(field_name)
        code = pbt[0] if pbt is not None else None
    else:
        return None, [me]
    rows = _load_rows(session, {cid})
    out: list[RowKey] = [me]
    if logical_field(field_name) == "max_price_won" and code is not None:
        out += [
            ("complex_type", t.id, "max_price_won") for t in rows.types.get(cid, []) if t.type_code == code
        ]
        out += [
            ("payment_terms", p.id, f"price_by_type.{code}.max_price_won") for p in rows.terms.get(cid, [])
        ]
    elif entity == "payment_terms":
        out += [("payment_terms", p.id, field_name) for p in rows.terms.get(cid, [])]
    else:
        out += [("complex_type", t.id, field_name) for t in rows.types.get(cid, []) if t.type_code == code]
    return cid, list(dict.fromkeys(out))


NOT_CATALYST: Final = "호재 아님"


def region_catalysts(
    session: Session, region_id: int, *, include_not_catalyst: bool = False
) -> list[tuple[Any, list[Any]]]:
    """지역의 지금 호재와 연결 [(호재, 연결들)] — 발행 전 리비전·materialize 가 읽는 값(발행 리비전은 저장본, D13-1).

    '호재 아님'(D11-2 — 판정기가 호재가 아니라고 본 후보)은 기본으로 뺀다(상세 catalysts·시장 보드·보고서 §5)."""
    from app.models import Catalyst, CatalystLink

    cats = list(
        session.scalars(select(Catalyst).where(Catalyst.region_id == region_id).order_by(Catalyst.id))
    )
    links: dict[int, list[Any]] = defaultdict(list)
    if cats:
        for lk in session.scalars(
            select(CatalystLink)
            .where(CatalystLink.catalyst_id.in_([c.id for c in cats]))
            .order_by(CatalystLink.complex_id)
        ):
            links[lk.catalyst_id].append(lk)
    return [(c, links.get(c.id, [])) for c in cats if include_not_catalyst or c.stage != NOT_CATALYST]
