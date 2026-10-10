"""API 테스트 공용: 경로·토큰·계약 응답 검증기 (WP5)."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CONTRACTS = REPO / "contracts"
FIXTURE = CONTRACTS / "fixtures" / "incheon_gimpo_2026-10-08"
OPENAPI_BUNDLED = CONTRACTS / "openapi.bundled.yaml"

WRITE_TOKEN = "w" * 32
READ_TOKEN = "r" * 32
WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}
READ = {"Authorization": f"Bearer {READ_TOKEN}"}

_URN = "urn:openapi-bundled"


@functools.cache
def bundled() -> dict[str, Any]:
    with OPENAPI_BUNDLED.open(encoding="utf-8") as f:
        doc: dict[str, Any] = yaml.safe_load(f)
    return doc


@functools.cache
def _registry() -> Registry[Any]:
    return Registry().with_resource(
        _URN, Resource.from_contents(bundled(), default_specification=DRAFT202012)
    )


def _operation(op_id: str) -> tuple[str, str, dict[str, Any]]:
    for path, item in bundled()["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and op.get("operationId") == op_id:
                return path, method, op
    raise KeyError(op_id)


def response_schema(op_id: str, status: int, content_type: str = "application/json") -> dict[str, Any]:
    _, _, op = _operation(op_id)
    resp = op["responses"][str(status)]
    if "$ref" in resp:
        name = resp["$ref"].rsplit("/", 1)[-1]
        resp = bundled()["components"]["responses"][name]
    schema: dict[str, Any] = resp["content"][content_type]["schema"]
    return schema


def _rewrite(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: (_URN + v if k == "$ref" and isinstance(v, str) and v.startswith("#") else _rewrite(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rewrite(v) for v in obj]
    return obj


def validate(op_id: str, status: int, body: Any) -> None:
    """응답 본문이 openapi.bundled.yaml 의 그 operation·status 스키마를 통과하는지(형식 검사 포함)."""
    schema = _rewrite(response_schema(op_id, status))
    validator = Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:300]}" for e in errors[:10]]
        raise AssertionError(f"{op_id} {status} 응답이 계약과 다르다:\n" + "\n".join(msgs))


FACT_KEYS = {"v", "label", "prov", "checked_at"}
_PROV_RE = re.compile(r"^(fp|sc|st|jl|hc|rd|cs)_[0-9A-Za-z_.:-]+$")


def iter_facts(obj: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    """응답 안의 Fact 전부(경로, Fact)."""
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(obj, dict):
        if set(obj) >= FACT_KEYS and isinstance(obj.get("label"), str):
            out.append((path, obj))
        for k, v in obj.items():
            out.extend(iter_facts(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(iter_facts(v, f"{path}[{i}]"))
    return out


def as_live(region_id: int = 1) -> None:
    """지역의 발행 스냅샷(devseed 11·12)을 '판정 끝·발행 전(ready)'으로 되돌리고 저장본을 지운다 — 스냅샷 GET(기본
    스냅샷 = 가장 새 ready 포함)이 실시간 계산 경로를 탄다.

    D13-1(계약 .10): 발행 리비전 GET 은 발행 때 저장한 응답만 돌려준다(``app.snapshot_view``). 사실 변경이 화면·CSV·
    보고서 계산에 어떻게 반영되는지 보는 테스트(강등 오버레이·할인·범위·CSV 등 실시간 계산 규칙)는 발행 전 리비전에서
    본다. 발행 리비전 불변은 ``test_r3e_invariant`` 가 본다."""
    from sqlalchemy import delete, select

    from app.core.db import get_session
    from app.models import Snapshot, SnapshotView

    with get_session() as s:
        for snap in s.scalars(
            select(Snapshot).where(Snapshot.region_id == region_id, Snapshot.status == "published")
        ):
            s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == snap.id))
            snap.status, snap.published_at = "ready", None


def assert_facts_labelled(body: Any) -> int:
    """모든 Fact 에 라벨이 있고, '확인 불가'가 아니면 v·prov 가 있다(AGENTS 규칙 5)."""
    facts = iter_facts(body)
    for path, f in facts:
        assert f["label"], path
        if f["label"] == "확인 불가":
            assert f.get("reason"), f"{path}: 확인 불가인데 reason 없음"
        else:
            assert f["v"] is not None, f"{path}: 값 없음 {f}"
            assert f["prov"] and _PROV_RE.match(f["prov"]), f"{path}: prov 없음 {f}"
    return len(facts)


def run_job(job_id: int) -> tuple[str, dict[str, Any]]:
    """worker 처럼 잡 하나를 잠가 실행한다(claim → execute) — D14-5: 발행(저장본)은 worker 잡에서만. (status, stats)."""
    from app.core.db import get_session, get_sessionmaker
    from app.models import JobRun
    from app.scheduler.context import SchedulerContext
    from app.scheduler.runner import claim, execute

    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    assert claim(ctx, job_id), f"job {job_id} 이 queued 가 아니다"
    status = execute(ctx, job_id)
    with get_session() as s:
        row = s.get(JobRun, job_id)
        assert row is not None
        return status, dict(row.stats or {})


def publish_revision(region_id: int = 1, reason: str = "테스트 리비전") -> int:
    """가장 새 발행 리비전 위 새 리비전을 실제 발행 경로로 발행(새 리비전 + snapshot.publish 잡 → worker 실행). 새 리비전 id."""
    from app.core.db import get_session
    from app.models import Snapshot
    from app.scheduler.snapshots import republish

    with get_session() as s:
        job = republish(s, region_id, reason=reason, created_at="2026-10-09T08:00:00+09:00")
        assert job is not None
        job_id, sid = job.id, int((job.payload or {})["snapshot_id"])
    status, stats = run_job(job_id)
    assert status == "done" and stats.get("published"), stats
    with get_session() as s:
        snap = s.get(Snapshot, sid)
        assert snap is not None and snap.status == "published"
    return sid
