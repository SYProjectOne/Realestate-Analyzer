"""JEV MCP 어댑터 (ADR-05, DECISIONS D6): stdio MCP 클라이언트 + 응답 정규화.

전송 (``McpStdioTransport``)
- ``JEV_MCP_CMD``(기본 ``npx -y @jkudish/jev-mcp@latest``)를 자식 프로세스로 띄워
  python ``mcp`` SDK 로 붙는다.
  프로세스는 한 번 띄워 재사용하고(호출마다 npx 기동 ≈2초를 피함), 실패하면 닫고 다음 호출에서 다시 띄운다.
- 메서드는 동기다(worker 스레드). 비동기 MCP 세션은 anyio blocking portal(전용 스레드의 이벤트 루프)에서 돈다.
- ``initialize`` 의 ``serverInfo.version`` → adapter_version (서버 버전이 바뀌면 모든 input_hash 가 바뀐다).
- 기동 실패·타임아웃·프로세스 사망·프로토콜 오류 → ``JudgeUnavailable`` (T18). 도구의 isError 응답은
  ``ToolResponse.is_error`` 로 돌려주고 어댑터가 error 행 + JudgeUnavailable 로 바꾼다.
- 자식 프로세스 환경변수는 MCP SDK 기본(PATH 등) + 판정기 자격 증명·설정(TYPESAFE_*, OPENROUTER_*, JEV_* …)만.
  DATA_GO_KR_KEY 같은 이 프로그램의 비밀값은 넘기지 않는다.

정규화 (``normalize``) — 실제 JEV 0.14.1 응답 모양(tests/judge/fixtures/jev_samples.json) 기준
| 도구 | JEV 응답 | 봉투 status |
| --- | --- | --- |
| screen | recommendation.action pass/skip/review/block | pass·skip→ok, block→blocked, review·invalid→review |
| extract | results[].status auto/review/not_found/invalid_* | 필드 decision; invalid_* 있으면 review |
| audit | action pass/escalate/review, records[].action | pass→ok, escalate→ok(flagged); invalid→review |
| classify | results[].decision auto/review, classification | auto→ok; review·manual_review·invalid→review |
| compare | overall.relation + decision | auto→ok; review·invalid→review |
| noul | status ok/invalid_response, results[].probability·label·auto | ok→ok; invalid→review |
| rerank | ranked[] 또는 status invalid_response | ok / review |
| decide | recommendation.selected·escaped·confidence, checks[] | escaped→escaped; invalid·escalate→review |
| verify | results[].verdict·action·status | ok; invalid 있으면 review (주장별은 verdict='review') |
임계값은 넘기지 않으며(JEV 기본값), 응답에 담긴 thresholds·decision 은 raw(output_json)에 그대로 남는다.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import tempfile
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractContextManager
from typing import Any, Final

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal

from app.core.protocols import JudgePayload, JudgeTool, JudgeUnavailable
from app.core.redact import redact_text
from app.judge.base import CachedJudgeAdapter, Normalized, SessionFactory, Status, ToolResponse, Transport

__all__ = [
    "DEFAULT_STARTUP_TIMEOUT_S",
    "DEFAULT_TIMEOUT_S",
    "JevMcpAdapter",
    "McpStdioTransport",
    "normalize",
    "split_command",
    "subprocess_env",
]

DEFAULT_TIMEOUT_S: Final = 120.0
DEFAULT_STARTUP_TIMEOUT_S: Final = 300.0  # 첫 npx 다운로드 포함
REQUIREMENT_KEYS: Final = ("access", "regulation", "funds")
ESCAPE_HATCHES: Final = ("ask_user", "investigate", "none")
NOUL_KEYS: Final = ("p5", "p10", "p20", "p_flat")
_FORWARD_PREFIXES: Final = (
    "JEV_",
    "TYPESAFE_",
    "OPENROUTER_",
    "AI_GATEWAY_",
    "CLOUDFLARE_",
    "NODE_",
    "NPM_CONFIG_",
)
_FORWARD_NAMES: Final = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY"})
_NEVER_FORWARD: Final = frozenset({"JEV_MCP_CMD", "JEV_MCP_TRANSPORT"})
_COMPLEX_ID_RE = re.compile(r"^complex[:_](\d+)$")
_LADDER_PURPOSE_RE = re.compile(
    r"^noul:ladder:(move_in_plus_1y|asof_plus_3y|asof_plus_5y):(\d{4}-\d{2})(?::|$)"
)
_STDERR_TAIL = 300

# ====================================================================== 전송


def split_command(cmd: str) -> list[str]:
    """``JEV_MCP_CMD`` → argv. Windows 경로의 역슬래시를 지키려고 nt 에서는 비POSIX 분리 + 따옴표 제거."""
    if os.name == "nt":
        parts = [
            p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p
            for p in shlex.split(cmd, posix=False)
        ]
    else:
        parts = shlex.split(cmd)
    if not parts:
        raise ValueError("JEV_MCP_CMD 가 비어 있다")
    return parts


def subprocess_env() -> dict[str, str]:
    """MCP SDK 기본 환경 + 판정기 자격 증명·설정만. 이 프로그램의 비밀값(DATA_GO_KR_KEY 등)은 빼고."""
    from mcp.client.stdio import get_default_environment

    env = dict(get_default_environment())
    for name, value in os.environ.items():
        upper = name.upper()
        if upper in _NEVER_FORWARD:
            continue
        if upper.startswith(_FORWARD_PREFIXES) or upper in _FORWARD_NAMES:
            env[name] = value
    return env


async def _timed[R](fn: Callable[[], Awaitable[R]], timeout_s: float) -> R:
    with anyio.fail_after(timeout_s):
        return await fn()


class McpStdioTransport:
    """stdio MCP 연결 1개(자식 프로세스 1개). 스레드 안전(호출은 한 번에 하나)."""

    def __init__(
        self,
        cmd: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        startup_timeout_s: float = DEFAULT_STARTUP_TIMEOUT_S,
        env: dict[str, str] | None = None,
    ) -> None:
        self._argv = split_command(cmd)
        self._timeout_s = timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._env = env
        self._lock = threading.RLock()
        self._portal_cm: AbstractContextManager[BlockingPortal] | None = None
        self._portal: BlockingPortal | None = None
        self._stdio_cm: AbstractContextManager[Any] | None = None
        self._session_cm: AbstractContextManager[Any] | None = None
        self._session: Any = None
        self._errlog: Any = None
        self._server_version: str | None = None

    # ------------------------------------------------------------------ 공개

    def server_version(self) -> str:
        with self._lock:
            self._ensure()
            assert self._server_version is not None
            return self._server_version

    def list_tool_names(self) -> list[str]:
        with self._lock:
            session = self._ensure()
            try:
                result = self._run(lambda: session.list_tools(), self._timeout_s)
            except Exception as exc:
                self._teardown()
                raise JudgeUnavailable(f"tools/list 실패: {type(exc).__name__}") from exc
            return [t.name for t in result.tools]

    def call(self, tool_name: str, arguments: JudgePayload) -> ToolResponse:
        with self._lock:
            session = self._ensure()
            t0 = time.monotonic()
            try:
                result = self._run(lambda: session.call_tool(tool_name, arguments), self._timeout_s)
            except Exception as exc:
                self._teardown()
                kind = "timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
                raise JudgeUnavailable(f"{tool_name}: {kind}") from exc
            duration_ms = int((time.monotonic() - t0) * 1000)
            is_error = bool(getattr(result, "is_error", getattr(result, "isError", False)))
            return ToolResponse(raw=_parse_content(result), is_error=is_error, duration_ms=duration_ms)

    def close(self) -> None:
        with self._lock:
            self._teardown()

    # ------------------------------------------------------------------ 내부

    def _run[R](self, fn: Callable[[], Awaitable[R]], timeout_s: float) -> R:
        assert self._portal is not None
        return self._portal.call(_timed, fn, timeout_s)

    def _ensure(self) -> Any:
        if self._session is not None:
            return self._session
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        exe = shutil.which(self._argv[0]) or self._argv[0]
        params = StdioServerParameters(
            command=exe, args=self._argv[1:], env=self._env if self._env is not None else subprocess_env()
        )
        try:
            # 프로세스 수명 동안 열어 둔다(_teardown 이 닫음)
            self._errlog = tempfile.TemporaryFile(  # noqa: SIM115
                "w+", encoding="utf-8", errors="replace"
            )
            self._portal_cm = start_blocking_portal()
            self._portal = self._portal_cm.__enter__()
            self._stdio_cm = self._portal.wrap_async_context_manager(
                stdio_client(params, errlog=self._errlog)
            )
            read, write = self._stdio_cm.__enter__()
            self._session_cm = self._portal.wrap_async_context_manager(ClientSession(read, write))
            session = self._session_cm.__enter__()
            init = self._run(lambda: session.initialize(), self._startup_timeout_s)
        except Exception as exc:
            tail = self._stderr_tail()
            self._teardown()
            detail = f"; stderr: {tail}" if tail else ""
            raise JudgeUnavailable(f"판정기 기동 실패({type(exc).__name__}){detail}") from exc
        info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
        self._server_version = str(getattr(info, "version", "") or "unknown")
        self._session = session
        return session

    def _stderr_tail(self) -> str:
        if self._errlog is None:
            return ""
        try:
            self._errlog.flush()
            self._errlog.seek(0)
            text = str(self._errlog.read())
        except (OSError, ValueError):
            return ""
        return redact_text(" ".join(text.split())[-_STDERR_TAIL:])

    def _teardown(self) -> None:
        # 이미 죽은 프로세스를 정리하다 나는 오류는 무시한다
        for cm in (self._session_cm, self._stdio_cm, self._portal_cm):
            if cm is not None:
                with contextlib.suppress(BaseException):
                    cm.__exit__(None, None, None)
        if self._errlog is not None:
            with contextlib.suppress(OSError):
                self._errlog.close()
        self._session = self._session_cm = self._stdio_cm = None
        self._portal = self._portal_cm = None
        self._errlog = None
        self._server_version = None


def _parse_content(result: Any) -> dict[str, Any]:
    """CallToolResult.content 의 첫 text 블록(JEV 는 JSON 문자열 하나) → dict."""
    texts = [getattr(c, "text", None) for c in getattr(result, "content", []) or []]
    text = next((t for t in texts if isinstance(t, str)), None)
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if text is None:
        return dict(structured) if isinstance(structured, dict) else {"error": "empty response"}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"error": text[:500]}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


# ====================================================================== 어댑터


class JevMcpAdapter(CachedJudgeAdapter):
    """JudgeAdapter 실구현. ``transport`` 가 있으면 그것(테스트), 없으면 ``cmd``(기본 JEV_MCP_CMD)."""

    def __init__(
        self,
        cmd: str | None = None,
        *,
        transport: Transport | None = None,
        session_factory: SessionFactory | None = None,
        secrets: Sequence[str] | None = None,
        timeout_s: float | None = None,
        startup_timeout_s: float | None = None,
    ) -> None:
        if transport is None:
            from app.core.settings import get_settings

            s = get_settings()
            transport = McpStdioTransport(
                cmd if cmd is not None else s.jev_mcp_cmd,
                timeout_s=timeout_s if timeout_s is not None else s.judge_call_timeout_s,
                startup_timeout_s=startup_timeout_s
                if startup_timeout_s is not None
                else s.judge_start_timeout_s,
            )
        super().__init__(transport, session_factory=session_factory, secrets=secrets)

    def normalize(
        self, tool: JudgeTool, raw: dict[str, Any], payload: JudgePayload, purpose: str
    ) -> Normalized:
        return normalize(tool, raw, payload, purpose)


# ====================================================================== 정규화


def normalize(tool: JudgeTool, raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    """JEV 원응답 → (status, result, confidence). 순수 함수(캐시 행에서 다시 만들어도 같은 값)."""
    fn = _NORMALIZERS.get(tool)
    if fn is None:
        raise ValueError(f"알 수 없는 도구: {tool!r}")
    return fn(raw, payload or {}, purpose)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _min_conf(values: list[Any]) -> float | None:
    nums = [v for v in (_num(x) for x in values) if v is not None]
    return min(nums) if nums else None


def _complex_id(candidate_id: Any) -> int | None:
    m = _COMPLEX_ID_RE.match(str(candidate_id))
    return int(m.group(1)) if m else None


def _option_id(jev_id: Any) -> str:
    """decide 후보 slug ``complex_7`` → 계약 option id ``complex:7``. 그 밖(wait_new, ask_user…)은 그대로."""
    cid = _complex_id(jev_id)
    return f"complex:{cid}" if cid is not None and str(jev_id).startswith("complex_") else str(jev_id)


def _screen(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    probs = raw.get("probabilities") or {}
    action = (raw.get("recommendation") or {}).get("action")
    scores = {k: _num(probs.get(k)) for k in ("injection", "substance", "relevance")}
    if raw.get("status") == "invalid_response" or action not in {"pass", "skip", "block"}:
        return Normalized("review", {"verdict": None, **scores, "action": action})
    status: Status = "blocked" if action == "block" else "ok"
    return Normalized(status, {"verdict": action, **scores})


def _extract(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    fields: list[dict[str, Any]] = []
    invalid = raw.get("status") == "invalid_response"
    for r in raw.get("results") or []:
        jev_status = r.get("status")
        if jev_status in {"invalid_pattern", "invalid_response"}:
            invalid = True
        decision = "auto" if jev_status in {"auto", "not_found"} else "review"
        value = r.get("value")
        fields.append(
            {
                "name": str(r.get("id")),
                "value_text": value if isinstance(value, str) else None,
                "decision": decision,
                "confidence": _num(r.get("confidence")),
                "excerpt": None,
            }
        )
    status: Status = "review" if invalid or not fields else "ok"
    return Normalized(status, {"fields": fields}, _min_conf([f["confidence"] for f in fields]))


def _audit(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    items: list[dict[str, Any]] = []
    invalid = False
    for r in raw.get("records") or []:
        action = r.get("action")
        if action == "invalid_response" or r.get("status") == "invalid_response":
            invalid = True
        p_wrong = _num(r.get("p_wrong"))
        items.append(
            {
                "field": str(r.get("id")),
                "p_wrong": p_wrong,  # 판정기가 안 주면 null(계약 2026-10-09.2)
                "flagged": action != "ok",
                "note": None if action == "ok" else str(action),
            }
        )
    overall = raw.get("action")
    if invalid or overall not in {"pass", "escalate"} or not items:
        return Normalized("review", {"verdict": "flagged", "items": items})
    verdict = "pass" if overall == "pass" else "flagged"
    return Normalized("ok", {"verdict": verdict, "items": items})


def _classify_one(r: dict[str, Any]) -> tuple[Status, dict[str, Any]]:
    label = r.get("classification")
    probs = r.get("probabilities") or {}
    if r.get("status") == "invalid_response" or label is None:
        return "review", {"label": "", "prob": 0.0, "decision": "review", "distribution": probs or {}}
    top = _num(r.get("top_probability"))
    prob = top if top is not None else (_num(probs.get(label)) or 0.0)
    decision = r.get("decision") if r.get("decision") in {"auto", "review"} else "review"
    if label == "manual_review":
        decision = "manual_review"
    status: Status = "ok" if decision == "auto" else "review"
    return status, {"label": str(label), "prob": prob, "decision": decision, "distribution": probs}


def _classify(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    results = raw.get("results") or []
    if not results:
        return Normalized("review", {"label": "", "prob": 0.0, "decision": "review"})
    graded = [_classify_one(r) for r in results]
    status, result = graded[0]
    if len(graded) > 1:
        # 배치(계약 2026-10-09.2 ClassifyResult.items): 최상위는 요약, 항목별 decision 으로 거른다.
        items = [{"id": r.get("id"), **g[1]} for r, g in zip(results, graded, strict=True)]
        auto = sum(1 for it in items if it["decision"] == "auto")
        result = {
            "label": "batch",
            "prob": round(auto / len(items), 4),
            "decision": "auto" if auto == len(items) else "review",
            "items": items,
        }
        valid = all(
            r.get("status") != "invalid_response" and r.get("classification") is not None for r in results
        )
        status = "ok" if valid else "review"
        return Normalized(status, result, _min_conf([_num(r.get("confidence")) for r in results]))
    return Normalized(status, result, _num(results[0].get("confidence")))


def _relation(block: dict[str, Any]) -> tuple[str, float | None, bool]:
    rel = block.get("relation")
    probs = block.get("probabilities") or {}
    ok = rel is not None and block.get("decision") == "auto" and block.get("status") != "invalid_response"
    return (str(rel) if rel is not None else "review"), _num(probs.get(rel)) if rel else None, ok


def _compare(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    overall = raw.get("overall") or {}
    rel, prob, ok = _relation(overall)
    aspects = []
    for a in raw.get("aspects") or []:
        arel, aprob, aok = _relation(a)
        aspects.append({"aspect": str(a.get("aspect")), "relation": arel if aok else "review", "prob": aprob})
    status: Status = "ok" if ok else "review"
    return Normalized(
        status, {"overall": rel, "prob": prob, "aspects": aspects}, _num(overall.get("confidence"))
    )


def _noul(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    results = raw.get("results") or []
    keys = NOUL_KEYS if len(results) == len(NOUL_KEYS) else tuple(f"q{i}" for i in range(len(results)))
    props = []
    for key, r in zip(keys, results, strict=True):
        label = r.get("label")
        props.append(
            {
                "key": key,
                "text": str(r.get("proposition") or ""),
                "prob": _num(r.get("probability")),
                "verdict": label if label in {"likely", "uncertain", "unlikely"} else None,
                "decision": "auto" if r.get("auto") is True else "review",
            }
        )
    result: dict[str, Any] = {"propositions": props}
    m = _LADDER_PURPOSE_RE.match(purpose)
    if m:
        result = {"horizon": m.group(1), "target_ym": m.group(2), **result}
    valid = (
        raw.get("status") == "ok"
        and bool(props)
        and all(p["prob"] is not None and p["verdict"] for p in props)
    )
    return Normalized("ok" if valid else "review", result)


def _rerank(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    ranked = raw.get("ranked")
    query = str(raw.get("query") or payload.get("query") or "")
    if raw.get("status") == "invalid_response" or not isinstance(ranked, list):
        return Normalized("review", {"query": query, "items": []})
    items = [
        {
            "candidate_id": str(r.get("id")),
            "complex_id": _complex_id(r.get("id")),
            "relevance": _num(r.get("relevance")) or 0.0,
            "rank": int(r.get("rank") or i + 1),
        }
        for i, r in enumerate(ranked)
    ]
    return Normalized("ok", {"query": query, "items": items})


def _decide(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    rec = raw.get("recommendation") or {}
    requirements = payload.get("requirements") or []
    req_keys = list(REQUIREMENT_KEYS[: len(requirements)]) if requirements else []
    checks: dict[str, dict[str, str]] = {}
    invalid_check = False
    for c in raw.get("checks") or []:
        j = c.get("requirement")
        if not isinstance(j, int) or not 0 <= j < len(req_keys):
            continue
        answer = c.get("answer")
        if answer not in {"supported", "contradicted", "unknown"}:
            invalid_check = True
            answer = "unknown"
        checks.setdefault(_option_id(c.get("candidate")), {})[req_keys[j]] = str(answer)
    selected_raw = rec.get("selected")
    selected = _option_id(selected_raw) if selected_raw is not None else None
    probs = {_option_id(k): v for k, v in (rec.get("probabilities") or {}).items() if _num(v) is not None}
    escaped = rec.get("escaped") is True
    result = {
        "selected": selected,
        "probs": probs,
        "checks": checks,
        "warnings": [str(w) for w in raw.get("warnings") or []],
        "escaped": escaped,
        "question": f"판정기가 결정을 보류했습니다({selected}): 사람 확인 필요" if escaped else None,
    }
    conf = _num(rec.get("confidence"))
    if (
        rec.get("status") in {"invalid_response", "escalate"}
        or (selected is None and not escaped)
        or invalid_check
    ):
        return Normalized("review", result, conf)
    return Normalized("escaped" if escaped else "ok", result, conf)


def _verify(raw: dict[str, Any], payload: JudgePayload, purpose: str) -> Normalized:
    claims = []
    invalid = False
    for i, r in enumerate(raw.get("results") or []):
        verdict = r.get("verdict")
        if r.get("status") == "invalid_response" or verdict not in {
            "verified",
            "contradicted",
            "unsupported",
        }:
            invalid = True
            verdict = "review"
        elif r.get("action") != "auto":
            verdict = "review"
        claims.append(
            {
                "claim_id": str(i),
                "verdict": verdict,
                "confidence": _num(r.get("confidence")),
                "action": r.get("action"),
            }
        )
    status: Status = "review" if invalid or not claims else "ok"
    return Normalized(status, {"claims": claims}, _min_conf([c["confidence"] for c in claims]))


_NORMALIZERS: dict[str, Callable[[dict[str, Any], JudgePayload, str], Normalized]] = {
    "screen": _screen,
    "extract": _extract,
    "audit": _audit,
    "classify": _classify,
    "compare": _compare,
    "noul": _noul,
    "rerank": _rerank,
    "decide": _decide,
    "verify": _verify,
}
