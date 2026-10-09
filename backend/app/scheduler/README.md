# app/scheduler

- **주인**: WP7
- **읽기 허용**: — (다른 WP 는 읽지 않는다)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§4-4·§5, DECISIONS D2-4·D6)

| 모듈 | 내용 |
| --- | --- |
| `jobs.py` | 잡 이름 7개, `enqueue`(같은 queued 잡 중복 없음), APScheduler 시간표(06:00 daily · 월 06:30 weekly · 매월 1일 05:00 reference) — 시간표는 job_run 행만 넣는다, `ensure_reference`(참조 표가 비면 1회) |
| `runner.py` | `main(argv)`(`python -m app.worker [--once] [--interval 초] [--no-schedule]`), job_run polling, 잠금(`UPDATE … WHERE status='queued'` 1행일 때만 실행), done/failed + stats·error_text |
| `handlers.py` | 잡 이름 → 처리 함수(collect.daily·weekly, rejudge, snapshot.publish, reference.refresh, region.bootstrap, report) |
| `collect.py` | 수집기(WP1) → `normalize.store`(WP2) → intake_status 행(분류 없이 '확인 불가(사유)', 파서의 접수 문구 후보는 note) → 변경 감지 |
| `detect.py` | 팝업 이미지 해시(기준일 전 마지막 해시와 비교) · 청약홈 목록 diff → change_event |
| `pipeline.py` | P1 screen → P2 extract → P3 audit(→ `normalize.judged.apply_extracted`) → 접수 상태 classify('접수 문구 미분류' 행) → P4 classify(포함/제외 배치) → P5 compare(contradicts → `apply_compare`) → P6 noul → P7 rerank → 점수(`analysis`, score_total.judge_scope 저장) → P8 decide → P9 verify → 저장 |
| `payloads.py` | 시나리오 → 판정 payload 목록 빌더 `scenario_payloads` + `cache_status`(미리보기 cache_hits, WP5) · 파이프라인과 공용 입력 조립(`score_base`·`rerank_pool`·`decide_plan`·`stored_scope`) |
| `inputs.py` | DB → `ScoreInputs`(2026-10-09.2 필드: unsold_scope_codes·intake_checked_at·*_label) · 증거 카드 |
| `persist.py` | ladder·score_run/component/total·decision·claim·comparable_set 쓰기, 변경 없는 날 파생 행 복사 |
| `rejudge.py` | rejudge 잡 등록(같은 스냅샷 queued 잡에 단지 합침)·실행 |
| `degraded.py` | `JudgeUnavailable` → `snapshot.degraded=true`, 복구 감지 시 degraded 스냅샷마다 rejudge 1개 |
| `judge_version.py` | adapter_version(서버 버전·모델) 변경 → `change_event(judge, version, critical)` + 전체 재판정 1회 |
| `notify.py` | `WEBHOOK_URL` 있으면 critical change_event 만 전송(guard 통과분), 없으면 no-op |
| `context.py` | `SchedulerContext`(세션·어댑터·수집기·알림·시계) — 테스트는 전부 바꿔 끼운다 |

## 다른 WP 가 알아야 할 것

- **degraded 플래그** = `snapshot.degraded`(계약 컬럼). 판정기 장애 중 만든 스냅샷은 `degraded=true`·`status=building`
  (점수 없음). 복구 후 rejudge 가 끝나면 `false`. 전역 판정기 상태가 필요하면 지역 최신 스냅샷의 값을 읽는다.
- **사람 확인(T3)**: API(WP5)가 `human_check` + `intake_status(path=human_check, status=…)` + `change_event` 를 넣고
  `app.scheduler.rejudge.enqueue_rejudge(session, snapshot_id, [complex_id], "사람 확인 입력", change_event_ids=[…])`
  를 부르면(또는 같은 모양 job_run 행) 같은 스냅샷 queued rejudge 에 합쳐진다. 새 스냅샷은 이전 스냅샷의 접수 행
  (사람 확인 포함)을 확인 시각 그대로 복사한다.
- **report 잡**(WP8 README '잡 규약'): `app.reports.job.run_report_job(payload, session=…)` → job_run.stats.
  `ReportBlocked` → failed `blocked: <사유>` + stats `{blocked_reason}`, `ReportNotFound` → `not_found: <사유>`,
  `ValueError`(payload 검증) → `invalid_payload: …`.
- **변경 없는 날**(T8): 이전 publish 스냅샷의 ladder·score_run·decision·claim·comparable_set 을 복사하고 publish
  (판정기 호출 0, `score_run.prev_score_run_id` = 원본 run).
- 판정기 호출은 `ctx.adapter()`(= `app.judge.get_adapter`) + `app.judge.pipeline` 단계 함수로만 한다(규칙 4).
  decide 의 chosen·tie 는 `app.analysis.score.decide_outcome`, mismatch 는 `app.analysis.scenarios.requirement_mismatch`.
- mock 어댑터의 녹화 디렉터리: 환경변수 `JUDGE_FIXTURE_DIR`(없으면 `contracts/fixtures/incheon_gimpo_2026-10-08`).

## 규칙

- 이 디렉터리와 `backend/tests/scheduler/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
