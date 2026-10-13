# R7-FIX — 오늘 받은 공식 홈페이지 원문 대신 어제 실패 행이 접수 표시 행이 된 결함 (2026-10-14)

브랜치 `wp/r7-fix`(main `8865eea` — `Merge wp/r7-queue`). 계약 `.19` 그대로(계약·마이그레이션·새 라이브러리 없음). 판정 규칙·
판정기 입력 조립 규칙(D10-2·D21-5·D22-2·D26)은 바꾸지 않았다 — **어느 접수 행이 오늘 스냅샷에 남는가**(복사)와 **그 행의 근거
주소**만.

## 1. 증상 (운영 DB 읽기 전용 — `SET TRANSACTION READ ONLY`, SELECT 만)

인천(지역 1) 스냅샷 2(2026-10-14, collect.daily #3, R7-SITE 배포 뒤). hillstate.co.kr 는 TLS 브라우저 경로(D26-4)로 오늘 받았다 —
원문 2313(`/s/GI59`, 단지 38)·2334(`/s/`, 단지 69 — 72·75·87 과 같은 주소, sha256 로 한 행)이 `official_site.meta`,
`render.reason='TLS 브라우저 경로'`, `fetch.result='ok'`, 스크린샷 행 2314. 그런데 접수 표시 행은 'TLS'·어제 원문(1258·1303).

스냅샷 2 의 그 단지 접수 행:

| 단지 | 오늘 수집 행(경로 headless_shot) | 어제에서 복사된 행(경로 official_popup) | 표시 행(`pick_intake`) |
| --- | --- | --- | --- |
| 38 | 134 · 원문 2314 · 동일성 미확인(jl_796) | 198 · 원문 1258 · **TLS** | 198(TLS) |
| 72·75·87 | 166·169·179 · 원문 2314 · 동일성 미확인 | 200·201·202 · 원문 1303 · **TLS** | TLS |
| 7·8·22·37 | 103·104·118·133 · 오늘 성공(판정 미해결·동일성 미확인·문구로 판단 불가·판정 미해결) | 193·194·195·197 · **403** | 403 |
| 69(공공분양) | 163 · 판정 대상 아님 | 199 · 판정 대상 아님 | 199 |
| 28 | 124 · official_popup(오늘 HTML, 렌더 시간 초과) | 196 · headless_shot(어제 스크린샷) | 124(오늘 — 표시는 맞음, 낡은 행이 남음) |

## 2. 원인

1. **`persist.copy_intake` 가 (단지, 경로) 단위로만 복사했다.** `collect` 는 오늘 원문으로 접수 행을 만든 뒤(`intake_rows` — 성공 + 렌더면
   경로 `headless_shot`, 실패·HTML 만이면 `official_popup`) 이전 스냅샷 행을 복사한다. 오늘 행과 **경로가 다르면** 어제 행(어제 실패
   'TLS'·'403')이 그대로 옆에 복사됐고, 표시 행 규칙(`analysis.scope.pick_intake`: human_check > official_popup > headless_shot —
   경로가 날짜보다 먼저)이 낡은 실패 행을 골랐다. 실패 → 성공(렌더) 전환이면 언제나 생긴다(TLS 5·403 4 — 1 은 공공분양).
   판정기는 오늘 행을 정상 분류했다(jl_796) — 분류가 아니라 **표시 행 선택**이 틀렸다.
2. (같은 재생) **근거 주소가 다른 단지 URL.** 브랜드 공통 화면이라 `/s/GI59`(38)와 `/s/`(69·72·75·87) 렌더 스크린샷이 바이트 동일 →
   원문 행 하나(2314, URL `/s/GI59`). `intake_rows` 가 `evidence_url = 스크린샷 행 URL`, `intake._html_row` 가 **스크린샷 행 URL** 로 HTML
   행을 찾아 72·75·87 의 근거 주소·동일성 근거(제목·설명·이동 후 주소)가 `/s/GI59` 페이지(2313)였다(`evidence_url ≠ official_site_url`
   4행 — 69·72·75·87).

검토했으나 원인이 아닌 것: 수집기의 URL 별 중복 제거(없음 — 단지마다 받고 robots.txt 만 원점당 1회), 원문 sha256 중복(같은 행을 돌려
주고 `fetch()` 가 단지 id 를 다시 단다 — 72·75·87 모두 오늘 행이 생겼다), `carry_classification`·`_previous_classified`(오늘 행은 미분류로
남아 판정기로 갔다).

## 3. 고친 것

| 파일 | 내용 |
| --- | --- |
| `scheduler/persist.py` | `copy_intake`: dst 에 그 단지의 **수집 관측 행**(`COLLECTED_INTAKE_PATHS` = official_popup·headless_shot 경로 + `raw_document_id` 있음 — `intake_rows` 가 만든 행)이 있으면 src 의 수집 관측 행은 **어느 경로든** 복사하지 않는다(오늘 관측이 어제 관측을 대신). 원문 없는 접수 행(적재·보고서 값)·human_check·unofficial_ref 는 그대로 복사. 새 리비전(`new_revision`, dst 빈 스냅샷)·수집하지 않은 날·오늘 행이 없는 단지는 변화 없음. 운영 DB 의 수집 경로 행은 스냅샷 1·2 모두 원문 id 가 있다(원문 없는 행 0) |
| `scheduler/collect.py` | `intake_rows`: `evidence_url` = 이 단지가 받은 HTML 행 주소(없으면 대표 행 주소) |
| `scheduler/intake.py` | `_html_row(doc, url)`: 스크린샷 행이면 접수 행 근거 주소(`evidence_url`)의 HTML 행 중 그 스크린샷을 가리키는 행 — 스크린샷 행 URL 로 찾지 않는다 |

원문 조건을 둔 이유: 첫 수정(경로만 보고 대신)은 T8(`tests/scheduler/test_detect_t8.py` 2건·`tests/regress/test_t08_no_change_day.py`·
`test_t18_judge_down.py`)을 깼다 — 픽스처 적재 접수 행(official_popup, 원문 없음 — 보고서 값)이 첫날 수집 headless_shot 행과 같은 스냅샷에
있다가 다음 날 복사되지 않아, 변경 없는 날 표시 접수가 바뀌고 판정 호출(58 ≠ 52)·사다리 수(30 ≠ 33)가 달라졌다. 적재 값은 수집 관측이
아니므로 수집이 대신하지 않는다.

결정성·D10-2: 같은 화면이 이어지는 날은 경로·원문·근거가 그대로라 입력 텍스트가 같다 → 분류 복사(호출 0, 테스트로 고정). 복사 규칙은
`pick_intake` 와 같은 결정적 비교(경로 집합 소속)만 — 판단 아님(규칙 3).

## 4. 테스트 (먼저 쓰고 main `8865eea` 코드에서 실패 확인)

`backend/tests/scheduler/test_r7_fix.py`. 수정 전 실행: 테스트 커밋(`9431fee`) 상태에서 `backend/app` 만 main 으로 되돌려 돌렸다.

| 테스트 | 결함 | 수정 전(main) |
| --- | --- | --- |
| `test_shared_url_day1_tls_day2_browser_success_shows_today` | 같은 주소 두 단지, 1일차 TLS(배포 전)·2일차 브라우저 성공 → 2일차 표시 행이 어제 'TLS' | **실패** — 행 `[('headless_shot', None, 3), ('official_popup', 'TLS', 1), …]`, 표시 = official_popup TLS 원문 1 |
| `test_unchanged_next_day_after_recovery_copies_without_judge` | 회복 다음 날 같은 화면 → 분류 복사·호출 0·표시 행 그대로 | **실패** — 표시 행이 복사된 낡은 official_popup(분류 복사 표식 없음) |
| `test_copy_intake_today_observation_replaces_yesterday_collected_rows` | `copy_intake` 단위: 오늘 headless_shot 단지에 어제 '403' official_popup(원문 있음) 복사(인천 7·8·22·37). 원문 없는 적재 행·사람 확인·비공식 참고·오늘 행 없는 단지는 복사 | **실패** |
| `test_identical_screenshot_on_other_url_keeps_own_evidence` | 다른 주소·같은 스크린샷 → 근거 주소·HTML 제목이 남의 페이지 | **실패** — `evidence_url == …/s/GI59` (기대 `…/s/`; 복사 수정만 적용한 상태에서도 실패 확인) |
| `test_human_check_row_is_still_carried_over` | 오늘 수집 행이 있어도 사람 확인 행은 복사 | 통과(회귀 방지) |

## 5. 운영 반영

- 배포 뒤 첫 `collect.daily`(스냅샷 3): 오늘 수집 행이 있는 단지는 스냅샷 2 의 낡은 실패 행(TLS 4·403 4·28 의 어제 스크린샷 행)을 복사하지
  않는다 → 표시 접수 행이 오늘 관측. 인천 해당 단지는 오늘 행도 모두 '확인 불가'(동일성 미확인·판정 미해결·문구로 판단 불가)라 표시
  status 가 같다 → intake change_event·판정 범위 변화 없음. 사유만 'TLS'·'403' → 실제 사유로 바뀐다(G7 사람 확인 대기열의 사유 묶음도).
- 근거 주소가 바뀌는 72·75·87 은 동일성 항목 입력(주소·제목)이 바뀌어 분류 복사가 막히고 동일성 classify 1배치(3항목)로 간다
  ≈ `tools/call` 1(69 는 판정 대상 아님 — 보내지 않음). 같은 날 다시 돌리면 0.
- 발행된 스냅샷 2 는 불변(D11-1) — 그 스냅샷 화면·대기열의 'TLS'·'403' 사유는 다음 일일 수집으로 대체된다. runbook §10-20.
- 확인: `SELECT complex_id, path, reason, raw_document_id FROM intake_status WHERE snapshot_id = <새 스냅샷> AND complex_id IN (7,8,22,28,37,38,72,75,87) ORDER BY 1, 2;` — 단지마다 수집 경로 행 1개(오늘 원문).

## 6. 대시보드 TOP 5 점검(스냅샷 2 base — 고치지 않음)

- **4행은 정상.** score_run 6(base): 판정 대상 7 = 시티오씨엘 8단지 5.3809(1)·힐스테이트 구월아트파크 4.6404(2)·엘리프 검단 포레듀
  4.6714(2)·디에트르 라 메르Ⅰ 3.4838(4) + 검암역자이르네(9)·신일 비아프 크레스트 1·2단지(27·28) total 없음 — 세 단지 모두 유동성
  성분 '공고문 값 없음'(계약금% 미공개, D24-3 수용 한계)이라 가중 합 미계산(`weighted_total` — 성분 하나라도 None 이면 None) → 순위 없음.
  TOP 5 = rank ≤ 5 인 단지 전부(`_ranking.top_set`)라 4개. KPI 판정 대상 7 은 저장 judge_scope 수(D10-1)라 TOP 5 수와 다르다.
- **공동 2위는 RA 규칙 그대로.** RA §6-4 "`|S_i − S_j| < 0.05`면 같은 rank" — |4.6714 − 4.6404| = 0.031 < 0.05 → 같은 rank 2·tie_group 1,
  다음은 경쟁 순위 4(1,2,2,4 — `analysis._ranking.rank_totals`).
- **공동 순위 안의 표시 순서**: 대시보드(`api/routers/snapshots.py` `dashboard_body` — `(rank, complex_id)`)·단지 목록 `sort=rank`·민감도
  `top5` 는 단지 id 순(16 → 41, 4.64 가 4.67 위), 보고서(`reports/data.py` `_score_views_live` — `(rank, -total, complex_id)`)는 점수 높은
  순(41 → 16). RA 는 공동 순위 안의 순서를 정하지 않고("1순위를 하나로 말하지 않는다") T1 골든(센트레빌 = 더샵 AB23 4.61 공동 5위)은
  id 순 — 버그로 보지 않았다. 화면·보고서 순서를 맞출지는 결정 필요(제안 1).

## 7. 제안 · 요청 (이번에 하지 않은 것)

1. **(WP5·WP8 결정)** 공동 순위 안 표시 순서를 화면·보고서 하나로: (a) 단지 id(공동 순위를 순서로 암시하지 않음 — 지금 API) 또는
   (b) 점수 높은 순(지금 보고서). (b)면 `dashboard_body`·목록 `sort=rank`·민감도 `top5` 정렬 키에 `-total` 을 넣고 T1 공동 5위
   (센트레빌·더샵 AB23 — 표시 4.61)의 저장 total 차이에 따라 골든 순서가 바뀌는지 확인해야 한다.
2. 원문 행이 sha256 로 하나라 HTML 이 바이트 동일한 다른 주소 단지도 HTML 행 URL 은 먼저 받은 단지 것이다(이번 수정은 스크린샷 공유만 —
   인천 사례). HTML 까지 같은 페이지면 같은 페이지이므로 근거로는 문제 없지만, 근거 주소를 단지 `official_site_url` 로 고정하려면
   수집기가 대상 URL 을 돌려주는 원문에 실어야 한다(계약 밖 메타 키 — 다음 라운드).

계약 변경 요청: 없음.
