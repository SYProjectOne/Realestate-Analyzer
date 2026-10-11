"""발행 리비전 = 저장된 읽기 모델(materialized) — DECISIONS D13-1·D14-1·D14-4·D14-5·D14-8·D14-9·**D15-2·D15-3·D15-6**, 계약 2026-10-09.12.

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

- 행마다 ``shape_version``(저장 모양 버전, 정수 — D15-3)·``sha256``(압축 전 JSON)을 갖고 **읽을 때 검증**한다(D14-4).
  다르면 ``StoredViewMismatch``(500 ``stored_view_mismatch`` + 오류 로그) — 조용히 내보내지 않는다. 계약 문자열
  (``contract_version``)은 기록만 한다(모양이 그대로인 계약 변경에 발행 GET 이 500 이 되지 않는다, m9).
- **완료 표식**(D15-3, ``snapshot_view_unit``): (리비전, kind, 시나리오) 단위마다 그 단위의 마지막 쓰기와 같은 트랜잭션에
  ``done``·``rows`` 를 쓴다. 표식이 없거나 미완(done=false·실제 행 수 < rows)이면 그 단위는 ``MaterializePending``(503
  ``materialize_pending`` — ``python -m app.snapshot_view backfill``·worker 시작이 그 단위의 빠진 행만 다시 만든다, 리비전마다
  따로 실패). 단위가 완료인데 그 키가 없거나, 그 kind 의 다른 시나리오는 있는데 이 시나리오 표식이 없으면 ``NotInRevision``
  (404 — 발행 뒤 만든 시나리오·그 리비전에 없던 생활권·단지·출처).
- 출처 서랍(D15-2)은 저장된 **모든 본문**(모든 시나리오·모든 kind·시나리오 patch 행의 ``{"$v": …}`` 포함)의 prov id 와 접수
  근거 ``raw_document_id`` → ``rd_<id>`` 를 모은다.
- 발행은 리비전마다 하나만 돈다(D15-6 single-flight: ``snapshot.publish_lease`` 조건부 UPDATE). 정리 DELETE 는 '발행 전'
  상태 조건을 붙인다. 계산이 읽은 시점에 보이던 후속 발행 잡(``follow_up``)은 전환 트랜잭션에서 '포함됨'(done)으로 닫는다 —
  보이지 않던 잡(계산 중에 들어온 변경)은 남아 새 리비전으로 이어 발행한다.
- 출처 누락(T13)은 발행을 막지 않는다: 저장본은 ENV 와 무관하게 '확인 불가(출처 누락)' 라벨 + 경고 로그, 잡 통계
  ``missing_provenance`` 에 건수(D14-8). 발행 전 리비전 실시간 GET 은 dev 500 그대로.

판단 없음 — 이미 계산된 응답의 저장·읽기뿐이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
import sys
import time
import zlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import delete, event, exists, func, insert, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.protocols import CONTRACT_VERSION
from app.core.settings import Settings, get_settings
from app.models import Complex, JobRun, Scenario, Snapshot, SnapshotView, SnapshotViewUnit

__all__ = [
    "KINDS",
    "LIVE_BUILDERS",
    "PUBLISHING",
    "SHAPE_VERSION",
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
    "unit_ready",
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

NO_SCENARIO_KINDS: Final = frozenset({"changes", "claims", "provenance"})
"""시나리오와 무관한 kind(단위 = (리비전, kind, ''))."""
SCENARIO_KINDS: Final = tuple(k for k in KINDS if k not in NO_SCENARIO_KINDS)
SHAPE_VERSION: Final = 1
"""저장 모양 버전(D15-3) — 저장 kind 의 JSON 모양이 바뀔 때만 올리고 저장본 변환 마이그레이션을 함께 낸다(D14-4). 계약 문자열과
무관하다(계약 버전만 바뀐 변경에 발행 GET 이 500 이 되지 않는다, R3 7차 m9)."""
LEASE_TTL_S: Final = 900.0
"""발행 임대가 이 시간보다 오래되면(보유 worker 사망) 다른 발행이 넘겨받는다(D15-6). 보유자가 잡이면 그 잡이 running 이
아닐 때도 넘겨받는다."""

PROV_BUCKET: Final = 256
"""출처 서랍 묶음 하나의 평균 출처 수(1000 단지 ≈ 출처 3만 6천 → 묶음 약 140 행)."""
CHUNK_BYTES: Final = 500_000
"""나눠 쓰기 한 트랜잭션의 압축 본문 합 상한(쓰기 잠금 시간 — D14-5 '그동안 API 쓰기 잠금 1초 이하'). R3g: 2MB → 0.5MB(부하 측정에서 2MB 묶음 1.36초·1MB 묶음 1.21초 — CPU 경합)."""
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


def _diff(base: Any, body: Any, depth: int, cache: dict[int, bytes] | None = None) -> dict[str, Any]:
    """body = apply(base, diff). 같은 키 순서의 dict 만 안으로 들어간다({"$p": {키: 하위}}), 그 밖은 값 통째({"$v": 값}).

    '같다'(patch 에서 빼도 된다)는 저장 바이트가 같다는 뜻이다(R3 7차 m8: ``==`` 는 ``1``·``1.0``·``true``·키 순서가 다른
    dict 를 같다고 본다). 빠른 ``==`` 로 거른 뒤 문자열·None 이 아니면 형까지 구분하는 구조 바이트(``_strict``)로 확인한다 —
    기본 시나리오 쪽 바이트는 ``cache``(id → 바이트, 기본 본문이 살아 있는 동안)로 한 번만 만든다."""
    if depth > 0 and type(base) is dict and type(body) is dict and list(base) == list(body):
        out: dict[str, Any] = {}
        for k, v in body.items():
            b = base[k]
            if v == b and _same_bytes(b, v, cache):
                continue
            out[k] = _diff(b, v, depth - 1, cache)
        return {"$p": out}
    return {"$v": body}


def _same_bytes(base: Any, value: Any, cache: dict[int, bytes] | None) -> bool:
    """``base == value`` 인 두 값의 저장 바이트도 같은가(형·키 순서까지)."""
    if type(base) is not type(value):
        return False
    if value is None or type(value) in (str, int, bool):
        return True
    if type(value) is float:
        return repr(base) == repr(value)  # 0.0 == -0.0 이지만 바이트는 다르다
    if cache is None:
        return _strict(base) == _strict(value)
    key = id(base)
    got = cache.get(key)
    if got is None:
        got = cache[key] = _strict(base)
    return got == _strict(value)


def _patch(base: Any, body: Any, cache: dict[int, bytes] | None = None) -> dict[str, Any] | None:
    """기본 시나리오 본문에 덮을 바뀐 부분(되살리면 원래 본문과 같은 저장 바이트). dict 가 아니면 None(본문 통째)."""
    node = _diff(base, body, _PATCH_DEPTH, cache)
    return dict(node["$p"]) if "$p" in node else None


def _strict(obj: Any) -> bytes:
    """형까지 구분하는 구조 바이트(pickle). 같으면 JSON 저장 바이트도 같다(int·float·bool·키 순서 구분). JSON 직렬화보다
    빠르다(D14-5 발행 30초)."""
    # memo 가 켜져 있어 객체 공유가 다르면 같은 구조도 다른 바이트가 될 수 있다 — 그때는 '다르다'로 patch 에 통째로 들어갈 뿐
    # (저장 크기만 조금 늘고 되살린 바이트는 늘 원래와 같다). Pickler 객체를 만들지 않는 편이 작은 값 수십만 개에서 빠르다
    return pickle.dumps(obj, protocol=5)


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


def _verified(snapshot_id: int, kind: str, key: str, body: bytes, sha: str, shape: int | None) -> Any:
    """저장본 1행을 검증해 되살린다(D14-4·D15-3). 저장 모양 버전·sha256 이 다르면 ``StoredViewMismatch``."""
    return json.loads(_verified_raw(snapshot_id, kind, key, body, sha, shape).decode("utf-8"))


def _verified_raw(snapshot_id: int, kind: str, key: str, body: bytes, sha: str, shape: int | None) -> bytes:
    """검증한 압축 전 JSON 바이트."""
    where = f"snapshot_view[{snapshot_id}·{kind}·{key or '-'}]"
    if shape != SHAPE_VERSION:
        log.error(
            "snapshot_view.shape_mismatch",
            extra={"snapshot_id": snapshot_id, "kind": kind, "stored": shape, "expected": SHAPE_VERSION},
        )
        raise StoredViewMismatch(f"{where} 저장 모양 버전 {shape} ≠ {SHAPE_VERSION}")
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
        select(SnapshotView.body, SnapshotView.sha256, SnapshotView.shape_version).where(
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
        base_sk = str(got[BASE_MARK])
        base = stored(session, snapshot_id, kind, key=key, scenario=base_sk)
        if base is None or _is_patch(base):
            if base is None and not unit_ready(session, snapshot_id, kind, base_sk):
                raise MaterializePending(
                    f"발행 리비전 {snapshot_id} 의 {kind}[시나리오 {base_sk}] 저장본이 미완(backfill 대기)"
                )
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


def _unit_row(session: Session, snapshot_id: int, kind: str, scenario: str) -> tuple[bool, int] | None:
    row = session.execute(
        select(SnapshotViewUnit.done, SnapshotViewUnit.rows).where(
            SnapshotViewUnit.snapshot_id == snapshot_id,
            SnapshotViewUnit.kind == kind,
            SnapshotViewUnit.scenario == scenario,
        )
    ).first()
    return None if row is None else (bool(row[0]), int(row[1] or 0))


def _unit_count(session: Session, snapshot_id: int, kind: str, scenario: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SnapshotView)
            .where(
                SnapshotView.snapshot_id == snapshot_id,
                SnapshotView.kind == kind,
                SnapshotView.scenario == scenario,
            )
        )
        or 0
    )


def unit_ready(session: Session, snapshot_id: int, kind: str, scenario: str = "") -> bool:
    """(리비전, kind, 시나리오) 완료 표식이 있는가(D15-3 — 그 단위의 마지막 쓰기와 같은 트랜잭션에 쓴 ``done``)."""
    got = _unit_row(session, snapshot_id, kind, scenario)
    return got is not None and got[0]


def kind_ready(session: Session, snapshot_id: int, kind: str) -> bool:
    """그 리비전의 그 종류 단위가 모두 완료인가(표식이 하나 이상 있고 미완 표식이 없다 — D15-3)."""
    states = list(
        session.scalars(
            select(SnapshotViewUnit.done).where(
                SnapshotViewUnit.snapshot_id == snapshot_id, SnapshotViewUnit.kind == kind
            )
        )
    )
    return bool(states) and all(bool(x) for x in states)


def _require_unit(session: Session, snap: Snapshot, kind: str, scenario: str) -> int:
    """발행 리비전 단위가 완료가 아니면 503(미완)·404(그 kind 의 다른 시나리오는 있는데 이 시나리오 없음). 완료면 표식 rows."""
    got = _unit_row(session, snap.id, kind, scenario)
    if got is not None and got[0]:
        return got[1]
    if (
        got is None
        and scenario
        and kind not in NO_SCENARIO_KINDS
        and not _unit_count(session, snap.id, kind, scenario)
    ):
        # 표식도 행도 없는 시나리오만 '발행 뒤 만든 시나리오'(404). 행이 있는데 표식이 없으면 미완(D16-2·m3 — 503)
        other = session.scalars(
            select(SnapshotViewUnit.id)
            .where(
                SnapshotViewUnit.snapshot_id == snap.id,
                SnapshotViewUnit.kind == kind,
                SnapshotViewUnit.done.is_(True),
            )
            .limit(1)
        ).first()
        if other is not None:  # 그 리비전 발행 뒤 만든 시나리오(D13-1)
            raise NotInRevision(
                f"발행 리비전 {snap.id} 에 시나리오 {scenario} 의 {kind} 저장본 없음(발행 뒤 만든 시나리오)"
            )
    raise MaterializePending(
        f"발행 리비전 {snap.id} 의 {kind}[시나리오 {scenario or '-'}] 저장본이 미완(backfill 대기 — 잠시 뒤 다시)"
    )


def _missing(
    session: Session, snap: Snapshot, kind: str, key: str, scenario: str, rows: int
) -> NotMaterialized:
    """완료 단위에 그 키가 없다 — 단위 행 수가 표식보다 적으면(행이 지워졌다) 미완 503, 아니면 그 리비전에 없는 키 404."""
    if _unit_count(session, snap.id, kind, scenario) < rows:
        return MaterializePending(
            f"발행 리비전 {snap.id} 의 {kind}[시나리오 {scenario or '-'}] 저장본 행이 모자란다(backfill 대기)"
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
        sk = "" if kind in NO_SCENARIO_KINDS else scenario_key(scenario)
        rows = _require_unit(session, snap, kind, sk)
        got = stored(session, snap.id, kind, key=key, scenario=sk)
        if got is None:
            raise _missing(session, snap, kind, key, sk, rows)
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
    rows = _require_unit(session, snap, "provenance", "")
    idx = stored(session, snap.id, "provenance", key="idx")
    if idx is None:
        raise _missing(session, snap, "provenance", "idx", "", rows)
    bucket = stored(session, snap.id, "provenance", key=_bucket(prov_id, int(idx.get("buckets") or 1)))
    if bucket is None:
        if _unit_count(session, snap.id, "provenance", "") < rows:
            raise MaterializePending(
                f"발행 리비전 {snap.id} 의 출처 서랍 저장본 행이 모자란다(backfill 대기)"
            )
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


Unit = tuple[str, str]
"""저장본 단위 (kind, 시나리오 키 — 시나리오 무관 kind 는 '')."""


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
    units: list[Unit] = field(default_factory=list)
    """계산한 단위(행이 0개인 단위 포함 — 보고서가 거부된 리비전의 report 등) — 완료 표식 대상(D15-3)."""
    followups: list[int] = field(default_factory=list)
    """계산이 읽은 시점에 보이던 후속 발행 잡(D15-6) — 전환 트랜잭션에서 '포함됨'으로 닫는다."""


def _scenarios(session: Session) -> list[Scenario]:
    return list(session.scalars(select(Scenario).order_by(Scenario.id)))


def _living_area_ids(session: Session, snap: Snapshot) -> list[str]:
    from app.models import Region

    region = session.get(Region, snap.region_id)
    return [
        str(a["id"]) for a in ((region.living_areas if region is not None else None) or []) if a.get("id")
    ]


_PROV_SKIP_KINDS: Final = frozenset({"provenance"})
"""출처 id 를 모으지 않는 kind — 출처 서랍 자신뿐(D15-2: 그 밖의 모든 kind·모든 시나리오)."""
_PROV_RE: Final = re.compile(rb'"prov":(?:\{"\$v":)?"((?:fp|sc|st|jl|hc|rd|cs)_[0-9A-Za-z_.:-]+)"')
"""Fact ``prov`` — 시나리오 patch 행의 바뀐 잎 ``"prov":{"$v":"st_2"}``(R3 7차 M1)도."""
_RAW_RE: Final = re.compile(rb'"raw_document_id":(?:\{"\$v":)?(\d+)')
"""접수 근거 원문(G3 '접수 근거 원문' — 화면이 ``rd_<raw_document_id>`` 로 연다, D15-2·m7)."""


def _collect_prov(raw: bytes, acc: set[str]) -> None:
    """응답 JSON 바이트 안의 출처 id 전부(Fact ``prov`` + 접수 근거 ``raw_document_id`` → ``rd_``) — 출처 서랍 저장 대상
    (D14-1·D15-2). JSON 문자열 안의 따옴표는 이스케이프되므로 ``"prov":…`` 는 실제 키뿐이다."""
    acc.update(m.decode("ascii") for m in _PROV_RE.findall(raw))
    acc.update(f"rd_{m.decode('ascii')}" for m in _RAW_RE.findall(raw))


@contextmanager
def _missing_counter() -> Iterator[list[int]]:
    from app.api.facts import MISSING_COUNT

    box = [0]
    token = MISSING_COUNT.set(box)
    try:
        yield box
    finally:
        MISSING_COUNT.reset(token)


def _stored_prov_ids(session: Session, snapshot_id: int, acc: set[str]) -> None:
    """그 리비전에 이미 저장된 본문(출처 서랍 제외, 모든 시나리오·patch 행)에서 출처 id 를 모은다."""
    for body, sha, shape, kind, key in session.execute(
        select(
            SnapshotView.body,
            SnapshotView.sha256,
            SnapshotView.shape_version,
            SnapshotView.kind,
            SnapshotView.key,
        ).where(SnapshotView.snapshot_id == snapshot_id, SnapshotView.kind.not_in(sorted(_PROV_SKIP_KINDS)))
    ):
        _collect_prov(_verified_raw(snapshot_id, kind, key, body, sha, shape), acc)


def stored_drawers(session: Session, snapshot_id: int) -> dict[str, Any]:
    """그 리비전에 저장된 출처 서랍 본문 전부(묶음 행 — 색인 제외). backfill 이 서랍을 다시 쓸 때 이미 있던 서랍은 바이트
    그대로 둔다(발행 순간 값)."""
    out: dict[str, Any] = {}
    for body, sha, shape, key in session.execute(
        select(SnapshotView.body, SnapshotView.sha256, SnapshotView.shape_version, SnapshotView.key).where(
            SnapshotView.snapshot_id == snapshot_id,
            SnapshotView.kind == "provenance",
            SnapshotView.key != "idx",
        )
    ):
        got = _verified(snapshot_id, "provenance", key, body, sha, shape)
        if isinstance(got, dict):
            out.update(got)
    return out


def _visible_followups(session: Session, snap: Snapshot) -> list[int]:
    """이 계산이 읽는 시점에 보이는 같은 지역의 queued 후속 발행 잡(D15-6) — 그 잡을 등록한 쓰기가 이 계산에 들어 있다."""
    region_snaps = {
        int(i): (str(a), int(r or 1))
        for i, a, r in session.execute(
            select(Snapshot.id, Snapshot.asof_date, Snapshot.revision).where(
                Snapshot.region_id == snap.region_id
            )
        )
    }
    me = (snap.asof_date, int(snap.revision or 1))
    out: list[int] = []
    for jid, payload in session.execute(
        select(JobRun.id, JobRun.payload).where(
            JobRun.job_name == "snapshot.publish", JobRun.status == "queued"
        )
    ):
        p = payload or {}
        target = p.get("snapshot_id")
        if (
            p.get("follow_up")
            and isinstance(target, int)
            and target in region_snaps
            and region_snaps[target] <= me
        ):
            out.append(int(jid))
    return sorted(out)


def compute(
    session: Session,
    snap: Snapshot,
    *,
    settings: Settings | None = None,
    kinds: Iterable[str] | None = None,
    units: Iterable[Unit] | None = None,
    dedup: bool = True,
    extra_prov_ids: Iterable[str] = (),
    reuse_drawers: bool = False,
) -> Computed:
    """그 리비전의 저장본 행을 계산만 한다(DB 쓰기 없음 — 호출자가 ``write_rows``·세션에 넣는다).

    ``kinds``·``units`` 로 계산할 단위를 고른다(없으면 전부 — 발행). 일부만 계산하면 출처 서랍은 이미 저장된 본문의 출처 id 도
    모으고(``_stored_prov_ids``), ``reuse_drawers`` 면 이미 저장된 서랍 본문은 그대로 쓴다(backfill — 발행 순간 값 유지).
    ``dedup=False`` 는 시나리오 patch 없이 본문 통째(backfill 이 일부 단위만 다시 만들 때 — 기본 시나리오 행과 무관).
    출처 누락은 ENV=prod 규칙('확인 불가(출처 누락)' + 경고 로그)으로 만들고 건수를 ``stats.missing_provenance`` 에(D14-8)."""
    from app.api import memo

    t0 = time.perf_counter()
    kind_set = set(kinds) if kinds is not None else set(KINDS)
    unit_set = set(units) if units is not None else None
    partial = kinds is not None or units is not None
    cfg = (settings or get_settings()).model_copy(update={"env": "prod"})
    out = Computed()
    prov_ids = out.prov_ids
    prov_ids.update(extra_prov_ids)
    timing: dict[str, float] = {}

    def wanted(kind: str, sk: str = "") -> bool:
        if kind not in kind_set:
            return False
        return unit_set is None or (kind, sk) in unit_set

    base_sk: str | None = None
    base_bodies: dict[tuple[str, str], Any] = {}
    strict_cache: dict[int, bytes] = {}  # 기본 시나리오 하위 값의 구조 바이트(id — base_bodies 가 살려 둔다)

    def put(kind: str, body: Any, *, key: str = "", scenario: str = "") -> None:
        t = time.perf_counter()
        stored_body = body
        if dedup and kind in DEDUP_KINDS and scenario:
            if scenario == base_sk:
                base_bodies[(kind, key)] = body
            elif (kind, key) in base_bodies:
                patch = _patch(base_bodies[(kind, key)], body, strict_cache)
                if patch is not None:
                    stored_body = {BASE_MARK: base_sk, PATCH_MARK: patch}
        raw = _dumps(stored_body)
        if kind not in _PROV_SKIP_KINDS:
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

    def unit(kind: str, sk: str = "") -> bool:
        if not wanted(kind, sk):
            return False
        out.units.append((kind, sk))
        return True

    out.followups = _visible_followups(session, snap)
    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == snap.region_id).order_by(Complex.id))
    )
    cache: dict[Any, Any] = {}  # 시나리오와 무관한 보고서 단지 뷰(시나리오마다 다시 만들지 않는다)
    with _missing_counter() as missing, memo.active():
        if unit("changes"):
            put("changes", timed("changes", build_changes, session, snap))
        if unit("claims"):
            put("claims", timed("claims", build_claims, session, snap))
        las = _living_area_ids(session, snap)
        all_sc = _scenarios(session)
        for sc in all_sc:
            sk = scenario_key(sc)
            if base_sk is None:
                base_sk = sk
            if unit("market", sk):  # 시나리오 × (전체 + 그 리비전 생활권별)
                put("market", timed("market", build_market, session, cfg, snap, None, sc), scenario=sk)
                for la in las:
                    put(
                        "market",
                        timed("market", build_market, session, cfg, snap, la, sc),
                        key=la,
                        scenario=sk,
                    )
            if unit("dashboard", sk):
                put(
                    "dashboard",
                    timed("dashboard", build_dashboard, session, cfg, snap, sc),
                    scenario=sk,
                )
            if unit("complexes", sk):
                put(
                    "complexes",
                    timed("complexes", build_complexes, session, cfg, snap, sc),
                    scenario=sk,
                )
            if unit("sensitivity", sk):
                put(
                    "sensitivity",
                    timed("sensitivity", build_sensitivity, session, snap, sc),
                    scenario=sk,
                )
            if unit("compare", sk) and complexes:
                put(
                    "compare",
                    timed("compare", build_compare, session, cfg, snap, sc, complexes),
                    scenario=sk,
                )
            if unit("complex", sk) and complexes:
                bodies = timed("complex", build_details, session, cfg, snap, sc, complexes)
                for cid, body in bodies.items():
                    put("complex", body, key=str(cid), scenario=sk)
            if unit("report", sk):
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
            if unit("report_diff", sk):
                put(
                    "report_diff",
                    timed("report_diff", build_report_diff, session, snap, sc),
                    scenario=sk,
                )
        if unit("provenance"):
            if partial:
                # 일부 단위만 다시 만들 때(backfill): 그 리비전에 이미 저장된 본문(모든 시나리오·patch 행)의 출처 id 도 모은다
                _stored_prov_ids(session, snap.id, prov_ids)
            keep = stored_drawers(session, snap.id) if reuse_drawers else {}
            for kind, key, body in timed("provenance", _provenance_bodies_rows, session, prov_ids, keep):
                put(kind, body, key=key)
        out.stats["missing_provenance"] = missing[0]
    out.stats.update(
        rows=len(out.rows),
        bytes=sum(len(r.body) for r in out.rows),
        provenance_ids=len(prov_ids),
        units=len(out.units),
        compute_s=round(time.perf_counter() - t0, 3),
        timing_s={k: round(v, 3) for k, v in sorted(timing.items())},
    )
    return out


def _provenance_bodies_rows(
    session: Session, prov_ids: set[str], keep: dict[str, Any] | None = None
) -> list[tuple[str, str, Any]]:
    """출처 서랍 저장본 행(kind, key, 본문): 색인 'idx' + 해시 묶음 'b<n>'. 서랍 안 '충돌 출처'(conflicts[].id)도 서랍으로
    연다(``provenance_bodies`` 가 같은 묶음 행을 함께 만든다). ``keep`` 에 있는 서랍은 다시 만들지 않고 그 본문을 쓴다."""
    kept = dict(keep or {})
    bodies = dict(kept)
    todo = {p for p in prov_ids if p not in kept}
    if todo:
        bodies.update({k: v for k, v in build_provenance(session, todo).items() if k not in kept})
    n_buckets = max(1, -(-len(bodies) // PROV_BUCKET))
    buckets: dict[str, dict[str, Any]] = {}
    for pid in sorted(bodies):
        buckets.setdefault(_bucket(pid, n_buckets), {})[pid] = bodies[pid]
    out: list[tuple[str, str, Any]] = [("provenance", "idx", {"buckets": n_buckets, "count": len(bodies)})]
    out += [("provenance", bkey, buckets[bkey]) for bkey in sorted(buckets)]
    return out


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


def _row_dicts(snapshot_id: int, rows: Sequence[ViewRow]) -> list[dict[str, Any]]:
    return [
        {
            "snapshot_id": snapshot_id,
            "kind": r.kind,
            "key": r.key,
            "scenario": r.scenario,
            "body": r.body,
            "sha256": r.sha256,
            "contract_version": CONTRACT_VERSION,
            "shape_version": SHAPE_VERSION,
        }
        for r in rows
    ]


def _mark(conn: Connection | Session, snapshot_id: int, unit: Unit, rows: int, *, done: bool = True) -> None:
    """완료 표식 쓰기(있으면 고치고 없으면 넣는다) — 호출자의 트랜잭션 안(그 단위의 마지막 쓰기와 같이, D15-3)."""
    kind, scenario = unit
    res = conn.execute(
        update(SnapshotViewUnit)
        .where(
            SnapshotViewUnit.snapshot_id == snapshot_id,
            SnapshotViewUnit.kind == kind,
            SnapshotViewUnit.scenario == scenario,
        )
        .values(done=done, rows=rows, shape_version=SHAPE_VERSION)
        .execution_options(synchronize_session=False)
    )
    if not int(getattr(res, "rowcount", 0) or 0):
        conn.execute(
            insert(SnapshotViewUnit).values(
                snapshot_id=snapshot_id,
                kind=kind,
                scenario=scenario,
                rows=rows,
                done=done,
                shape_version=SHAPE_VERSION,
            )
        )


@contextmanager
def write_connection(engine: Engine) -> Iterator[Connection]:
    """저장본 쓰기·전환용 연결 하나. SQLite 면 이 연결의 WAL 자동 체크포인트를 끄고(끝나면 되돌린 뒤 쓰기 잠금 없이 PASSIVE
    체크포인트) — 저장본 수 MB 를 쓰는 동안 커밋 안에서 체크포인트(WAL → DB 복사·fsync)가 돌면 그 커밋(쓰기 잠금)이 부하에서
    수 초가 됐다(R3g D14-5 측정: 묶음 3.0s·전환 1.7s → 0.02~0.08s)."""
    with engine.connect() as conn:
        raw: Any = conn.connection.dbapi_connection if engine.dialect.name == "sqlite" else None
        if raw is not None:  # 자동 커밋(isolation_level None) — BEGIN 없이 PRAGMA
            raw.execute("PRAGMA wal_autocheckpoint=0")
        try:
            yield conn
        finally:
            if conn.in_transaction():
                conn.rollback()
            if raw is not None:
                raw.execute("PRAGMA wal_autocheckpoint=1000")
                raw.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()


def write_rows(
    bind: Engine | Connection,
    snapshot_id: int,
    rows: Sequence[ViewRow],
    *,
    finish: dict[Unit, int] | None = None,
) -> WriteStats:
    """짧은 트랜잭션 여러 개로 넣는다(묶음 하나 = 쓰기 잠금 한 번, ``CHUNK_BYTES``).

    ``finish`` = 끝낼 단위 → 그 단위의 최종 행 수: 단위마다 **그 단위의 마지막 행이 든 묶음 트랜잭션**에 완료 표식을 쓴다
    (D15-3). 이번에 쓸 행이 없는 단위는 마지막 묶음(행이 아예 없으면 따로 한 트랜잭션)에서. 행은 단위별로 이어져 있어야 한다
    (``compute`` 의 순서). ``bind`` 가 엔진이면 ``write_connection`` 하나로 쓴다."""
    if isinstance(bind, Engine):
        with write_connection(bind) as conn:
            return write_rows(conn, snapshot_id, rows, finish=finish)
    conn = bind
    st = WriteStats()
    todo = dict(finish or {})
    last: dict[Unit, int] = {}
    for i, r in enumerate(rows):
        last[(r.kind, r.scenario)] = i
    pos = 0
    chunks = list(_chunks(rows))
    for n, chunk in enumerate(chunks):
        t = time.perf_counter()
        end = pos + len(chunk)
        with conn.begin():
            conn.execute(insert(SnapshotView), _row_dicts(snapshot_id, chunk))
            for u, total in list(todo.items()):
                at = last.get(u)
                if (at is not None and pos <= at < end) or (at is None and n == len(chunks) - 1):
                    _mark(conn, snapshot_id, u, total)
                    del todo[u]
        pos = end
        dt = time.perf_counter() - t
        st.chunks += 1
        st.rows += len(chunk)
        st.max_lock_s = max(st.max_lock_s, dt)
        st.total_write_s += dt
    if todo:  # 쓸 행이 없었다(빈 단위만)
        with conn.begin():
            for u, total in todo.items():
                _mark(conn, snapshot_id, u, total)
    return st


def _unit_totals(computed: Computed) -> dict[Unit, int]:
    totals: dict[Unit, int] = dict.fromkeys(computed.units, 0)
    for r in computed.rows:
        totals[(r.kind, r.scenario)] = totals.get((r.kind, r.scenario), 0) + 1
    return totals


def _add_rows(session: Session, snapshot_id: int, rows: Sequence[ViewRow]) -> None:
    if rows:
        session.execute(insert(SnapshotView), _row_dicts(snapshot_id, rows))


def _purge_unpublished(conn: Connection, snapshot_id: int, lease: str | None = None) -> None:
    """발행 전 리비전에 남은 저장본·표식(실패한 시도의 찌꺼기)만 지운다 — **상태 조건**(D15-6·m1): 그 사이 다른 발행이
    리비전을 published 로 바꿨으면 아무것도 지우지 않는다. **임대 조건**(D16-3·R3 8차 m4): ``lease`` 를 주면 그 임대를 아직
    들고 있을 때만 지운다(멈췄던 이전 보유자가 깨어나 넘겨받은 새 보유자의 저장본을 지우지 않는다)."""
    cond = [Snapshot.id == snapshot_id, Snapshot.status != "published"]
    if lease is not None:
        cond.append(Snapshot.publish_lease == lease)
    unpublished = exists().where(*cond)
    conn.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id, unpublished))
    conn.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == snapshot_id, unpublished))


# ====================================================================== 발행 single-flight (D15-6)


def _lease_stale(conn: Connection, value: str, holder: str) -> bool:
    who, _, ts = value.rpartition("|")
    if who == holder:  # 같은 잡이 다시 돈다(worker 사망 → stale 회수 → 재실행)
        return True
    try:
        age = time.time() - float(ts)
    except ValueError:
        return True
    if age > LEASE_TTL_S:
        return True
    if who.startswith("job:") and who[4:].isdigit():
        status = conn.execute(select(JobRun.status).where(JobRun.id == int(who[4:]))).scalar()
        return status != "running"
    return False


def acquire_lease(engine: Engine, snapshot_id: int, holder: str) -> str | None:
    """발행 임대(조건부 UPDATE — 비교 후 교체). 얻으면 임대 값, 다른 발행이 들고 있으면 None."""
    mine = f"{holder[:60]}|{time.time():.0f}"
    with engine.connect() as conn:
        cur = conn.execute(select(Snapshot.publish_lease).where(Snapshot.id == snapshot_id)).scalar()
        stale = cur is None or _lease_stale(conn, str(cur), holder[:60])
        conn.rollback()
    if not stale:
        return None
    cond = Snapshot.publish_lease.is_(None) if cur is None else Snapshot.publish_lease == cur
    with engine.begin() as conn:
        res = conn.execute(
            update(Snapshot).where(Snapshot.id == snapshot_id, cond).values(publish_lease=mine)
        )
        got = int(getattr(res, "rowcount", 0) or 0) == 1
    return mine if got else None


def release_lease(engine: Engine, snapshot_id: int, lease: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(Snapshot)
            .where(Snapshot.id == snapshot_id, Snapshot.publish_lease == lease)
            .values(publish_lease=None)
        )


def _lease_job_id(lease: str) -> int | None:
    who = lease.rpartition("|")[0]
    return int(who[4:]) if who.startswith("job:") and who[4:].isdigit() else None


def _lease_holder(engine: Engine, snapshot_id: int) -> str | None:
    with engine.connect() as conn:
        cur = conn.execute(select(Snapshot.publish_lease).where(Snapshot.id == snapshot_id)).scalar()
    return None if cur is None else str(cur).rpartition("|")[0]


# ====================================================================== 발행(worker 전용)


@dataclass
class PublishResult:
    published: bool
    contradicted: int = 0
    reason: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    busy: bool = False
    """다른 발행이 같은 리비전을 발행 중(single-flight, D15-6) — 아무것도 쓰지 않았다."""


def publish_revision(
    bind: Engine | Connection,
    snapshot_id: int,
    *,
    now: str,
    settings: Settings | None = None,
    holder: str | None = None,
) -> PublishResult:
    """ready 리비전을 발행한다(D14-5): 임대 → 계산(읽기 전용) → 나눠 쓰기(단위마다 완료 표식) → 짧은 전환. worker 잡에서만.

    **single-flight**(D15-6): 리비전마다 발행은 하나만 돈다(``acquire_lease`` — 다른 발행이 들고 있으면 ``busy``, 아무것도
    지우지 않는다). 정리 DELETE 는 '발행 전' 상태 조건을 붙인다. 계산이 읽은 시점에 보이던 후속 발행 잡은 전환 트랜잭션에서
    '포함됨'으로 닫는다. 호출자는 열린 쓰기 트랜잭션이 없어야 한다(``scheduler.snapshots.publish`` 가 먼저 commit 한다)."""
    import os
    import threading

    from app.judge.claims import remaining_contradicted

    engine = bind.engine if isinstance(bind, Connection) else bind
    t0 = time.perf_counter()
    who = holder or f"pid:{os.getpid()}:{threading.get_ident()}"
    lease = acquire_lease(engine, snapshot_id, who)
    if lease is None:
        other = _lease_holder(engine, snapshot_id)
        log.warning("snapshot_view.publish_busy", extra={"snapshot_id": snapshot_id, "holder": other})
        return PublishResult(
            False, 0, f"publish_in_progress: 다른 발행({other})이 진행 중", {"holder": other}, busy=True
        )
    try:
        return _publish_locked(engine, snapshot_id, now=now, settings=settings, lease=lease, t0=t0,
                               remaining=remaining_contradicted)  # fmt: skip
    finally:
        release_lease(engine, snapshot_id, lease)


def _publish_locked(
    engine: Engine,
    snapshot_id: int,
    *,
    now: str,
    settings: Settings | None,
    lease: str,
    t0: float,
    remaining: Callable[[Session, int], Sequence[Any]],
) -> PublishResult:
    rs = _read_session(engine)
    try:
        snap = rs.get(Snapshot, snapshot_id)
        if snap is None:
            raise LookupError(f"snapshot {snapshot_id} 없음")
        if snap.status == "published":
            return PublishResult(True, 0, "이미 발행됨")
        if snap.status != "ready" or snap.degraded:
            return PublishResult(False, 0, f"status={snap.status} degraded={bool(snap.degraded)}")
        n = len(remaining(rs, snapshot_id))
        if n:
            return PublishResult(False, n, f"contradicted {n}건")
        with _as_published(rs, snap, now):
            computed = compute(rs, snap, settings=settings)
    finally:
        rs.rollback()
        rs.close()
    with engine.begin() as conn:  # 이전 실패가 남긴 행·표식(발행 전 리비전 + 이 임대를 든 동안만 — D16-3)
        _purge_unpublished(conn, snapshot_id, lease)
    done = 0
    try:
        with write_connection(engine) as wconn:
            ws = write_rows(wconn, snapshot_id, computed.rows, finish=_unit_totals(computed))
            t = time.perf_counter()
            done, n = _flip(
                wconn, snapshot_id, now=now, lease=lease, followups=computed.followups, remaining=remaining
            )
            flip_s = time.perf_counter() - t
    except BaseException:
        with engine.begin() as conn:
            _purge_unpublished(conn, snapshot_id, lease)  # 임대를 넘겨받은 새 보유자의 행은 지우지 않는다(m4)
        raise
    return _published_result(computed, ws, flip_s=flip_s, t0=t0, done=done, n=n, snapshot_id=snapshot_id)


def _flip(
    conn: Connection,
    snapshot_id: int,
    *,
    now: str,
    lease: str,
    followups: Sequence[int],
    remaining: Callable[[Session, int], Sequence[Any]],
) -> tuple[int, int]:
    """짧은 전환 트랜잭션: (published 로 바뀐 행 수, 남은 contradicted 수)."""
    done = 0
    with Session(bind=conn) as s, s.begin():
        # 쓰기 잠금부터(아무것도 바꾸지 않는 UPDATE): SQLite 는 읽은 뒤 쓰기로 올리다 그 사이 다른 커밋이 있으면 즉시
        # 'database is locked'(BUSY_SNAPSHOT) — 먼저 잠그면 아래 읽기·쓰기가 한 시점이다(R3 7차 재현 c/test_c_flip_busy)
        s.execute(
            update(Snapshot)
            .where(Snapshot.id == snapshot_id)
            .values(publish_lease=Snapshot.publish_lease)
            .execution_options(synchronize_session=False)
        )
        n = len(remaining(s, snapshot_id))
        if not n:
            res = s.execute(
                update(Snapshot)
                .where(
                    Snapshot.id == snapshot_id,
                    Snapshot.status == "ready",
                    Snapshot.publish_lease == lease,
                )
                .values(status="published", published_at=now)
                .execution_options(synchronize_session=False)
            )
            done = int(getattr(res, "rowcount", 0) or 0)
        if done and followups:  # 이 계산에 들어 있는 쓰기의 후속 발행 잡 = 포함됨(D15-6)
            s.execute(
                update(JobRun)
                .where(JobRun.id.in_(followups), JobRun.status == "queued")
                .values(
                    status="done",
                    finished_at=now,
                    stats={
                        "published": True,
                        "included_in_snapshot_id": snapshot_id,
                        "publish_job_id": _lease_job_id(lease),  # 계약 .12: 이 쓰기를 발행한 잡
                    },
                )
                .execution_options(synchronize_session=False)
            )
        if not done:
            _purge_unpublished(s.connection(), snapshot_id, lease)
    return done, n


def _published_result(
    computed: Computed, ws: WriteStats, *, flip_s: float, t0: float, done: int, n: int, snapshot_id: int
) -> PublishResult:
    stats = {
        **computed.stats,
        "write_chunks": ws.chunks,
        "write_max_lock_s": round(ws.max_lock_s, 3),
        "write_total_s": round(ws.total_write_s, 3),
        "flip_s": round(flip_s, 3),
        "total_s": round(time.perf_counter() - t0, 3),
        "followups_included": list(computed.followups) if done else [],
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
    """이미 발행된 리비전의 저장본을 호출자 세션에 넣는다(devseed·합성 도구). 넣은 행 수. 완료 표식도 함께(D15-3).

    ``replace=True`` 는 devseed·합성 도구만(개발용 픽스처를 다시 쓰는 경우 — 그 리비전 저장본·표식을 지우고 다시). 아니면 표식이
    하나도 없는 종류만. 운영 경로의 발행은 ``publish_revision``(worker), 빠진 단위 채우기는 ``backfill``."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    if replace:
        session.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snapshot_id))
        session.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == snapshot_id))
        session.flush()
        want = set(kinds) if kinds is not None else set(KINDS)
    else:
        present = set(
            session.scalars(
                select(SnapshotViewUnit.kind).where(SnapshotViewUnit.snapshot_id == snapshot_id).distinct()
            )
        )
        want = (set(kinds) if kinds is not None else set(KINDS)) - present
    if not want:
        return 0
    computed = compute(session, snap, settings=settings, kinds=want)
    _add_rows(session, snapshot_id, computed.rows)
    for u, total in _unit_totals(computed).items():
        _mark(session, snapshot_id, u, total)
    session.flush()
    log.info(
        "snapshot_view.materialized",
        extra={"snapshot_id": snapshot_id, **{k: v for k, v in computed.stats.items() if k != "timing_s"}},
    )
    return len(computed.rows)


def materialize_missing(session: Session, *, settings: Settings | None = None) -> list[int]:
    """표식이 하나도 없는 종류가 있는 발행 리비전 전부를 채운다(개발 도구). 채운 스냅샷 id. 운영은 ``backfill``."""
    done: list[int] = []
    for sid in list(
        session.scalars(select(Snapshot.id).where(Snapshot.status == "published").order_by(Snapshot.id))
    ):
        if materialize(session, int(sid), settings=settings):
            done.append(int(sid))
    return done


def _expected_units(scenarios: Iterable[str]) -> set[Unit]:
    sks = list(scenarios)
    return {(k, "") for k in NO_SCENARIO_KINDS} | {(k, sk) for k in SCENARIO_KINDS for sk in sks}


def unit_states(session: Session, snapshot_id: int) -> dict[Unit, tuple[bool, int, int]]:
    """그 리비전의 단위 → (done, 표식 rows, 실제 행 수). **행이 있는데 표식이 없는 단위**도 넣는다(done=False — D16-2·m3:
    예전에는 표식 목록에만 기대 pending·backfill 둘 다 놓쳐 영구 404 였다)."""
    counts: dict[Unit, int] = {
        (str(k), str(sc)): int(n)
        for k, sc, n in session.execute(
            select(SnapshotView.kind, SnapshotView.scenario, func.count())
            .where(SnapshotView.snapshot_id == snapshot_id)
            .group_by(SnapshotView.kind, SnapshotView.scenario)
        )
    }
    out: dict[Unit, tuple[bool, int, int]] = {
        (str(k), str(sc)): (bool(d), int(r or 0), counts.get((str(k), str(sc)), 0))
        for k, sc, d, r in session.execute(
            select(
                SnapshotViewUnit.kind, SnapshotViewUnit.scenario, SnapshotViewUnit.done, SnapshotViewUnit.rows
            ).where(SnapshotViewUnit.snapshot_id == snapshot_id)
        )
    }
    if out:  # 표식이 하나도 없는 리비전(0010 이전 발행분)은 그대로 비워 둔다 — backfill 이 지금 시나리오 전부로 표식부터
        for u, n in counts.items():
            out.setdefault(u, (False, 0, n))
    return out


def _incomplete(states: dict[Unit, tuple[bool, int, int]]) -> set[Unit]:
    return {u for u, (done, rows, have) in states.items() if not done or have < rows}


class _AnyKey:
    def __contains__(self, _key: object) -> bool:
        return True


_ANY_KEY: Final = _AnyKey()


def _revision_keys(session: Session, sid: int, present: set[tuple[str, str, str]]) -> dict[str, Any]:
    """backfill 이 그 리비전에 새로 넣어도 되는 키(불변 — 발행 뒤 생긴 단지·생활권은 옛 리비전의 키가 아니다, D11-1·D16-2).

    단지 상세 = 그 리비전 단지 목록 저장본(어느 시나리오든)의 단지 id ∪ 이미 있는 키, 시장 = '' ∪ 시장 저장본의 생활권 id ∪
    이미 있는 키. 근거 저장본이 하나도 없으면 제한 없음(0010 이전 발행분처럼 처음 만드는 경우)."""
    out: dict[str, Any] = {}
    for kind, list_kind in (("complex", "complexes"), ("market", "market")):
        keys = {key for (k, key, _sc) in present if k == kind}
        found = False
        for k, key, sc in sorted(present):
            if k != list_kind or key != "":
                continue
            try:
                body = stored(session, sid, list_kind, key="", scenario=sc)
            except (NotMaterialized, StoredViewMismatch):
                continue
            if not isinstance(body, dict):
                continue
            found = True
            if kind == "complex":
                keys |= {str(r["item"]["complex_id"]) for r in body.get("rows") or [] if isinstance(r, dict)}
            else:
                keys |= {""} | {str(a["id"]) for a in body.get("living_areas") or [] if isinstance(a, dict)}
        out[kind] = keys if found else _ANY_KEY
    return out


def _backfill_one(eng: Engine, sid: int, s: Settings) -> dict[str, Any] | None:
    """발행 리비전 1개의 미완 단위를 채운다(D15-3). 이미 있는 행은 그대로 두고(발행 순간 바이트) 빠진 키만 넣는다.
    만든 것이 없으면 None."""
    with Session(bind=eng) as ses:
        states = unit_states(ses, sid)
        if not states:  # 표식이 하나도 없다(0010 이전 발행분) — 지금 시나리오 전부로 '만들 단위' 표식부터
            expected = _expected_units(scenario_key(x) for x in _scenarios(ses))
            ses.rollback()  # 읽기 트랜잭션을 끝내고(다시 읽을 때 새 표식이 보이게) 표식은 따로 짧게 쓴다
            with eng.begin() as conn:
                for u in sorted(expected):
                    _mark(conn, sid, u, 0, done=False)
            states = unit_states(ses, sid)
        todo = _incomplete(states)
        if not todo:
            return None
        present = {
            (str(k), str(key), str(sc))
            for k, key, sc in ses.execute(
                select(SnapshotView.kind, SnapshotView.key, SnapshotView.scenario).where(
                    SnapshotView.snapshot_id == sid
                )
            )
        }
        have_drawers = states.get(("provenance", ""), (False, 0, 0))[2] > 0
    rs = _read_session(eng)
    try:
        snap = rs.get(Snapshot, sid)
        assert snap is not None
        main = compute(rs, snap, settings=s, units=todo - {("provenance", "")}, dedup=False)
        allowed = _revision_keys(rs, sid, present)
        new_rows = [
            r
            for r in main.rows
            if (r.kind, r.key, r.scenario) not in present and r.key in allowed.get(r.kind, _ANY_KEY)
        ]
        new_ids: set[str] = (
            set()
        )  # 새로 넣는 행이 가리키는 출처(지금 계산의 다른 출처는 서랍에 넣지 않는다 — 발행 순간 범위)
        for r in new_rows:
            _collect_prov(zlib.decompress(r.body), new_ids)
        rebuild_prov = ("provenance", "") in todo
        if not rebuild_prov and new_rows:
            known = set(stored_drawers(rs, sid)) if have_drawers else set()
            rebuild_prov = bool(new_ids - known)
        prov = (
            compute(
                rs,
                snap,
                settings=s,
                units={("provenance", "")},
                extra_prov_ids=new_ids,
                reuse_drawers=True,
            )
            if rebuild_prov
            else None
        )
    finally:
        rs.rollback()
        rs.close()
    finish = {u: states.get(u, (False, 0, 0))[2] for u in main.units}
    for u in todo - set(main.units) - {("provenance", "")}:
        finish[u] = states[u][
            2
        ]  # 지금은 계산할 수 없는 단위(그 뒤 지운 시나리오 등) — 있는 행 그대로 완료로 닫는다
    for r in new_rows:
        finish[(r.kind, r.scenario)] = finish.get((r.kind, r.scenario), 0) + 1
    if (
        prov is not None
    ):  # 서랍을 다시 쓰는 동안은 미완(먼저 표식을 내린다 — 그 사이 실패해도 다음 backfill 이 다시)
        with eng.begin() as conn:
            _mark(conn, sid, ("provenance", ""), 0, done=False)
            conn.execute(
                delete(SnapshotView).where(SnapshotView.snapshot_id == sid, SnapshotView.kind == "provenance")
            )
    ws = write_rows(eng, sid, new_rows, finish=finish)
    rows = ws.rows
    missing = int(main.stats.get("missing_provenance") or 0)
    if prov is not None:
        rows += write_rows(eng, sid, prov.rows, finish=_unit_totals(prov)).rows
        missing += int(prov.stats.get("missing_provenance") or 0)
    return {"rows": rows, "units": sorted(todo | ({("provenance", "")} if prov is not None else set())),
            "missing_provenance": missing}  # fmt: skip


def backfill(engine: Engine | None = None, *, settings: Settings | None = None) -> dict[str, Any]:
    """멱등 backfill(D14-9·**D15-3**): 행 단위 사람 확인 → 의미 묶음(m14) + 발행 리비전의 **미완 단위**(완료 표식 없음·
    done=false·행 수 모자람) 채우기. 리비전마다 따로 실패한다(한 리비전 예외가 나머지를 막지 않는다, m11 — ``failed``).

    리비전마다 계산(읽기) → 짧은 트랜잭션으로 쓰기, 단위마다 마지막 쓰기 트랜잭션에 완료 표식. worker 시작과
    ``python -m app.snapshot_view backfill`` 이 부른다."""
    from app.core.db import get_engine

    s = settings or get_settings()
    eng = engine or get_engine(s)
    out: dict[str, Any] = {
        "snapshots": [],
        "rows": 0,
        "human_checks_migrated": 0,
        "missing_provenance": 0,
        "failed": [],
    }
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
        try:
            got = _backfill_one(eng, sid, s)
        except (
            Exception
        ) as exc:  # 리비전마다 따로 실패(D15-3·m11) — 그 리비전은 미완 그대로(GET 503), 다음 실행이 다시
            log.error(
                "snapshot_view.backfill_failed", extra={"snapshot_id": sid, "error": type(exc).__name__}
            )
            out["failed"].append({"snapshot_id": sid, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        if got is None:
            continue
        out["snapshots"].append(sid)
        out["rows"] += int(got["rows"])
        out["missing_provenance"] += int(got["missing_provenance"])
    if out["snapshots"] or out["human_checks_migrated"] or out["failed"]:
        log.info(
            "snapshot_view.backfill",
            extra={"snapshots": len(out["snapshots"]), "rows": out["rows"], "failed": len(out["failed"])},
        )
    return out


def pending_count(session: Session) -> int:
    """미완 단위(표식 없음·done=false·행 수 모자람)가 있는 발행 리비전 수(운영 점검, D15-3)."""
    n = 0
    for sid in session.scalars(select(Snapshot.id).where(Snapshot.status == "published")):
        states = unit_states(session, int(sid))
        if not states or _incomplete(states):
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
