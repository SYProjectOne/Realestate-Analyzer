# R9-API — 초보자 UI 데이터 요청 API 쪽 (D28-5, 계약 2026-10-09.20) (2026-10-14)

브랜치 `wp/r9-api`(main `f8c464c` = "docs: D28 novice UI improvement decisions" 기준). 계약 **`.20`** 을 이 브랜치가 냈다
(`contracts/CHANGELOG.md` 맨 위 — FE 차이 표 F1~F10, 의미 변경 S1~S3). 마이그레이션·새 라이브러리 없음. `collectors/`·`normalize/`(R9-PARSE)·
`frontend/src/pages`(R9-UI)는 고치지 않았다 — FE 는 생성물(`src/api/schema.d.ts`·`src/mocks/handlers.gen.ts`)만 다시 만들었다.

요청 원문: `docs/design/ui-benchmark/20-gap.md` §2-2 Q1·Q4·Q5·Q6·Q7·Q8·Q9, 화면 자리: `30-proposal.md`.

## 1. 무엇을 만들었나

| 요청 | 계약 | 서버 | 판단 여부 |
| --- | --- | --- | --- |
| Q1 계약금·중도금·잔금 원 금액 | `ComplexDetail.price.payment_amounts`(`PaymentAmounts`), `ComplexRow.down_payment_won` | `views.payment_amounts`·`down_payment_won_fact`·`share_fact` → `analysis.price.share_won`(ROUND_HALF_UP(P_mid × 비율 ÷ 100)). 비교 `TermsRow.down_payment_won` 도 같은 함수로 합쳤다 | 산술(RA §6-7 `P_mid × D`) — 라벨 '추정', reason '산술(P_mid × 계약금 n%)' |
| Q4 경쟁률 요약·당첨 가점 | `CompetitionSummary`(목록·점수 행·상세), `Competition.winning_score_min/max/avg` | `analysis.competition_summary.summarize`(순수 함수 — 1순위 해당지역 행의 접수 ÷ 공급 최댓값·미달 행 수), `views.competition_summary_view`(Fact 조립), `views.winning_score_fact`(`Competition` 에 가점 컬럼이 생기면 그 값, 없으면 '확인 불가(가점 미수집)') | 산술·회차 문자열 머리말(파싱) |
| Q5 사유 코드 | `Fact.reason_code`·`Intake.reason_code`·`IntakeQueueItem.reason_code`(`ReasonCode` enum 21) | `api/reason_codes.py`(저장 사유 머리말·낱말 규칙, 대기열 `queue_key` 와 같은 데이터 기준) — `facts.unknown`/`fact` 가 '확인 불가'마다 붙인다 | 문자열 규칙 |
| Q5 짧은 지역 합계 사유 | `KpiUnsold.breakdown`, 합계 reason '지역 합계(시군구 n곳)' | `routers/snapshots._sum_fact`·`dashboard_body` | — |
| Q5 변경 피드 요약 | `ChangeEvent.field_label`·`summary`·`value_kind` | `api/change_text.py`(필드 이름 표 + 값 모양 — '…_hash' 이름·16진 32자 이상 = hash, `[`·`{` = json) | 문자열 규칙 |
| Q5 생활권 이름 | `SupplyPoint`·`MoveInMarker`·`BenchmarkView`·`BenchmarkFlag` `living_area_name` | `routers/market.py`(`region.living_areas[].name`) | — |
| Q6 가격 갭 % vs 점수 | `Gap.gap_score`(새, = 옛 `score`), 성분 원값 prov `sc_<실행>_<단지>_<성분>.raw` | `gap_view`·`gap_pct_fact`·`_component_view` 원값 prov, 출처 서랍 `_component_key`·`_component_body`(한 건씩·여럿 같은 함수) | — |
| Q7 점수 행 사실 | `ScoreRow.price_low/high`·`resale_end`·`move_in_ym`·`gap_pct`·`competition_summary` | `views.score_row_facts`(목록 행과 같은 함수) → 대시보드 TOP·비교 rows·상세 score | D10-1 — 같은 리비전(발행 = 저장본) |
| Q8 접수 공급 종류 | `Intake.supply_kind`(SUPPLY_KIND 어휘)·`supply_kind_basis` | `views.supply_kind`: 수집 경로 + 상태 가능·미정·불가 행의 메모 '문구 후보'(판정 표식 조각 제외)를 `normalize.official_site_parser.scan_text`(파서 키워드 정규식)로 — 공급 종류 키워드가 정확히 한 종류일 때만 | 새 판단 없음(저장 문구 후보가 이미 말한 것만) |
| Q9 정렬 키 `intake` | `ComplexSort` 패턴 `…|intake` + 설명 | `routers/snapshots`: `INTAKE_ORDER`(가능 0 · 미정 1 · 확인 불가/행 없음 2 · 불가 3), 목록 키 `intake_deadline`(apply_dates 끝날짜 중 기준일 이후 가장 이른 날), `sort_keyed` 특례(방향은 상태에만) | 정렬 |
| 설명만(이월) | D27-3 `intake_current`·`intake.json` 설명에 D27-1 예외, D25-13 `scenario.json` RequirementRule access 공통 조건 | — | — |

**저장 모양 버전(`SHAPE_VERSION`)은 올리지 않았다(1 그대로).** 새 필드는 모두 선택이고 옛 발행 저장본(키 없음)도 계약을 통과한다. D15-3 은
"모양이 바뀔 때만 올림"이고 지금까지 선택 필드 추가(.16 `name_prov`·.17 `judge_scope_reason`)도 올리지 않았다. 올리면 이미 발행된 리비전
저장본 전부가 `_verified_raw` 에서 500 `stored_view_mismatch` 가 되고, backfill 은 모양이 다른 기존 행을 다시 쓰지 않는다(빠진 키만 채운다)
— 운영 리비전이 모두 깨진다. 새 필드는 새로 발행하는 리비전부터 저장본에 들어간다(`test_new_fields_are_optional_for_stored_revisions`).

## 2. 테스트 (먼저 쓰고 수정 전 실패 확인)

수정 전 = `git archive HEAD`(main `f8c464c`)를 scratch 에 풀고 새 테스트 파일 2개만 복사해 같은 venv 로 실행(`python -m pytest` — `app` 은
그 디렉터리에서 import 됨을 확인). 서버 함수 import 는 테스트 안에서 해 테스트마다 실패가 따로 보이게 했다.
**수정 전 87개 중 86 실패, 1 통과**(`test_q9_unknown_sort_key_still_422` — 바뀌지 않아야 하는 회귀 가드). 수정 후 87 통과.

| 테스트 | 확인하는 것 | 수정 전 |
| --- | --- | --- |
| `tests/api/test_r9_api.py::test_q1_detail_payment_amounts_are_pmid_times_ratio` | 엘리프(2): 계약금·중도금·잔금 = `share_won(P_mid, 현재 조건 비율)`, 라벨 추정·reason '산술(P_mid × 계약금 …)'·prov = price_mid prov, 1차 정액 = 공고 Fact | **실패**(`KeyError: 'payment_amounts'`) |
| `…::test_q1_same_value_in_list_row_and_compare_terms` | 목록 `down_payment_won` = 상세 = 비교 TermsRow(같은 함수·같은 Fact) | **실패**(`KeyError: 'payment_amounts'`) |
| `…::test_q1_missing_ratio_is_unknown_with_reason` | 잔금 비율이 없으면 balance_won '확인 불가'(사유·reason_code), 계약금은 그대로 | **실패**(`KeyError: 'payment_amounts'`) |
| `…::test_q4_summary_from_first_rank_local_rows` | 1순위 해당지역 2행(7.50·0.40)·기타지역·무순위 행 → rows 2, max 7.5(라벨·reason '산술(접수 750 ÷ 공급 100)'·prov = 그 행 접수 출처), 미달 1, 표시 주택형; 목록·대시보드 TOP 같은 값 | **실패**(`KeyError: 'competition_summary'`) |
| `…::test_q4_no_rows_and_winning_score_not_collected` | 기준 행 없음 → rows 0 · '확인 불가(1순위 해당지역 경쟁률 없음)'; 경쟁률 행 가점 3칸 '확인 불가(가점 미수집)'·`not_collected` | **실패**(`KeyError: 'competition_summary'`) |
| `…::test_q4_incomplete_basis_row_makes_shortfall_unknown` | 공급·접수 없는 기준 행 → 미달 수 '확인 불가(일부 누락 1건)', 최고 경쟁률은 값 있는 행으로 | **실패**(`KeyError: 'competition_summary'`) |
| `…::test_q5_reason_code_rules[×47]` | 사유 47가지(403·HTTP 500·DNS·connect·TLS·empty_dataset·원문 없음·공고 전·해석 실패·표 없음·스캔·출처 누락·검증 모순·상충·모호·일부 누락·동일성·다른 단지·문구 2·판정 대상 아님·입력 차단·미해결 3·미판정 3·미입력·비교군 없음·사람 확인·값 없음·미기재·없음·결측·모르는 사유 2·빈 사유) → 코드 | **47 실패**(`ModuleNotFoundError: app.api.reason_codes`) |
| `…::test_q5_every_unknown_fact_carries_its_reason_code` | 대시보드·목록·상세 2·시장의 모든 '확인 불가' Fact(50개 이상)에 `reason_code == reason_code(reason)`, 그 밖 Fact 엔 없음 | **실패**(`ModuleNotFoundError: app.api.reason_codes`) |
| `…::test_q5_intake_reason_code_and_queue` | 오퍼스(4) 403 → `fetch_failed`, 가능 행 null, 대기열 항목 코드 = 같은 함수(수집 실패 묶음 = `fetch_failed`) | **실패**(`KeyError: 'reason_code'`) |
| `…::test_q5_region_sum_reason_is_short_with_breakdown` | KPI 미분양 사유 '지역 합계(시군구 n곳)'(20자 이하), breakdown 합 = 합계(총·준공 후), 시리즈 사유에 나열 없음 | **실패**(합계 사유가 '지역 합계(' 로 시작하지 않음 — 단위 나열 '… 합') |
| `…::test_q5_change_feed_summary_hides_hash` | official_popup_hash 64자리 변경 → label '공식 홈페이지 팝업'·kind hash·summary '공식 홈페이지 팝업이 바뀌었습니다'(해시 없음), old/new 그대로; 계약금 변경 '계약금 비율(%): 10 → 5' | **실패**(`KeyError: 'field_label'`) |
| `…::test_q5_change_text_table[×7]` | 그림 해시('9be1…c04' 줄인 값도 이름으로 hash)·apply_dates JSON·중도금 n회차 납부일·`price_by_type.84A.max_price_won`·없음 → 값·새 공고·모르는 필드 | **7 실패**(모듈 없음) |
| `…::test_q5_market_living_area_names` | 공급·벤치마크 표식·벤치마크·입주 마커 `living_area_name` = `living_areas[].name` | **실패**(`KeyError: 'living_area_name'`) |
| `…::test_q6_gap_percent_and_score_have_distinct_names_and_drawers` | gap 원값 8.1 → `gap_pct` prov `sc_<실행>_2_gap.raw`·unit pct, `gap_score` prov `sc_…_gap`·unit score = 옛 `score`; 서랍 `.raw` field 'gap.raw'·value_text '8.1', 점수 서랍 value_text = 점수 | **실패**(`'sc_1_2_gap' == 'sc_1_2_gap.raw'` — 퍼센트와 점수가 같은 출처 id) |
| `…::test_q6_published_drawer_for_raw_gap` | 새 발행 리비전 저장 서랍에 `…_gap.raw` 가 200(D15-2 서랍 수집) | **실패**(prov 가 `.raw` 로 끝나지 않음) |
| `…::test_q7_dashboard_top_rows_carry_list_facts` · `…compare_and_detail_score_rows_carry_same_facts` · `…live_revision_same_as_list` | TOP 5·비교 rows·상세 score 의 가격·전매·입주·갭·경쟁률 요약 = 같은 리비전 목록 행(발행 저장본·발행 전 실시간 둘 다) | **3 실패**(`KeyError: 'price_low'`) |
| `…::test_q8_supply_kind_from_stored_phrase_only[×7]` | 무순위·잔여세대 선착순(→ 선착순)·임의공급 미정(→ 임의)·둘 다(null + '공급 종류 문구가 여럿(무순위·선착순)')·키워드 없음·'확인 불가' 행·판정 표식 조각만(무순위 낱말이 표식 안) → null | **7 실패**(`KeyError: 'supply_kind'`) |
| `…::test_q8_human_check_and_unofficial_rows_have_no_supply_kind` | devseed 팝업 '선착순 동·호지정' → 선착순, 사람 확인·비공식 참고 행 null | **실패**(`KeyError: 'supply_kind'`) |
| `…::test_q9_sort_by_intake_status_then_id` | `sort=intake` 상태 순, `-intake` 역순, 같은 상태 안 순서는 방향과 무관, READONLY 200 | **실패**(422 — 패턴에 없음) |
| `…::test_q9_nearest_deadline_first_within_status` | 가능 두 단지: 기준일 이후 가장 이른 접수 끝날짜가 앞(지난 일정은 무시) | **실패**(422 — 패턴에 없음) |
| `…::test_q9_unknown_sort_key_still_422` | 'intake_status' 는 여전히 422 | 통과(회귀 가드) |
| `tests/contracts/test_r9_api_contract.py`(8) | 버전 `.20` 4곳, CHANGELOG `.20` FE 차이 표(Q1~Q9·`SHAPE_VERSION` 설명·이 문서), `ReasonCode` enum = 서버 표, 정렬 패턴 = 서버 `SORT_PATTERN`, `supply_kind` 어휘 = `SUPPLY_KIND`, D27-3·D25-13 설명, 새 필드 전부 선택(저장 모양 1), 예시 9개가 서버 함수와 같은 값(계약금 산술·TOP = 목록 행·breakdown 합·변경 요약·생활권 이름·대기열 코드·모든 확인 불가 예시 Fact 코드·`_gap.raw`) | **8 실패**(`'2026-10-09.19' == '2026-10-09.20'`, `IndexError`(CHANGELOG 항목 없음), `ModuleNotFoundError`, 패턴 불일치, `KeyError: 'supply_kind'`·`'description'`, `('fact.json', 'reason_code')`, `ImportError: share_won`) |
| `tests/contracts/test_openapi.py`·`test_protocols.py`·`test_r7_queue_contract.py` | 버전 단언 `.20`(r7 은 '.19 항목 유지 + .19 이상') | 계약만 올린 상태에서 실패 → 단언 갱신 |
| `tests/api/test_schemathesis.py` | 새 정렬 값·새 필드 포함 전 operation 계약 검사(생성 사례) | 같은 테스트(새 스키마로 생성) |
| `tests/api/test_perf_r3c.py::test_list_responses_match_golden` | 목록 응답 골든(sha256·바이트) | 응답 모양이 바뀌어 골든 갱신(`UPDATE_GOLDEN=1`) — 아래 §4 |

## 3. FE 연결 메모 (R9-UI 가 맞출 자리 — 30-proposal)

| 화면 자리(30-proposal) | 지금(임시) | .20 에서 읽을 값 |
| --- | --- | --- |
| P1 G3 머리 2단 '내야 할 돈' (§2, `ko.json page.G3.summary.down/interim/balance`, `downWonMissing`) | 원 금액 칸 '확인 불가(계산값 미제공)' | `price.payment_amounts.down_payment_won`·`interim_won`·`balance_won`(FactCell, 라벨 '추정(산술(…))') · `down_payment_first_won`(1차) · 툴팁 `formula`. 키가 없으면(옛 저장본) 지금 문구 그대로 |
| P4 G2 열 '계약금 %' 옆 원 금액(갭 #12) · P5 모바일 카드 | 없음 | `ComplexRow.down_payment_won` |
| P1 G3 '현재 적용 공고' 옆 접수 종류 (§2, 요청 Q8) | `payment[].notice_kind` 만 | `intake_current.supply_kind`(값 있을 때만 '접수: 무순위'), 근거 `supply_kind_basis` 는 title. null 이면 지금처럼 공고 종류만 |
| P2 G1 TOP 카드 가격·전매·갭 (§3-1, 결정 14) | 목록 API 행을 complex_id 로 조인 | `top5[].price_low/high`·`resale_end`·`gap_pct`·`move_in_ym` — 조인 제거. 키가 없으면 조인 유지 |
| P9 G4 비교 TermsTable 위 사실 비교 | 목록 조인 | `rows[].price_low/high`·`resale_end`·`gap_pct`·`competition_summary` |
| P8 G3 '주변 시세 비교' 탭 (§9-3) | `gap.score` 를 '가격 갭 점수(0~10)'로 이름만 | `gap.gap_score`(없으면 `score`). 퍼센트 칸 출처는 `gap_pct.prov`(…`.raw`) — 서랍 value_text 가 퍼센트 |
| P8 경쟁률·추가 모집 탭 '당첨 가점' 줄 (§9-2) | '제공하지 않음 — 청약홈 경쟁률에서 확인' 링크 | `competition[].winning_score_*` 가 '확인 불가(가점 미수집)'인 동안은 지금 링크 그대로. 값이 오면 FactCell |
| G2 경쟁률 요약 열(요청 Q4 ②) · G3 머리 | 없음 | `competition_summary.max_ratio`('7.50 : 1' — 소수 2자리 그대로)·`max_ratio_type_code`·`shortfall_types`(0 = 미달 없음). rows 0 이면 '확인 불가(1순위 해당지역 경쟁률 없음)' |
| P7 '확인 불가' 쉬운 말 (§8-2, `lib/format.ts formatUnknown`) | 문자열 포함 매핑 | `reason_code` 기준: `parse_failed` → parse_failed 문구, `unresolved`, `unjudged`, `no_value`, `not_entered`, `not_published` → pre_notice … 코드가 없으면(옛 저장본) 지금 문자열 매핑. 원 사유(reason)는 title·출처 패널 |
| P2 G1 변경 피드 (§3, 갭 #4 `changeFieldText`·`changeValueText`) | `page.common.changeField` 4개 + 해시 원문 | `summary` 한 줄, `value_kind` 가 `hash`·`json` 이면 old/new 는 `<details>` '바뀐 값 보기' 안. `field_label` 은 툴팁·표 머리 |
| P2·P3 G1 미분양 카드 라벨(갭 #5) | 긴 사유 줄바꿈·40자 줄임 | 사유가 '지역 합계(시군구 n곳)'로 짧다. 내역은 `kpis.unsold.breakdown`(시군구별 FactCell — 출처 1클릭) |
| G6 입주 물량 범례(범위 밖 기록 → Q5) | `la_1~la_10` | `supply[].living_area_name`(없으면 `living_areas[]` 에서 찾기) |
| P4 G2 정렬 '접수 상태 우선'(결정 4 — 옵션) | '지금 접수 가능만' 칩 | `sort=intake`(기본 정렬은 그대로 `-total`) |

## 4. 완료 기준 실행 결과

| 기준 | 명령 | 결과 |
| --- | --- | --- |
| 백엔드 전체 | `uv run pytest -p no:randomly -m "not live"` | **4,330 통과 · 3 건너뜀 · 0 실패**(43분) |
| 새 테스트 | `uv run pytest tests/api/test_r9_api.py tests/contracts/test_r9_api_contract.py` | 87 통과(수정 전 86 실패 · 1 통과) |
| 정적 검사 | `uv run ruff check app tests` · `ruff format --check` · `uv run mypy app` | 통과 · 통과 · 172 파일 문제 없음 |
| 생성물 | `uv run python scripts/gen_contracts.py --check` · `scripts/fixture_manifest.py --check` | 0 · 0 |
| 회귀 | `python scripts/tasks.py regress` | T01~T18·모듈·흐름·e2e 3 모두 PASS(종료 코드 [0, 0, 0]) |
| 프론트 | `npm run gen:api` · `gen:msw`(재생성) → `npm run typecheck` · `npx vitest run` · `npm run lint` | 통과 · **66 파일 904 통과** · 통과 |

- 목록 골든(`tests/api/snapshots/list_r3c*`)은 `UPDATE_GOLDEN=1` 로 다시 만들었다 — 바뀐 것은 새 필드(목록 행 `down_payment_won`·
  `competition_summary`, 사유 코드)와 `gap_pct` prov `….raw`(CSV `gap_pct_prov` 열 포함)뿐. 목록 응답이 골든 기준 약 10~50% 커졌다(경쟁률 요약 Fact
  5개 + 계약금 원 금액). 발행 리비전 size=1000 cold 는 단독 실행 중앙값 0.141초(< 0.2초). 같은 테스트가 프론트 vitest 와 동시에 돌린
  첫 API 실행에서 한 번 넘었고(부하), 전체 단독 실행에서는 통과했다.

## 5. 하지 않은 것 / 가정한 것

- 당첨 가점 값은 아직 없다 — R9-PARSE 가 `Competition` 에 `winning_score_min/max/avg` 컬럼(+ 같은 이름 출처 행)을 두면 코드 변경 없이 값이
  나온다(이름이 다르면 `views.WINNING_SCORE_FIELDS`·`winning_score_fact` 한 곳). 컬럼 추가는 models(WP0) 소유라 여기서 하지 않았다.
- 중도금 금액은 비율 합계 × P_mid 하나(회차별 금액 없음). 잔금·중도금이 공고에 원 금액으로 적힌 경우는 지금 저장 칸이 없어 비율 산술만.
- '대표 타입' = 판정 기준 타입(84㎡에 가장 가까운 — `price.basis_type_code`) 하나로 읽었다. 타입마다 금액은 내지 않는다.
- `supply_kind` '본청약'은 생산 경로가 없다(어휘만 맞춤). 판정기 classify 가 공급 종류를 내게 되면(WP3) 그 값을 쓴다.
- Q9 마감 임박은 단지 `apply_dates`(본청약 일정)만 본다 — 무순위·선착순 접수에는 마감일 칸이 없어 같은 상태 안에서 뒤(id 순)로 간다.
- 화면(`frontend/src/pages`)·i18n 은 R9-UI 몫이라 고치지 않았다.
