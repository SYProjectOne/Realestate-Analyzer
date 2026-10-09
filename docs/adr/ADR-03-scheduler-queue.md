# ADR-03 스케줄·큐

- 상태: 채택 (RA v1 §1, §4-4, DECISIONS D2-4)
- 결정: **worker 프로세스 안 APScheduler + DB `job_run` 테이블이 큐**
- 버린 대안: Celery + Redis

## 이유

- 프로세스 하나를 줄인다(Redis 없음).
- 작업 상태가 DB 에 있으니 화면(G7)에 바로 보인다.
- api 는 판정기를 직접 부르지 않고 `job_run` 행만 넣는다 → "판단은 판정기, 프로그램은 기록" 이 프로세스 경계가 된다.

## 결과

- 잡: `collect.daily`(06:00), `collect.weekly`(월 06:30), `rejudge`, `report`, `snapshot.publish`,
  `reference.refresh`(월 1일 05:00), `region.bootstrap`.
- `python -m app.worker` 는 `app.scheduler.runner.main(argv)`(WP7)에 위임한다. 없으면 heartbeat 만.
- 동시 실행 2개 → 하나만 동작(락, WP7 완료 기준).

## 바꿀 신호

일일 작업 1시간 초과.
