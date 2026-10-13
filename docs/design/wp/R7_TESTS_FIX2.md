# R7-FIX2 — 같은 기준일 리비전에 남은 어제 실패 접수 행 · 공동 순위 표시 순서 (2026-10-14)

브랜치 `wp/r7-fix2`(main `91bf120` — `Merge wp/r7-fix`). 계약 `.19` 그대로(계약·마이그레이션·새 라이브러리 없음). 판정 규칙·판정기
입력 조립 규칙은 바꾸지 않았다 — **어느 접수 행이 리비전에 남고 표시되는가**와 **공동 순위 안 표시 순서**만.

## 1. 증상 (운영 DB 읽기 전용 — `SET TRANSACTION READ ONLY`, SELECT 만)

인천(지역 1) 스냅샷:

| id | 기준일 | 리비전 | 사유 | 만든 잡 |
| --- | --- | --- | --- | --- |
| 1 | 2026-10-13 | 1 | — | bootstrap |
| 2 | 2026-10-14 | 1 | — | collect.daily #3(수동, R7-FIX 배포 전) |
| 3 | 2026-10-14 | 2 | 같은 기준일 재수집 | collect.daily #8(수동 06:09, R7-FIX 배포 뒤) |
| 4 | 2026-10-14 | 3 | 같은 기준일 재수집 | collect.daily #7(예약 06:00, 06:26 시작) |

스냅샷 3·4 의 접수 행(단지 7 예 — 8·22·37·38·72·75·87 같은 모양):

| 스냅샷 | 행 | 경로 | 사유 | 원문 | 응답 | 확인 시각 |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 103 | headless_shot | 판정 미해결(jl_798) | 2299 | 200 | 10-14 02:39 |
| 2 | 193 | official_popup | **403** | 1221 | 403 | 10-13 19:26 |
| 3 | 209 | headless_shot | 판정 미해결(jl_855) | 2299 | 200 | 10-14 02:39 |
| 3 | 210 | official_popup | **403** | 1221 | 403 | 10-13 19:26 |
| 4 | 315 | headless_shot | 판정 미해결(jl_855) | 2299 | 200 | 10-14 02:39 |
| 4 | 316 | official_popup | **403** | 1221 | 403 | 10-13 19:26 |

38·72·75·87 은 headless_shot 원문 2314 + official_popup 'TLS'(1258·1303, 응답 없음), 69(공공분양)는 둘 다 '판정 대상 아님(공공분양)'.
스냅샷 3·4 의 행은 **모두 복사본**이다(확인 시각이 02:39 — 오늘 재수집은 같은 sha256 원문 2299 를 돌려줘 새 행을 만들지 않았다).

## 2. 원인

1. **같은 기준일 재수집은 `copy_intake` 의 R7-FIX 규칙을 거치지 않는다.** `snapshots.get_or_create` 가 발행된 리비전을 보면
   `new_revision` → `copy_intake(앞 리비전, 새 리비전)` 을 **빈 새 리비전**에 부른다(오늘 관측 행이 아직 없어 '오늘 관측이 어제 실패를
   대신' 조건이 안 걸린다 — 전부 복사). 그 뒤 `collect.intake_rows` 는 (단지, 경로)가 이미 있으면 오늘 행을 만들지 않고, `collect` 의
   `copy_intake(previous, 새 리비전)` 도 이미 다 있어 아무것도 하지 않는다. 그래서 리비전 1(스냅샷 2, R7-FIX 전 수집)이 물려받은 어제
   실패 행이 리비전 2·3 으로 그대로 이어졌다.
2. 같은 결함이 지금 코드만으로도 생긴다: 같은 기준일 리비전 1 이 실패(TLS)·리비전 2 가 성공이면 리비전 1 의 실패 행(이른 수집 원문)이
   리비전 2 에 남아 표시된다. 반대로 리비전 2 의 오늘 관측이 같은 경로이면 복사된 행이 자리를 차지해 오늘 행이 아예 만들어지지 않는다
   (예: 복사된 적재 행 official_popup '미정' 이 오늘 'TLS' 관측을 막았다 — 테스트 3).
3. 표시 규칙(`pick_intake`)은 경로가 날짜보다 먼저라(official_popup > headless_shot) 어제 실패가 오늘 성공을 가렸다.

## 3. 고친 것

| 파일 | 내용 |
| --- | --- |
| `scheduler/collect.py` | `intake_rows`: 오늘 관측이 있는 단지는 스냅샷 안의 그 단지 행 중 **오늘 받은 원문이 아닌** (1) 수집 실패 행(`is_fetch_failure`, 어느 수집 경로든)과 (2) 오늘 행과 같은 경로의 행을 지우고 오늘 행을 만든다 — 새 기준일(오늘 행 먼저 + `copy_intake` 거름)과 같은 결과. 같은 원문 재수집은 아무것도 바꾸지 않는다(멱등) |
| `analysis/scope.py` | `is_fetch_failure`(수집 경로·'확인 불가'·200 아님·원문 행 또는 응답 코드) · `pick_intake`: 수집 실패 행은 그보다 나중(KST 날짜, 같은 날이면 id)의 수집 성공 행(수집 경로·200·원문)이 있으면 후보에서 빠진다 |
| `scheduler/persist.py` | `copy_intake`: 실패 행 판정을 `is_fetch_failure` 로(원문 없이 응답 코드만 남은 적재 실패 행 — 픽스처 '403' — 도 포함) |
| `analysis/_ranking.py` | `tie_order_key`·`display_order_key`(순위 → 같은 순위 안 점수 높은 순 → complex_id, 점수는 저장 정밀도 4자리) |
| `api/routers/snapshots.py` | 대시보드 TOP 5·단지 목록 `sort=rank`/`-rank` 가 공용 키 |
| `analysis/sensitivity.py` | `base_top5`·변형 `top5`·`ranks` 가 공용 키(예전 id 순) |
| `reports/data.py` | 점수 행 정렬(같은 결과 — 공용 키로)·§12 순위 비교 표(예전 순위만 — 같은 순위는 집합 순회 순서) |

### DECISIONS 후보 문단

> **D27-1 (R7-FIX2) 접수 표시 행과 이른 수집 실패.** 표시 접수 행은 경로 우선(human_check > official_popup > headless_shot)을 유지하되,
> **수집 실패 행**(수집 경로 · '확인 불가' · 응답 200 아님 · 원문 행 또는 응답 코드가 있음 — 403·404·TLS·접속·robots 등)은 그보다
> **나중에 기록된 수집 성공 행**(수집 경로 · 200 · 원문; KST 확인 날짜, 같은 날은 기록 순서)이 있으면 표시 후보가 아니다. 수집은
> 오늘 관측이 있는 단지에 대해 스냅샷 안의 이른 수집 실패 행(어느 경로든)과 오늘 행과 같은 경로의 이른 행을 오늘 행으로 대신한다 —
> 새 기준일 스냅샷과 같은 기준일 리비전이 같은 결과를 낸다. 나중 실패는 이른 성공을 이긴다(오늘 막힌 사이트는 막힌 것으로 보인다).
> 성공 관측끼리의 경로 우선·사람 확인 최우선·원문 없는 적재 행 처리는 그대로(T8).
>
> **D27-2 (CEO) 공동 순위 안 표시 순서** = 종합 점수 높은 순 → complex_id. 대시보드 TOP 5·단지 목록 `sort=rank`·민감도·보고서가
> 한 키(`analysis._ranking.display_order_key`)를 쓴다. 순위·공동 순위 규칙(§6-4)은 그대로다.

## 4. 테스트 (먼저 쓰고 main `91bf120` 코드에서 실패 확인)

수정 전 실행: main `91bf120` 을 따로 worktree 로 꺼내 새 테스트 파일만 복사해 돌렸다.

| 테스트 | 결함 | 수정 전(main) |
| --- | --- | --- |
| `scheduler/test_r7_fix2.py::test_live_pattern_same_asof_revisions_drop_inherited_failure_rows` | 운영 그대로: 1일차 TLS → 2일차 리비전 1(어제 실패 행 물려받음 — 스냅샷 2) → 같은 기준일 리비전 2·3 | **실패** — 리비전 2 단지 4 `[('headless_shot', …, 200), ('official_popup', 'TLS', 원문 1, None), …]`, 표시 = 어제 TLS |
| `…::test_same_day_failed_revision_then_success_revision` | 같은 날 리비전 1 TLS → 리비전 2 성공 | **실패** — 리비전 2 에 리비전 1 의 TLS 행이 남아 표시 |
| `…::test_same_day_success_then_failure_revision_shows_failure` | 리비전 1 성공 → 리비전 2 실패: 오늘 실패가 보여야 한다 | **실패** — 복사된 적재 행(official_popup '403', 원문 없음)이 자리를 차지해 오늘 TLS 행이 안 생김 |
| `…::test_intake_rows_today_observation_replaces_copied_failure_rows` | `intake_rows` 단위 — 복사된 이른 실패·같은 경로 행 대체, 사람 확인·비공식·다른 경로 성공·적재 행·같은 원문 유지 | **실패** — (7, official_popup, '403') 남음 |
| `…::test_copy_intake_into_revision_after_today_rows_skips_failures` | 지운 실패 행을 `copy_intake(앞 리비전)` 이 되살리지 않는다 | **실패** — `[('official_popup', '403'), ('headless_shot', …)]` |
| `…::test_pick_intake_failed_fetch_does_not_outrank_newer_success` | 표시 규칙 방어(인천 스냅샷 2 행 모양 그대로) | **실패** — 어제 403 official_popup 이 오늘 headless_shot 을 이김 |
| `api/test_r7_fix2_tie_order.py::test_dashboard_top5_tie_group_ordered_by_total_then_id` | 공동 5위(단지 5 4.6050 · 6 4.6400) | **실패** — `[5, 6]`(기대 `[6, 5]`) |
| `api/…::test_complex_list_sort_rank_tie_group_ordered_by_total_then_id` | 목록 `sort=rank`·`-rank` | **실패** — `[5, 6]` |
| `analysis/test_r7_fix2_tie_order.py` 2건 | 공용 키 · 민감도 base_top5·ranks | **실패**(ImportError — 키 없음). 같은 입력의 main 민감도: `base_top5 [1, 2, 3]`(기대 `[1, 3, 2]`) |
| `reports/test_r7_fix2_tie_order.py` | 보고서 점수 행 순서 | 통과(보고서는 이미 점수 순 — 공용 키로 바꾼 뒤 고정용) |

§12 순위 비교 표 정렬(순위만 → 공용 키)은 같은 순위가 있을 때만 다르고 회귀 골든에는 그 경우가 없다(전용 테스트 없음).

골든 변경: **없음**. T1 공동 5위는 센트레빌(단지 5, 골든 4.61) · 더샵 AB23(단지 6, 원값 4.605)이라 점수 순 = id 순 — T1 순서 그대로(회귀 통과로 확인).
T12 민감도·보고서 골든도 그대로.

## 5. 운영 반영

runbook §10-21. 발행된 스냅샷 2·3·4 는 그대로(D11-1) — 저장본 화면은 다음 발행부터 바뀐다. G7 대기열은 행을 바로 읽어 배포 즉시 실제
사유로 바뀐다. 다음 수집(새 기준일·같은 기준일 리비전 모두)에서 8단지의 'TLS'·'403' 행이 빠지고, status 가 같아 change_event·판정 범위
변화 없음, 분류 복사라 접수 classify 호출 0.

## 6. 하지 않은 것

- 발행된 스냅샷 2·3·4 를 고치지 않았다(D11-1).
- 성공 관측끼리 경로가 바뀌는 날(어제 HTML 만 official_popup 성공, 오늘 렌더 headless_shot)의 경로 우선은 그대로(R7_TESTS_FIX §7-3, T8).
- 원문 sha256 중복 제거 때문에 오늘 같은 화면을 다시 받으면 접수 행 확인 시각이 첫 수집 시각으로 남는다(스냅샷 3·4 의 02:39). 표시 규칙
  방어는 KST 날짜·id 로 비교하므로 이 경우 이른 실패를 못 거를 수 있지만 수집 쪽 규칙(원문 id 비교)이 거른다.
- `api/views.py`·`reports/policy.py` 의 `pick_intake` 는 `analysis.scope.pick_intake` 를 그대로 부른다 — 따로 고칠 것 없음.

## 7. 완료 검사 (브랜치 끝)

- `uv run pytest -p no:randomly -m "not live"` → 4245 수집, 실패 0(종료 코드 0). `ruff check`·`ruff format --check`·`mypy app` 통과.
- `gen_contracts.py --check`·`fixture_manifest.py --check` 종료 코드 0. `python scripts/tasks.py regress` → T01~T18·모듈·흐름·e2e 3개 전부
  통과(골든 변경 없음).
- 프론트: 계약 예시·픽스처·골든이 바뀌지 않아 MSW 응답 순서가 그대로다(별도 vitest 실행 안 함). 회귀 e2e 3개(실제 API)는 통과.
