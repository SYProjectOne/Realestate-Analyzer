"""R4-FIX C1 (D18-2) — G7 ``real_calls`` 는 판정기로 실제 보낸 tools/call 수(잡 stats 전송 계층 계수)를 쓴다.

R4: 2회차 judgment_log 새 행 0 인데 tools/call 298 — 옛 G7 은 행 수만 세어 0 으로 보였다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.core.db import get_session
from app.models import JobRun

from ._support import WRITE, validate


def _job(stats: dict[str, object]) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with get_session() as s:
        s.add(
            JobRun(
                job_name="rejudge", kind="rejudge", payload={}, scheduled_at=now, started_at=now,
                finished_at=now, status="done", stats=stats,
            )
        )  # fmt: skip


def test_real_calls_count_hidden_tools_calls(client: TestClient) -> None:
    before = client.get("/api/ops/judgments", headers=WRITE).json()["stats"]
    logged = before["real_calls"]
    # 1회차: 행 수와 같은 tools/call · 2회차: 새 행 0 인데 tools/call 298(R4 숨은 호출)
    _job({"tools_calls": logged, "tools_calls_by_tool": {}, "cached": 0})
    _job(
        {
            "tools_calls": 298,
            "tools_calls_by_tool": {"extract": 149, "screen": 148, "classify": 1},
            "cached": 434,
        }
    )
    body = client.get("/api/ops/judgments", headers=WRITE).json()
    validate("getJudgmentOps", 200, body)
    stats = body["stats"]
    assert stats["real_calls"] == logged + 298, "실제 호출 = 보낸 tools/call 수(행 수가 아니라)"
    assert stats["total_calls"] == stats["real_calls"] + stats["cached_hits"]
    extract = client.get("/api/ops/judgments", params={"tool": "extract"}, headers=WRITE).json()["stats"]
    assert extract["real_calls"] >= 149


def test_real_calls_falls_back_to_rows_without_meter(client: TestClient) -> None:
    """계수가 없는 옛 잡·MockAdapter 재생만 있으면 행 수(blocked 제외)가 실제 호출이다."""
    body = client.get("/api/ops/judgments", headers=WRITE).json()
    stats = body["stats"]
    assert stats["real_calls"] == body["total"] - stats["blocked"]
