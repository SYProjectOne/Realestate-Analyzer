# ruff: noqa: E501
"""devseed 다음 단계: ``reference.refresh`` 잡을 네트워크 없이 1회(공식 사본 contracts/fixtures/reference).

    cd backend && uv run python ../e2e/support/reference_offline.py      # DATABASE_URL·RAW_DIR 은 환경변수

devseed(``--reference region``)는 법정동·행정동·매핑만 넣고 주민등록 세대 현황(household_stat)은 넣지 않는다 →
재판정 때 공급 점수(생활권 세대수)가 '확인 불가'가 되어 종합 점수가 전부 미계산이 된다. 운영에서는 worker 기동 시
reference.refresh 가 채우므로, e2e 도 같은 잡을 큐에 넣고 worker 진입점(runner.main --once)으로 처리한다.
수집기 HTTP 는 전부 ConnectError → ReferenceCollector 가 사본으로 적재(운영 폴백 경로 그대로).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from offline import offline_transport

from app.collectors.reference import ReferenceCollector
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.settings import get_settings
from app.models import JobRun
from app.scheduler import runner
from app.scheduler.context import default_context
from app.scheduler.jobs import enqueue

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "contracts" / "fixtures" / "reference"


def refresh(day: date) -> dict[str, Any]:
    http = HttpClient(max_retries=0, jitter=0.0, sleep=lambda _s: None, transport=offline_transport())
    try:
        rep = ReferenceCollector(http=http, fallback_dir=REFERENCE, today=day).refresh()
    finally:
        http.close()
    return {"used_fallback": list(rep.used_fallback), "household_ym": rep.household_ym}


def main() -> int:
    settings = get_settings()
    with get_session(settings) as s:
        job_id = enqueue(s, "reference.refresh", {}).id
    ctx = replace(default_context(settings), collectors={}, reference_refresh=refresh)
    runner.main(["--once"], ctx=ctx)
    with get_session(settings) as s:
        job = s.get(JobRun, job_id)
        status = job.status if job else None
        stats = job.stats if job else None
    sys.stdout.write(f"reference_offline: job {job_id} {status} {stats}\n")
    return 0 if status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
