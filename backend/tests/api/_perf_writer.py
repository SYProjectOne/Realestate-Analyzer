"""D14-5 성능 시험의 API 쓰기 프로세스(R3h) — 운영처럼 api 와 worker 를 **다른 프로세스**로 둔다.

``python tests/api/_perf_writer.py <db> <raw_dir> <report_dir> <out.json> <ready_file> <stop_file>``: 같은 SQLite 파일에 실제 API
쓰기(``POST /api/share-links``)를 50ms 간격으로 보내고 응답 시간을 잰다. 준비되면 ``ready_file`` 을 만들고, ``stop_file`` 이 생기면
요청마다 [시작 뒤 초, 전체 지연, SQL 실행 최대(쓰기 잠금 대기 포함), COMMIT 시간(자동 체크포인트 포함), 상태 코드] 를
``out.json`` 에 쓰고 끝난다 — 느린 요청이 잠금 대기인지·커밋(체크포인트·fsync)인지·그 밖(CPU)인지 나눠 보인다.

같은 프로세스의 스레드로 재면 잡의 계산(파이썬 GIL·GC)이 API 스레드를 멈춰 쓰기 잠금과 무관한 지연이 섞였다(R3h 측정: 0.4~2.3s —
WAL 크기 변화 없이 계산 구간에서만). 운영 compose 는 api·worker 가 다른 컨테이너다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def main(argv: list[str]) -> int:
    db, raw_dir, report_dir, out, ready, stop = (Path(a) for a in argv[:6])
    from fastapi.testclient import TestClient

    from app.core.db import get_engine
    from app.core.settings import Settings, set_settings
    from app.main import create_app

    write_token, read_token = "w" * 32, "r" * 32
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=f"sqlite:///{db.as_posix()}",
        raw_dir=raw_dir,
        reference_dir=db.parent / "reference",
        report_dir=report_dir,
        judge_adapter="mock",
        api_token=write_token,  # type: ignore[arg-type]
        readonly_token=read_token,  # type: ignore[arg-type]
        log_json=False,
        # 요청마다 남는 INFO 로그(stderr → 디스크 파일)는 측정 대상이 아니다 — 디스크 부하에서 그 쓰기가 요청을 늦춘다
        log_level="WARNING",
    )
    set_settings(settings)
    cur: dict[str, float] = {"exec": 0.0, "commit": 0.0}
    engine = get_engine()
    dialect: Any = engine.dialect
    real_execute, real_commit = dialect.do_execute, dialect.do_commit

    def timed_execute(cursor: Any, statement: Any, parameters: Any, context: Any = None) -> Any:
        t = time.perf_counter()
        try:
            return real_execute(cursor, statement, parameters, context)
        finally:
            cur["exec"] = max(cur["exec"], time.perf_counter() - t)

    def timed_commit(dbapi_connection: Any) -> Any:
        t = time.perf_counter()
        try:
            return real_commit(dbapi_connection)
        finally:
            cur["commit"] += time.perf_counter() - t

    dialect.do_execute, dialect.do_commit = timed_execute, timed_commit
    rows: list[list[float]] = []
    headers = {"Authorization": f"Bearer {write_token}"}
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        c.post("/api/share-links", json={"label": "warmup"}, headers=headers)
        ready.write_text("ok", encoding="utf-8")
        t0 = time.perf_counter()
        while not stop.exists():
            cur["exec"], cur["commit"] = 0.0, 0.0
            t = time.perf_counter()
            r = c.post("/api/share-links", json={"label": "perf"}, headers=headers)
            rows.append(
                [round(t - t0, 3), time.perf_counter() - t, cur["exec"], cur["commit"], r.status_code]
            )
            time.sleep(0.05)
    out.write_text(json.dumps(rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
