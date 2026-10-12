# ruff: noqa: E501
"""``python -m app.worker --once`` 의 오프라인 대역 — 수집기를 녹화 재생으로 바꿔 끼운 같은 진입점(runner.main).

    cd backend && uv run python ../e2e/support/replay_worker.py      # DATABASE_URL 등은 환경변수(e2e/env.ts)

왜 필요한가(WP9 발견): worker CLI 에는 녹화 재생·오프라인 모드가 없다. 수집기 팩토리(app/scheduler/context.py
``default_collectors``)가 ``HttpClient()``를 직접 만들고 설정·환경변수로 전송을 바꿀 길이 없다 → 그대로 돌리면
실제 사이트에 접속한다. 그래서 e2e 는 같은 ``runner.main(["--once"], ctx=…)`` 에 다음 문맥을 넣는다:

| 키 | 수집기 | 전송 |
| --- | --- | --- |
| applyhome | ApplyhomeCollector(web 경로, today=녹화일 2026-10-09) | 청약홈 웹 녹화 재생(WP1a zip) |
| notice_pdf | NoticePdfCollector | 오프라인(ConnectError → 실패 행) |
| official_site | 빈 결과 | (Playwright 렌더 폴백이 실제 접속을 하므로 넣지 않는다) |
| stats | UnsoldCollector | 오프라인(실패 행) |
| rtms·news | 기본(키 없으면 비활성) | — |

판정기는 설정 그대로(JUDGE_ADAPTER=mock). 시계는 녹화일(목록 조회 창이 녹화와 같아야 한다).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from offline import offline_transport, replay_transport

from app.collectors.applyhome import ApplyhomeCollector
from app.collectors.notice_pdf import NoticePdfCollector
from app.collectors.stats import UnsoldCollector
from app.core.http import HttpClient
from app.core.settings import get_settings
from app.core.time import KST
from app.scheduler import runner
from app.scheduler.context import default_collectors, default_context, recorded_window

REPO = Path(__file__).resolve().parents[2]
RECORDING = REPO / "backend" / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_2026-10-09.zip"
TODAY = date(2026, 10, 9)


class _Empty:
    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        return []


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    replay = replay_transport(RECORDING)

    def client(transport: Any) -> HttpClient:
        return HttpClient(max_retries=0, jitter=0.0, rate_per_host=1000.0, sleep=lambda _s: None, transport=transport)

    web = client(replay)
    off = client(offline_transport())
    base = default_collectors()
    collectors = {
        # 계약 .15 기본 조회 창(지난 24 + 향후 12개월)은 녹화에 없다 — 녹화 때 창으로 재생(R4-FIX D20-1)
        "applyhome": lambda c: ApplyhomeCollector(
            http=web, today=lambda: TODAY, service_key=None, window=recorded_window(RECORDING)
        ),
        "notice_pdf": lambda c: NoticePdfCollector(http=off, ocr=None),
        "official_site": lambda c: _Empty(),
        "stats": lambda c: UnsoldCollector(http=off),
        "rtms": base["rtms"],
        "news": base["news"],
    }
    ctx = replace(
        default_context(settings),
        collectors=collectors,
        today=lambda: TODAY,
        now=lambda: datetime(TODAY.year, TODAY.month, TODAY.day, 6, 0, tzinfo=KST),
        worker_id="e2e-replay",
    )
    try:
        code = runner.main(["--once", *(argv or [])], ctx=ctx)
    finally:
        web.close()
        off.close()
    misses = getattr(replay, "misses", [])
    sys.stdout.write(f"replay_worker: exit={code} replay_misses={len(misses)}\n")
    for m in misses[:10]:
        sys.stdout.write(f"  miss: {m}\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
