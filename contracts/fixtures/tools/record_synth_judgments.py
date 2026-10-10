"""합성 판정 녹화 생성기 (WP9-후속, CEO 결정 W2) → contracts/fixtures/incheon_gimpo_2026-10-08/judgments_synth/

사용 (backend/ 에서, app 패키지를 import 하므로):
    uv run python ../contracts/fixtures/tools/record_synth_judgments.py           # 다시 쓴다
    uv run python ../contracts/fixtures/tools/record_synth_judgments.py --check   # 커밋된 파일과 다르면 exit 1

왜: ``judgments/``(보고서 재구성 녹화)는 payload 가 보고서 '입력 요약'이라 파이프라인 payload 와 hash 가 다르다 →
MockAdapter 재판정이 전부 review(종합 점수 미계산). 여기서는 **실제 파이프라인을 한 번 돌려** 그 payload hash 그대로
봉투를 저장한다. 값은 결정적 가짜 판정기(``ReportSynthJev`` — WP7 ``SynthJev`` 를 상속)가 만들고, 보고서에 있는 값은
보고서 재구성 녹화(``judgments/``)·``complexes.json`` 에서 가져온다(아래 표). 라벨은 '합성'(README·_meta·봉투 raw.synth).

| 도구 | 값의 출처 |
| --- | --- |
| classify(포함/제외) | complexes.json inclusion(보고서 #62·#110: 클래스·decision·확률) — 스위첸·지엔하임·그랑포레 = review |
| classify(호재 단계) | 보고서 #64·#111 의 같은 이름 항목(없으면 review) |
| classify(접수 상태) | complexes.json 공식 경로 접수 행(가능→open, 미정→pending, 불가→closed, 확인 불가→unknown) |
| noul | 입주 후 1년(move_in_plus_1y) = 보고서 #65~70·#118~123 의 단지별 p5·p10·p20·보합(라벨·auto 그대로). 3년·5년 = 보고서에 없음 → review |
| rerank | #124 relevance(후보 안에서 relevance 내림차순, 같은 값 = 같은 순위) |
| decide | 상황별 #125~#129(통합). 선택·확률·확신도 = 보고서 그대로(A = 가상 후보 wait_new .94, 계약 .5) — 보고서 선택이 후보에 없으면 녹화 실패(대체 없음), 요건 판정은 후보에 있는 것만 |
| verify | 보고서 §8-5·§12-5-5 최종 검증 = verified(auto) — 파이프라인 주장 문장과 1:1 대응은 없음 |
| screen·extract·audit·compare | SynthJev 기본(pass·not_found·ok·same_fact) — 보고서에 필드별 대응 값 없음(지어내지 않음) |

돌리는 흐름(둘 다 devseed + reference.refresh(공식 사본) 직후 DB 에서, 시계 2026-10-09 06:00 KST):
- ``full``: rejudge(스냅샷 12, 단지 전부, 시나리오 전부) — 회귀·e2e mock 재판정의 기본 payload
- ``t3``: POST /ops/human-checks(raw/human_check/t3_switzen_possible.json) → 응답의 suggested_job(rejudge [4]) — 회귀 T3·e2e 흐름 (b)

adapter_version 은 ``judgments/_meta.json`` 과 같은 ``mock-fixture-2026-10-08`` 이다 — devseed 의 judgment_log(보고서 녹화)와
다르면 mock 재판정이 '판정기 버전 변경'(critical)과 전체 재판정을 만든다. 파일 이름(hash)은 payload 가 달라 겹치지 않는다.
"""

# ruff: noqa: E501  (원문 표기)
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
BACKEND = REPO / "backend"
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
REFERENCE = REPO / "contracts" / "fixtures" / "reference"
REPORT_JUDGMENTS = FIXTURE / "judgments"
OUT = FIXTURE / "judgments_synth"
SYNTH_CONFTEST = BACKEND / "tests" / "scheduler" / "conftest.py"  # WP7 SynthJev(결정적 JEV 응답 모양)
sys.path.insert(0, str(BACKEND))

from app.core.contracts_gen import JudgmentEnvelope  # noqa: E402
from app.core.protocols import JudgePayload, JudgeTool  # noqa: E402
from app.judge import cache, guard  # noqa: E402
from app.judge.jev_mcp import normalize  # noqa: E402
from app.judge.mock import load_meta_version, log_replay  # noqa: E402

LABEL = "합성"
ADAPTER_VERSION = load_meta_version(FIXTURE)  # = judgments/_meta.json (mock-fixture-2026-10-08)
SNAPSHOT = 12
TODAY = date(2026, 10, 9)
KST_NOW = "2026-10-09T06:00:00+09:00"
MODEL = "jev-1.13.0"  # 보고서 §2 확인 모델(합성 봉투 raw.model 표기)
WRITE_TOKEN = "w" * 32
READ_TOKEN = "r" * 32
DECIDE_SEQ = {"base": 125, "A": 126, "B": 127, "C": 128, "D": 129}  # 보고서 §12-5-2 통합 재판정
REQ_KEYS = ("access", "regulation", "funds")
HATCHES = ("ask_user", "investigate", "none")
INTAKE_CLASS = {"가능": "open", "미정": "pending", "불가": "closed", "확인 불가": "unknown"}


def _load_synth_base() -> type:
    spec = importlib.util.spec_from_file_location("wp7_scheduler_conftest", SYNTH_CONFTEST)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 가 모듈을 찾는다
    spec.loader.exec_module(mod)
    return mod.SynthJev  # type: ignore[no-any-return]


SynthJev = _load_synth_base()


# ---------------------------------------------------------------- 보고서 값


def _report() -> dict[int, dict[str, Any]]:
    """judgment_seq → {row(_index), env(봉투)}."""
    idx = json.loads((REPORT_JUDGMENTS / "_index.json").read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for r in idx:
        env = json.loads((REPORT_JUDGMENTS / r["file"]).read_text(encoding="utf-8"))
        out[int(r["judgment_seq"])] = {"row": r, "env": env}
    return out


class ReportSynthJev(SynthJev):  # type: ignore[misc, valid-type]
    """SynthJev(결정적 JEV 응답 모양) + 보고서 수치. ``respond`` 는 purpose 까지 받아 단지·시점·상황을 고른다."""

    def __init__(self) -> None:
        super().__init__(model=MODEL)
        rep = _report()
        bundles = json.loads((FIXTURE / "complexes.json").read_text(encoding="utf-8"))
        self.inclusion: dict[int, tuple[str, str, float]] = {}
        self.intake: dict[int, str] = {}
        for b in bundles:
            c = b["complex"]
            self.inclusion[c["id"]] = (c["inclusion_class"], c["inclusion_decision"], float(c["inclusion_prob"]["v"]))
            official = [i for i in b["intake"] if i["path"] in ("human_check", "official_popup", "headless_shot")]
            if official:
                self.intake[c["id"]] = official[0]["status"]
        self.ladder: dict[int, tuple[int, list[dict[str, Any]]]] = {}
        self.catalyst: dict[str, tuple[int, dict[str, Any]]] = {}
        self.rerank: dict[int, float] = {}
        self.rerank_order: dict[int, int] = {}
        self.decide: dict[str, tuple[int, dict[str, Any]]] = {}
        for seq, v in rep.items():
            env, row = v["env"], v["row"]
            if env["tool"] == "noul" and env["status"] == "ok" and row["payload"].get("horizon") == "move_in_plus_1y":
                self.ladder[int(row["payload"]["complex_id"])] = (seq, env["result"]["propositions"])
            elif env["tool"] == "classify" and row["purpose"].startswith("classify:catalyst"):
                for it in env["result"].get("items", []):
                    self.catalyst.setdefault(str(it["candidate"]), (seq, it))
            elif env["tool"] == "rerank" and seq == 124:
                for pos, it in enumerate(env["result"]["items"]):
                    self.rerank[int(it["complex_id"])] = float(it["relevance"])
                    self.rerank_order[int(it["complex_id"])] = pos
        for code, seq in DECIDE_SEQ.items():
            self.decide[code] = (seq, rep[seq]["env"])
        self.calls_by_tool: dict[str, int] = {}

    # --- 진입점(RecordingAdapter 가 부른다)
    def respond(self, tool: JudgeTool, payload: JudgePayload, purpose: str) -> dict[str, Any]:
        self.calls_by_tool[tool] = self.calls_by_tool.get(tool, 0) + 1
        a = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        fn = getattr(self, f"_r_{tool}", None)
        if fn is None:  # screen·extract·audit·compare: SynthJev 기본
            body = getattr(self, f"_{tool}")(a)
            basis = "SynthJev 기본(보고서에 필드별 대응 값 없음)"
        else:
            body, basis = fn(a, purpose)
        return {"tool": f"jev_{tool}", "model": self.model, **body, "synth": {"label": LABEL, "basis": basis}}

    # --- classify
    def _r_classify(self, a: dict[str, Any], purpose: str) -> tuple[dict[str, Any], str]:
        ids = {c["id"] for c in a["classes"]}
        if "private_sale_apt" in ids:
            return self._inclusion(a), "complexes.json inclusion(보고서 #62·#110)"
        if "open" in ids:
            return self._intake(a), "complexes.json 공식 경로 접수 행"
        return self._catalyst(a), "보고서 #64·#111 같은 이름 항목"

    @staticmethod
    def _cls(item_id: str, label: str | None, prob: float, decision: str) -> dict[str, Any]:
        if label is None:
            return {"id": item_id, "classification": None, "status": "invalid_response"}
        return {"id": item_id, "classification": label, "probabilities": {label: prob}, "top_probability": prob,
                "confidence": prob, "decision": decision}  # fmt: skip

    def _inclusion(self, a: dict[str, Any]) -> dict[str, Any]:
        out = []
        for it in a["items"]:
            cid = int(str(it["id"]).split(":")[1])
            cls, decision, prob = self.inclusion.get(cid, (None, "review", 0.0))
            out.append(self._cls(it["id"], cls, prob, decision if decision in ("auto", "review") else "review"))
        return {"results": out}

    def _intake(self, a: dict[str, Any]) -> dict[str, Any]:
        out = []
        for it in a["items"]:
            cid = int(str(it["id"]).split(":")[0].lstrip("c"))
            status = self.intake.get(cid)
            out.append(self._cls(it["id"], INTAKE_CLASS.get(status or ""), 0.9, "auto"))
        return {"results": out}

    def _catalyst(self, a: dict[str, Any]) -> dict[str, Any]:
        out = []
        for it in a["items"]:
            first = str(it["text"]).split("\n", 1)[0].removeprefix("호재: ").strip()
            hit = self.catalyst.get(first)
            if hit is None:
                out.append(self._cls(it["id"], None, 0.0, "review"))
            else:
                rec = hit[1]
                out.append(self._cls(it["id"], rec["label"], float(rec["prob"]), rec["decision"]))
        return {"results": out}

    # --- noul
    def _r_noul(self, a: dict[str, Any], purpose: str) -> tuple[dict[str, Any], str]:
        # purpose = noul:ladder:<horizon>:<target_ym>:c<id>
        parts = purpose.split(":")
        horizon, cid = parts[2], int(parts[-1].lstrip("c"))
        hit = self.ladder.get(cid) if horizon == "move_in_plus_1y" else None
        if hit is None:
            why = "보고서에 이 시점 사다리 없음(입주 후 1년만 판정)" if horizon != "move_in_plus_1y" else "보고서에 이 단지 사다리 없음"
            return {"status": "review", "results": []}, why
        seq, props = hit
        results = [
            {"id": f"proposition{i}", "proposition": text, "probability": p["prob"], "label": p["verdict"],
             "auto": p["decision"] == "auto"}
            for i, (text, p) in enumerate(zip(a["propositions"], props, strict=True))
        ]  # fmt: skip
        return {"status": "ok", "results": results}, f"보고서 #{seq} noul(입주 후 1년)"

    # --- rerank
    def _r_rerank(self, a: dict[str, Any], purpose: str) -> tuple[dict[str, Any], str]:
        cands = []
        for c in a["candidates"]:
            cid = int(str(c["id"]).split(":")[1])
            cands.append((c["id"], cid, self.rerank.get(cid, 0.0)))
        cands.sort(key=lambda x: (-x[2], self.rerank_order.get(x[1], 999), x[1]))
        ranked, prev_rel, rank = [], None, 0
        for pos, (oid, _cid, rel) in enumerate(cands, start=1):
            if rel != prev_rel:
                rank, prev_rel = pos, rel
            ranked.append({"rank": rank, "id": oid, "relevance": rel})
        return {"query": a["query"], "ranked": ranked}, "보고서 #124 relevance(같은 값 = 같은 순위)"

    # --- decide
    def _r_decide(self, a: dict[str, Any], purpose: str) -> tuple[dict[str, Any], str]:
        code = purpose.removeprefix("decide:scenario_")
        seq, env = self.decide.get(code, (None, None))
        cand_ids = [str(c["id"]) for c in a["candidates"]]  # complex_<n> · wait_new
        if env is None:
            body = self._decide(a)
            return body, "SynthJev 기본(보고서에 이 상황 없음)"
        res = env["result"]
        rprobs: dict[str, float] = res.get("probs") or {}
        rchecks: dict[str, dict[str, str]] = res.get("checks") or {}

        def opt(jev_id: str) -> str:  # complex_7 → complex:7
            return jev_id.replace("complex_", "complex:", 1) if jev_id.startswith("complex_") else jev_id

        probs = {jid: float(rprobs.get(opt(jid), 0.0)) for jid in cand_ids}
        for h in HATCHES:  # escape hatch(ask_user·investigate·none)는 payload 와 무관하게 판정기가 낼 수 있다
            if h in rprobs and h not in probs:
                probs[h] = float(rprobs[h])
        want = res.get("selected")
        selected = next((jid for jid in cand_ids if opt(jid) == want), None)
        if selected is None:  # 대체 선택(경고 경로)은 없다 — 보고서 선택이 후보에 없으면 녹화 실패(R3 마무리)
            raise RuntimeError(f"보고서 #{seq} 선택 '{want}'이(가) decide 후보 {cand_ids} 에 없음 — 합성 녹화 불가")
        confidence = env.get("confidence")
        warnings = list(res.get("warnings") or [])
        checks = [
            {"candidate": jid, "requirement": j, "answer": rchecks.get(opt(jid), {}).get(k, "unknown")}
            for jid in cand_ids for j, k in enumerate(REQ_KEYS[: len(a["requirements"])])
        ]  # fmt: skip
        body = {
            "recommendation": {"selected": selected, "escaped": False, "confidence": confidence, "probabilities": probs},
            "checks": checks,
            "warnings": warnings,
        }
        basis = f"보고서 #{seq} decide(선택·확률·확신도 그대로)"
        return body, basis

    # --- verify
    def _r_verify(self, a: dict[str, Any], purpose: str) -> tuple[dict[str, Any], str]:
        return self._verify(a), "보고서 §8-5·§12-5-5 최종 verify = verified(문장 1:1 대응 없음)"


# ---------------------------------------------------------------- 녹화 어댑터


class RecordingAdapter:
    """JudgeCaller — MockAdapter 와 같은 hash(adapter_version = 녹화 _meta)로 합성 봉투를 만들고 모은다.

    재생(MockAdapter + session_factory)과 똑같이 흐름 DB 의 judgment_log 에 남겨 judgment_seq 를 단다(``log_replay``) —
    그래야 녹화 흐름의 점수·순위(→ decide 후보)가 회귀·e2e 재생과 같다(R3 마무리). 녹화 파일의 봉투는 seq 없이 쓴다.
    """

    def __init__(self, jev: ReportSynthJev, store: dict[str, JudgmentEnvelope], runs: dict[str, set[str]], run: str,
                 session_factory: Callable[[], Any]) -> None:  # fmt: skip
        self.jev, self.store, self.runs, self.run = jev, store, runs, run
        self.session_factory = session_factory
        self.payloads: dict[str, Any] = {}

    @property
    def adapter_version(self) -> str:
        return ADAPTER_VERSION

    def close(self) -> None:
        return None

    def call(self, tool: JudgeTool, payload: JudgePayload, purpose: str, *, snapshot_id: int | None = None,
             complex_id: int | None = None) -> JudgmentEnvelope:  # fmt: skip
        key = cache.compute_hash(tool, purpose, payload, ADAPTER_VERSION)
        checked = guard.check_payload(payload, secrets=[])
        if not checked.ok:  # MockAdapter 도 재생 때 같은 blocked 봉투를 만든다 — 녹화하지 않는다
            raise RuntimeError(f"guard 차단 payload({tool} {purpose}) — 합성 녹화 대상 아님")
        self.runs.setdefault(key, set()).add(self.run)
        if key in self.store:
            hit = self.store[key].model_copy(update={"cached": True})
            return log_replay(self.session_factory, hit, payload, snapshot_id=snapshot_id, complex_id=complex_id)
        raw = self.jev.respond(tool, payload, purpose)
        norm = normalize(tool, raw, payload, purpose)
        env = JudgmentEnvelope(
            tool=tool, purpose=purpose, input_hash=key, input_len=cache.payload_length(payload), status=norm.status,
            confidence=norm.confidence, cached=False, result=norm.result, raw=raw, duration_ms=None, judgment_seq=None,
            created_at=KST_NOW, adapter_version=ADAPTER_VERSION, snapshot_id=snapshot_id, complex_id=complex_id,
            error_text=None,
        )  # fmt: skip
        self.store[key] = env
        PAYLOADS[key] = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        return log_replay(self.session_factory, env, payload, snapshot_id=snapshot_id, complex_id=complex_id)

    def __getattr__(self, name: str) -> Callable[[JudgePayload, str], JudgmentEnvelope]:
        if name in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify"):
            return lambda payload, purpose: self.call(name, payload, purpose)  # type: ignore[arg-type]
        raise AttributeError(name)


PAYLOADS: dict[str, Any] = {}


# ---------------------------------------------------------------- 흐름


def _settings(db: Path, base: Path) -> Any:
    from app.core.settings import Settings

    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",  # type: ignore[arg-type]
        database_url=f"sqlite:///{db.as_posix()}",
        raw_dir=base / "raw",
        reference_dir=base / "reference",
        report_dir=base / "reports",
        judge_adapter="mock",
        api_token=WRITE_TOKEN,  # type: ignore[arg-type]
        readonly_token=READ_TOKEN,  # type: ignore[arg-type]
        log_json=False,
        log_level="WARNING",
    )


def _offline_refresh(settings: Any) -> Callable[[date], dict[str, Any]]:
    import httpx

    from app.collectors.reference import ReferenceCollector
    from app.core.db import get_session
    from app.core.http import HttpClient

    def refresh(day: date) -> dict[str, Any]:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("[synth] offline", request=request)

        http = HttpClient(max_retries=0, jitter=0.0, sleep=lambda _s: None, transport=httpx.MockTransport(fail))
        try:
            rep = ReferenceCollector(http=http, session_factory=lambda: get_session(settings), raw_dir=settings.raw_dir,
                                     fallback_dir=REFERENCE, today=day).refresh()  # fmt: skip
        finally:
            http.close()
        return {"used_fallback": list(rep.used_fallback), "errors": list(rep.errors)}

    return refresh


def _ctx(settings: Any, adapter: RecordingAdapter | None) -> Any:
    from app.core.db import get_sessionmaker
    from app.core.time import KST
    from app.scheduler.context import default_context

    base = default_context(settings)
    now = datetime(TODAY.year, TODAY.month, TODAY.day, 6, 0, tzinfo=KST)
    return replace(
        base,
        session_factory=get_sessionmaker(settings),
        adapter_factory=(lambda: adapter) if adapter is not None else base.adapter_factory,
        collectors={},
        reference_refresh=_offline_refresh(settings),
        today=lambda: TODAY,
        now=lambda: now,
        worker_id="synth-recorder",
    )


def _seed(work: Path) -> Path:
    """devseed + reference.refresh(공식 사본) — 회귀 conftest·e2e 와 같은 공개 진입점."""
    from app.api import devseed
    from app.core.db import get_sessionmaker, reset_engine
    from app.core.settings import set_settings
    from app.scheduler import runner
    from app.scheduler.jobs import enqueue

    db = work / "seed.db"
    st = _settings(db, work)
    set_settings(st)
    try:
        devseed.seed(st, fixture_dir=FIXTURE, reference="region")
        with get_sessionmaker(st)() as s:
            enqueue(s, "reference.refresh", {})
            s.commit()
        assert runner.main(["--once"], ctx=_ctx(st, None)) == 0
    finally:
        set_settings(None)
        reset_engine()
    return db


def _run(seed: Path, work: Path, name: str, jev: ReportSynthJev, store: dict[str, JudgmentEnvelope],
         runs: dict[str, set[str]]) -> dict[str, Any]:  # fmt: skip
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core.db import get_sessionmaker, reset_engine
    from app.core.settings import set_settings
    from app.main import create_app
    from app.models import JobRun
    from app.scheduler import runner

    d = work / name
    d.mkdir()
    db = d / "run.db"
    shutil.copyfile(seed, db)
    st = _settings(db, work)
    set_settings(st)
    # 세션은 호출 때마다 지금 엔진에서(앱 수명 주기가 엔진을 닫고 다시 만들 수 있다 — 닫힌 엔진에 연결을 남기지 않게)
    adapter = RecordingAdapter(jev, store, runs, name, lambda: get_sessionmaker(st)())
    headers = {"Authorization": f"Bearer {WRITE_TOKEN}"}
    try:
        with TestClient(create_app(st), raise_server_exceptions=True) as client:
            if name == "full":
                job = {"job_name": "rejudge", "payload": {"snapshot_id": SNAPSHOT, "scenario_id": None, "complex_ids": None,
                                                          "reason": "합성 판정 녹화(WP9-후속 W2)"}}  # fmt: skip
            else:
                req = json.loads((FIXTURE / "raw" / "human_check" / "t3_switzen_possible.json").read_text(encoding="utf-8"))
                r = client.post("/api/ops/human-checks", headers=headers, json=req)
                assert r.status_code == 201, r.text
                # 계약 .9(D12-5): 재판정은 사람 확인이 자동 등록한다(rejudge_job_id) — 화면이 POST /jobs 하지 않는다
                assert r.json()["rejudge_job_id"], r.text
                job = None
            if job is not None:
                r = client.post("/api/jobs", headers=headers, json=job)
                assert r.status_code == 202, r.text
        assert runner.main(["--once"], ctx=_ctx(st, adapter)) == 0
        with get_sessionmaker(st)() as s:
            jobs = [(j.job_name, j.status, j.error_text) for j in s.scalars(select(JobRun).order_by(JobRun.id))]
        bad = [j for j in jobs if j[1] != "done"]
        assert not bad, bad
        return {"jobs": [j[0] for j in jobs]}
    finally:
        set_settings(None)
        reset_engine()


def build(out: Path) -> dict[str, Any]:
    """out(= judgments_synth 와 같은 구조의 디렉터리)에 녹화를 쓴다. 요약을 돌려준다."""
    import logging

    logging.disable(logging.WARNING)
    jev = ReportSynthJev()
    store: dict[str, JudgmentEnvelope] = {}
    runs: dict[str, set[str]] = {}
    PAYLOADS.clear()
    with tempfile.TemporaryDirectory(prefix="synth_judgments_") as tmp:
        work = Path(tmp)
        seed = _seed(work)
        summary = {name: _run(seed, work, name, jev, store, runs) for name in ("full", "t3")}
    jdir = out / "judgments"
    if out.exists():
        shutil.rmtree(out)
    jdir.mkdir(parents=True)
    index = []
    for key in sorted(store, key=lambda k: (store[k].tool, store[k].purpose, k)):
        env = store[key]
        hex_ = key.removeprefix("sha256:")
        path = jdir / env.tool / f"{hex_}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
        index.append({"tool": env.tool, "purpose": env.purpose, "input_hash": key, "file": f"{env.tool}/{hex_}.json",
                      "status": env.status, "complex_id": env.complex_id, "basis": (env.raw or {}).get("synth", {}).get("basis"),
                      "runs": sorted(runs.get(key, set())), "payload": PAYLOADS[key]})  # fmt: skip
    meta = {
        "adapter_version": ADAPTER_VERSION,
        "label": LABEL,
        "recorded_at": TODAY.isoformat(),
        "generator": "contracts/fixtures/tools/record_synth_judgments.py",
        "note": "합성 판정 녹화(CEO W2). 실제 파이프라인 payload hash 그대로, 값은 결정적 가짜 판정기(ReportSynthJev = WP7 SynthJev + "
                "보고서 수치). 실제 JEV 응답이 아니다 — R4 실호출 녹화로 교체 가능. adapter_version 은 judgments/_meta.json 과 같다"
                "(devseed judgment_log 와 버전이 같아야 mock 재판정이 '판정기 버전 변경'을 만들지 않는다).",
        "runs": {"full": "rejudge(스냅샷 12, 단지 전부, 시나리오 전부)", "t3": "사람 확인(스위첸 가능) → suggested_job rejudge [4]"},
        "counts": {t: sum(1 for r in index if r["tool"] == t) for t in sorted({r["tool"] for r in index})},
        "index": "_index.json = [{tool, purpose, input_hash, file, status, complex_id, basis, runs, payload}] — payload·purpose·"
                 "adapter_version 으로 app.core.protocols.input_hash 를 다시 계산하면 input_hash 와 같다.",
    }  # fmt: skip
    (jdir / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (jdir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    readme = OUT / "README.md"
    if readme.is_file() and out != OUT:
        shutil.copyfile(readme, out / "README.md")
    return {"envelopes": len(index), "counts": meta["counts"], "runs": summary,
            "status": {s: sum(1 for r in index if r["status"] == s) for s in sorted({r["status"] for r in index})}}  # fmt: skip


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="다시 만들어 커밋된 judgments_synth/ 와 바이트 비교")
    args = ap.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="synth_check_") as tmp:
            out = Path(tmp) / "judgments_synth"
            info = build(out)
            new, old = _files(out), _files(OUT)
            diff = sorted(k for k in set(new) | set(old) if new.get(k) != old.get(k))
        if diff:
            sys.stdout.write(f"judgments_synth 불일치 {len(diff)}개: {diff[:10]}\n")
            return 1
        sys.stdout.write(f"judgments_synth 일치 ({info['envelopes']}개 봉투)\n")
        return 0
    readme = OUT / "README.md"
    keep = readme.read_bytes() if readme.is_file() else None
    info = build(OUT)
    if keep is not None:
        readme.write_bytes(keep)
    sys.stdout.write(json.dumps(info, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
