"""사실 읽기 단일 함수 — 강등(검증 모순) 읽기 시점 오버레이 (DECISIONS D11-3, 계약 2026-10-09.8, R3 3차 리뷰 C-3·C-4·M-3).

강등은 사실 테이블 값을 지우지 않는다. ``fact_demotion`` 행이 (entity, entity_id, field, 모순 값 ``value_norm``)를
기록하고, 사실 값을 읽는 모든 곳 — 파이프라인 입력(``scheduler.inputs.load_facts``)·API(``api.facts.ProvIndex``·
``api.views.load_bundles``)·보고서(``reports.data``)·CSV·체크리스트 동기화 — 이 이 모듈로 같은 규칙을 적용한다:

    강등 중 = 복원 기록 없음(restored_at NULL)
              AND chosen 출처 행이 사람 확인이 아님
              AND chosen 출처 행 value_norm == 강등한 모순 값

창(window)이 없다 — 다음 수집·파이프라인을 기다리지 않고 강등 기록이 생긴 순간부터 상세·목록·CSV·보고서·점수 입력 모두
'확인 불가(검증 모순)'이다. 해제는 두 가지뿐이다(``api.demotion``):

(a) 사람 확인 — ``human_check`` 가 resolver 0순위 후보(source_rank 0, reason '사람 확인(…)')로 들어가 chosen 이 되고,
    재정규화(같은 원문 재수집)에도 그대로 이긴다.
(b) 새 출처가 **다른 값**을 낼 때 — chosen 값이 모순 값과 달라진다. 같은 값 재수집(sha 만 다름)·값 없는 행(파싱 실패)은
    chosen 값이 그대로라 해제되지 않는다.

여기는 읽기만 한다(DB 쓰기 없음 — GET 도 이 함수를 쓴다). 복원 기록(restored_at)은 쓰기 경로(``api.demotion.sync_demotions``)가
남긴다. 판단 없음 — 문자열 비교뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FactDemotion, FieldProvenance

__all__ = [
    "DEMOTION_LABEL",
    "DEMOTION_REASON",
    "HUMAN_REASON",
    "ChosenRef",
    "DemotionOverlay",
    "is_human",
    "load_overlay",
    "logical_field",
    "overlay_applies",
]

DEMOTION_LABEL: Final = "확인 불가"
DEMOTION_REASON: Final = "검증 모순"
HUMAN_REASON: Final = "사람 확인"
"""사람 확인 출처 행 reason 머리('사람 확인(phone)'). resolver 0순위 후보(``api.demotion.apply_human_check``)."""
_CHUNK: Final = 500


def is_human(reason: str | None) -> bool:
    """사람 확인 출처 행인가(reason '사람 확인(…)')."""
    return bool(reason) and str(reason).startswith(HUMAN_REASON)


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
    """강등이 지금 적용되는가(모듈 설명의 규칙). 복원 기록이 있으면 False."""
    if d.restored_at is not None:
        return False
    if chosen is None:
        return True  # chosen 출처 행이 없다 = 값도 없다(강등 표시가 맞다)
    if is_human(chosen.reason):
        return False
    if (chosen.reason or "") == DEMOTION_REASON and chosen.raw_document_id is None:
        return True  # 0006 강등 출처 행(값을 비운 강등)이 아직 chosen
    if d.value_norm is not None and chosen.value_norm is not None:
        return chosen.value_norm == d.value_norm
    # 정준 값(value_norm)을 모르는 옛 출처 행(0002 이전·시드): 강등한 그 출처 행이 chosen 인 동안만
    return chosen.id == d.original_fp_id


@dataclass
class DemotionOverlay:
    """적용 중인 강등 색인. ``fields(entity, id)`` → 강등된 필드(출처 필드 경로, 예 'price_by_type.84A.max_price_won')."""

    active: dict[tuple[str, int, str], FactDemotion] = field(default_factory=dict)
    pending: dict[tuple[str, int, str], FactDemotion] = field(default_factory=dict)
    """복원 기록은 없지만 오버레이가 풀린 강등(새 출처 다른 값·사람 확인 — 다음 쓰기 경로가 복원으로 기록)."""
    _by_row: dict[tuple[str, int], set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, d: FactDemotion, applies: bool) -> None:
        key = (d.entity, d.entity_id, d.field)
        if applies:
            self.active[key] = d
            self._by_row[(d.entity, d.entity_id)].add(d.field)
        else:
            self.pending[key] = d

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


def _chosen_refs(
    session: Session, keys: Iterable[tuple[str, int, str]]
) -> dict[tuple[str, int, str], ChosenRef]:
    want: dict[str, set[int]] = defaultdict(set)
    fields: set[tuple[str, int, str]] = set()
    for e, i, f in keys:
        want[e].add(i)
        fields.add((e, i, f))
    out: dict[tuple[str, int, str], ChosenRef] = {}
    fp = FieldProvenance
    for entity, ids in want.items():
        id_list = sorted(ids)
        for start in range(0, len(id_list), _CHUNK):
            stmt = (
                select(fp.entity_id, fp.field, fp.id, fp.value_norm, fp.reason, fp.raw_document_id)
                .where(
                    fp.entity == entity,
                    fp.entity_id.in_(id_list[start : start + _CHUNK]),
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


def load_overlay(
    session: Session,
    *,
    entity: str | None = None,
    ids: Iterable[int] | None = None,
    complex_ids: Iterable[int] | None = None,
    chosen: Mapping[tuple[str, int, str], ChosenRef] | None = None,
) -> DemotionOverlay:
    """복원 기록 없는 강등을 읽어 오버레이를 만든다(읽기 전용). 범위: ``entity``+``ids`` 또는 ``complex_ids``, 없으면 전부.

    ``chosen``: 호출자가 이미 읽은 chosen 출처 행(없으면 여기서 강등된 키만 한 번 더 읽는다)."""
    stmt = select(FactDemotion).where(FactDemotion.restored_at.is_(None))
    if entity is not None:
        stmt = stmt.where(FactDemotion.entity == entity)
    rows: list[FactDemotion] = []
    if ids is not None:
        id_list = sorted(set(ids))
        for start in range(0, len(id_list), _CHUNK):
            rows.extend(
                session.scalars(stmt.where(FactDemotion.entity_id.in_(id_list[start : start + _CHUNK])))
            )
    elif complex_ids is not None:
        cids = sorted(set(complex_ids))
        for start in range(0, len(cids), _CHUNK):
            rows.extend(
                session.scalars(stmt.where(FactDemotion.complex_id.in_(cids[start : start + _CHUNK])))
            )
    else:
        rows = list(session.scalars(stmt))
    out = DemotionOverlay()
    if not rows:
        return out
    # 같은 사실에 강등 행이 여럿이면(같은 사실의 두 번째 주장 등) 가장 새 것 하나
    latest: dict[tuple[str, int, str], FactDemotion] = {}
    for d in sorted(rows, key=lambda r: r.id):
        latest[(d.entity, d.entity_id, d.field)] = d
    refs: Mapping[tuple[str, int, str], ChosenRef]
    missing = [k for k in latest if chosen is None or k not in chosen]
    refs = dict(chosen or {})
    if missing:
        refs = {**refs, **_chosen_refs(session, missing)}
    for key, d in latest.items():
        out.add(d, overlay_applies(d, refs.get(key)))
    return out


def chosen_from_rows(rows: Iterable[Any]) -> dict[tuple[str, int, str], ChosenRef]:
    """이미 읽은 FieldProvenance(ORM) chosen 행 → ChosenRef 색인."""
    out: dict[tuple[str, int, str], ChosenRef] = {}
    for r in rows:
        if r.entity_id is None or not r.chosen:
            continue
        key = (str(r.entity), int(r.entity_id), str(r.field))
        out.setdefault(key, ChosenRef(int(r.id), r.value_norm, r.reason, r.raw_document_id))
    return out
