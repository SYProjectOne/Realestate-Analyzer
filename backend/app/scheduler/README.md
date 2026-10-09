# app/scheduler

- **주인**: WP7
- **읽기 허용**: — (다른 WP 는 읽지 않는다)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§4-4·§5, DECISIONS D2-4)

잡 정의·실행: `jobs.py`(`collect.daily` 06:00, `collect.weekly` 월 06:30, `reference.refresh`, `region.bootstrap`,
`rejudge`, `report`, `snapshot.publish`), `runner.py`(job_run polling, 락), `detect.py`, `rejudge.py`,
`notify.py`(`WEBHOOK_URL` 이 비면 보내지 않음), `degraded.py`.

## 연결 방법 (WP0 뼈대와의 접점)

- `app/scheduler/runner.py` 에 `def main(argv: list[str] | None = None) -> int` 를 두면
  `python -m app.worker [args]` 가 인자 목록을 그대로 넘겨 위임한다. `--once`(한 번 돌고 종료)를 지원할 것 —
  운영 점검과 CI 가 `python -m app.worker --once` 를 쓴다.
- 없으면 worker 는 heartbeat 로그만 남긴다.
- 로그는 `app.core.logging.configure_logging()` 이 worker 시작 시 이미 설정한다.

## 규칙

- 이 디렉터리와 `backend/tests/scheduler/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
