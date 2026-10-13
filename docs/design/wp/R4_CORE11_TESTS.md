# R4-CORE11 — 운영 전 정리(N16·m-e) 테스트·수정 전 실패 확인 (2026-10-13)

원문: `docs/design/wp/R4_RESULT5.md` §10(N16·m-e), 결정 `docs/design/DECISIONS.md` **D24-1**. 브랜치 `wp/r4-core11`(main `9280516` 기준),
계약 **2026-10-09.18 그대로**(계약 변경 없음 — 잡 stats `pipeline.checklist` 는 계약 밖 자유 형식 stats 에 키 하나를 더한 것).

**방법(D23-1 확장).** 고치기 전에 테스트를 먼저 썼다(커밋 `adcb3f9 [R4-CORE11] 테스트 먼저: …`). 끝에 `git archive 9280516 backend contracts`(수정
전 앱·계약)에 새 테스트·바뀐 테스트·재생 도구만 얹어 **한 번 더** 돌린 실제 출력이 아래 "수정 전" 열이다(scratchpad `core11/prefix_final.txt` — 같은
가상환경, 작업 디렉터리만 수정 전 트리, `import app` 이 그 트리를 가리키는 것 확인). 실제 판정기·외부 사이트는 부르지 않았다(가짜 판정기 — 전송 계층
`tools/call` 계수 — 와 녹화 재생). R4 DB(`subscription_analyzer_r4`)는 SELECT 만 했다(읽기 전용 연결, 접속 주소는 루트 `.env` 의 `R4_DATABASE_URL`
을 스크립트가 읽어 환경 변수로만 넘기고 출력하지 않음): 5차 재생 매니페스트(뉴스 포함) 만들기, m-e SQL 확인.

## 1. 결함별 수정·테스트·수정 전 실패

| 결함 · 결정 | 수정 | 테스트 | 수정 전(9280516) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **N16** major · D24-1 (멱등성 속성, 첫 수집 전체 → 같은 날 daily) | `scheduler/pipeline.run_pipeline`: P9 뒤·`ready` 전에 `_sync_checklist` → `normalize.checklist.sync_checklist`(수집 조립과 같은 함수, 스냅샷 기준일). 주간 단계가 만든 트랙 (A) 후보 단지와 P4 포함 classify 가 제외한 단지가 **발행 전** 체크리스트에 반영된다. 결과 stats `pipeline.checklist`. bootstrap 만이 아니라 판정 파이프라인을 도는 모든 경로(주간 수집·daily 뒤 재판정·지역 확장)에 같은 규칙 | `tests/scheduler/test_core11_bootstrap_idempotency.py::test_full_bootstrap_then_same_day_daily_is_idempotent[r4·r4b·r4c·r4d·r4d-full]` — bootstrap(일일 + **주간 뉴스 원문** + 판정 + 발행) → 사전 조건(트랙 A 후보 생김·제외 단지 있음) → bootstrap 직후 체크리스트 = 그 시점 사실로 다시 맞춘 것(돌려 보고 되돌림) · 트랙 A '모집공고 예정' open · 제외 단지 자동 항목 open 0 · 발행 보고서 저장본 → 같은 날 `collect.daily`(같은 순서·섞은 순서) DB 스냅샷(체크리스트 포함 정규화 테이블 전부) 동일 · 사실 change_event 0 · `tools/call` 0 · daily 체크리스트 동기화 변경 0 · 새 발행 리비전 보고서 체크리스트 = bootstrap 것 → 같은 날 재판정 `tools/call` 0 · DB 동일 | `[r4b]` **`멱등성 위반 7건 (bootstrap tools/call 23, 트랙 A [7, 8], 제외 단지 5) [bootstrap 직후] 체크리스트가 bootstrap 최종 사실과 어긋남 — 다시 맞추면 {'inserted': 6, 'closed': 2}`** · `트랙 A 후보 [7, 8] 에 '모집공고 예정' open 없음` · `제외 단지 5 자동 항목 open [(1, '토지거래허가구역 …'), (2, '비과세 거주요건 …')]` · `[같은 날 첫 daily] DB 스냅샷 차이 {'checklist_item': 8}: 생김 6 · 바뀜 2` · `daily 체크리스트 동기화가 행을 바꿈 {'inserted': 6, 'closed': 2}` · `발행 보고서 체크리스트 차이(리비전 1 → 2): 사라짐 2 · 생김 8`(R4 5차 실측 6행 생김·2행 na 와 같은 모양) · `[r4c]` 같은 7건 `{'inserted': 6, 'closed': 2}` · `[r4d]` 7건 `{'inserted': 6, 'closed': 3}`(DB 차이 9) · `[r4]` 6건 `{'inserted': 6}`(이 녹화는 법정동 참조가 없어 청약홈 단지가 전부 '범위 경계' — 트랙 A 경로만) · **`[r4d-full]`(R4 5차 원문 전부 + 5차 뉴스 원문) 7건 `(bootstrap tools/call 690, 트랙 A [71, 72], 제외 단지 3) … {'inserted': 6, 'closed': 10}` · DB 차이 `{'checklist_item': 16}`** — 트랙 A 단지 id 71·72 는 R4 5차 실데이터의 id 와 같다 | 5세트 모두 통과(`r4d-full` 109초) |
| **N16** 단위 · D24-1 | (위와 같음) + 옛 기준일 보호: 그 지역에 더 새 기준일 스냅샷이 있으면(옛 기준일 재판정) 체크리스트를 건드리지 않는다(`pipeline.checklist` = None) — 체크리스트는 지역에 한 벌(지금 상태)이고 옛 기준일로 맞추면 지난 일정 항목이 다시 열린다 | `tests/scheduler/test_core11_n16.py::test_pipeline_resyncs_checklist_after_inclusion_judgment`(픽스처 16단지, 일일 단계처럼 먼저 맞춘 뒤 판정이 단지 하나를 public_sale auto 로 → 같은 실행에서 그 단지 자동 항목 na(auto), 다시 맞춰도 변경 0) · `::test_pipeline_on_older_asof_leaves_checklist_alone` | **`AssertionError: 판정이 제외한 단지의 자동 항목은 같은 실행에서 닫혀야 한다(N16) assert ['전매제한 종료(당첨자...여부 확인(확인 권고)'] == [] Left contains 3 more items`** · `AttributeError: 'PipelineResult' object has no attribute 'checklist'`(옛 기준일 보호는 이번 수정이 새로 만든 규칙의 테스트 — 수정 전에는 그 결과 필드가 없어 실패, N16 재현 아님) | 통과 |
| (바뀐 기존 테스트) | — | `tests/scheduler/test_r3b_g2.py::test_p9_claims_carry_fact_target_and_pipeline_syncs_demotions`: 강등 정리 호출이 `[{2}]` 한 번 → 첫 호출 `{2}`(load_facts 앞, D10-3 그대로) + 판정 뒤 체크리스트 동기화의 지역 전체 강등 정리 1회 | `AssertionError: [{2}] assert (1 == 2)` | 통과 |
| **m-e** minor(문서) · D24-1 | `docs/runbook.md` §10-13 ① SQL 정정: 같은 경쟁률(단지·구분·회차·공급·접수·경쟁률 문구)이 **원 면적 코드**(`^[0-9]+\.[0-9]+$`)와 **그 정수부 표시 코드**(`^0*<정수부>[A-Za-z]*$`) 또는 '확인 불가(타입 모호)'로 두 번 저장된 짝만 센다. 5차 주·§10-15 갱신 | R4 5차 DB(읽기 전용) + 4차 중복 모양 합성 행(읽기 전용 CTE) — scratchpad `core11/me_sql.py`·`me_new.sql` (§3) | 옛 SQL: 5차 깨끗한 데이터 **87행**(단지 5 '124I'·'100C' 등 다른 주택형 우연 일치), 합성 행 9 | 새 SQL: 5차 데이터 **0행**, 합성 행 **4**(4차 중복 4쌍만 — '84.9939'↔'84', '122.5'↔'122', '66.123'↔'66A', '53.5854'↔'확인 불가(타입 모호)') |

수정 전 합계(`prefix_final.txt`): **실패 8 · 통과 0**(새 테스트 7 + 바뀐 기존 테스트 1, `r4d-full` 포함). 수정 전에도 통과하는 새 테스트는 없다 — 사전
조건 단언(트랙 A 후보 생김·제외 단지 있음·published)은 수정 전에도 성립했고(실패 메시지가 그 뒤 단계에서 나옴), 속성 테스트의 같은 날 재판정 단계는
수정 전에도 `tools/call` 0 이었다(실패 목록에 없음).

## 2. 속성 테스트 범위(D23-1 → D24-1)

| | CORE10 `test_renormalize_is_idempotent` | CORE11 `test_full_bootstrap_then_same_day_daily_is_idempotent` |
| --- | --- | --- |
| bootstrap 일일 단계 | 녹화 원문 전부 | 같음 |
| bootstrap 주간 단계 | 원문 없음(수집기 없음) | **뉴스 원문**(매니페스트 `docs.news` — 5차 원문 1건, 없으면 저장소 R4 1차 뉴스 녹화 `tests/scheduler/fixtures/r4_news_2026-10-12.json`) → 호재 후보(P1 screen) · 트랙 (A) 공고 예정 후보(screen·extract·classify·compare) |
| 판정 | `SynthJev` — 포함 classify 전부 첫 클래스(포함) | `BootJev` — 포함 classify 첫 배치의 가장 작은 단지 = public_sale auto(제외), 공고 예정 이름 = 발췌 따옴표 안 이름 |
| 단언 | 같은 날 daily(같은 순서·섞기 2)·재판정·다음 날 daily: DB 스냅샷·사실 이벤트·`tools/call` | bootstrap 직후 체크리스트 = 다시 맞춘 것 · 트랙 A·제외 단지 항목 · 발행 보고서 저장본 체크리스트, 같은 날 daily(같은 순서·섞기): DB 스냅샷(체크리스트 포함)·사실 이벤트·`tools/call`·daily 체크리스트 동기화 변경 0·**발행 보고서 체크리스트 동일**, 같은 날 재판정 |

CORE10 테스트는 그대로 두었다(가짜 판정기가 단지를 제외하면 N13·N14 회귀가 덮는 단지가 줄 수 있어 범위를 바꾸지 않고 새 테스트로 넓힘). 두 테스트
모두 수정 후 통과(`r4d-full` 은 5차 원문 매니페스트로 — CORE10 165초 · CORE11 109초).

**5차 재생 매니페스트**: `scripts/replay_manifest.py` 가 bootstrap 잡 구간의 뉴스 원문(`source_kind='news'`)을 `docs.news` 로 담도록 고쳤다(일일 단계 원문
규칙은 그대로, 키·토큰 정규식 검사에 뉴스 행 포함). 5차 R4 DB 로 다시 만든 매니페스트: 청약홈 563 · 원 공고 77 · 공고문 138 · 공식 홈페이지 90 · **뉴스 1**
(scratchpad `core11/manifest/docs.json`, 원문은 `r4e/raw` 를 그 자리에서 읽음 — 저장소 밖).

## 3. m-e SQL 확인(읽기 전용)

| 데이터 | 옛 SQL(`o.type_code <> n.type_code`) | 새 SQL(runbook §10-13 ①) |
| --- | --- | --- |
| R4 5차 DB `competition` 1,906행(원 면적 코드 163 · 정수+문자 주택형 코드 1,743) | 87행 | **0행** |
| 합성 행(CTE — 4차 중복 4쌍 + 같은 회차 다른 주택형 우연 일치 3쌍('100A'·'124H' 27/0, 원 면적 코드 둘 '84.9939'·'84.9582' + '59.98') + '84.9939'↔'845' 함정) | 9 | **4**(중복 4쌍만) |

한계: 웹 폴백 경쟁률('84A')과 API 경쟁률('84.9582')이 같은 회차에 함께 있으면 새 SQL 에 걸린다 — 그 행의 `raw_document_id` 원문이 웹이면 N13 이 아니라
CORE10 §5 의 표시 겹침이다(runbook 에 적음). R4 실데이터에는 이 경우가 없었다.

## 4. 하지 않은 것 / 가정 / 남은 위험

- **실데이터 재시험은 하지 않았다** — N16 수정은 재생(5차 원문 전부 + 5차 뉴스)과 단위 테스트로만 확인했다. 다음 R4 재시험·운영 첫 지역에서 runbook §10-15
  확인 항목(bootstrap `pipeline.checklist` → 같은 날 daily `assembled.checklist` 변경 0, 두 리비전 report 저장본 `checklist` 같음)을 본다.
- **가짜 판정기 결정**: 어떤 단지가 제외되는지·뉴스에서 어떤 이름이 공고 예정 후보가 되는지는 가짜 판정기가 정한다(5차 실측의 제외 단지 45 와 재생의 제외
  단지 3 은 다르다). 트랙 A 단지 id 71·72 가 5차 실데이터와 같은 것은 같은 원문을 같은 순서로 넣어 단지 행 70개가 먼저 생겼기 때문으로 보인다(추정 — 이름까지 같은지는 비교하지 않음).
- **주간 단계 중 실거래·분양권·미분양·입주물량·벤치마크(rtms·stats)** 는 여전히 재생하지 않는다(수집기 없음 — 체크리스트 근거가 아니다). 뉴스만 넣었다.
- **수정 위치**: D24-1 문구는 bootstrap 이지만 판정 파이프라인 끝(ready 전)에 넣어 주간 수집(트랙 A 후보가 생긴 주간 재판정)·daily 뒤 재판정(새 단지가
  판정으로 제외될 때)·지역 확장에도 같이 적용된다 — 같은 결함 모양이 그 경로에도 있었다(코드 읽기로 확인, 그 경로별 실데이터 재현은 하지 않음).
- **옛 기준일 재판정**은 체크리스트를 맞추지 않는다(새 규칙). 옛 기준일 재판정 뒤 발행되는 리비전의 보고서 체크리스트는 지금 체크리스트(최신 기준일 기준)를
  그대로 쓴다 — 이전과 같은 동작.
- 이미 발행된 R4 5차 리비전 1~4 저장본은 그대로다(D11-1). 운영 DB(D19) 데이터 정정은 필요 없다(체크리스트는 다음 판정·daily 가 맞춘다, 운영 DB 는 비어 있음).
- m-a(D24-3 수용)는 범위 밖. 프론트(`frontend/**`)·계약은 바꾸지 않았다.
