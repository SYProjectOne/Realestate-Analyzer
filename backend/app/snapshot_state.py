"""리비전 시점 값 — 발행 스냅샷이 나중에 바뀌지 않게(DECISIONS D12-4, 계약 2026-10-09.9, R3 4차 M-7).

판정 범위·생활권·호재 단계/연결처럼 **리비전마다 달라질 수 있는 값**은 사실 테이블에서 제자리로 갱신된다(단지 분류
``complex.inclusion_class``·생활권 ``complex.living_area``·``region.living_areas``·호재 ``catalyst.stage``·``kind``·
``catalyst_link``). 발행(``scheduler.snapshots.publish``) 순간 그 값을 ``snapshot_state`` 에 얼려 두고, 그 스냅샷을
읽는 화면·보고서는 얼린 값을 쓴다 — 옛 리비전 상세·시장·보고서가 나중 편집으로 바뀌지 않는다.

- 얼린 값이 없는 스냅샷(발행 전 building·ready, 0009 이전 발행분)은 지금 값(사실 테이블)을 쓴다.
- 얼린 뒤 생긴 호재는 그 스냅샷에 없다. 얼린 뒤 지운 연결도 그 스냅샷에는 남는다.
- 읽기 전용 감싸개(``_Override``)로 속성만 바꿔 보인다 — DB 쓰기 없음(GET 도 쓴다).

판단 없음 — 값 복사뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Catalyst, CatalystLink, Complex, Region, Snapshot, SnapshotState

__all__ = [
    "CATALYST_KEYS",
    "COMPLEX_KEYS",
    "FrozenLink",
    "State",
    "catalysts_for",
    "freeze",
    "load_state",
    "region_for",
]

COMPLEX_KEYS: Final = ("inclusion_class", "inclusion_decision", "living_area", "legal_dong_code")
CATALYST_KEYS: Final = ("stage", "kind", "location_confirmed", "expected_ym", "lat", "lon")
NOT_CATALYST: Final = "호재 아님"


class _Override:
    """행의 일부 속성만 얼린 값으로 보이는 읽기 전용 감싸개."""

    __slots__ = ("_row", "_values")

    def __init__(self, row: Any, values: Mapping[str, Any]) -> None:
        self._row = row
        self._values = values

    def __getattr__(self, name: str) -> Any:
        if name in self._values:
            return self._values[name]
        return getattr(self._row, name)


@dataclass(frozen=True, slots=True)
class FrozenLink:
    """얼린 catalyst_link 1행(``CatalystLink`` 과 같은 속성)."""

    catalyst_id: int
    complex_id: int
    distance_m: int | None
    weight: Decimal | None
    label: str | None
    reason: str | None


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    return v


def _dec(v: Any) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def freeze(session: Session, snapshot_id: int) -> int:
    """발행 순간의 리비전 시점 값을 얼린다(이미 얼렸으면 그대로 — 발행 스냅샷은 불변). 넣은 행 수."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        return 0
    if session.scalars(
        select(SnapshotState.id).where(SnapshotState.snapshot_id == snapshot_id).limit(1)
    ).first():
        return 0
    region = session.get(Region, snap.region_id)
    rows: list[SnapshotState] = []
    if region is not None:
        rows.append(
            SnapshotState(
                snapshot_id=snapshot_id, entity="region", entity_id=region.id,
                data={"living_areas": list(region.living_areas or [])},
            )
        )  # fmt: skip
    for cx in session.scalars(
        select(Complex).where(Complex.region_id == snap.region_id).order_by(Complex.id)
    ):
        rows.append(
            SnapshotState(
                snapshot_id=snapshot_id, entity="complex", entity_id=cx.id,
                data={k: getattr(cx, k) for k in COMPLEX_KEYS},
            )
        )  # fmt: skip
    cats = list(
        session.scalars(select(Catalyst).where(Catalyst.region_id == snap.region_id).order_by(Catalyst.id))
    )
    links: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if cats:
        for lk in session.scalars(
            select(CatalystLink)
            .where(CatalystLink.catalyst_id.in_([c.id for c in cats]))
            .order_by(CatalystLink.complex_id)
        ):
            links[lk.catalyst_id].append(
                {"complex_id": lk.complex_id, "distance_m": lk.distance_m, "weight": _jsonable(lk.weight),
                 "label": lk.label, "reason": lk.reason}
            )  # fmt: skip
    for c in cats:
        data = {k: _jsonable(getattr(c, k)) for k in CATALYST_KEYS}
        data["links"] = links.get(c.id, [])
        rows.append(SnapshotState(snapshot_id=snapshot_id, entity="catalyst", entity_id=c.id, data=data))
    session.add_all(rows)
    session.flush()
    return len(rows)


@dataclass
class State:
    """얼린 값(스냅샷 1개)."""

    snapshot_id: int
    region: dict[str, Any] | None = None
    complexes: dict[int, dict[str, Any]] = field(default_factory=dict)
    catalysts: dict[int, dict[str, Any]] = field(default_factory=dict)

    def complex(self, row: Any) -> Any:
        """단지 행 → 분류·생활권·법정동이 얼린 값인 감싸개(얼린 값이 없는 단지는 그대로)."""
        data = self.complexes.get(int(row.id))
        return row if data is None else _Override(row, data)

    def region_row(self, row: Any) -> Any:
        return (
            row
            if self.region is None
            else _Override(row, {"living_areas": self.region.get("living_areas") or []})
        )

    def catalyst(self, row: Any) -> Any:
        data = self.catalysts.get(int(row.id))
        if data is None:
            return row
        vals = {k: data.get(k) for k in CATALYST_KEYS}
        vals["lat"], vals["lon"] = _dec(vals["lat"]), _dec(vals["lon"])
        return _Override(row, vals)

    def links(self, catalyst_id: int) -> list[FrozenLink]:
        data = self.catalysts.get(catalyst_id) or {}
        return [
            FrozenLink(catalyst_id, int(lk["complex_id"]), lk.get("distance_m"), _dec(lk.get("weight")),
                       lk.get("label"), lk.get("reason"))
            for lk in data.get("links") or []
        ]  # fmt: skip


def load_state(session: Session, snapshot_id: int | None) -> State | None:
    """얼린 값. 없으면 None(지금 값을 쓴다)."""
    if snapshot_id is None:
        return None
    rows = list(session.scalars(select(SnapshotState).where(SnapshotState.snapshot_id == snapshot_id)))
    if not rows:
        return None
    st = State(snapshot_id)
    for r in rows:
        data = dict(r.data or {})
        if r.entity == "region":
            st.region = data
        elif r.entity == "complex":
            st.complexes[r.entity_id] = data
        elif r.entity == "catalyst":
            st.catalysts[r.entity_id] = data
    return st


def region_for[R: Region | None](session: Session, region: R, snapshot_id: int | None) -> R:
    """그 스냅샷 시점의 지역(생활권) — 얼린 값이 없으면 지금 행."""
    if region is None:
        return region
    st = load_state(session, snapshot_id)
    return cast(R, st.region_row(region)) if st is not None else region


def catalysts_for(
    session: Session,
    region_id: int,
    snapshot_id: int | None,
    *,
    include_not_catalyst: bool = False,
    state: State | None = None,
) -> list[tuple[Any, list[Any]]]:
    """그 스냅샷 시점의 호재와 연결 [(호재, 연결들)]. 얼린 값이 있으면 그 호재·단계·연결, 없으면 지금 값.
    '호재 아님'(D11-2 — 판정기가 호재가 아니라고 본 후보)은 기본으로 뺀다(R3 4차 M-7: 상세·보고서 §5 에 섞였다)."""
    st = state if state is not None else load_state(session, snapshot_id)
    cats = list(
        session.scalars(select(Catalyst).where(Catalyst.region_id == region_id).order_by(Catalyst.id))
    )
    out: list[tuple[Any, list[Any]]] = []
    if st is not None:
        for c in cats:
            if c.id not in st.catalysts:
                continue  # 얼린 뒤 생긴 호재
            view = st.catalyst(c)
            if view.stage == NOT_CATALYST and not include_not_catalyst:
                continue
            out.append((view, list(st.links(c.id))))
        return out
    links: dict[int, list[Any]] = defaultdict(list)
    if cats:
        for lk in session.scalars(
            select(CatalystLink)
            .where(CatalystLink.catalyst_id.in_([c.id for c in cats]))
            .order_by(CatalystLink.complex_id)
        ):
            links[lk.catalyst_id].append(lk)
    for c in cats:
        if c.stage == NOT_CATALYST and not include_not_catalyst:
            continue
        out.append((c, links.get(c.id, [])))
    return out


def complexes_for(state: State | None, rows: Iterable[Any]) -> list[Any]:
    """단지 행들 → 그 스냅샷 시점 값으로 보이는 행들."""
    if state is None:
        return list(rows)
    return [state.complex(r) for r in rows]
