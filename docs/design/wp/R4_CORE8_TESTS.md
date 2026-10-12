# R4-CORE8 — R4 재시험 결함 수정 테스트·수정 전 실패 확인 (2026-10-12)

원문: `docs/design/wp/R4_RESULT2.md` §10(N1~N7·m-a~m-d), 결정 `docs/design/DECISIONS.md` **D21**. 브랜치 `wp/r4-core8`(main `fea3976` 기준),
계약 **2026-10-09.16**(이 브랜치가 냄 — `contracts/CHANGELOG.md` 맨 위, FE 차이 표 F1~F8).

**방법.** 결함마다 테스트를 먼저 쓰고(커밋 `[R4-CORE8] 테스트 먼저: …`) 그 시점 코드로 돌려 실패를 확인한 뒤 고쳤다. 끝에
`git archive fea3976 backend contracts`(수정 전 앱·계약)에 새 테스트·녹화만 얹어 **한 번 더** 돌린 실제 출력이 아래 "수정 전" 열이다
(scratchpad `core8/prefix_all.txt`·`prefix_d218.txt`, 그룹별 `prefix_n1.txt`…`prefix_minor.txt`·`prefix_d218_env.txt`).
실데이터 재현은 R4 재시험 원문(scratchpad `r4b/raw`, 공개 분양 정보)을 녹화 픽스처 `backend/tests/normalize/fixtures/r4b_core8/`
(33건 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표, **PDF 바이너리 제외**)로 넣어 재생했다. 넣기 전 키·토큰 검사(`serviceKey`·
`authorization`·`bearer`·`api_key`·`token=`·`X-NCP-APIGW` 정규식, URL 포함) 통과분만 넣었다. R4 DB(`subscription_analyzer_r4`)는 조사용 SELECT 만
했다(접속 주소는 루트 `.env` 에서 스크립트로 읽고 출력하지 않음). 실제 판정기·외부 사이트는 부르지 않았다(가짜 판정기·녹화 재생).

## 1. 결함별 수정·테스트·수정 전 실패

| 결함 · 결정 | 수정 | 테스트 | 수정 전(fea3976) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **N1** critical · D21-1 단위 | `normalize/notice_parser.py`: 공급금액 표 머리(표 제목 줄 ~ 첫 금액 행)의 `단위:` 표기에서 금액 단위(원·천원·만원·백만원)를 읽어 행 금액을 원으로 환산(`_price_unit`·`_scaled`). 원이 아닌 단위로 환산한 가격 후보 발췌 = 금액 행 + `[단위 근거] <표 머리 줄>`. 단위 표기 없으면 원 + reason `UNIT_ASSUMED`('단위 표기 없음 — 원으로 봄'). 원 단위 표는 발췌·사유 그대로(회귀 녹화·compare 입력 불변) | `tests/normalize/test_core8_n1_units.py` 파서 4 — R4 재시험 원문(중흥S-클래스 2025000253 '(단위: 세대, 천원)') | **`{'84A': 617000.0} != {'84A': 617000000}`**(4타입 모두 1/1000) · 발췌 `'… 617,000 61,700 …'` 에 '천원' 없음 · `assert '단위 표기 없음' in ''` | 통과(84A 617,000,000 · 최저층 576,000,000, 발췌에 `(단위: 세대, 천원)`) |
| **N1** · D21-1 10배 상충 | `normalize/fields.py` `is_price_amount`·`magnitude_apart`(10배). `normalize/resolver.py`: 가격 필드는 **다른 출처 종류 1차와 10배 이상**이면 rank 와 무관하게 채택 보류 + needs_compare. `resolve(…, refs)` — 공고별 타입 가격(`price_by_type`)은 같은 타입 청약홈 최고가(`store.price_refs`, 비교만)와 10배 이상이면 보류. `store.py`: 청약홈 타입 가격이 나중에 와도 그 타입 공고 가격 그룹을 다시 resolve(순서 무관). `judged.apply_compare`: 단위 상충 그룹은 same_fact → 단위가 분명한 출처 채택, contradicts·different_facts·review → 보류 유지. `scheduler/pipeline._p5`: 10배 이상이면 cross-rank compare | `test_core8_n1_units.py` resolver 1 · 저장·compare 4 · P5 1 | `needs_compare=False`(rank 1 공고문 채택) · **`assert 617000 == 617000000`** · `assert 617000 is None`(×3 — 단위 없는 공고문 617,000 이 '확인됨'으로 채택) · `'compare:complex_type:1:max_price_won' in []` | 통과(보류 → same_fact 면 617,000,000, 그 밖이면 '확인 불가') |
| **N2** major · D21-2 | `normalize/_text.py` `clean_control`(NUL·제어 문자 → 공백 1자, 탭·줄바꿈·쪽 나눔 유지, 길이 그대로) — `read_raw_text` 가 돌려주는 문자열에만(원문 파일 그대로). `normalize/provenance.py` 출처 행 쓰기 마지막 방어(`_no_nul`) | `tests/normalize/test_core8_n2_nul.py` 4 + `tests/contracts/test_core8_pg_nul.py`(**임베디드 Postgres 16**) — R4 재시험 원문 rd613·rd616 | `assert '\x00' not in '…송도센터니얼…'` · **`('2025910104', None) == ('2025910104', '2020000611')`**(인용 못 읽음) · `assert '\x00' not in '민영 비규제지역 무순…\x00무주택세대구성원'` · **`psycopg.DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`** | 통과(Postgres 저장 성공, 원 번호 인용 → 자기 번호 행 없음) |
| **N3** major · D21-3 | `normalize/notice_parser.py` `_NO_PAT`(`2025000302`·`2025-000302`·`2025 - 000302`) — 최초·이 공고 주택관리번호 모두 | `tests/scheduler/test_core8_n3_n4_replay.py::test_hyphenated_original_number_is_cited`·`::test_remnant_notices_attach_to_original_and_recollect_is_unchanged`·`::test_attribution_does_not_depend_on_storage_order` — 엘리프(원 2025000302 + 무순위 2025910193 + 임의공급 2025940252) + N2 2건 + N1 재생 | **`('2025910193', None) == ('2025910193', '2025000302')`** · **`잔여 공고 번호로 단지 행: ['2025910104', '2025910193', '2025930032', '2025940252']`**(R4 재시험 74·75·62·63 재현) | 통과(잔여 공고는 원 단지 2025000302 의 `remaining_event`, 공고문 순서·청약홈 잔여 공고 원문을 다음 실행에 받아도 같은 귀속, 원 단지 세대수 덮지 않음) |
| **N4** major · D21-3 | N3 의 결과(같은 원문의 귀속이 저장 순서와 무관) | `test_core8_n3_n4_replay.py::test_same_day_daily_after_bootstrap_is_noop_on_r4b_replay` — R4 재시험 원문으로 bootstrap → 같은 날 `collect.daily` | **`AssertionError: 19` / `assert 19 == 0`**(같은 날 daily change_event 19 — R4 재시험 §6 (b) 와 같은 수) | 통과: change_event 0 · rejudge 0 · tools/call 0 · judgment_log 새 행 0 |
| **N5** major · D21-4 | `api/routers/market.py` `trade_price_fact`: 거래 행 출처 행이 없으면 그 거래의 실거래 API **원문 문서**(`rd_<raw_document_id>`, 성공 응답이면 '확인됨', 확인일 = 원문 수집일). 거래 행마다 출처 행을 만들지 않는다. 발행 저장본의 rd_ 서랍(D15-2)이 그대로 담는다 | `tests/scheduler/test_core8_n5_market_trades.py` | **`실거래 출처 행이 없어도 생활권 84㎡ 시세 블록이 있다 … assert []`** | 통과(생활권 블록, prov `rd_`, 출처 누락 수가 실거래만큼 준다. 원문도 출처 행도 없는 옛 시드 거래는 그대로 출처 누락) |
| **N6** major · D21-5 | `judge/payloads.py` `SITE_IDENTITY_CLASSES`(same_complex·other_complex·unclear)·`classify_site_identity_payload`, `judge/pipeline.py` `p4_classify_site_identity`·`is_same_site`, `scheduler/intake.page_text`(페이지 텍스트 1,500자), `scheduler/pipeline._same_site_only`: 접수 classify 전에 판정기 classify(단지 이름·위치 + 페이지 텍스트) → auto `same_complex` 만 접수 classify, 그 밖·review = '확인 불가(공식 홈페이지가 다른 단지)' + 판정 표식(같은 문구 다음 날 분류 복사) | `tests/scheduler/test_core8_n6_site_identity.py` 3 — R4 재시험 rd842(예미지 퍼스트포레 홈페이지 = 대구 '더샵 동성로 센트리엘') DOM 텍스트 | **`('가능', None) == ('확인 불가', '공식 홈페이지가 다른 단지')`**(×2) · `assert 0 == 1`(동일성 판정 호출 없음) | 통과 |
| **N7** minor · D21-6 | `normalize/living_area.assign_complex_area(alt_addresses=…)`: 주소에 맞는 읍면동 토큰이 없으면 같은 단지의 다른 출처 주소(원 단지에 묶여 쓰지 않은 잔여 공고 공급위치 — `store._merged_addresses`, 그 단지 주소 출처 행)로 법정동(단지 주소 그대로, 찾은 법정동은 재배정에도 유지), 지역 안이면 '범위 경계' → 미분류. `analysis/scope.py` `BOUNDARY_NO_DONG`·`has_dong_name`, `judge_scope(address, legal_dong_code)`(API·파이프라인·보고서 호출 4곳) | `tests/normalize/test_core8_n7_no_dong.py` 3 — R4 재시험 원 공고 API(2021000189 'RC3BL'·2021000830 '396-11번지(…A17BL)') + 원 번호 인용 잔여 공고문(공급위치 당하동·송도동) | `TypeError: judge_scope() got an unexpected keyword argument 'address'`(사유 구분 없음) · **`('2021000189', None)` / `assert None == '2826011700'`** | 통과 |
| **m-b** · D21-7 | `normalize/store.py` 첫 적재(`first_load`)면 수집 정규화 이벤트 **전부**(값 → 다른 값 덮어쓰기 포함)를 요약 수로. `scheduler/collect._first_load_event` 문구 | `tests/scheduler/test_core8_minor.py::test_mb_bootstrap_folds_value_to_value_overwrites` — R4 원문(R4-FIX 녹화 + R4 재시험 엘리프) | **`첫 적재 중 값 기록·덮어쓰기 이벤트 6건: [('complex', 'move_in_ym', '2026-01', '2026-07'), ('complex', 'move_in_ym', '2026-07', '2026-01'), ('complex', 'name', …), ('complex_type', 'max_price_won', '581000000', '578000000') …]`** | 통과(region·first_load 한 줄) |
| **m-c** · D21-7 | `scheduler/pipeline._inclusion_changed`: 포함/제외 classify 는 직전 판정(같은 판정기 버전)의 그 단지 항목 텍스트와 지금 입력이 다른 단지(또는 판정 없음)만 보낸다 | `test_core8_minor.py::test_mc_inclusion_batch_rejudges_only_changed_inputs` | **`입력이 바뀐 단지만 다시 판정: ['complex:1', 'complex:2', … 'complex:16']`**(16개 전체 배치) | 통과(바뀐 1개만, 다른 단지 분류·seq 그대로, 입력 그대로면 호출 없음) |
| **m-d** · D21-7 | `reports/data.report_living_areas`: §1-1 생활권 세대수 = API 와 같은 세대 현황 집계(`living_area.region_household_facts`, 라벨 추정, prov `rd_`) | `tests/normalize/test_core8_md_households.py` | `ImportError: cannot import name 'report_living_areas'`(보고서는 저장 json `households` null → '확인 불가(출처 누락)') | 통과 |
| **D21-8** 공고 예정 후보 | `api/views.py` `is_pre_notice`(트랙 A·주택관리번호·공고일 없음)·`notice_fact`·`price_range` 사유 '공고 전', `api/routers/analysis.py` 비교 입력 | `tests/scheduler/test_core8_d21_8_upcoming.py`(수집 경로 모양 후보 행), `tests/api/test_core8_d21_8.py::test_pre_notice_candidate_price_and_notice_date_reason`(devseed — 회귀 방지, 수정 전에도 통과: 시드 후보는 공고일 출처 행 사유가 이미 '공고 전') | **`('확인 불가', '값 없음') == ('확인 불가', '공고 전')`** | 통과 |
| **D21-8** 계약 .16 `name_prov`·`name_label` | `contracts/schemas/complex.json`·`complex_row.json`(선택 필드 + 예시), `api/views.name_provenance`(chosen 이름 출처 행 → `fp_<id>`·라벨, 없으면 두 키를 내지 않음 — 목록 1,000행 저장본 크기 그대로, API 골든 불변), 목록 출처 필드에 `name` | `tests/api/test_core8_d21_8.py::test_name_provenance_fields`·`::test_name_provenance_from_chosen_row`·`::test_contract_version_is_16` | `ImportError: cannot import name 'name_provenance'` · `'2026-10-09.15' == '2026-10-09.16'`(`test_name_provenance_fields` 는 시드에 이름 출처 행이 없어 수정 전에도 통과 — 키 쌍 일관성 회귀 방지) | 통과 |
| **D21-8 · D19-3** `.env` 판정기 자격 증명 | `judge/jev_mcp.subprocess_env`: 설정 파일(`ENV_FILE`·`.env`)의 판정기 자격 증명 이름(`JUDGE_SECRET_ENV_NAMES`·판정기 접두)도 자식 env 로(프로세스 환경변수가 이김, 판정기 무관 비밀은 제외) — 값은 기존 `judge_secret_values` 가 stderr·오류에서 가림. `tests/judge/fake_jev_server.py` 설정 `require_env` | `tests/judge/test_core8_env_credentials.py` 5 — 사용자 환경변수 없이 `.env` 만 | **`assert None == 'tsk_dotenv_only_value_7Qx'`** · **`JudgeUnavailable: 판정기 기동 실패(MCPError); stderr: missing credential env TYPESAFE_API_KEY`** · 가림 확인 실패(`KeyError: 'TYPESAFE_API_KEY'` — 자식이 키를 못 받음) | 통과(가짜 판정기가 `.env` 만으로 뜨고, 값은 `[REDACTED…]`) |

수정 전에도 통과하는 테스트(회귀 방지 — 의도): `test_core8_n1_units.py::test_won_tables_are_unchanged`(원 단위 표 그대로), `test_core8_n2_nul.py::
test_recorded_notice_really_has_nul`(녹화 원문에 NUL 이 그대로), `test_core8_n5_market_trades.py::test_trade_without_raw_document_is_still_missing`,
`test_core8_env_credentials.py::test_process_env_wins_over_dotenv`·`::test_settings_type_is_untouched`, `test_core8_d21_8.py::test_pre_notice_candidate_price_and_notice_date_reason`.

## 2. 바뀐 기존 테스트·골든·픽스처와 이유

| 파일 | 바뀐 것 | 이유 |
| --- | --- | --- |
| `tests/contracts/test_openapi.py::test_contract_version`, `tests/contracts/test_protocols.py::test_contract_version_matches_changelog` | 버전 단언 .15 → .16 | 계약 .16 |
| `tests/api/test_r4fix_contract15.py::test_contract_version_is_15` | 삭제(같은 일을 `test_core8_d21_8.py::test_contract_version_is_16` 이 한다) | 계약 .16 |
| `tests/judge/fake_jev_server.py` | 설정 `require_env`(그 환경변수가 없으면 기동 실패) | D21-8 '.env 만으로 판정기가 뜨는가' |
| `contracts/fixtures/tools/record_synth_judgments.py`, `contracts/fixtures.sha256.json` | 생성기가 동일성 classify(`same_complex`) 합성 응답을 안다. 매니페스트 사유: R4-CORE8 D21-5 record_synth_judgments.py knows site identity classify (recordings unchanged) | 다음 녹화 대비 — `--check` 결과 녹화 254개 봉투는 그대로(회귀 흐름에 미분류 공식 홈페이지 행이 없어 동일성 호출 0, 포함 배치는 devseed 판정 입력과 달라 그대로 전부) |
| 새 `tests/normalize/fixtures/r4b_core8/` + `tests/normalize/_r4b.py` | R4 재시험 원문 33건(그룹 elif 15 · n1 5 · n2 9 · n7 4), `docs.json` = raw_document 행(수집 순서) | N1·N2·N3·N4·N7·m-b 재생. HTML·JSON 은 `.gitattributes` 로 LF 정규화되어 sha256 이 녹화와 다를 수 있다(내용 동일 — 재생은 행의 sha256 으로 찾을 뿐 파일 해시를 검사하지 않는다). NUL 공고문 2건은 바이너리로 저장된다 |

회귀 골든(`expected_scores*.json`)·API 스냅샷 골든(`tests/api/snapshots/list_r3c*` — 한때 null 키로 바꿨다가 null 이면 키를 내지 않게 고쳐 원래 바이트로 되돌림)·`judgments_synth` 녹화는 바꾸지 않았다.

## 3. 다음 R4 재시험(3차)에서 확인할 항목

`docs/runbook.md` §10-9 에 절차·SQL 을 적었다. 요약:

1. 사용자 환경변수 없이 r4 env(`ENV_FILE`)의 `TYPESAFE_API_KEY` 만으로 smoke·워커가 판정기를 띄운다(D21-8).
2. `complex_type.max_price_won < 30,000,000` 0행, 중흥S-클래스 84A 617,000,000(N1). 단위 상충 보류 그룹·compare 결과·`단위 표기 없음` 행 수를 기록.
3. bootstrap·daily `store_errors` = [](N2).
4. 잔여 공고 번호(`^20..9.....$`) 단지 행 = 원 번호를 인용하지 않은 것만(2차의 74·75·64~66·71·62·63 없음), 같은 날 daily change_event 0 ·
   `tools_calls` 0(N3·N4·D18-6).
5. 시장 `living_area_prices` 생활권마다 + prov `rd_`, 발행 stats `missing_provenance` 가 2차 5,938~5,973 보다 크게 준다(N5).
6. `classify:site_identity:*` 호출 수·결과, 예미지 퍼스트포레(2차 55)가 '확인 불가(공식 홈페이지가 다른 단지)'로 판정 대상이 아닌지(N6 —
   실제 판정기 응답에 달렸다).
7. 2차 46·47(동 없는 주소)의 법정동 = 당하동·송도동, 범위 경계 아님(N7). 남은 동 없는 주소 행의 사유.
8. bootstrap change_event 에 단지·타입·납부 조건 이벤트 0(m-b), daily 포함 classify 항목 = 바뀐 단지 수(m-c), 보고서 §1-1 세대수 값(m-d).
9. 트랙 A 후보 공고일·가격 '확인 불가(공고 전)', `name_label` '비공식'(D21-8). 1회차 판정기 호출 수와 2차(582) 대비 차이 — 동일성 classify
   (+배치 1~2) · 포함 classify(입력 바뀐 단지만) · compare(단위 상충 cross-rank)를 이유와 함께 기록.

## 4. 하지 않은 것 / 가정 / 남은 위험

- **m-a**(판정 대상 2단지 유동성 입력 없음 — 계약금%·거주의무·전매기간을 공고문 extract 가 못 뽑음)는 D21 범위가 아니라 고치지 않았다.
- **N3 결정성**: 하이픈 인용을 읽으므로 R4 재시험 사례(74·75 등)는 자기 번호 행이 생기지 않는다. 그러나 공고문이 원 번호를 **전혀 인용하지 않는**
  잔여 공고가 청약홈 잔여 공고 원문보다 **다른 실행에서 먼저** 오면 자기 번호 행이 먼저 생기고, 이후 청약홈 원문이 같은 블록으로 원
  단지를 찾을 수 있어도 이미 있는 자기 번호 행에 붙는다(행 병합 없음 — R4_FIX_TESTS §5 와 같은 남은 위험). 같은 실행 안에서는 저장 순서
  (D18-4)로 막는다.
- **단위 상충**: compare 가 contradicts·different_facts·review 면 어느 금액도 채택하지 않는다 — 그 타입 가격·현재 구매가는 사람 확인까지
  '확인 불가(출처 상충 — compare 대기)'. 공고별 타입 가격이 상충으로 보류되면 compare 가 청약홈 값을 채택해도 그 공고의 현재 구매가는
  '확인 불가'로 남는다(옛 공고 가격으로 돌아가지 않는다 — R3 3차 M-4). 단위 검사는 최고가·대표층가만(발코니·옵션·계약금 정액은 단위 근거
  발췌만, 10배 검사 없음).
- **단위 근거 발췌**는 원이 아닌 단위로 환산한 경우에만 붙였다 — 원 단위 표(녹화 공고문 전부)의 발췌를 바꾸면 compare 입력 해시가 바뀌어
  회귀 녹화가 어긋나기 때문이다. 원 단위 표의 단위 근거는 표 머리 원문에 있다(발췌에 없음).
- **N6**: 동일성 classify 는 미분류 접수 행마다 1회(같은 문구 다음 날은 분류 복사로 0회). 판정기가 review 를 많이 내면 접수 근거가 줄어든다
  (설계 — D21-5 '아니거나 review 면 쓰지 않는다'). 동일성 판정의 입력은 페이지 텍스트 앞 1,500자다.
- **N7**: 대체 주소는 원 단지에 묶인 잔여 공고의 공급위치·주소 출처 행에서만 찾는다(공식 홈페이지 페이지 텍스트의 주소는 읽지 않음).
  '범위 경계(주소에 동 없음)' 사유는 법정동이 없고 주소 토큰에 …동·…읍·…면·…리·…N가 모양이 없을 때만이다.
- **m-c**: 판정기 버전을 모르는 실행(판정기 다운 + 전부 캐시)에서는 재사용하지 않고 이전처럼 전체 배치를 보낸다(같은 입력이면 캐시). guard
  가 입력 텍스트를 바꿔 기록한 경우 텍스트 비교가 어긋나 그 단지만 따로 다시 보낸다(그 뒤로는 캐시).
- **m-b**: 첫 적재 중에는 수집 정규화 이벤트를 모두 접는다 — bootstrap 중의 가격 변화는 '첫 적재' 요약 수에만 남는다(운영 중 수집은
  그대로).
- **D21-8**: '공고 전' 사유는 트랙 A(공고 예정 후보)·주택관리번호·공고일 없는 행에만. 이름 출처는 chosen 출처 행만 본다(옛 이름은 출처 없음).
  `.env` 판정기 자격 증명은 이 프로그램의 간단한 `KEY=VALUE` 읽기로 고른다(따옴표·`export`·주석 허용, 여러 줄 값·변수 치환 없음 — 새
  라이브러리 없음).
- 2차 R4 DB 의 기존 행(74·75 등) 병합·정리 마이그레이션은 만들지 않았다(D20-3 과 같다 — 3차 재시험은 새 DB). 마이그레이션 없음.
- 프론트(`frontend/**`)는 바꾸지 않았다 — 계약 .16 FE 차이(F1~F8)는 FE 라운드가 맞춘다(`npm run gen:api`·`gen:msw` 포함).
