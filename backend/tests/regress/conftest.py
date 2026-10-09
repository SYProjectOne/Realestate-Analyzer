"""WP9 R3 통합 회귀(RA §9 T1~T18) 공용 fixture — 시스템 경계에서 본다.

원칙
- 모듈 테스트(``tests/<모듈>/``)의 helper 를 import 하지 않는다. 적재는 공개 진입점(``app.api.devseed``),
  확인은 API(``app.main.create_app`` + TestClient)·worker(``app.scheduler.runner.main``)·DB 행으로 한다.
- 네트워크 없음: SchedulerContext 의 수집기는 기본 ``{}`` (테스트가 필요한 것만 넣는다).
- 판정기: ``mock`` = ``app.judge.get_adapter``(JUDGE_ADAPTER=mock, **합성 판정 녹화** ``judgments_synth/`` 재생 — e2e 와 같은
  ``JUDGE_FIXTURE_DIR``; 보고서 재구성 녹화 ``judgments/`` 는 devseed judgment_log·T7 등 보고서 대조용) /
  ``fake`` = 실제 어댑터 경로(``JevMcpAdapter``: guard·캐시·judgment_log)에 결정적 가짜 전송 ``FakeJev`` /
  ``down`` = 모든 호출 JudgeUnavailable.

fixture
- ``seed_db``(세션 1회): 임시 디렉터리에 devseed(인천·김포 픽스처 + 픽스처 지역 참조 데이터).
- ``env``: 테스트마다 그 DB 를 복사한 ``RegressEnv`` (settings·client·ctx()·worker()·session()).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_session, get_sessionmaker, reset_engine
from app.core.protocols import JudgeUnavailable
from app.core.settings import Settings, env_var_names, set_settings
from app.core.time import KST

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
SYNTH = (
    FIXTURE / "judgments_synth"
)  # 합성 판정 녹화(W2) — mock 재판정이 재생하는 녹화(MockAdapter fixture_dir)
REFERENCE = REPO / "contracts" / "fixtures" / "reference"

WRITE_TOKEN = "w" * 32
READ_TOKEN = "r" * 32
WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}
READ = {"Authorization": f"Bearer {READ_TOKEN}"}

SNAP_OLD = 11  # 2026-10-07 인천 8
SNAP = 12  # 2026-10-08 통합 16


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_settings(db: Path, raw_dir: Path, report_dir: Path, *, env: str = "dev") -> Settings:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=f"sqlite:///{db.as_posix()}",
        raw_dir=raw_dir,
        reference_dir=db.parent / "reference",
        report_dir=report_dir,
        # prod + mock 는 설정 단계에서 거부된다(R3 minor 31) — prod 설정은 jev 로 두고 판정기는 호출하지 않는다(T13 은 API 만)
        judge_adapter="jev" if env == "prod" else "mock",
        api_token=WRITE_TOKEN,  # type: ignore[arg-type]
        readonly_token=READ_TOKEN,  # type: ignore[arg-type]
        log_json=False,
    )
    # ENV=prod + SQLite 는 설정 검증이 거부한다(D11-9). prod 화면 동작(라벨·경고) 시험만 검증을 건너뛰어 바꾼다
    return settings.model_copy(update={"env": env}) if env != "dev" else settings


# ---------------------------------------------------------------- 가짜 JEV 전송


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


@dataclass
class FakeJev:
    """JEV MCP 응답 모양을 payload 에서 결정적으로 만든다(테스트 전용 Transport).

    ``calls`` = 판정기로 실제 나간 (도구, arguments) — 캐시 적중·guard 차단은 여기 오지 않는다.
    """

    version: str = "0.14.1"
    model: str = "jev-1.13.0"
    down: bool = False
    verdict: str = "verified"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def server_version(self) -> str:
        if self.down:
            raise JudgeUnavailable("fake: down")
        return self.version

    def close(self) -> None:
        return None

    def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        from app.judge.base import ToolResponse

        if self.down:
            raise JudgeUnavailable("fake: down")
        self.calls.append((tool_name, json.loads(json.dumps(arguments, ensure_ascii=False, default=str))))
        fn = getattr(self, "_" + tool_name.removeprefix("jev_"))
        return ToolResponse(
            raw={"tool": tool_name, "model": self.model, **fn(arguments)}, is_error=False, duration_ms=1
        )

    def tools(self) -> list[str]:
        return [t for t, _ in self.calls]

    # --- 도구별 (JEV 0.14.x 응답 모양)
    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "probabilities": {"injection": 0.01, "substance": 0.97, "relevance": 0.97},
            "recommendation": {"action": "pass"},
        }

    def _extract(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {"id": f["id"], "value": None, "status": "not_found", "confidence": 0.9}
                for f in a.get("fields", [])
            ]
        }

    def _audit(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "pass",
            "records": [{"id": r["id"], "action": "ok", "p_wrong": 0.05} for r in a.get("records", [])],
        }

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        first = a["classes"][0]["id"]
        return {
            "results": [
                {
                    "id": it["id"],
                    "classification": first,
                    "probabilities": {first: 0.96},
                    "top_probability": 0.96,
                    "confidence": 0.95,
                    "decision": "auto",
                }
                for it in a["items"]
            ]
        }

    def _compare(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall": {
                "relation": "same_fact",
                "probabilities": {"same_fact": 0.9},
                "confidence": 0.9,
                "decision": "auto",
            },
            "aspects": [],
        }

    def _noul(self, a: dict[str, Any]) -> dict[str, Any]:
        out = []
        for i, p in enumerate(a["propositions"]):
            prob = min(0.95, max(0.05, round(0.3 + (_h(p[:60]) % 40) / 100 - 0.08 * i, 2)))
            label = "likely" if prob >= 0.6 else "unlikely" if prob <= 0.3 else "uncertain"
            out.append(
                {"id": f"proposition{i}", "proposition": p, "probability": prob, "label": label, "auto": True}
            )
        return {"status": "ok", "results": out}

    def _rerank(self, a: dict[str, Any]) -> dict[str, Any]:
        cands = sorted(a["candidates"], key=lambda c: _h(c["text"]))
        n = len(cands)
        return {
            "query": a["query"],
            "ranked": [
                {"rank": i + 1, "id": c["id"], "relevance": round(0.95 - 0.8 * i / max(1, n - 1), 3)}
                for i, c in enumerate(cands)
            ],
        }

    def _decide(self, a: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in a["candidates"]]
        probs: dict[str, float] = {cid: round(0.6 / (i + 1), 3) for i, cid in enumerate(ids)}
        probs.update({"ask_user": 0.02, "investigate": 0.01})
        checks = [
            {"candidate": cid, "requirement": j, "answer": "supported"}
            for cid in ids
            for j in range(len(a["requirements"]))
        ]
        return {
            "recommendation": {
                "selected": ids[0],
                "escaped": False,
                "confidence": 0.8,
                "probabilities": probs,
            },
            "checks": checks,
            "warnings": [],
        }

    def _verify(self, a: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {"id": f"claim{i}", "claim": c, "verdict": self.verdict, "confidence": 0.95, "action": "auto"}
                for i, c in enumerate(a["claims"])
            ]
        }


# ---------------------------------------------------------------- 환경


class MissSpy:
    """MockAdapter 감싸기 — 녹화가 없어 review('no recording')가 된 호출을 모은다(합성 녹화가 payload 를 다 덮는지)."""

    def __init__(self, inner: Any, misses: list[tuple[str, str]]) -> None:
        self._inner = inner
        self._misses = misses

    @property
    def adapter_version(self) -> str:
        return str(self._inner.adapter_version)

    def call(self, tool: Any, payload: Any, purpose: str, **kw: Any) -> Any:
        env = self._inner.call(tool, payload, purpose, **kw)
        if (env.raw or {}).get("reason") == "no recording":
            self._misses.append((str(tool), purpose))
        return env

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@dataclass(frozen=True)
class Seeded:
    db: Path
    raw_dir: Path


def offline_reference_refresh(settings: Settings) -> Callable[[date], dict[str, Any]]:
    """``reference.refresh`` 잡 본체(ReferenceCollector)를 네트워크 없이: 모든 요청 DNS 실패 →
    ``contracts/fixtures/reference`` 공식 사본으로 적재(법정동·행정동·매핑·주민등록 세대 현황)."""
    import httpx

    from app.collectors.reference import ReferenceCollector
    from app.core.http import HttpClient

    def refresh(day: date) -> dict[str, Any]:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("[regress] offline", request=request)

        http = HttpClient(
            max_retries=0, jitter=0.0, sleep=lambda _s: None, transport=httpx.MockTransport(fail)
        )
        try:
            rep = ReferenceCollector(
                http=http,
                session_factory=lambda: get_session(settings),
                raw_dir=settings.raw_dir,
                fallback_dir=REFERENCE,
                today=day,
            ).refresh()
        finally:
            http.close()
        return {
            "used_fallback": list(rep.used_fallback),
            "household_ym": rep.household_ym,
            "errors": list(rep.errors),
        }

    return refresh


def prepare_db(settings: Settings) -> dict[str, Any]:
    """devseed + reference.refresh(오프라인 사본) — 잡 큐·worker 경로로 적재한다. refresh 잡 stats 를 돌려준다."""
    from dataclasses import replace

    from app.api import devseed
    from app.models import JobRun
    from app.scheduler import runner
    from app.scheduler.context import default_context
    from app.scheduler.jobs import enqueue

    devseed.seed(settings, fixture_dir=FIXTURE, reference="region")
    factory = get_sessionmaker(settings)
    with factory() as s:
        job_id = enqueue(s, "reference.refresh", {}).id
        s.commit()
    ctx = replace(
        default_context(settings), collectors={}, reference_refresh=offline_reference_refresh(settings)
    )
    runner.main(["--once"], ctx=ctx)
    with factory() as s:
        job = s.get(JobRun, job_id)
        assert job is not None and job.status == "done", (
            job.status if job else None,
            job.error_text if job else None,
        )
        return dict(job.stats or {})


@pytest.fixture(scope="session")
def seed_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Seeded]:
    """devseed(공개 CLI 와 같은 함수) — 인천·김포 16단지 + 녹화 판정 + 점수, 그리고 reference.refresh 잡(공식 사본)."""
    base = tmp_path_factory.mktemp("regress_seed")
    seeded = Seeded(db=base / "seed.db", raw_dir=base / "raw")
    settings = make_settings(seeded.db, seeded.raw_dir, base / "reports")
    set_settings(settings)
    try:
        prepare_db(settings)
    finally:
        set_settings(None)
        reset_engine()
    yield seeded


@dataclass
class Clock:
    day: date = date(2026, 10, 9)

    def today(self) -> date:
        return self.day

    def now(self) -> datetime:
        return datetime(self.day.year, self.day.month, self.day.day, 6, 0, tzinfo=KST)


@dataclass
class RegressEnv:
    settings: Settings
    client: TestClient
    tmp: Path
    jev: FakeJev = field(default_factory=FakeJev)
    clock: Clock = field(default_factory=Clock)
    mock_misses: list[tuple[str, str]] = field(
        default_factory=list
    )  # mock 재판정에서 녹화가 없던 (도구, purpose)
    _ctxs: list[Any] = field(default_factory=list)

    @property
    def factory(self) -> sessionmaker[Session]:
        return get_sessionmaker(self.settings)

    def session(self) -> Session:
        return self.factory()

    def ctx(
        self,
        judge: str = "fake",
        *,
        collectors: Mapping[str, Callable[[Any], Any]] | None = None,
        probe_judge: Callable[[], bool] | None = None,
    ) -> Any:
        """SchedulerContext — default_context(settings) 에서 판정기·수집기·시계만 바꾼다."""
        from dataclasses import replace

        from app.judge.jev_mcp import JevMcpAdapter
        from app.judge.mock import MockAdapter
        from app.scheduler.context import default_context

        base = default_context(self.settings)
        factory = self.factory

        if judge == "fake":

            def adapter() -> Any:
                return JevMcpAdapter(transport=self.jev, session_factory=factory, secrets=[])
        elif judge == "mock":
            inner = (
                base.adapter_factory
            )  # JUDGE_ADAPTER=mock → get_adapter(settings, fixture_dir=JUDGE_FIXTURE_DIR=SYNTH)

            def adapter() -> Any:
                return MissSpy(inner(), self.mock_misses)
        elif judge == "down":

            def adapter() -> Any:
                return MockAdapter(FIXTURE, unavailable=True)
        else:
            raise ValueError(judge)
        c = replace(
            base,
            adapter_factory=adapter,
            collectors=dict(collectors or {}),
            reference_refresh=lambda d: {"skipped": "regress"},
            probe_judge=probe_judge,
            today=self.clock.today,
            now=self.clock.now,
            worker_id="regress",
        )
        self._ctxs.append(c)
        return c

    def worker(self, ctx: Any | None = None) -> int:
        """``python -m app.worker --once`` 와 같은 진입(runner.main) — 큐를 비운다."""
        from app.scheduler import runner

        return runner.main(["--once"], ctx=ctx or self.ctx())

    def close(self) -> None:
        for c in self._ctxs:
            c.reset_adapter()


@pytest.fixture
def env(seed_db: Seeded, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RegressEnv]:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "JUDGE_FIXTURE_DIR", str(SYNTH)
    )  # mock 재판정 = 합성 판정 녹화(e2e/env.ts 와 같은 구성)
    db = tmp_path / "regress.db"
    shutil.copyfile(seed_db.db, db)
    settings = make_settings(db, seed_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    from app.main import create_app

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        e = RegressEnv(settings=settings, client=client, tmp=tmp_path)
        try:
            yield e
        finally:
            e.close()
            set_settings(None)
            reset_engine()


def api_get(env: RegressEnv, path: str, **params: Any) -> Any:
    r = env.client.get(f"/api{path}", headers=WRITE, params=params or None)
    assert r.status_code == 200, f"GET {path} → {r.status_code} {r.text[:300]}"
    return r.json()


def by_key() -> dict[str, int]:
    """expected_scores.json key → complex_id."""
    return {c["key"]: c["complex_id"] for c in load_json(FIXTURE / "expected_scores.json")["complexes"]}


def cur(env: RegressEnv, snap: int = SNAP) -> int:
    """``snap`` 기준일의 가장 큰 리비전 id. 발행 스냅샷 재판정·사람 확인은 같은 기준일 새 리비전에 쓴다(D11-1) —
    재판정 뒤 화면 값은 이 리비전에서 읽는다(발행 리비전은 그대로)."""
    from app.models import Snapshot
    from app.scheduler.snapshots import latest_revision

    with env.session() as s:
        base = s.get(Snapshot, snap)
        assert base is not None
        row = latest_revision(s, base.region_id, base.asof_date)
        return int(row.id if row is not None else snap)
