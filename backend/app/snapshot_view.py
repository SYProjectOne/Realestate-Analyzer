"""발행 리비전 = 저장된 읽기 모델(materialized) — DECISIONS D13-1·**D14-1·D14-4·D14-5·D14-8·D14-9**, 계약 2026-10-09.11.

리비전 발행은 worker 잡(``snapshot.publish`` 처리 함수와 같은 ``publish_revision``)에서만 한다(D14-5 — API 요청 안에서
발행하지 않는다). 순서:

1. **계산**(읽기 전용 세션 1개 — SQLite WAL 읽기 트랜잭션 하나·Postgres REPEATABLE READ = 한 시점의 일관된 값):
   그 리비전을 메모리에서만 '발행됨'으로 보고(``PUBLISHING`` — DB 에는 쓰지 않는다, flush 금지 감시) 화면 응답 전부·
   보고서 입력·출처 서랍·주장 목록을 시나리오별로 만든다. 같은 계산 안의 반복 적재는 ``app.api.memo`` 로 한 번만.
2. **나눠 쓰기**: 짧은 트랜잭션 여러 개로 ``snapshot_view`` 행을 넣는다(쓰기 잠금 = 한 묶음 동안만).
3. **짧은 전환**: ``UPDATE snapshot SET status='published' WHERE status='ready'`` + 남은 contradicted 0 재확인 한 트랜잭션.
   끝날 때까지 이전 발행 리비전이 기본 화면이다(발행 전 리비전 GET 은 실시간).

| kind | key | scenario | 내용 |
| --- | --- | --- | --- |
| dashboard | '' | 시나리오 id | G1 대시보드 응답 |
| complexes | '' | 시나리오 id | G2 단지 행 전부(필터·정렬 키 포함) — 목록·CSV 는 이 행에 질의만 적용 |
| complex | 단지 id | 시나리오 id | G3 단지 상세 응답 |
| compare | '' | 시나리오 id | G4 비교 입력 |
| market | '' · 생활권 id | 시나리오 id | G6 시장 응답 |
| changes | '' | '' | 변경 피드 원장 |
| sensitivity | '' | 시나리오 id | C10 민감도 응답 |
| report | '' | 시나리오 id | 보고서 입력 데이터 |
| report_diff | '' | 시나리오 id | 리비전 diff 입력 |
| provenance | 'idx' · 'b<n>' | '' | **G3 출처 서랍**(D14-1): 저장본이 가리키는 출처 id 전부의 ``GET /provenance/{id}`` 응답을 해시 묶음(b<n>)으로 |
| claims | '' | '' | **주장 목록**(D14-1, m1): ``GET /snapshots/{sid}/claims`` 전체(상태 질의는 읽을 때) |

- 행마다 ``contract_version``·``sha256``(압축 전 JSON)을 갖고 **읽을 때 검증**한다(D14-4). 다르면 ``StoredViewMismatch``
  (500 ``stored_view_mismatch`` + 오류 로그) — 조용히 내보내지 않는다. 모양을 바꾸는 계약 변경은 저장본 변환 마이그레이션을
  함께 낸다(0011 = .10 → .11 식별 변환).
- 발행 리비전인데 그 종류 저장본이 아직 없으면 ``MaterializePending``(503 ``materialize_pending`` — 0010 이전 발행분·새 종류는
  ``python -m app.snapshot_view backfill``·worker 시작이 채운다, D14-9). 그 종류는 있는데 그 키·시나리오가 없으면
  ``NotInRevision``(404 — 발행 뒤 만든 시나리오·그 리비전에 없던 생활권·단지·출처).
- 출처 누락(T13)은 발행을 막지 않는다: 저장본은 ENV 와 무관하게 '확인 불가(출처 누락)' 라벨 + 경고 로그, 잡 통계
  ``missing_provenance`` 에 건수(D14-8). 발행 전 리비전 실시간 GET 은 dev 500 그대로.

판단 없음 — 이미 계산된 응답의 저장·읽기뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import zlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from sqlalchemy import delete, event, func, insert, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.protocols import CONTRACT_VERSION
from app.core.settings import Settings, get_settings
from app.models import Complex, Scenario, Snapshot, SnapshotView

__all__ = [
    "KINDS",
    "LIVE_BUILDERS",
    "PUBLISHING",
    "MaterializePending",
    "NotInRevision",
    "NotMaterialized",
    "PublishResult",
    "StoredViewMismatch",
    "backfill",
    "claims",
    "compute",
    "decode",
    "encode",
    "is_materialized",
    "kind_ready",
    "materialize",
    "materialize_missing",
    "provenance",
    "publish_revision",
    "read",
    "scenario_key",
    "stored",
    "write_rows",
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
    "provenance",
    "claims",
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
    "build_provenance",
    "build_claims",
)
"""실시간 계산 함수(이 모듈 이름 — 발행 리비전 읽기가 이것을 부르지 않음을 테스트가 막아 놓고 확인한다)."""

PROV_BUCKET: Final = 256
"""출처 서랍 묶음 하나의 평균 출처 수(1000 단지 ≈ 출처 3만 6천 → 묶음 약 140 행)."""
CHUNK_BYTES: Final = 2_000_000
"""나눠 쓰기 한 트랜잭션의 압축 본문 합 상한(쓰기 잠금 시간 — D14-5 '그동안 API 쓰기 잠금 1초 이하')."""
ZLIB_LEVEL: Final = 1

PUBLISHING: ContextVar[tuple[int, int] | None] = ContextVar("snapshot_view_publishing", default=None)
"""계산 중인 리비전 (snapshot_id, region_id) — 메모리에서만 '발행됨'(``views.latest_snapshot_id`` 가 발행 리비전으로 센다)."""


class NotMaterialized(LookupError):
    """발행 리비전인데 저장본이 아직 없다 — API 503 ``materialize_pending``(D14-9)."""


class MaterializePending(NotMaterialized):
    """그 종류의 저장본을 아직 만들지 않았다(0010 이전 발행분·계약 .11 새 종류 — backfill 대기)."""


class NotInRevision(NotMaterialized):
    """발행 리비전에 그 종류는 있는데 그 키·시나리오가 없다(발행 뒤 만든 시나리오·없는 생활권·출처 — API 404)."""


class StoredViewMismatch(RuntimeError):
    """저장본 sha256·계약 버전이 맞지 않는다 — API 500 ``stored_view_mismatch``(D14-4)."""


# ====================================================================== 직렬화


def _dumps(obj: Any) -> bytes:
    return json.dumps(
        obj, ensure_ascii=False, separators=(",", ":"), allow_nan=True, check_circular=False
    ).encode("utf-8")


def encode(obj: Any) -> tuple[bytes, str]:
    """JSON(키 순서 유지·한글 그대로) → (zlib 압축 본문, 압축 전 sha256)."""
    raw = _dumps(obj)
    return zlib.compress(raw, ZLIB_LEVEL), hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------- 시나리오 사이 같은 부분(저장 크기·발행 시간 — D14-5)

BASE_MARK: Final = "$base_scenario"
PATCH_MARK: Final = "$patch"
DEDUP_KINDS: Final = frozenset({"complex", "report", "compare", "complexes", "dashboard", "market"})
"""기본 시나리오 본문과 같은 부분을 다시 저장하지 않는 종류 — 행 = {BASE_MARK: 기본 시나리오, PATCH_MARK: 바뀐 부분}.
읽을 때(``stored``) 기본 시나리오 행에 바뀐 부분을 덮어 원래 본문(같은 키 순서·같은 바이트)으로 되살린다."""
_PATCH_DEPTH: Final = 4


def _diff(base: Any, body: Any, depth: int) -> dict[str, Any]:
    """body = apply(base, diff). 같은 키 순서의 dict 만 안으로 들어간다({"$p": {키: 하위}}), 그 밖은 값 통째({"$v": 값})."""
    if depth > 0 and type(base) is dict and type(body) is dict and list(base) == list(body):
        return {"$p": {k: _diff(base[k], v, depth - 1) for k, v in body.items() if v != base[k]}}
    return {"$v": body}


def _apply(base: Any, node: dict[str, Any]) -> Any:
    if "$v" in node:
        return node["$v"]
    out = dict(base)
    for k, sub in node["$p"].items():
        out[k] = _apply(base[k], sub)
    return out


def _is_patch(body: Any) -> bool:
    return type(body) is dict and len(body) == 2 and BASE_MARK in body and PATCH_MARK in body


def decode(body: bytes) -> Any:
    return json.loads(zlib.decompress(body).decode("utf-8"))


def _verified(snapshot_id: int, kind: str, key: str, body: bytes, sha: str, version: str) -> Any:
    """저장본 1행을 검증해 되살린다(D14-4). 계약 버전·sha256 이 다르면 ``StoredViewMismatch``."""
    return json.loads(_verified_raw(snapshot_id, kind, key, body, sha, version).decode("utf-8"))


def _verified_raw(snapshot_id: int, kind: str, key: str, body: bytes, sha: str, version: str) -> bytes:
    """검증한 압축 전 JSON 바이트."""
    where = f"snapshot_view[{snapshot_id}·{kind}·{key or '-'}]"
    if version != CONTRACT_VERSION:
        log.error(
            "snapshot_view.version_mismatch",
            extra={"snapshot_id": snapshot_id, "kind": kind, "stored": version, "contract": CONTRACT_VERSION},
        )
        raise StoredViewMismatch(f"{where} 계약 버전 {version or '없음'} ≠ {CONTRACT_VERSION}")
    try:
        raw = zlib.decompress(body)
    except zlib.error as exc:
        log.error("snapshot_view.corrupt", extra={"snapshot_id": snapshot_id, "kind": kind})
        raise StoredViewMismatch(f"{where} 본문을 풀 수 없다") from exc
    if hashlib.sha256(raw).hexdigest() != sha:
        log.error("snapshot_view.sha256_mismatch", extra={"snapshot_id": snapshot_id, "kind": kind})
        raise StoredViewMismatch(f"{where} sha256 불일치")
    return raw


def scenario_key(sc: Scenario | int | None) -> str:
    if sc is None:
        return ""
    return str(sc if isinstance(sc, int) else sc.id)


# ====================================================================== 읽기


def is_published(snap: Snapshot) -> bool:
    return snap.status == "published"


def stored(session: Session, snapshot_id: int, kind: str, *, key: str = "", scenario: str = "") -> Any | None:
    """저장본 1행(검증 후). 없으면 None."""
    row = session.execute(
        select(SnapshotView.body, SnapshotView.sha256, SnapshotView.contract_version).where(
            SnapshotView.snapshot_id == snapshot_id,
            SnapshotView.kind == kind,
            SnapshotView.key == key,
            SnapshotView.scenario == scenario,
        )
    ).first()
    if row is None:
        return None
    got = _verified(snapshot_id, kind, key, row[0], row[1], row[2])
    if _is_patch(got):  # 기본 시나리오 본문 + 바뀐 부분(두 행 모두 검증)
        base = stored(session, snapshot_id, kind, key=key, scenario=str(got[BASE_MARK]))
        if base is None or _is_patch(base):
            log.error("snapshot_view.patch_base_missing", extra={"snapshot_id": snapshot_id, "kind": kind})
            raise StoredViewMismatch(
                f"snapshot_view[{snapshot_id}·{kind}·{key or '-'}] 기본 시나리오 행 없음"
            )
        return _apply(base, {"$p": got[PATCH_MARK]})
    return got


def is_materialized(session: Session, snapshot_id: int) -> bool:
    return (
        session.scalars(
            select(SnapshotView.id).where(SnapshotView.snapshot_id == snapshot_id).limit(1)
        ).first()
        is not None
    )


def kind_ready(session: Session, snapshot_id: int, kind: str) -> bool:
    """그 리비전에 그 종류 저장본이 있는가(한 행이라도)."""
    return (
        session.scalars(
            select(SnapshotView.id)
            .where(SnapshotView.snapshot_id == snapshot_id, SnapshotView.kind == kind)
            .limit(1)
        ).first()
        is not None
    )


def _missing(session: Session, snap: Snapshot, kind: str, key: str, scenario: str) -> NotMaterialized:
    if not kind_ready(session, snap.id, kind):
        return MaterializePending(
            f"발행 리비전 {snap.id} 의 {kind} 저장본을 아직 만들지 않았다(backfill 대기 — 잠시 뒤 다시)"
        )
    return NotInRevision(
        f"발행 리비전 {snap.id} 에 {kind}[{key or '-'}·시나리오 {scenario or '-'}] 저장본 없음"
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
    """발행 리비전 = 저장본(없으면 ``MaterializePending``·``NotInRevision``), 그 밖 = ``live()``(없으면 그 종류의 실시간 계산)."""
    if is_published(snap):
        sk = scenario_key(scenario)
        got = stored(session, snap.id, kind, key=key, scenario=sk)
        if got is None:
            raise _missing(session, snap, kind, key, sk)
        return got
    if live is not None:
        return live()
    return _build(kind, session, settings or get_settings(), snap, scenario, key)


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


def claims(session: Session, snap: Snapshot) -> list[dict[str, Any]]:
    """주장 목록 전체(D14-1·m1) — 발행 리비전은 저장본, 그 밖은 지금 값."""
    if is_published(snap):
        return list(read(session, snap, "claims"))
    out: list[dict[str, Any]] = globals()["build_claims"](session, snap)
    return out


def _bucket(prov_id: str, n: int) -> str:
    return f"b{zlib.crc32(prov_id.encode('utf-8')) % max(n, 1)}"


def provenance(session: Session, snap: Snapshot, prov_id: str) -> dict[str, Any] | None:
    """발행 리비전 저장본의 출처 서랍 1건(D14-1). 그 리비전에 없으면 None. 저장본이 아직 없으면 ``MaterializePending``."""
    idx = stored(session, snap.id, "provenance", key="idx")
    if idx is None:
        raise _missing(session, snap, "provenance", "idx", "")
    bucket = stored(session, snap.id, "provenance", key=_bucket(prov_id, int(idx.get("buckets") or 1)))
    if bucket is None:
        return None
    got = bucket.get(prov_id)
    return dict(got) if isinstance(got, dict) else None


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


def build_provenance(session: Session, prov_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    from app.api.routers.complexes import provenance_bodies

    return provenance_bodies(session, prov_ids)


def build_claims(session: Session, snap: Snapshot) -> list[dict[str, Any]]:
    from app.api.routers.claims import claims_body

    return claims_body(session, snap)


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
    if kind == "claims":
        return g["build_claims"](session, snap)
    raise ValueError(f"실시간 계산 종류 아님: {kind}")


def _need(sc: Scenario | None) -> Scenario:
    if sc is None:
        raise ValueError("시나리오가 필요한 종류")
    return sc


# ====================================================================== 계산(materialize)


@dataclass(slots=True)
class ViewRow:
    kind: str
    key: str
    scenario: str
    body: bytes
    sha256: str


@dataclass
class Computed:
    rows: list[ViewRow] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    prov_ids: set[str] = field(default_factory=set)


def _scenarios(session: Session) -> list[Scenario]:
    return list(session.scalars(select(Scenario).order_by(Scenario.id)))


def _living_area_ids(session: Session, snap: Snapshot) -> list[str]:
    from app.models import Region

    region = session.get(Region, snap.region_id)
    return [
        str(a["id"]) for a in ((region.living_areas if region is not None else None) or []) if a.get("id")
    ]


_PROV_SKIP_KINDS: Final = frozenset({"report", "report_diff", "provenance"})
_PROV_RE: Final = re.compile(rb'"prov":"((?:fp|sc|st|jl|hc|rd|cs)_[0-9A-Za-z_.:-]+)"')


def _collect_prov(raw: bytes, acc: set[str]) -> None:
    """응답 JSON 바이트 안의 출처 id 전부(Fact ``prov``) — 출처 서랍 저장 대상(D14-1). JSON 문자열 안의 따옴표는 이스케이프
    되므로 ``"prov":"…"`` 는 실제 키뿐이다."""
    acc.update(m.decode("ascii") for m in _PROV_RE.findall(raw))


@contextmanager
def _missing_counter() -> Iterator[list[int]]:
    from app.api.facts import MISSING_COUNT

    box = [0]
    token = MISSING_COUNT.set(box)
    try:
        yield box
    finally:
        MISSING_COUNT.reset(token)


def compute(
    session: Session,
    snap: Snapshot,
    *,
    settings: Settings | None = None,
    kinds: Iterable[str] | None = None,
    collect_prov: bool = False,
    scenario_part: tuple[int, int] | None = None,
) -> Computed:
    """그 리비전의 저장본 행을 계산만 한다(DB 쓰기 없음 — 호출자가 ``write_rows``·세션에 넣는다).

    ``scenario_part=(i, n)`` = 시나리오 목록의 i 번째 몫(``[i::n]``)만 행으로 낸다(나눠 계산). 기본 시나리오는 늘 계산한다(다른
    시나리오 행이 기본 시나리오 본문 + 바뀐 부분이라) — 몫이 아니면 행만 내지 않는다.

    출처 누락은 ENV=prod 규칙('확인 불가(출처 누락)' + 경고 로그)으로 만들고 건수를 ``stats.missing_provenance`` 에(D14-8)."""
    from app.api import memo

    t0 = time.perf_counter()
    want = set(kinds) if kinds is not None else set(KINDS)
    cfg = (settings or get_settings()).model_copy(update={"env": "prod"})
    out = Computed()
    prov_ids = out.prov_ids
    timing: dict[str, float] = {}

    base_sk: str | None = None
    base_bodies: dict[tuple[str, str], Any] = {}

    emit_sk: set[str] | None = None

    def put(kind: str, body: Any, *, key: str = "", scenario: str = "") -> None:
        t = time.perf_counter()
        stored_body = body
        if kind in DEDUP_KINDS and scenario == base_sk:
            base_bodies[(kind, key)] = body
        if scenario and emit_sk is not None and scenario not in emit_sk:
            return  # 이 몫이 아닌 시나리오(기본 시나리오 — 바뀐 부분의 바탕으로만 계산했다)
        if kind in DEDUP_KINDS and scenario:
            if scenario == base_sk:
                pass
            elif (kind, key) in base_bodies:
                node = _diff(base_bodies[(kind, key)], body, _PATCH_DEPTH)
                if "$p" in node:
                    stored_body = {BASE_MARK: base_sk, PATCH_MARK: node["$p"]}
        raw = _dumps(stored_body)
        if kind not in _PROV_SKIP_KINDS and ("provenance" in want or collect_prov):
            _collect_prov(raw, prov_ids)
        out.rows.append(
            ViewRow(kind, key, scenario, zlib.compress(raw, ZLIB_LEVEL), hashlib.sha256(raw).hexdigest())
        )
        timing["encode"] = timing.get("encode", 0.0) + time.perf_counter() - t

    def timed(name: str, fn: Callable[..., Any], *args: Any) -> Any:
        t = time.perf_counter()
        try:
            return fn(*args)
        finally:
            timing[name] = timing.get(name, 0.0) + time.perf_counter() - t

    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == snap.region_id).order_by(Complex.id))
    )
    cache: dict[Any, Any] = {}  # 시나리오와 무관한 보고서 단지 뷰(시나리오마다 다시 만들지 않는다)
    with _missing_counter() as missing, memo.active():
        if "changes" in want:
            put("changes", timed("changes", build_changes, session, snap))
        if "claims" in want:
            put("claims", timed("claims", build_claims, session, snap))
        las = _living_area_ids(session, snap)
        all_sc = _scenarios(session)
        if scenario_part is not None:
            i, n = scenario_part
            emit_sk = {scenario_key(x) for x in all_sc[i::n]}
        for sc in all_sc:
            sk = scenario_key(sc)
            if base_sk is None:
                base_sk = sk
            if emit_sk is not None and sk not in emit_sk and sk != base_sk:
                continue
            if "market" in want:  # 시나리오 × (전체 + 그 리비전 생활권별)
                put("market", timed("market", build_market, session, cfg, snap, None, sc), scenario=sk)
                for la in las:
                    put(
                        "market",
                        timed("market", build_market, session, cfg, snap, la, sc),
                        key=la,
                        scenario=sk,
                    )
            if "dashboard" in want:
                put(
                    "dashboard",
                    timed("dashboard", build_dashboard, session, cfg, snap, sc),
                    scenario=sk,
                )
            if "complexes" in want:
                put(
                    "complexes",
                    timed("complexes", build_complexes, session, cfg, snap, sc),
                    scenario=sk,
                )
            if "sensitivity" in want:
                put(
                    "sensitivity",
                    timed("sensitivity", build_sensitivity, session, snap, sc),
                    scenario=sk,
                )
            if "compare" in want and complexes:
                put(
                    "compare",
                    timed("compare", build_compare, session, cfg, snap, sc, complexes),
                    scenario=sk,
                )
            if "complex" in want and complexes:
                bodies = timed("complex", build_details, session, cfg, snap, sc, complexes)
                for cid, body in bodies.items():
                    put("complex", body, key=str(cid), scenario=sk)
            if "report" in want:
                from app.reports.errors import ReportBlocked

                try:
                    put(
                        "report",
                        timed("report", build_report, session, snap, sc, cache, cfg.env),
                        scenario=sk,
                    )
                except ReportBlocked:
                    # 발행은 contradicted 0 일 때만 — 여기 오는 것은 개발 도구(devseed 재생성)가 contradicted 주장이 남은
                    # 픽스처를 다시 쓸 때뿐이다. 보고서 저장본을 만들지 않는다(그 리비전 보고서는 같은 검사로 거부된다)
                    log.warning(
                        "snapshot_view.report_blocked", extra={"snapshot_id": snap.id, "scenario": sk}
                    )
            if "report_diff" in want:
                put(
                    "report_diff",
                    timed("report_diff", build_report_diff, session, snap, sc),
                    scenario=sk,
                )
        if "provenance" in want:
            if not (set(KINDS) - _PROV_SKIP_KINDS) <= want:
                # 출처 서랍만 다시 만들 때(backfill): 그 리비전에 이미 저장된 응답에서 출처 id 를 모은다
                for body, sha, ver, kind, key in session.execute(
                    select(
                        SnapshotView.body,
                        SnapshotView.sha256,
                        SnapshotView.contract_version,
                        SnapshotView.kind,
                        SnapshotView.key,
                    ).where(
                        SnapshotView.snapshot_id == snap.id,
                        SnapshotView.kind.not_in(sorted(_PROV_SKIP_KINDS)),
                    )
                ):
                    _collect_prov(_verified_raw(snap.id, kind, key, body, sha, ver), prov_ids)
            for kind, key, body in timed("provenance", _provenance_bodies_rows, session, prov_ids):
                put(kind, body, key=key)
        out.stats["missing_provenance"] = missing[0]
    out.stats.update(
        rows=len(out.rows),
        bytes=sum(len(r.body) for r in out.rows),
        provenance_ids=len(prov_ids),
        compute_s=round(time.perf_counter() - t0, 3),
        timing_s={k: round(v, 3) for k, v in sorted(timing.items())},
    )
    return out


def _provenance_bodies_rows(
    session: Session, prov_ids: set[str], *, done: dict[str, Any] | None = None
) -> list[tuple[str, str, Any]]:
    """출처 서랍 저장본 행(kind, key, 본문): 색인 'idx' + 해시 묶음 'b<n>'. 서랍 안 '충돌 출처'(conflicts[].id)도 서랍으로
    연다(``provenance_bodies`` 가 같은 묶음 행을 함께 만든다). ``done`` = 다른 프로세스가 같은 시점에서 이미 만든 서랍."""
    bodies = dict(done or {})
    bodies.update(build_provenance(session, {p for p in prov_ids if p not in bodies}))
    n_buckets = max(1, -(-len(bodies) // PROV_BUCKET))
    buckets: dict[str, dict[str, Any]] = {}
    for pid in sorted(bodies):
        buckets.setdefault(_bucket(pid, n_buckets), {})[pid] = bodies[pid]
    out: list[tuple[str, str, Any]] = [("provenance", "idx", {"buckets": n_buckets, "count": len(bodies)})]
    out += [("provenance", bkey, buckets[bkey]) for bkey in sorted(buckets)]
    return out


# ---------------------------------------------------------------- 큰 리비전: 프로세스 나눠 계산(D14-5 — 1000 단지 × 시나리오 5 = 15초)

PARALLEL_MIN_CELLS: int = 2000
"""단지 수 × 시나리오 수가 이 값 이상이면 종류를 프로세스로 나눠 계산한다(작은 리비전은 한 프로세스 — 시작 비용 1~2초)."""
PARALLEL_GROUPS: tuple[tuple[tuple[str, ...], tuple[int, int] | None], ...] = (
    (("report",), None),
    (("complex", "provenance"), None),
    (("compare", "report_diff"), None),
)
"""다른 프로세스에서 계산할 (종류 묶음, 시나리오 몫) — 나머지 종류는 이 프로세스. 묶음에 'provenance' 가 있으면 그 자식이 자기
응답이 가리키는 출처 서랍까지 만든다(단지 상세 = 출처 id 대부분) — 이 프로세스는 남은 출처만. 시나리오 몫(i, n)을 주면 그
종류를 시나리오로 더 나눌 수 있다(측정: 보고서를 둘로 나누면 프로세스 경합으로 오히려 느려 지금은 쓰지 않는다). 0개면 늘 한 프로세스."""


def _snapshot_source(engine: Engine, tmp: Path) -> tuple[str, Any]:
    """모든 프로세스가 같은 한 시점을 읽게 한다. SQLite = DB 파일의 일관된 사본(backup API — 다른 연결의 쓰기와 무관한 한
    시점), Postgres = 이 트랜잭션의 스냅샷을 내보내 자식이 ``SET TRANSACTION SNAPSHOT`` 으로 같은 시점을 읽는다(pg_dump -j 와
    같은 방식). 반환 (자식이 읽을 URL, Postgres 면 부모 연결 — 자식이 끝날 때까지 열어 둔다)."""
    import sqlite3

    url = engine.url
    if engine.dialect.name == "sqlite":
        src_path = url.database
        if not src_path or src_path == ":memory:":
            raise RuntimeError("메모리 SQLite 는 나눠 계산하지 않는다")
        copy = tmp / "snapshot.db"
        src = sqlite3.connect(src_path)
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return f"sqlite:///{copy.as_posix()}", None
    conn = engine.connect().execution_options(isolation_level="REPEATABLE READ")
    conn.begin()
    token = conn.exec_driver_sql("SELECT pg_export_snapshot()").scalar_one()
    return url.render_as_string(hide_password=False), (conn, str(token))


def _part_session(url: str, settings: Settings, pg_token: str | None) -> tuple[Session, Engine]:
    from app.core.db import make_engine

    engine = make_engine(url, settings=settings)
    if pg_token is None:
        return Session(bind=engine), engine
    conn = engine.connect().execution_options(isolation_level="REPEATABLE READ")
    conn.begin()
    conn.exec_driver_sql(f"SET TRANSACTION SNAPSHOT '{pg_token}'")
    return Session(bind=conn), engine


def _compute_part(
    url: str,
    settings: Settings,
    snapshot_id: int,
    now: str,
    kinds: tuple[str, ...],
    pg_token: str | None,
    scenario_part: tuple[int, int] | None = None,
) -> tuple[list[tuple[str, str, str, bytes, str]], list[str], dict[str, Any], dict[str, Any]]:
    """자식 프로세스: 같은 시점(``_snapshot_source``)을 읽어 ``kinds`` 저장본 행과 출처 id 를 계산한다(쓰기 없음). 'provenance' 가
    있으면 그 출처 id 의 서랍 본문도(같은 계산 — ``build_provenance``)."""
    from app.api import memo
    from app.core.settings import set_settings

    cfg = settings.model_copy(update={"database_url": url})
    set_settings(cfg)
    rs, engine = _part_session(url, cfg, pg_token)
    bodies: dict[str, Any] = {}
    try:
        snap = rs.get(Snapshot, snapshot_id)
        if snap is None:
            raise LookupError(f"snapshot {snapshot_id} 없음(자식)")
        with _as_published(rs, snap, now):
            c = compute(
                rs,
                snap,
                settings=cfg,
                kinds=tuple(k for k in kinds if k != "provenance"),
                collect_prov=True,
                scenario_part=scenario_part,
            )
            if "provenance" in kinds:
                t = time.perf_counter()
                with memo.active():
                    bodies = build_provenance(rs, c.prov_ids)
                c.stats.setdefault("timing_s", {})["provenance"] = round(time.perf_counter() - t, 3)
    finally:
        rs.rollback()
        rs.close()
        engine.dispose()
    return (
        [(r.kind, r.key, r.scenario, r.body, r.sha256) for r in c.rows],
        sorted(c.prov_ids),
        c.stats,
        bodies,
    )


_POOL: Any = None
_POOL_SIZE = 0


def _pool(size: int) -> Any:
    """자식 프로세스 풀(spawn) — 한 번 띄워 계속 쓴다(worker 상주: 시작 비용·import 를 발행마다 치르지 않는다)."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    global _POOL, _POOL_SIZE
    if _POOL is None or size > _POOL_SIZE:
        if _POOL is not None:
            _POOL.shutdown(wait=False, cancel_futures=True)
        _POOL = ProcessPoolExecutor(max_workers=size, mp_context=multiprocessing.get_context("spawn"))
        _POOL_SIZE = size
        import atexit

        atexit.register(_reset_pool)  # 인터프리터 종료 전에 정리(종료 중 풀 콜백 경고 방지)
    return _POOL


def _reset_pool() -> None:
    global _POOL, _POOL_SIZE
    if _POOL is not None:
        _POOL.shutdown(wait=True, cancel_futures=True)
    _POOL, _POOL_SIZE = None, 0


def _warm_child() -> int:
    """자식 프로세스가 무거운 모듈을 미리 읽는다(첫 발행이 import 시간을 치르지 않게)."""
    import os

    import app.api.routers.analysis
    import app.api.routers.complexes
    import app.api.routers.market
    import app.api.routers.snapshots
    import app.reports.data  # noqa: F401

    return os.getpid()


def warm_pool() -> int:
    """worker 시작 때 발행 자식 프로세스를 띄워 둔다(D14-5). 나눠 계산하지 않는 설정이면 0. 띄운 프로세스 수."""
    if not PARALLEL_GROUPS:
        return 0
    ex = _pool(len(PARALLEL_GROUPS))
    pids = {f.result(timeout=120) for f in [ex.submit(_warm_child) for _ in range(len(PARALLEL_GROUPS) * 2)]}
    return len(pids)


def _cells(session: Session, snap: Snapshot) -> int:
    n_cx = session.scalar(
        select(func.count()).select_from(Complex).where(Complex.region_id == snap.region_id)
    )
    n_sc = session.scalar(select(func.count()).select_from(Scenario))
    return int(n_cx or 0) * int(n_sc or 0)


def _compute_parallel(
    engine: Engine,
    snapshot_id: int,
    now: str,
    settings: Settings | None,
    groups: tuple[tuple[tuple[str, ...], tuple[int, int] | None], ...],
) -> Computed:
    """종류 묶음을 자식 프로세스에서, 나머지 종류·출처 서랍을 이 프로세스에서 계산한다(모두 같은 한 시점)."""
    import shutil
    import tempfile

    from app.api import memo

    cfg = settings or get_settings()
    tmp = Path(tempfile.mkdtemp(prefix="publish-"))
    pg_conn: Any = None
    t0 = time.perf_counter()
    try:
        url, pg = _snapshot_source(engine, tmp)
        token: str | None = None
        if pg is not None:
            pg_conn, token = pg
            rs = Session(bind=pg_conn)
            read_engine = engine
        else:
            from app.core.db import make_engine

            read_engine = make_engine(url, settings=cfg)
            rs = Session(bind=read_engine)
        copy_s = time.perf_counter() - t0
        mine = tuple(k for k in KINDS if k != "provenance" and all(k not in g for g, _p in groups))
        ex = _pool(len(groups))
        futs = [ex.submit(_compute_part, url, cfg, snapshot_id, now, g, token, part) for g, part in groups]
        snap = rs.get(Snapshot, snapshot_id)
        if snap is None:
            raise LookupError(f"snapshot {snapshot_id} 없음")
        with _as_published(rs, snap, now):
            own = compute(rs, snap, settings=cfg, kinds=mine, collect_prov=True)
            parts = [f.result() for f in futs]
            prov_ids = set(own.prov_ids)
            done: dict[str, Any] = {}
            for _rows, ids, _st, bodies in parts:
                prov_ids.update(ids)
                done.update(bodies)
            t = time.perf_counter()
            with memo.active():
                prov_rows = _provenance_bodies_rows(rs, prov_ids, done=done)
            prov_s = time.perf_counter() - t
        out = Computed(rows=list(own.rows), prov_ids=prov_ids)
        for rows, _ids, _st, _b in parts:
            out.rows += [ViewRow(*r) for r in rows]
        for kind, key, body in prov_rows:
            data, sha = encode(body)
            out.rows.append(ViewRow(kind, key, "", data, sha))
        missing = int(own.stats.get("missing_provenance") or 0) + sum(
            int(st.get("missing_provenance") or 0) for _r, _i, st, _b in parts
        )
        timing = dict(own.stats.get("timing_s") or {})
        for _r, _i, st, _b in parts:
            for k, v in (st.get("timing_s") or {}).items():
                timing[k] = round(timing.get(k, 0.0) + float(v), 3)
        timing["provenance"] = round(timing.get("provenance", 0.0) + prov_s, 3)
        out.stats = {
            "missing_provenance": missing,
            "rows": len(out.rows),
            "bytes": sum(len(r.body) for r in out.rows),
            "provenance_ids": len(prov_ids),
            "compute_s": round(time.perf_counter() - t0, 3),
            "timing_s": dict(sorted(timing.items())),
            "parallel": {
                "processes": 1 + len(groups),
                "snapshot_copy_s": round(copy_s, 3),
                "parts": [
                    {"kinds": list(g), "compute_s": st.get("compute_s")}
                    for (g, _p), (_r, _i, st, _b) in zip(groups, parts, strict=True)
                ]
                + [{"kinds": list(mine), "compute_s": own.stats.get("compute_s")}],
            },
        }
        rs.rollback()
        rs.close()
        if pg is None:
            read_engine.dispose()
        return out
    finally:
        if pg_conn is not None:
            pg_conn.rollback()
            pg_conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def _forbid_flush(session: Session, _ctx: Any, _instances: Any) -> None:
    raise RuntimeError("저장본 계산 세션은 쓰지 않는다(D14-5 — 쓰기 잠금 없이 계산)")


@contextmanager
def _as_published(session: Session, snap: Snapshot, now: str) -> Iterator[None]:
    """계산 동안만 그 리비전을 메모리에서 '발행됨'으로 본다(DB 에는 쓰지 않는다 — flush 하면 예외)."""
    token = PUBLISHING.set((snap.id, snap.region_id))
    event.listen(session, "before_flush", _forbid_flush)
    try:
        with session.no_autoflush:
            snap.status = "published"
            snap.published_at = now
            yield
    finally:
        event.remove(session, "before_flush", _forbid_flush)
        PUBLISHING.reset(token)


def _read_session(bind: Engine | Connection) -> Session:
    """일관된 한 시점의 읽기 세션(SQLite WAL 읽기 트랜잭션 · Postgres REPEATABLE READ)."""
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name == "postgresql":
        return Session(bind=engine.execution_options(isolation_level="REPEATABLE READ"))
    return Session(bind=engine)


# ====================================================================== 쓰기


@dataclass
class WriteStats:
    chunks: int = 0
    rows: int = 0
    max_lock_s: float = 0.0
    total_write_s: float = 0.0


def _chunks(rows: Sequence[ViewRow]) -> Iterator[Sequence[ViewRow]]:
    start, size = 0, 0
    for i, r in enumerate(rows):
        size += len(r.body)
        if size >= CHUNK_BYTES:
            yield rows[start : i + 1]
            start, size = i + 1, 0
    if start < len(rows):
        yield rows[start:]


def write_rows(engine: Engine, snapshot_id: int, rows: Sequence[ViewRow]) -> WriteStats:
    """짧은 트랜잭션 여러 개로 넣는다(묶음 하나 = 쓰기 잠금 한 번, ``CHUNK_BYTES``)."""
    st = WriteStats()
    for chunk in _chunks(rows):
        t = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(
                insert(SnapshotView),
                [
                    {
                        "snapshot_id": snapshot_id,
                        "kind": r.kind,
                        "key": r.key,
                        "scenario": r.scenario,
                        "body": r.body,
                        "sha256": r.sha256,
                        "contract_version": CONTRACT_VERSION,
                    }
                    for r in chunk
                ],
            )
        dt = time.perf_counter() - t
        st.chunks += 1
        st.rows += len(chunk)
        st.max_lock_s = max(st.max_lock_s, dt)
        st.total_write_s += dt
    return st


def _add_rows(session: Session, snapshot_id: int, rows: Sequence[ViewRow]) -> None:
    session.execute(
        insert(SnapshotView),
        [
            {
                "snapshot_id": snapshot_id,
                "kind": r.kind,
                "key": r.key,
                "scenario": r.scenario,
                "body": r.body,
                "sha256": r.sha256,
                "contract_version": CONTRACT_VERSION,
            }
            for r in rows
        ],
    )


# ====================================================================== 발행(worker 전용)


@dataclass
class PublishResult:
    published: bool
    contradicted: int = 0
    reason: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)


def _can_split(engine: Engine) -> bool:
    if engine.dialect.name == "postgresql":
        return True
    db = engine.url.database
    return engine.dialect.name == "sqlite" and bool(db) and db != ":memory:"


def publish_revision(
    bind: Engine | Connection, snapshot_id: int, *, now: str, settings: Settings | None = None
) -> PublishResult:
    """ready 리비전을 발행한다(D14-5): 계산(읽기 전용) → 나눠 쓰기 → 짧은 전환. worker 잡에서만 부른다.

    호출자는 열린 쓰기 트랜잭션이 없어야 한다(``scheduler.snapshots.publish`` 가 먼저 commit 한다). 실패하면 넣던 행을
    지운다(발행 전 리비전에 남은 행은 다음 시도 첫 단계도 지운다)."""
    from app.judge.claims import remaining_contradicted

    engine = bind.engine if isinstance(bind, Connection) else bind
    t0 = time.perf_counter()
    rs = _read_session(engine)
    try:
        snap = rs.get(Snapshot, snapshot_id)
        if snap is None:
            raise LookupError(f"snapshot {snapshot_id} 없음")
        if snap.status == "published":
            return PublishResult(True, 0, "이미 발행됨")
        if snap.status != "ready" or snap.degraded:
            return PublishResult(False, 0, f"status={snap.status} degraded={bool(snap.degraded)}")
        n = len(remaining_contradicted(rs, snapshot_id))
        if n:
            return PublishResult(False, n, f"contradicted {n}건")
        parallel = bool(PARALLEL_GROUPS) and _cells(rs, snap) >= PARALLEL_MIN_CELLS and _can_split(engine)
        if not parallel:
            with _as_published(rs, snap, now):
                computed = compute(rs, snap, settings=settings)
    finally:
        rs.rollback()
        rs.close()
    if parallel:
        try:
            computed = _compute_parallel(engine, snapshot_id, now, settings, PARALLEL_GROUPS)
        except Exception as exc:
            log.error(
                "snapshot_view.parallel_failed",
                extra={"snapshot_id": snapshot_id, "error": type(exc).__name__},
            )
            _reset_pool()
            rs = _read_session(engine)
            try:
                snap = rs.get(Snapshot, snapshot_id)
                assert snap is not None
                with _as_published(rs, snap, now):
                    computed = compute(rs, snap, settings=settings)
                computed.stats["parallel_failed"] = type(exc).__name__
            finally:
                rs.rollback()
                rs.close()
    with engine.begin() as conn:  # 이전 실패가 남긴 행(발행 전 리비전) 정리
        conn.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
    try:
        ws = write_rows(engine, snapshot_id, computed.rows)
        t = time.perf_counter()
        with Session(bind=engine) as s, s.begin():
            n = len(remaining_contradicted(s, snapshot_id))
            done = 0
            if not n:
                res = s.execute(
                    update(Snapshot)
                    .where(Snapshot.id == snapshot_id, Snapshot.status == "ready")
                    .values(status="published", published_at=now)
                )
                done = int(getattr(res, "rowcount", 0) or 0)
            if not done:
                s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
        flip_s = time.perf_counter() - t
    except BaseException:
        with engine.begin() as conn:
            conn.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
        raise
    stats = {
        **computed.stats,
        "write_chunks": ws.chunks,
        "write_max_lock_s": round(ws.max_lock_s, 3),
        "write_total_s": round(ws.total_write_s, 3),
        "flip_s": round(flip_s, 3),
        "total_s": round(time.perf_counter() - t0, 3),
    }
    if n:
        return PublishResult(False, n, f"contradicted {n}건(계산 중 생김)", stats)
    if not done:
        return PublishResult(False, 0, "계산 중 리비전 상태가 바뀌었다", stats)
    log.info(
        "snapshot_view.published",
        extra={"snapshot_id": snapshot_id, **{k: v for k, v in stats.items() if k != "timing_s"}},
    )
    return PublishResult(True, 0, None, stats)


# ====================================================================== 개발 도구·backfill


def materialize(
    session: Session,
    snapshot_id: int,
    *,
    settings: Settings | None = None,
    replace: bool = False,
    kinds: Iterable[str] | None = None,
) -> int:
    """이미 발행된 리비전의 저장본을 호출자 세션에 넣는다(devseed·합성 도구·backfill). 넣은 행 수.

    ``kinds`` 를 주면 그 종류 중 아직 없는 것만(backfill). ``replace=True`` 는 devseed·합성 도구만(개발용 픽스처를 다시 쓰는
    경우). 발행은 ``publish_revision``(worker)만 한다."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    if replace:
        session.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
        session.flush()
        want = set(kinds) if kinds is not None else set(KINDS)
    else:
        present = set(
            session.scalars(
                select(SnapshotView.kind).where(SnapshotView.snapshot_id == snapshot_id).distinct()
            )
        )
        want = (set(kinds) if kinds is not None else set(KINDS)) - present
    if not want:
        return 0
    computed = compute(session, snap, settings=settings, kinds=want)
    _add_rows(session, snapshot_id, computed.rows)
    session.flush()
    log.info(
        "snapshot_view.materialized",
        extra={"snapshot_id": snapshot_id, **{k: v for k, v in computed.stats.items() if k != "timing_s"}},
    )
    return len(computed.rows)


def materialize_missing(session: Session, *, settings: Settings | None = None) -> list[int]:
    """저장본 종류가 빠진 발행 리비전 전부를 채운다(0010 이전 발행분·계약 .11 새 종류 — D14-9). 채운 스냅샷 id."""
    done: list[int] = []
    for sid in list(
        session.scalars(select(Snapshot.id).where(Snapshot.status == "published").order_by(Snapshot.id))
    ):
        if materialize(session, int(sid), settings=settings):
            done.append(int(sid))
    return done


def backfill(engine: Engine | None = None, *, settings: Settings | None = None) -> dict[str, Any]:
    """멱등 backfill(D14-9): 행 단위 사람 확인 → 의미 묶음(m14) + 저장본 종류가 빠진 발행 리비전 채우기.

    스냅샷마다 계산(읽기) → 짧은 트랜잭션으로 쓰기. worker 시작과 ``python -m app.snapshot_view backfill`` 이 부른다."""
    from app.core.db import get_engine

    s = settings or get_settings()
    eng = engine or get_engine(s)
    out: dict[str, Any] = {"snapshots": [], "rows": 0, "human_checks_migrated": 0}
    try:
        from app.api.demotion import migrate_row_human_checks
    except ImportError:  # pragma: no cover - 사람 확인 이전 함수가 없는 빌드
        migrate_row_human_checks = None  # type: ignore[assignment]
    if migrate_row_human_checks is not None:
        with Session(bind=eng) as ses, ses.begin():
            out["human_checks_migrated"] = int(migrate_row_human_checks(ses) or 0)
    with Session(bind=eng) as ses:
        sids = [
            int(i)
            for i in ses.scalars(
                select(Snapshot.id).where(Snapshot.status == "published").order_by(Snapshot.id)
            )
        ]
    for sid in sids:
        rs = _read_session(eng)
        try:
            present = set(
                rs.scalars(select(SnapshotView.kind).where(SnapshotView.snapshot_id == sid).distinct())
            )
            want = set(KINDS) - present
            if not want:
                continue
            snap = rs.get(Snapshot, sid)
            assert snap is not None
            computed = compute(rs, snap, settings=s, kinds=want)
        finally:
            rs.rollback()
            rs.close()
        if (
            not computed.rows
        ):  # 만들 것이 없다(보고서가 거부된 리비전의 report 등) — 채운 리비전으로 세지 않는다
            continue
        write_rows(eng, sid, computed.rows)
        out["snapshots"].append(sid)
        out["rows"] += len(computed.rows)
        out.setdefault("missing_provenance", 0)
        out["missing_provenance"] += int(computed.stats.get("missing_provenance") or 0)
    if out["snapshots"] or out["human_checks_migrated"]:
        log.info("snapshot_view.backfill", extra={"snapshots": len(out["snapshots"]), "rows": out["rows"]})
    return out


def pending_count(session: Session) -> int:
    """저장본 종류가 빠진 발행 리비전 수(운영 점검)."""
    n = 0
    for sid in session.scalars(select(Snapshot.id).where(Snapshot.status == "published")):
        have = session.scalar(
            select(func.count(func.distinct(SnapshotView.kind))).where(SnapshotView.snapshot_id == sid)
        )
        if int(have or 0) < len(KINDS):
            n += 1
    return n


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.snapshot_view", description="발행 리비전 저장본 도구(D14-9)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backfill", help="빠진 저장본 종류 채우기 + 행 단위 사람 확인 이전(멱등)")
    args = p.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "backfill":
        res = backfill()
        sys.stdout.write(
            f"backfill: snapshots={res['snapshots']} rows={res['rows']} "
            f"human_checks_migrated={res['human_checks_migrated']} missing_provenance={res.get('missing_provenance', 0)}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
