"""발행 리비전 = 저장된 읽기 모델(materialized) — DECISIONS D13-1, 계약 2026-10-09.10 (R3 5차 리뷰 K2·M6).

리비전을 published 로 바꾸는 트랜잭션(``scheduler.snapshots.publish``)에서 ``materialize`` 가 그 리비전의 화면 응답
전부와 보고서 입력 데이터를 시나리오별로 만들어 ``snapshot_view`` 에 저장한다. 발행 리비전의 GET 은 ``read`` 로
**저장본만** 읽는다(현재 사실·강등 오버레이·생활권·호재·점수 문맥 재계산 없음). building·ready 리비전만 실시간 계산.

| kind | key | scenario | 내용 |
| --- | --- | --- | --- |
| dashboard | '' | 시나리오 id | G1 대시보드 응답 |
| complexes | '' | 시나리오 id | G2 단지 행 전부(필터·정렬 키 포함) — 목록·CSV 는 이 행에 질의만 적용 |
| complex | 단지 id | 시나리오 id | G3 단지 상세 응답 |
| compare | '' | 시나리오 id | G4 비교 입력(단지별 행·사다리·갭·자금 조건 + 결정·가중치) |
| market | '' · 생활권 id | 시나리오 id | G6 시장 응답(전체·생활권별 — 입주 마커 범위가 시나리오 실행 값) |
| changes | '' | '' | 변경 피드 원장(지역 관련 change_event 전부 — 기본·since·비교·심각도 질의는 읽을 때) |
| sensitivity | '' | 시나리오 id | C10 민감도 응답 |
| report | '' | 시나리오 id | 보고서 입력 데이터(``reports.data.ReportData``·후보군·이름) |
| report_diff | '' | 시나리오 id | 리비전 diff 입력(점수·사다리·접수·결정·주장·호출 집계) |

- 이전의 값별 동결(``snapshot_state`` — 분류·생활권·호재 단계/연결만 얼림)은 이 저장본으로 대체됐다(0010 에서 삭제).
  얼리지 않던 값(사실·강등·단지 목록·체크리스트·지역 이름·호재 확률·입주 물량 등)도 이제 리비전과 함께 고정된다.
- 출처 누락은 발행을 막지 않는다: 저장본은 ENV=prod 규칙('확인 불가(출처 누락)' + 경고 로그)으로 만든다(dev 의 500 은
  발행 전 리비전 실시간 GET 에서 드러난다 — T13).
- 저장본이 없는 발행 리비전(있으면 안 된다 — 0010 마이그레이션이 옛 발행분을 materialize 한다)은 실시간으로 대신
  계산하지 않고 ``NotMaterialized`` 로 실패한다(조용한 폴백 금지).
- 발행 뒤 만든 시나리오는 그 리비전에 저장본이 없다 → 404(그 시나리오 결과는 시나리오 실행이 만드는 새 리비전에 있다).

판단 없음 — 이미 계산된 응답의 저장·읽기뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import json
import zlib
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.models import Complex, Scenario, Snapshot, SnapshotView

__all__ = [
    "KINDS",
    "LIVE_BUILDERS",
    "NotInRevision",
    "NotMaterialized",
    "decode",
    "encode",
    "is_materialized",
    "materialize",
    "materialize_missing",
    "read",
    "scenario_key",
    "stored",
]

log = get_logger("app.snapshot_view")

KINDS: Final = (
    "dashboard",
    "complexes",
    "complex",
    "compare",
    "market",
    "changes",
    "sensitivity",
    "report",
    "report_diff",
)
LIVE_BUILDERS: Final = (
    "build_dashboard",
    "build_complexes",
    "build_details",
    "build_compare",
    "build_market",
    "build_changes",
    "build_sensitivity",
    "build_report",
    "build_report_diff",
)
"""실시간 계산 함수(이 모듈 이름 — 발행 리비전 읽기가 이것을 부르지 않음을 테스트가 막아 놓고 확인한다)."""


class NotMaterialized(LookupError):
    """발행 리비전인데 저장본이 하나도 없다(있으면 안 된다 — API 500 internal)."""


class NotInRevision(NotMaterialized):
    """발행 리비전에 그 종류·키·시나리오 저장본이 없다(발행 뒤 만든 시나리오·없는 생활권 — API 404)."""


# ====================================================================== 직렬화


def encode(obj: Any) -> tuple[bytes, str]:
    """JSON(키 순서 유지·한글 그대로) → (zlib 압축 본문, 압축 전 sha256)."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=True)
    raw = text.encode("utf-8")
    return zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest()


def decode(body: bytes) -> Any:
    return json.loads(zlib.decompress(body).decode("utf-8"))


def scenario_key(sc: Scenario | int | None) -> str:
    if sc is None:
        return ""
    return str(sc if isinstance(sc, int) else sc.id)


# ====================================================================== 읽기


def is_published(snap: Snapshot) -> bool:
    return snap.status == "published"


def stored(session: Session, snapshot_id: int, kind: str, *, key: str = "", scenario: str = "") -> Any | None:
    row = session.scalars(
        select(SnapshotView.body).where(
            SnapshotView.snapshot_id == snapshot_id,
            SnapshotView.kind == kind,
            SnapshotView.key == key,
            SnapshotView.scenario == scenario,
        )
    ).first()
    return decode(row) if row is not None else None


def is_materialized(session: Session, snapshot_id: int) -> bool:
    return (
        session.scalars(
            select(SnapshotView.id).where(SnapshotView.snapshot_id == snapshot_id).limit(1)
        ).first()
        is not None
    )


def read(
    session: Session,
    snap: Snapshot,
    kind: str,
    *,
    settings: Settings | None = None,
    scenario: Scenario | None = None,
    key: str = "",
    live: Callable[[], Any] | None = None,
) -> Any:
    """발행 리비전 = 저장본(없으면 ``NotMaterialized``), 그 밖 = ``live()``(없으면 그 종류의 실시간 계산 전체)."""
    if is_published(snap):
        got = stored(session, snap.id, kind, key=key, scenario=scenario_key(scenario))
        if got is None:
            if not is_materialized(session, snap.id):
                raise NotMaterialized(
                    f"발행 리비전 {snap.id} 의 저장본이 없다(마이그레이션 0010·publish 확인)"
                )
            raise NotInRevision(
                f"발행 리비전 {snap.id} 에 {kind}[{key or '-'}·시나리오 {scenario_key(scenario) or '-'}] 저장본 없음"
            )
        return got
    if live is not None:
        return live()
    return _build(kind, session, settings or get_settings(), snap, scenario, key)


# ====================================================================== 실시간 계산(발행 전 리비전 · materialize)


def build_dashboard(session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    from app.api.routers.snapshots import dashboard_body

    return dashboard_body(session, settings, snap, sc)


def build_complexes(session: Session, settings: Settings, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    from app.api.routers.snapshots import complexes_body

    return complexes_body(session, settings, snap, sc)


def build_details(
    session: Session, settings: Settings, snap: Snapshot, sc: Scenario, complexes: Sequence[Complex]
) -> dict[int, dict[str, Any]]:
    from app.api.routers.complexes import detail_bodies

    return detail_bodies(session, settings, snap, sc, complexes)


def build_compare(
    session: Session, settings: Settings, snap: Snapshot, sc: Scenario, complexes: Sequence[Complex]
) -> dict[str, Any]:
    from app.api.routers.analysis import compare_body

    return compare_body(session, settings, snap, sc, complexes)


def build_market(
    session: Session, settings: Settings, snap: Snapshot, living_area: str | None, sc: Scenario | None = None
) -> dict[str, Any]:
    from app.api.routers.market import market_body

    return market_body(session, settings, snap, living_area, sc)


def build_changes(session: Session, snap: Snapshot) -> dict[str, Any]:
    from app.api.routers.snapshots import changes_ledger

    return changes_ledger(session, snap)


def build_sensitivity(session: Session, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    from app.api.routers.analysis import sensitivity_body

    return sensitivity_body(session, snap, sc)


def build_report(
    session: Session,
    snap: Snapshot,
    sc: Scenario,
    cache: dict[Any, Any] | None = None,
    env: str | None = None,
) -> dict[str, Any]:
    from app.reports.data import report_payload_live

    return report_payload_live(session, snap.id, sc.id, cache=cache, env=env)


def build_report_diff(session: Session, snap: Snapshot, sc: Scenario) -> dict[str, Any]:
    from app.reports.diff import diff_digest_live

    return diff_digest_live(session, snap.id, sc)


def _build(
    kind: str, session: Session, settings: Settings, snap: Snapshot, sc: Scenario | None, key: str
) -> Any:
    g = globals()
    if kind == "dashboard":
        return g["build_dashboard"](session, settings, snap, _need(sc))
    if kind == "complexes":
        return g["build_complexes"](session, settings, snap, _need(sc))
    if kind == "market":
        return g["build_market"](session, settings, snap, key or None, sc)
    if kind == "changes":
        return g["build_changes"](session, snap)
    if kind == "sensitivity":
        return g["build_sensitivity"](session, snap, _need(sc))
    if kind == "report":
        return g["build_report"](session, snap, _need(sc))
    if kind == "report_diff":
        return g["build_report_diff"](session, snap, _need(sc))
    raise ValueError(f"실시간 계산 종류 아님: {kind}")


def _need(sc: Scenario | None) -> Scenario:
    if sc is None:
        raise ValueError("시나리오가 필요한 종류")
    return sc


def details(
    session: Session, snap: Snapshot, sc: Scenario, cx: Complex, *, settings: Settings | None = None
) -> dict[str, Any]:
    """단지 상세 1개 — 발행 리비전은 저장본, 그 밖은 실시간."""
    if is_published(snap):
        return dict(read(session, snap, "complex", scenario=sc, key=str(cx.id)))
    out: dict[str, Any] = globals()["build_details"](session, settings or get_settings(), snap, sc, [cx])[
        cx.id
    ]
    return out


def compare_parts(
    session: Session,
    snap: Snapshot,
    sc: Scenario,
    complexes: Sequence[Complex],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """비교 입력 — 발행 리비전은 저장본(그 리비전 단지 전부), 그 밖은 요청 단지만 실시간."""
    if is_published(snap):
        return dict(read(session, snap, "compare", scenario=sc))
    out: dict[str, Any] = globals()["build_compare"](session, settings or get_settings(), snap, sc, complexes)
    return out


# ====================================================================== materialize


def _scenarios(session: Session) -> list[Scenario]:
    return list(session.scalars(select(Scenario).order_by(Scenario.id)))


def _living_area_ids(session: Session, snap: Snapshot) -> list[str]:
    from app.models import Region

    region = session.get(Region, snap.region_id)
    return [
        str(a["id"]) for a in ((region.living_areas if region is not None else None) or []) if a.get("id")
    ]


def materialize(
    session: Session,
    snapshot_id: int,
    *,
    settings: Settings | None = None,
    replace: bool = False,
    kinds: Iterable[str] | None = None,
) -> int:
    """그 리비전의 저장본을 만든다(이미 있으면 그대로 — 발행 리비전은 불변). 넣은 행 수.

    ``replace=True`` 는 devseed·합성 도구(개발용 픽스처를 다시 쓰는 경우)만 쓴다. 호출자가 트랜잭션을 연다(publish 와
    같은 트랜잭션 — 실패하면 발행도 되돌아간다)."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    if is_materialized(session, snapshot_id):
        if not replace:
            return 0
        session.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
        session.flush()
    want = set(kinds) if kinds is not None else set(KINDS)
    # 출처 누락은 발행을 막지 않는다 — 저장본은 ENV=prod 규칙('확인 불가(출처 누락)' + 경고 로그)으로 만든다. dev 의
    # 500 contract_violation 은 발행 전 리비전의 실시간 GET 에서 드러난다(T13). 한 행의 출처 누락으로 리비전 전체가
    # 발행되지 않으면 화면이 옛 리비전에 묶인다
    cfg = (settings or get_settings()).model_copy(update={"env": "prod"})
    rows: list[SnapshotView] = []

    def put(kind: str, body: Any, *, key: str = "", scenario: str = "") -> None:
        data, sha = encode(body)
        rows.append(
            SnapshotView(
                snapshot_id=snapshot_id, kind=kind, key=key, scenario=scenario, body=data, sha256=sha
            )
        )

    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == snap.region_id).order_by(Complex.id))
    )
    cache: dict[Any, Any] = {}  # 시나리오와 무관한 보고서 단지 뷰(시나리오마다 다시 만들지 않는다)
    if "changes" in want:
        put("changes", build_changes(session, snap))
    las = _living_area_ids(session, snap)
    for sc in _scenarios(session):
        sk = scenario_key(sc)
        if "market" in want:  # 시나리오 × (전체 + 그 리비전 생활권별)
            put("market", build_market(session, cfg, snap, None, sc), scenario=sk)
            for la in las:
                put("market", build_market(session, cfg, snap, la, sc), key=la, scenario=sk)
        if "dashboard" in want:
            put("dashboard", build_dashboard(session, cfg, snap, sc), scenario=sk)
        if "complexes" in want:
            put("complexes", build_complexes(session, cfg, snap, sc), scenario=sk)
        if "sensitivity" in want:
            put("sensitivity", build_sensitivity(session, snap, sc), scenario=sk)
        if "compare" in want and complexes:
            put("compare", build_compare(session, cfg, snap, sc, complexes), scenario=sk)
        if "complex" in want and complexes:
            for cid, body in build_details(session, cfg, snap, sc, complexes).items():
                put("complex", body, key=str(cid), scenario=sk)
        if "report" in want:
            from app.reports.errors import ReportBlocked

            try:
                put("report", build_report(session, snap, sc, cache, env=cfg.env), scenario=sk)
            except ReportBlocked:
                # publish 는 contradicted 0 일 때만 부른다 — 여기 오는 것은 개발 도구(devseed 재생성)가 남은 contradicted 주장이
                # 있는 픽스처를 다시 쓸 때뿐이다. 보고서 저장본을 만들지 않는다(그 리비전 보고서 생성은 같은 검사로 거부된다)
                log.warning(
                    "snapshot_view.report_blocked", extra={"snapshot_id": snapshot_id, "scenario": sk}
                )
        if "report_diff" in want:
            put("report_diff", build_report_diff(session, snap, sc), scenario=sk)
    session.add_all(rows)
    session.flush()
    log.info(
        "snapshot_view.materialized",
        extra={"snapshot_id": snapshot_id, "rows": len(rows), "bytes": sum(len(r.body) for r in rows)},
    )
    return len(rows)


def materialize_missing(session: Session, *, settings: Settings | None = None) -> list[int]:
    """저장본이 없는 발행 리비전 전부(0010 이전 발행분)를 지금 한 번 materialize 한다. materialize 한 스냅샷 id."""
    done: list[int] = []
    for sid in session.scalars(
        select(Snapshot.id).where(Snapshot.status == "published").order_by(Snapshot.id)
    ):
        if not is_materialized(session, sid):
            materialize(session, sid, settings=settings)
            done.append(int(sid))
    return done
