"""D14-5 성능 시험의 API 쓰기 프로세스(R3h) — 운영처럼 api 와 worker 를 **다른 프로세스**로 둔다.

``python tests/api/_perf_writer.py <db> <raw_dir> <report_dir> <out.json> <ready_file> <stop_file>``: 같은 SQLite 파일에 실제 API
쓰기(``POST /api/share-links``)를 50ms 간격으로 보내고 응답 시간을 잰다. 준비되면 ``ready_file`` 을 만들고, ``stop_file`` 이 생기면
[[시작 뒤 초, 지연 초, 상태 코드], …] 를 ``out.json`` 에 쓰고 끝난다.

같은 프로세스의 스레드로 재면 잡의 계산(파이썬 GIL·GC)이 API 스레드를 멈춰 쓰기 잠금과 무관한 지연이 섞였다(R3h 측정: 0.4~2.3s —
WAL 크기 변화 없이 계산 구간에서만). 운영 compose 는 api·worker 가 다른 컨테이너다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    db, raw_dir, report_dir, out, ready, stop = (Path(a) for a in argv[:6])
    from fastapi.testclient import TestClient

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
    )
    set_settings(settings)
    rows: list[list[float]] = []
    headers = {"Authorization": f"Bearer {write_token}"}
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        c.post("/api/share-links", json={"label": "warmup"}, headers=headers)
        ready.write_text("ok", encoding="utf-8")
        t0 = time.perf_counter()
        while not stop.exists():
            t = time.perf_counter()
            r = c.post("/api/share-links", json={"label": "perf"}, headers=headers)
            rows.append([round(t - t0, 3), time.perf_counter() - t, r.status_code])
            time.sleep(0.05)
    out.write_text(json.dumps(rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
