# R10-FOLLOW — 청약 접수·당첨자 발표 일정(D29-3), 도화 중복 단지 행 병합(D29-2), 당첨 가점 '-' 사유 (계약 2026-10-09.21) (2026-10-14)

브랜치 `wp/r10-follow`(main `c1506a5` = "Merge wp/r9-parse"). 계약 **`.21`** 을 이 브랜치가 냈다(`contracts/CHANGELOG.md` 맨 위 — FE 차이 표
F1~F5, 의미 변경 S1·S2). 마이그레이션 **0018**(`checklist_item.kind` CHECK 값 2 · `complex.merged_into_id`). 새 라이브러리 없음.
이번 라운드 소유: contracts, backend normalize·scheduler·api(+ 필요한 곳의 한 줄 필터 — 아래 §3), frontend.

운영 DB(`subscription_analyzer`, 인천 지역 1)는 **읽기 전용**으로만 봤다(`SET TRANSACTION READ ONLY`, SELECT 만 — 운영 DB 는 0017, 새 열은
`defer` 로 빼고 읽음). URL·비밀값은 출력하지 않았다.

## 1. 증상 (운영 DB 읽기 전용, 2026-10-14)

| 과제 | 관측 |
| --- | --- |
| D29-3 | 체크리스트 kind 는 법적 확인·중도금·만료·공고 예상·계약·사실 재확인뿐(열린 항목 306: 법적 확인 176·중도금 99·만료 29·계약 2). 청약 일정(`complex.apply_dates`)·당첨자 발표일(`winner_date`)은 있는데 항목이 없다 — 예: 단지 1 '산곡역자이힐스테이트앤하늘채' 특별공급 10-19 · 1순위 해당/기타 10-20 · 2순위 10-21 · 당첨자 발표 10-27. G1 '다가오는 일정'은 '청약 접수일은 아직 일정에 없습니다(수집 전)' 안내 |
| D29-2 | 단지 39(2025000397, 본청약 납부 조건 13)와 99(2025940268, 임의 납부 조건 145)가 같은 이름 '두산위브 더센트럴 도화'. R9-PARSE 뒤 재정규화로 39 에도 임의 납부 조건 147(2025940268)이 붙었지만 99 는 그대로 — 99 에 주택형 6·경쟁률 6·잔여 이력 1·접수 6·점수(총점 30·성분 180)·비교군 85·체크리스트 6 행(발행 스냅샷 1~5 파생 행 포함). 사람이 넣은 자료(사람 확인·호재 연결·사람이 닫은 항목) 0. 다른 잔여 번호 행 96~98·100(연수 서해그랑블 5단지 1~4차)·101(부평 보류지)은 공고문에 원 번호 인용이 없거나 9자리 오기 |
| 과제 3 | 받아 둔 청약홈 경쟁률 팝업 58개(41 단지)의 당첨가점 묶음: 숫자 144 · 0/0/0 76 · **'-' 350**(그 1순위 행이 미달('△') 222 · 미달 아님 128). 저장은 숫자 묶음만(출처 행 660 = 220 × 3) — '-' 묶음은 후보가 없어 화면이 모두 '확인 불가(가점 미수집)'(팝업을 안 받은 것과 같은 문구) |

## 2. 원인

1. **D29-3** — 계약 `checklist_item.kind` enum(·DB CHECK)에 종류가 없어 R9-PARSE 가 항목을 만들지 않았다(R9_TESTS_PARSE §7). 데이터(`apply_dates` `{kind,start,end}`·`winner_date`)는 이미 있다.
2. **D29-2** — R9-PARSE 가 인용 정규식을 고쳐 새로 생기지는 않게 했고 재정규화가 임의공급 원문을 원 단지 39 에 쓰게 했지만(`_absorbing_original`), 이미 있는 행 99 를
   원 단지에 합치는 경로가 없었다. 행을 지우면 발행 리비전 파생 행(점수·사다리·접수·비교군)의 FK 가 깨진다(D11-1).
3. **과제 3** — `applyhome_parser._winning_scores` 가 '-' 칸에 후보를 내지 않아 '팝업에서 가점 당첨자 없음을 봤다'는 관측이 저장되지 않았다. 화면 쪽(`views.winning_score_fact`)은 값이 없으면 모두 '가점 미수집'.

## 3. 고친 것

| 파일 | 내용 |
| --- | --- |
| `contracts/schemas/checklist_item.json`·`fact.json`·`competition.json`·`openapi.yaml`·`examples/checklist.json`·`CHANGELOG.md` | 계약 .21 — kind +2, `ReasonCode` + `no_winner`(human_check 다음), 설명, MSW 예시 2항목, FE 차이 표 |
| `contracts/migrations/versions/0018_r10_follow.py` + `app/models/enums.py`·`complex.py` | CHECK 값 2 · `complex.merged_into_id`(FK complex.id, NULL). 앱 import 없음. downgrade = 새 kind 항목 삭제 + 열 삭제 |
| `normalize/checklist.py` | `apply_groups`: `apply_dates` → 순위·구분(kind 첫 낱말)과 기간이 같은 항목을 묶어 '1순위 청약 접수(해당지역·기타지역)'(잔여·임의 전체 한 칸은 '청약 접수'), 옛 `{kind,date}` 도. 기한 = 접수 시작일, 끝날짜 ≥ 기준일만(접수 중 포함), 메모 = 접수 기간. '당첨자 발표' = `winner_date`(기준일 이후). 키 `apply:<구분>`·`winner`(값이 바뀌어도 같은 항목 — R3b N-M5). `absorbed_remnant_rows` 에 병합된 행 포함 |
| `normalize/merge.py`(새) + `normalize/store.py` | 잔여 공고문이 원 공고(이미 있던 원 단지 행)를 인용하면 그 공고 **자기 번호**의 다른 단지 행을 원 단지에 병합(`merged_into_id`, 이름이 다르면 원 단지 `former_names` 별칭 — D20-2 와 같은 모양) + change_event(`complex`·`merged_into`, critical, complex_id = 원 단지). 첫 적재면 요약 수로 접힘. 병합된 행의 번호로 오는 뒤 원문은 원 단지로(단지 단위 값은 덮지 않음 — D11-4). 원 단지 찾기(`_absorbing_original`·`_remnant_target`·같은 블록·공고 예정 후보)는 병합된 행을 고르지 않는다. 원 단지 행을 이 원문이 새로 만든 경우(자리표시)·인용이 없는 경우는 병합하지 않는다 |
| 병합된 행 제외(한 줄 필터 `Complex.merged_into_id.is_(None)`) | `scheduler/inputs.load_facts`(판정·점수 입력) · `scheduler/collect`(첫 적재 요약 수·원 공고 다시 받기·입주 물량) · `snapshot_view`(발행 저장본 단지) · `api/routers/snapshots`(실시간 목록·대시보드) · `api/views` 지역 하위 질의 · `api/routers/market`·`analysis`(민감도)·`catalysts`(생활권 연결) · `api/intake_queue` · `normalize/living_area`(법정동 재배정)·`remaining`(원 단지 대조)·`upcoming`(공고 예정 대조) · `collectors/official_site`(수집 대상 — WP1 파일, 한 줄) · `reports/data`(보고서 단지 범위 — WP8 파일, 두 줄) |
| `normalize/applyhome_parser.py`·`fields.py` | 팝업 당첨가점 '-' → 값 없는 '확인 불가' 후보(원문 '-', 사유 `WINNING_SCORE_DASH_REASON` = "가점 당첨자 없음(청약홈 '-')"). 값 있는 후보가 이긴다(resolver 규칙 1), 저장 값은 지우지 않는다 |
| `api/views.py`·`routers/complexes.py`·`reason_codes.py`·`change_text.py` | `winning_score_fact`: 값 없음 → ① 당첨자 발표일 > 기준일 '발표 전(당첨자 발표 …)'(`not_published`) ② '-' 출처 행이고 발표 뒤 관측 → 행 경쟁률 원문 '△' 면 '가점 당첨자 없음(미달)', 아니면 출처 행 사유(`no_winner`, prov = 팝업 출처 행) ③ '가점 미수집'. 요약 최저·최고는 `no_winner` 행을 빼고 셈. 사유 코드 규칙 + '발표 전'·`no_winner`. 변경 피드 '같은 사업 단지 병합' 한 줄 요약 |
| frontend | `npm run gen:api`·`gen:msw` 재생성. G1 다가오는 일정: 안내 문구 삭제, 청약 접수 항목 둘째 줄에 어느 순위인지(`scheduleDetail`). G7 체크리스트 종류(`checkKind`)·`CHECKLIST_KINDS`·eslint 한글 허용 목록(계약 enum 값). G3 경쟁률 가점 칸: `no_winner` → '가점 당첨자 없음(미달)'/'가점제 당첨자 없음', `not_published` → '발표 전', `not_collected` → '가점 미수집'(원 사유 title), 가점 열은 값 또는 그 두 사유가 있으면 보인다 |

판단은 늘지 않았다(규칙 3) — 날짜 정리·문자열 대조(인용 번호·'△'·사유 머리말)·표 조회뿐. 판정기 호출 경로 변경 없음.

## 4. 수정 전 실패 표

수정 전 = `git archive c1506a5`(main)를 scratch 에 풀고 새 테스트 파일만 복사해 같은 venv 로 `python -m pytest`(`app` 은 그 디렉터리에서 import —
확인함). 프론트는 같은 archive 의 `frontend`(node_modules 연결)에서 `npx vitest run`. **백엔드 새 테스트 28 개 모두 실패, 프론트 새·바뀐 테스트 8 중 6 실패**
(통과 2 는 바뀌지 않아야 하는 회귀 가드).

| 테스트 | 확인하는 것 | 수정 전 |
| --- | --- | --- |
| `tests/normalize/test_r10_follow.py::test_d29_3_apply_and_winner_items_from_complex_dates` | 운영 단지 1 모양 → 특별공급·1순위(해당지역·기타지역)·2순위(…) 청약 접수 + 당첨자 발표 4항목, 메모 | **실패**(`AssertionError: []` — 항목 없음) |
| `…::test_d29_3_open_window_kept_until_end_past_ones_not_created` | 접수 중(10-19~10-22, 기준일 10-20)은 둠·메모 기간, 끝난 접수·지난 발표는 만들지 않음 | **실패**(항목 없음) |
| `…::test_d29_3_old_shape_and_remnant_window` | 옛 `{kind,date}`·잔여 '청약접수' 한 칸 → '청약 접수' | **실패**(항목 없음) |
| `…::test_d29_3_item_keys_are_stable` | 키 `apply:1순위(해당지역·기타지역)`·`apply:`·`winner`, 다른 종류의 같은 글자는 사람 키 | **실패**(`'title:청약 접수:…'`) |
| `…::test_d29_3_idempotent_and_date_change_updates_same_item` | 같은 날 다시 맞추면 0, 발표일 변경 → 같은 항목 기한만(updated 1) | **실패**(`(0, 0) == (0, 1)`) |
| `…::test_d29_3_excluded_or_merged_complex_gets_no_items` | 범위 경계·병합된 행 → 항목 없음, 병합 뒤 그 행 항목 auto 로 닫힘 | **실패**(`0 == 4` — 항목이 안 생김) |
| `…::test_d29_2_cited_notice_merges_existing_duplicate_row` | 운영 39/99 모양 + 도화 원문 재정규화 → 99.merged_into_id = 39, change_event 1(critical, complex_id 39), 별칭 그대로, 임의공급 API 경쟁률은 39 에, 다시 정규화(역순·연결 없이) DB 그대로·이벤트 0 | **실패**(`AttributeError: merged_into_id`) |
| `…::test_d29_2_merged_row_redirects_later_documents` | 병합 뒤 그 번호의 청약홈 원문이 인용 없이 와도 원 단지에 | **실패**(같음) |
| `…::test_d29_2_uncited_remnant_row_is_not_merged` | 공고문 인용 없이(청약홈 원문만) → 병합 안 함·이벤트 없음 | **실패**(같음 — 열 없음) |
| `…::test_d29_2_first_load_merge_is_folded` | 첫 적재 안의 병합 → 이벤트 대신 요약 수 | **실패**(같음) |
| `…::test_dash_score_cells_are_unknown_candidates_with_reason` | 팝업(2025000271) '-' → 1순위 해당·기타지역 행에 값 없는 '확인 불가' 후보 3칸(원문 '-', 사유), 2순위 행엔 없음 | **실패**(`('해당지역', {})`) |
| `…::test_dash_scores_stored_as_reasoned_unknown_and_idempotent` | '-' 출처 행 저장·재정규화 0·나중 팝업 숫자는 채택(첫 값 이벤트 없음) | **실패**(`NoResultFound` — 출처 행 없음) |
| `tests/api/test_r10_follow_api.py::test_reason_codes_for_new_winning_score_reasons` | '가점 당첨자 없음(…)' → `no_winner`, '발표 전(…)' → `not_published` | **실패**(`'other' == 'no_winner'`) |
| `…::test_dash_cells_give_no_winner_reasons_distinct_from_not_collected` | 미달 '△' → '가점 당첨자 없음(미달)'·prov fp_, 미달 아님 → 출처 사유, 발표 전에 받은 '-'·팝업 없음 → '가점 미수집' | **실패**(모두 '가점 미수집') |
| `…::test_before_announcement_is_not_published` | 발표일 > 기준일 → '발표 전(당첨자 발표 …)' · 요약도 | **실패**('가점 미수집') |
| `…::test_summary_skips_no_winner_rows` | 요약은 가점 당첨자 없는 행 빼고 42/63, 사유에 '1행 제외', 모두 '-' 면 그 사유 | **실패**('가점 미수집') |
| `…::test_checklist_new_kinds_are_stored_and_listed` | 새 kind 저장(CHECK)·`GET /ops/checklist` 계약 통과(쓰기·읽기 토큰) | **실패**(`CHECK constraint failed: ck_checklist_item_kind`) |
| `…::test_merged_row_leaves_new_revision_but_published_view_is_unchanged` | 발행 리비전 목록·TOP 5 그대로(D11-1)·옛 상세 200, 새 리비전(실제 발행 경로)에서는 빠짐 | **실패**(새 리비전에 그대로 — `1 not in {…}`) |
| `…::test_merged_row_leaves_live_list_and_market` | 실시간 목록·대시보드에서 빠짐 | **실패**(목록에 그대로) |
| `…::test_merge_event_summary` | field_label '같은 사업 단지 병합'·summary '중복 단지 행 병합: …' | **실패**(`'merged_into'`) |
| `tests/contracts/test_r10_follow_contract.py`(6) | 버전 .21 4곳·CHANGELOG .21 FE 표(F1~F5·0018·SHAPE_VERSION)·kind enum = models·`ReasonCode` = 서버(no_winner 위치)·MSW 예시 2항목(서버 키 규칙)·0018 왕복(0017 CHECK 거부 → head 허용·FK → downgrade 가 새 kind 삭제·열 삭제) | **6 실패**(`'.20' == '.21'`, IndexError, enum, 예시 없음, CHECK) |
| `tests/scheduler/test_r10_follow_flow.py::test_daily_collect_merges_duplicate_and_syncs_checklist` | `collect`(applyhome + notice_pdf 단계, 녹화 원문) 한 번 → 병합 + 이벤트 + `load_facts` 에서 빠짐 + 체크리스트(원 단지만 새 종류·중도금, 같은 일정 두 번 없음) · 같은 날 다시 → 이벤트 0·DB 그대로 | **실패**(`AttributeError: merged_into_id`) |
| `…::test_rejudge_after_merge_scores_without_the_merged_row` | 병합 뒤 새 리비전 재판정: 점수·사다리·주장에 병합된 행 없음, 발행 리비전 행은 그대로 | **실패**(병합된 행이 점수에 — `2 not in {…}`) |
| `frontend/src/pages/wiring21.test.tsx` G1 일정 | 청약 접수(둘째 줄 '1순위 청약 접수(해당지역·기타지역)')·당첨자 발표, 안내 문구 없음 | **실패** |
| `…` G7 캘린더·범례·종류 칸 | 두 종류 | **실패** |
| `…` `scheduleDetail` | 청약 접수만 둘째 줄 | **실패**(함수 없음) |
| `…` G3 '-' 미달/미달 아님 | '가점 당첨자 없음(미달)'·'가점제 당첨자 없음'·title 원 사유·안내 줄 없음 | **실패** |
| `…` G3 발표 전·미수집 | '발표 전'·'가점 미수집' | **실패** |
| `…` 잔여 전체 접수 한 칸 · 모두 미수집이면 안내 줄 | 회귀 가드 | 통과 · 통과 |
| `frontend/src/pages/dashboard/dashboard.test.tsx` 다가오는 일정(바꿈) | 안내 문구 없음(예전: 있어야 함) | **실패**(안내 문구 있음) |

바뀐 옛 테스트(의도한 변경): `tests/normalize/test_r9_parse.py::test_q4_popup_winning_scores_per_type_and_area`('-' 는 후보 없음 → 값 없는 '확인 불가' 후보),
`tests/contracts/test_migrations.py`(head 0018), `test_openapi.py`·`test_protocols.py`(버전 .21), `test_r9_api_contract.py`(버전 단언 '.20 이상' — r7 과 같은 관례),
`dashboard.test.tsx`(안내 문구 없음).

## 5. 완료 기준 실행 결과

| 기준 | 명령 | 결과 |
| --- | --- | --- |
| 백엔드 전체 | `uv run pytest -p no:randomly -m "not live"` | **4,399 통과 · 6 건너뜀 · 0 실패**(34분) |
| 새 테스트 | `uv run pytest tests/normalize/test_r10_follow.py tests/api/test_r10_follow_api.py tests/contracts/test_r10_follow_contract.py tests/scheduler/test_r10_follow_flow.py` | 28 통과(수정 전 28 실패) |
| 정적 검사 | `uv run ruff check app tests` · `ruff format --check` · `uv run mypy app` | 통과 · 통과 · 175 파일 문제 없음 |
| 생성물 | `uv run python scripts/gen_contracts.py --check` · `scripts/fixture_manifest.py --check` | 0 · 0 |
| 회귀 | `python scripts/tasks.py regress` | T01~T18·모듈·흐름·e2e 3 모두 PASS(종료 코드 [0, 0, 0]) — **골든 변경 없음**(목록 골든 `list_r3c*`·회귀 골든 그대로) |
| 프론트 | `npm ci` · `gen:api`·`gen:msw` · `npm run typecheck` · `npm run lint` · `npx vitest run` · `npm run build` · `npm audit` | 통과 · 재생성 · 통과 · 통과 · **74 파일 1,025 통과** · 통과 · 취약점 0 |
| e2e | `npm run e2e`(E2E_PORT 6773 · E2E_PAGES_PORT 6771 · E2E_PERF_PORT 6772) | 스모크 46 통과(차트 갤러리 스크린샷 포함 — 차트 그림 변경 없음) · 화면 32 통과 |
| e2e:api | `npm run e2e:api`(새 E2E_API_DATA, E2E_API_PORT 17995 · E2E_API_WEB_PORT 6791) | 47 통과 |
| 운영 DB 건식 실행 | 읽기 전용 — `checklist._wants` 를 기준일 2026-10-15 로 | 새 항목 4(단지 1), 병합 후보 99 → 39 |

## 6. 하지 않은 것 / 가정한 것

- **기한 = 접수 시작일**로 정했다(달력에 '접수하는 날'). 마감은 메모(기간)에 있다. 접수 중(시작 < 기준일 ≤ 끝)인 항목은 기한이 지났어도 만든다/둔다.
- 같은 순위의 해당지역·기타지역이 **같은 기간**이면 한 항목(제목 괄호)으로 묶었다 — G1 다가오는 일정(최대 5건)이 한 단지의 거주지역 구분으로 차지 않게. 기간이
  다르면 따로('1순위 청약 접수(해당지역)'·'(기타지역)').
- 원 단지에 묶인 잔여·임의 공고의 접수(`remaining_event.apply_dates`)는 항목을 만들지 않았다(D29-3 '데이터는 complex.apply_dates·winner_date').
- 병합된 행은 지우지 않고 표식만 — 그 행의 옛 사실 행(납부 조건·경쟁률 등)은 이력으로 남는다(원 단지는 재정규화로 같은 원문 값을 가진다). 병합된 행의 사람 확인·호재
  연결은 옮기지 않는다(운영 도화 99 는 0건 — runbook §10-23 ① SQL 로 확인).
- 병합 필터를 넣지 않은 곳: 이름 표(변경 피드·보고서 이름 매핑 — 옛 이벤트가 이름을 찾게), `regions` 생활권 편집·지역 확장 재배정(표식 행도 일관되게), 강등 대상 이름
  검사, 변경 원장 조회(병합 이벤트는 complex_id = 원 단지).
- 같은 스냅샷(발행 전 리비전)에서 병합 전에 만든 병합된 행의 사다리·주장 행은 그 리비전에 남는다(쓰이지 않음 — 목록·점수에서 빠짐). 운영은 발행 뒤 새 리비전이라 해당 없음.
- 당첨 가점 '-' 의 뜻(미달·추첨제·해당지역에서 마감)은 나누지 않았다 — 원문 '△' 만 '(미달)'로 붙인다(판단 아님). 발표 당일 이전에 받은 팝업의 '-' 는 결과로 보지 않는다
  ('가점 미수집' — 수집기가 발표 뒤 다시 받는다).

## 7. 제안

- 새 라이브러리 없음.
- 원 단지에 병합된 행의 상세(`GET /complexes/{병합된 id}`)는 옛 리비전 링크라 그대로 열린다 — 화면에서 '이 단지는 <원 단지>에 병합됨' 안내를 하려면 `ComplexDetail.header`
  에 `merged_into_id`(선택) 노출이 필요하다(다음 계약 버전 후보).
