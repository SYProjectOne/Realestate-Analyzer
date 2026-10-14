# R9-PARSE — 공고문 납부 표·청약 일정·당첨가점·실거래 경로·G7 캘린더 중복 (2026-10-14)

브랜치 `wp/r9-parse`(main `f8c464c` — D28). 요청 원문: `ui-benchmark/20-gap.md` §2-2 **Q2·Q3·Q4(수집 쪽)·Q12**, `00-baseline.md` §6,
DECISIONS D28-5. 추가 요청(조정자): G7 캘린더에 '두산위브 더센트럴 도화 · 중도금 3~6회차 납부일'이 두 번씩 나온다.

저장·파싱만 고쳤다 — API·계약(openapi·schemas) 노출은 R9-API(계약 `.20`) 몫이다(§6 표가 R9-API 가 이어 붙일 저장 위치).
새 라이브러리 없음. 마이그레이션 1개(`contracts/migrations/versions/0017_r9parse_competition_scores.py`, 열 추가만).

운영 DB 는 **읽기 전용**으로만 봤다(`SET TRANSACTION READ ONLY`, SELECT). 원문 파일은 `backend/data/raw`(읽기만)에서 공개 공고 발췌를
픽스처로 옮겼다(`backend/tests/normalize/fixtures/r9_parse/manifest.json` — 남긴 줄 범위·sha256, 납부 계좌 줄 제외).

## 1. 증상 (운영 DB, 인천 지역 1)

| 요청 | 관측 |
| --- | --- |
| Q2 | 단지 32(시티오씨엘 8단지) `payment_terms` 2행(2025000560 본청약·2025910275 무순위) 모두 `interim_schedule = [{seq 2, 2028-12-07, 35%}]`, `balance_pct NULL`('잔금 비율 표기 해석 실패'). 같은 모양 4건(단지 32 의 2건 + 같은 HDC 양식 2건). 잔금 비율 NULL 은 146행 중 51행 |
| Q2 | `complex_type.options_text` 654행 중 276행이 고지문 '상기 공급금액에는 발코니 확장비용 및 추가 선택품목[유상옵션] 비용이 미포함된 가격이며…' — 가격표 '필수 옵션' 칸에 매 행 반복 |
| Q2 | `floor_sample_text` 가 대부분 '1층'(단지 32: 8타입 중 6타입) |
| Q3 | `complex.apply_dates` 는 101단지 중 96단지에 있으나 모양이 `[{kind:'특별공급'·'1순위'·'2순위', date}]` — **시작일만**, 해당지역·기타지역 구분 없음, 마감일 없음 |
| Q4 | 경쟁률 2,610행(92단지)은 공식 API 로 수집되나 **당첨가점은 0** — API 경쟁률에 가점 필드가 없고, 웹 경쟁률 팝업(가점이 있는 유일한 곳)은 API 실패 때만 받았다(운영 원문 HTML 226개 중 팝업 0) |
| Q12 | 실거래 수집기 원문은 모두 `apis.data.go.kr`(RTMSDataSvcAptTrade·SilvTrade) |
| G7 중복 | 열린 날짜 항목 중 같은 (단지 이름, 제목, 날짜)가 둘인 것 = 도화 4건뿐: 단지 **39**(applyhome 2025000397, 본청약)와 **99**(2025940268, 임의공급) — 서로 다른 단지 행. 두 행의 `payment_terms`(2025000397 본청약·2025940268 임의)가 같은 중도금 일정을 가져 각자 체크리스트를 만들었다 |

## 2. 원인

1. **Q2 중도금 '2회차 35%' 한 줄** — `notice_parser._INSTALL_RE`(`(\d)(회|차)\s*\((\d+)%\)`)가 표 머리 줄
   `계약금1차 계약금2차 (35%)`(계약금 분납 열 머리 + 다음 열 머리 '잔금 (35%)'가 pdfplumber 로 한 줄에 붙음)의 **'2차 (35%)'를 중도금
   회차로** 읽었다. 진짜 회차 머리 `1회 2회 … 6회` 와 비율 줄 `10% … 10%` 는 서로 다른 줄이라 정규식이 못 읽었다 → 회차 1개 + 마지막 날짜.
2. **Q2 잔금 '해석 실패'** — `_BALANCE_RE` 는 `잔금(35%)` 처럼 붙은 표기만 읽는다. 이 양식은 '잔금' 과 '(35%)' 가 다른 줄.
3. **Q2 필수 옵션 칸 고지문** — `_options` 가 '추가 선택품목 비용 미포함' 문장(필수 옵션 0원의 **근거**)을 `options_text`(옵션 **설명**)에도
   그대로 넣었다(R3 3차 'RA 부분'). 화면은 options_text 를 필수 옵션 칸에 표시한다.
4. **Q2 '대표 층' 1층** — 결함 아님. 계약 `complex_type.floor_sample_price_won` = RA §6-1 구매가 범위의 **아래 끝**이고 파서는 그 타입의
   **최저 공급금액 행**을 고른다 — 대부분 1층이 최저가다(75 는 1층 행이 없어 2층, 136P 는 45-46층). 바꾸면 P_low·P_mid·점수·골든이 바뀐다
   — 화면 이름('대표 층' → '최저가 층')으로 풀 일이다(요청 §7).
5. **Q3** — 청약홈 API(`GNRL_RNK1_CRSPAREA_RCPTDE/ENDDE`·`…ETC_AREA…`·`…ETC_GG…`·`SPSPLY_RCEPT_BGNDE/ENDDE`·`SUBSCRPT_RCEPT_*`)와 웹 상세
   (특별공급·1순위·2순위 × 해당지역·기타지역 칸)에는 다 있는데 파서가 '해당지역' 시작일 하나만 읽었다. 웹 잔여세대 화면의 '청약접수' 칸은
   읽지 않았다(API 와 웹이 다른 값 — 테스트가 비교에서 apply_dates 를 빼 두었다).
6. **Q4** — 수집 경로 누락(위 표). 파서도 팝업의 당첨가점 칸(`td.cpResideSenm` + 최저·최고·평균, rowspan 2)을 읽지 않았고 저장 열도 없었다.
7. **G7 중복** — 임의공급 공고문(2025940268)의 원 공고 인용이 조사 없는 변형
   `… 임의공급 입주자모집공고 주택관리번호는 2025-940268이며, 최초 입주자모집공고일 주택관리번호 2025-000397으로 각각 상이함으로 …` 이다.
   `_ORIG_NO_RE` 는 `주택관리번호는` 만 읽어 인용을 놓쳤고(D18-4 실패) → 공고문·임의공급 API 원문이 잔여 공고 번호로 **두 번째 단지 행(99)**
   을 만들었다(같은 블록 병합은 주소가 '…번지 일원'(구역 표현)이라 D10-4 대로 하지 않음). 두 행이 같은 일정을 가져 캘린더에 두 번.
   **구별 속성**: 단지 행(39 = 본청약 2025000397 · 99 = 임의공급 2025940268)과 납부 조건의 공고(notice_no·notice_kind) — 항목 제목·날짜는 같다.
   (운영 DB 의 다른 잔여 번호 행 6개는 공고문에 원 번호 인용이 없거나(연수 서해그랑블 5단지 1~4차, 96~98·100 — 공고문에 '최초' 번호
   문장 없음), 9자리 오기('최초 보류지 … 주택관리번호는 202400173' — 101)라 고칠 수 있는 파싱이 아니다. 캘린더 중복은 도화뿐.)

## 3. 고친 것

| 파일 | 내용 |
| --- | --- |
| `normalize/notice_parser.py` | `_INSTALL_RE` 에 '계약금' 바로 뒤 회차 제외. `_split_installments`: 회차 머리 줄 `1회 … k회`(1부터 연속) + 그 뒤 '%' 가 정확히 k개인 줄(계약금·중도금·잔금 낱말 없는 줄), **비율 합 = 중도금 비율일 때만**. 잔금 비율을 바로 못 읽고 계약금·중도금 비율이 있으면 `100 − 계약금 − 중도금`, 라벨 **'추정'**·사유 `산술(100-계약금-중도금)`, 발췌 = 납부 표 머리. **판정기 extract 요청은 그대로 남긴다**(needs_extract, 예전 '확인 불가' 후보와 같은 발췌 = 같은 요청·같은 캐시 키) — 판정기가 auto 로 읽으면 그 추출 행('확인됨')이 산술 값을 대신한다(OCR 판독 후보와 같은 규칙). `options_text`: 고지문 0원 경로는 **null**(후보는 내서 옛 값을 지운다 — 0원 후보의 발췌에 고지문이 남는다). 원 공고 인용 `주택관리번호(?:는|은)?` |
| `normalize/applyhome_api_parser.py` | `APPLY_KINDS`·`apply_items`·`apply_text`: apply_dates = `[{kind, start, end}]`, kind ∈ 특별공급 / 1·2순위 × 해당지역·기타경기·기타지역 / 일반공급 / 청약접수(다른 구분이 있으면 전체 기간인 '청약접수'는 뺀다) |
| `normalize/applyhome_parser.py` | 웹 상세 일정 표: 머리 행(구분·해당지역·[기타경기]·기타지역)으로 칸을 읽어 API 와 **같은 JSON**(운영 원문 259 공고 중 두 원문이 다 있는 226 공고 모두 일치 — 다른 값 0). 잔여·임의 '청약접수' 한 칸·'일반공급' 행. 경쟁률 팝업 `_winning_scores`: `td.cpResideSenm` 뒤 세 칸 → `competition.winning_score_min/max/avg`, 행 키 `<번호>:본청약:1순위 <거주지역>:<원 면적 코드>`(API 행과 같은 행). '-'(발표 전·가점 당첨자 없음)는 후보 없음, 숫자는 원문 그대로(0 포함) |
| `normalize/fields.py`·`resolver.py`·`judged.py` | `is_provisional`(OCR 판독 + 잔금 산술 — 같은 원문 판정기 추출 행이 생기면 물러남, 추출의 대상 행), `BALANCE_DERIVED_REASON`. `DECIMAL_FIELDS` 에 winning_score_*; `QUIET_FIRST_FIELDS`: 당첨가점의 빈 값 → 값(처음 수집)은 change_event 없음(지난 결과 — 배포 뒤 첫 수집이 경쟁률 행마다 이벤트를 쏟지 않게), 값 → 다른 값은 info 이벤트 |
| `normalize/store.py` | `complex_for`: 잔여 공고 원문의 번호로 이미 단지 행이 있어도, 그 번호가 같은 지역 **다른** 단지의 납부 조건 공고번호면(D18-4 인용으로 붙은 원 단지) 그 원 단지에 쓴다(merged — 원 단지 값을 덮지 않음). `QUIET_FIRST_FIELDS` 적용 |
| `normalize/checklist.py` | `absorbed_remnant_rows`: 다른 단지의 납부 조건 공고번호를 주택관리번호로 가진 행(인용을 못 읽던 때 생긴 같은 사업의 두 번째 행)은 체크리스트에서 제외처럼 — 열린 자동 항목을 na(closed_by auto)로 닫고 새로 만들지 않는다. 사람 항목은 그대로 |
| `collectors/applyhome/collector.py` | API 경로: APT 공고는 `last_date`(당첨자 발표·접수 마감 중 늦은 날)가 지났고 받아 둔 팝업이 없거나 그날까지 받은 것뿐이면 **웹 경쟁률 팝업**을 받는다(끝난 공고 경로 포함 — 한 번). 받아 둔 발표 뒤 팝업은 다시 쓴다. `fetch_originals`(원 공고 다시 받기)도 API 상세가 있을 때 팝업 한 번. 잔여·임의 팝업은 가점이 없어 받지 않는다. `web_detail=False` 면 받지 않는다(테스트·운영 끄기). 공개 페이지·`core.http` 속도 제한·robots(청약홈 robots 404) |
| `models/complex.py` + `0017` | `competition.winning_score_min/max/avg` Numeric(5,2) NULL — **WP0 소유 파일**(마이그레이션과 models↔migration diff 0 때문에 함께 바꿈) |
| `tests/contracts/test_migrations.py` | head = 0017(**WP0 소유 테스트** — 마이그레이션 추가에 따른 한 줄) |

판단은 늘지 않았다(규칙 3) — 표 읽기·산술(100 − a − b)·문자열 대조뿐. 잔금 산술 값은 '추정'.

## 4. 수정 전 실패 표 (새 테스트를 main `f8c464c` 앱 코드로 돌림 — 새 이름 import 는 대체 값으로 바꿔 돌림)

| 테스트 | 수정 전 | 수정 뒤 |
| --- | --- | --- |
| `tests/normalize/test_r9_parse.py::test_q2_interim_schedule_has_six_installments` | FAIL — `[{seq 2, 2028-12-07, 35%}]` | PASS |
| `…::test_q2_down_payment_second_column_is_not_an_installment` | FAIL — '계약금2차 (35%)' 매치 | PASS |
| `…::test_q2_balance_pct_is_derived_and_labelled_estimate` | FAIL — '확인 불가'(잔금 비율 표기 해석 실패) | PASS |
| `…::test_q2_balance_pct_read_directly_stays_confirmed` | FAIL — 키 `2025940268:2025940268`(인용 못 읽음) | PASS |
| `…::test_q2_options_text_is_not_the_boilerplate` | FAIL — options_text = 고지문 | PASS |
| `…::test_q2_renormalize_clears_stored_boilerplate_and_fills_schedule` | (수정 중 추가 — 옛 저장 상태에서 재정규화) | PASS |
| `…::test_q2_derived_balance_keeps_extract_request_and_yields_to_judge` | (수정 중 추가 — §8) | PASS |
| `…::test_q2_floor_sample_is_lowest_priced_row_by_definition` | PASS(정의 고정 — 바꾸지 않음) | PASS |
| `…::test_dohwa_citation_without_particle_is_read` | FAIL — 납부 조건 키가 잔여 번호 | PASS |
| `…::test_dohwa_notice_numbers` | FAIL — `('2025940268', None)` | PASS |
| `…::test_dohwa_fresh_store_makes_no_second_complex_row` | FAIL — 단지 행 2025940268 생성 | PASS |
| `…::test_dohwa_existing_stray_row_is_absorbed_and_calendar_not_duplicated` | FAIL — 재정규화 뒤에도 같은 일정 두 번 | PASS |
| `…::test_q3_api_apply_dates_by_rank_and_area_with_start_end` | FAIL — `[{kind:'1순위', date}]` | PASS |
| `…::test_q3_remnant_apply_window_has_start_and_end` | FAIL — 시작일만 | PASS |
| `…::test_q3_web_detail_and_api_give_the_same_apply_dates` | FAIL — 웹 잔여 화면 '청약접수' 미파싱 | PASS |
| `…::test_q4_popup_winning_scores_per_type_and_area` | FAIL — 가점 후보 없음 | PASS |
| `…::test_q4_popup_and_api_agree_on_ratios` | PASS(회귀 방지 — 팝업·API 경쟁률 같은 값) | PASS |
| `…::test_q4_scores_stored_with_provenance_and_idempotent` | FAIL — 열 없음 | PASS |
| `…::test_q4_first_scores_are_quiet_later_change_is_info_event` | (수정 중 추가) | PASS |
| `tests/collectors/applyhome/test_r9_q4_score_popup.py` 3개 | FAIL — 팝업 미수집 | PASS |
| `tests/collectors/rtms/test_r9_q12_openapi_only.py` 3개 | PASS(확인 — Open API 만) | PASS |

바뀐 옛 테스트(의도한 값 변경): `test_applyhome_api_parser.py`(apply_dates 종류 + API·웹 비교에서 apply_dates 제외를 풀어 **강화**),
`test_applyhome_parser.py`(종류), `test_notice_prices.py`(라벨 '추정'은 잔금 산술만 허용), `test_r3c_features.py`(options_text null).

## 5. 운영 영향(배포 뒤 첫 `collect.daily`) — 읽기 전용 재생 추정

공고문 텍스트 전부(픽스처 16 + 운영 원문 텍스트 232)를 고치기 전·후 파서로 돌려 후보를 비교했다(`dump_notice`·`cmp`, 운영 DB·파일 쓰기 없음).

| 무엇 | 바뀌는 수 | 이벤트 |
| --- | --- | --- |
| `payment_terms.balance_pct` NULL → '추정' 산술 | 공고문 35건(운영 32 + 픽스처 3: 스위첸·호반3·리버프론트) | critical(`CRITICAL_FIELDS`) → 그 단지 재판정 잡. 판정기 입력(점수 입력은 `down_payment_pct` 만)은 그대로라 캐시 적중 예상 |
| `interim_schedule` | 운영 4건(단지 32 두 공고·HDC 양식 2건) 1행 → 6행, 픽스처 호반3 '확인 불가' → 6행 | critical |
| `options_text` 고지문 → null | 376 후보(운영 276행) | info(값 → null, 재판정 없음) |
| `apply_dates` 모양 | 청약홈 원문 있는 단지 전부(≈ 96) | notice(`severity_for` — 재판정 없음) |
| 도화 임의공급 | 공고문 납부 조건·타입 가격이 단지 39 로(새 `payment_terms` 1행 — 새 공고 이벤트), API 경쟁률·잔여 이력도 39. 단지 99 의 열린 자동 항목 → na | 새 공고 1 + 99 체크리스트 닫힘 |
| 판정기 extract 요청 | 잔금 산술은 extract 요청을 그대로 남겨 요청이 같다(캐시 적중). 바뀌는 묶음은 도화 임의공급 공고문 1건(단지 키 2025940268 → 2025000397, `resale_months`) | 첫 수집 `extract` `tools/call` **≈ 1**, 같은 날 다시 돌리면 0 |
| 당첨가점 팝업 | APT 92 단지 × 1회 GET(1 req/s ≈ 1.5분) | `QUIET_FIRST_FIELDS` — 이벤트 0 |

발행된 리비전 저장본은 그대로(D11-1) — 다음 발행부터 반영.

## 6. R9-API 가 이어 붙일 저장 위치 (계약 `.20` 노출용)

| 화면 요청 | 테이블.열 | 모양·라벨 | 출처 행(`field_provenance`) |
| --- | --- | --- | --- |
| 청약 접수 일정(Q3) | `complex.apply_dates` (JSON) | `[{kind, start, end}]` ISO 날짜. kind 순서 = `normalize.applyhome_api_parser.APPLY_KINDS`(특별공급·1순위 해당지역·1순위 기타경기·1순위 기타지역·2순위 …·일반공급·청약접수). 지금 `api/views._schedule` 이 `start`·`end` 를 이미 읽는다(ScheduleItem 모양 그대로) | entity 'complex', field 'apply_dates' 1행(청약홈, 확인됨) |
| 당첨자 발표·계약 | `complex.winner_date`, `complex.contract_dates`(`[{from,to}]`) | 그대로 | 그대로 |
| 중도금 회차(Q2) | `payment_terms.interim_schedule` (JSON) | `[{seq, due_date, pct}]` | entity 'payment_terms', field 'interim_schedule' |
| 계약금·잔금 비율(Q2) | `payment_terms.down_payment_pct`·`down_payment_first_won`·`interim_pct`·`balance_pct` | balance_pct 는 산술이면 출처 행 라벨 **'추정'**·reason `산술(100-계약금-중도금)` — Fact 라벨을 출처 행에서 그대로 | entity 'payment_terms' |
| 계약금 원 금액(Q1) | 저장 열 없음 — `analysis`(§6-7 `P_mid × D`, TermsRow.down_payment_won)와 같은 식으로 R9-API/WP4 가 계산 | — | — |
| 당첨가점(Q4) | `competition.winning_score_min`·`winning_score_max`·`winning_score_avg` (Numeric(5,2), NULL = 없음) | 행 = (단지, kind '본청약', round **'1순위 <거주지역>'**, type_code 원 면적 코드). 표시 주택형은 `normalize.competition.display_type_codes`. 0/0/0 은 청약홈 원문 그대로(그 지역 가점 당첨자 없음 표기 — 화면 문구로 풀 것) | entity 'competition', field 'winning_score_*'(웹 팝업 원문, 확인됨) |
| 경쟁률 요약(Q4 ②) | `competition.supply`·`applied`·`ratio_or_shortfall_text` | 요약 규칙은 WP4 | 그대로 |
| 필수 옵션 설명(Q2) | `complex_type.options_text` | 필수 선택품목 줄이 있을 때만 값, 고지문 0원이면 null | 그대로 |

## 7. 요청 (하지 않은 것)

- **캘린더 '청약 접수'·'당첨자 발표' 항목(Q3 ②)**: 계약 `checklist_item.kind` enum(법적 확인·중도금·만료·공고 예상·계약·사실 재확인)에
  없어 만들지 않았다 → **R9-API(계약 .20)**: kind 추가(예 '청약 접수'·'당첨자 발표'). 추가되면 `normalize/checklist._wants` 에
  `apply_dates`(구분별 `end` 마감)·`winner_date` 항목을 넣는 일은 WP2/R9-PARSE 후속(데이터는 이미 있음).
- **도화 단지 행 99(이미 있는 두 번째 행)**: 이번 수정은 새로 생기지 않게 하고(인용), 재정규화가 임의공급 원문을 원 단지 39 에 쓰게 하고,
  캘린더 중복을 닫는다. 행 99 자체(목록 G2 에 같은 이름 두 줄, 점수 대상)는 남는다 — 행 병합(19개 FK·발행 저장본)은 데이터 결정이 필요하다
  → CEO: 병합 마이그레이션 또는 목록에서 숨김 규칙. 같은 모양의 연수 서해그랑블 5단지 1~4차(96~98·100)는 공고문에 원 번호가 없어
  인용으로 붙일 수 없다(이름·주소 병합은 D10-4 규칙 밖).
- **'대표 층' 이름(Q2)**: 값은 정의대로(최저 공급금액 행) — 화면 문구 '최저가 층'(WP6)으로. 정의를 바꾸려면 CEO 결정(골든 영향).
- 당첨가점 0/0/0 표시 문구, `QUIET_FIRST_FIELDS`(첫 수집 이벤트 없음)의 DECISIONS 기록 — CEO.

## 8. 수정 중 바로잡은 것

- 처음 판에서는 잔금 산술 후보가 extract 요청을 없앴다 → R4 3차 녹화 재생(`tests/scheduler/test_core9_n9_reextract.py` 2건)에서 판정기가 원문으로
  읽어 '확인됨'으로 채택하던 잔금 5건이 '추정' 산술로 내려갔다(전체 스위트에서 발견). 산술 값을 OCR 판독처럼 '판정기 추출이 나오면 물러나는
  후보'로 바꿔 요청·캐시 키를 예전 그대로 두었다(테스트 `test_q2_derived_balance_keeps_extract_request_and_yields_to_judge`).
- R9-API 조정: 당첨가점 열·출처 필드 이름을 `winning_score_min/max/avg` 로 맞췄다(R9-API 가 그 이름으로 읽는다 — API 변경 없이 연결).
