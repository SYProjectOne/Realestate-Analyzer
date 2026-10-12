# R4-CORE10 — 재정규화 멱등성 속성 테스트 · R4 4차 재시험 결함 수정 테스트·수정 전 실패 확인 (2026-10-13)

원문: `docs/design/wp/R4_RESULT4.md` §10(N13·N14·N15), 결정 `docs/design/DECISIONS.md` **D23**. 브랜치 `wp/r4-core10`(main `b0b8c65` 기준),
계약 **2026-10-09.18**(이 브랜치가 냄 — `contracts/CHANGELOG.md` 맨 위, FE 차이 표 F1~F4, 데이터 마이그레이션 `0016`).

**방법(D23-1).** 결함을 하나씩 막기 전에 **재정규화 멱등성 속성 테스트**를 먼저 썼다(커밋 `5191927 [R4-CORE10] 테스트 먼저: …`). 녹화
원문 전체로 `region.bootstrap`(일일 단계 + 판정 P1~P9 + 발행) → 같은 날 `collect.daily`(같은 원문·같은 순서) → 같은 날 `collect.daily`(순서를
섞어서, 시드 2개) → 같은 스냅샷 재판정 → 다음 날 `collect.daily`(섞어서)를 돌리고, 단계마다 **DB 스냅샷**(실행·리비전 기록
`_idem.RUN_TABLES` 를 뺀 모든 테이블의 모든 행·모든 열 + 최신 리비전 접수 상태 행)이 bootstrap 직후와 같은지, 사실 change_event 0, 판정기
`tools/call` 0(가짜 판정기 `SynthJev` 전송 계층 계수)인지 본다. 새 테이블은 자동으로 비교 대상이다(빼려면 사유와 함께 `RUN_TABLES`).
그 테스트가 수정 전 코드에서 N13·N14 를 잡는지 확인한 뒤 고쳤다. 끝에 `git archive b0b8c65 backend contracts`(수정 전 앱·계약)에 새
테스트·녹화만 얹어 **한 번 더** 돌린 실제 출력이 아래 "수정 전" 열이다(scratchpad `core10/prefix_final_full.txt` — 같은 가상환경, 작업
디렉터리만 수정 전 트리).

**재생 세트**(R4 1~4차 녹화 — 저장소에 있는 것 전부 + 4차 전체 원문):

| 세트 | 녹화 | 원문 |
| --- | --- | --- |
| `r4` | R4 1차(2026-10-12) `tests/normalize/fixtures/r4_remnant` | 청약홈 30 · 공고문 8 · 원 공고 응답 4단지 |
| `r4b` | R4 재시험(2차) `r4b_core8` | 그룹 elif·n1·n2·n7 전부 |
| `r4c` | R4 3차 `r4c_core9` | 그룹 n9·n10·n12 + 원 공고 응답 n10_orig |
| `r4d` | **R4 4차 새 녹화** `r4d_core10.zip`(1.8MB) | bootstrap 일일 단계 원문 중 단지 18개(N13 중복 경쟁률 단지 · N14 compare 단지 · N9 추출 · 원 공고 다시 받기): 청약홈 목록 12(일일 단계 전부) · 상세 201 · 원 공고 21 · 공고문 51(추출 텍스트·표) · 공식 홈페이지 26(DOM 텍스트) + 지역·법정동 565행 |
| `r4d-full` | R4 4차 **전체**(scratchpad `r4d/raw`, 저장소 밖) | bootstrap 일일 단계 전부: 청약홈 559 · 원 공고 77 · 공고문 137 · 공식 홈페이지 90. `R4_REPLAY_MANIFEST=<docs.json>` 이 있을 때만(없으면 skip) — 매니페스트는 `backend/scripts/replay_manifest.py`(R4 DB 읽기 전용) |

녹화는 넣기 전 키·토큰 정규식(`serviceKey`·`authorization`·`bearer`·`api_key`·`token=`·`X-NCP-APIGW`)과 루트 `.env` 의 비밀 값(원문·URL
인코딩·DB 비밀번호 조각 16개)을 zip 안 361개 파일 전부에서 찾아 **0건**. PDF 바이너리·공식 홈페이지 HTML 은 넣지 않았다(파서는 추출 텍스트를
먼저 읽는다). R4 DB(`subscription_analyzer_r4`)는 녹화용 SELECT 만 했다(읽기 전용 연결, 접속 주소는 루트 `.env` 에서 스크립트로 읽고 출력
하지 않음). 실제 판정기·외부 사이트는 부르지 않았다.

## 1. 결함별 수정·테스트·수정 전 실패

| 결함 · 결정 | 수정 | 테스트 | 수정 전(b0b8c65) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **D23-1** 재정규화 멱등성(속성) | 아래 N13·N14 수정(속성 테스트가 찾은 비멱등 지점 전부 — §2) | `tests/scheduler/test_core10_idempotency.py::test_renormalize_is_idempotent[r4·r4b·r4c·r4d·r4d-full]` | `[r4]` **`재정규화 멱등성 위반 1건 … [같은 원문 재정규화] DB 스냅샷 차이 {'field_provenance': 36}: ~ 449: [(10, '판정기 compare 병기 jl_1 — same_fact — 우선순위 채택', None)] …`**(R4 1차 녹화에서도 N14) · `[r4c]` **`{'competition': 4, 'field_provenance': 16}: competition 생김 4: (244, 3, '1순위 해당지역', '본청약', '122', 212, 47, '(△165)', None) …`**(R4 3차 녹화에서도 N13 — 3차 결과서가 '모른다'고 한 것) · `[r4d]` **`{'competition': 70, 'field_provenance': 343}`** · `[r4d-full]` **`{'competition': 70, 'field_provenance': 585}`**(R4 4차 실측 70행과 같다) · `[r4b]` 통과(이 녹화에는 경쟁률·compare 상충이 없다) | 5세트 모두 통과: 같은 원문 · 섞은 순서 2회 · 다음 날 재정규화 모두 DB 스냅샷 동일, 사실 이벤트 0, 수집·같은 날 재판정 `tools/call` 0(`r4d-full` 약 2분) |
| **N13** critical · D23-2 | `normalize/store._Binder.competition_for`: 행 = (단지, 구분, 회차, **원 면적 코드**) — 그 시점 단지 주택형 대조(`competition_type`)를 지웠다. 표시 주택형은 `normalize/competition.display_type_codes`(옛 규칙 그대로 + 같은 회차 표시 코드 겹침은 원 코드 순 첫 행만)를 `api/routers/complexes.detail_bodies`(→ `views.competition_view`)·`reports/data` 가 읽기 시점에 쓴다 | `tests/normalize/test_core10_n13_competition.py::test_same_competition_raw_renormalized_after_types_changed_makes_no_new_rows[2026000073·2026000367·2025000573·2025000555·2025940263]`(R4 4차 순서: 청약홈 상세·주택형·경쟁률 → 공고문 → 같은 경쟁률 원문 재정규화) · `::test_competition_rows_do_not_depend_on_store_order[같은 5단지]` · `::test_display_type_matches_types_at_read_time` · `::test_display_rules_ambiguous_and_collisions_are_deterministic` | **`재정규화가 경쟁률 행 8개를 새로 만들었다(N13, R4 4차 8행): [(9, '본청약', '1순위 해당지역', '84', 337, 210, '(△127)'), …]`**(28) · **`… 4개 …(N13, R4 4차 4행): [(49, '본청약', '1순위 해당지역', '122', 212, 47, '(△165)'), …]`**(25) · **`… 32개 …[(33, '본청약', '1순위 해당지역', '66A', 181, 13, '(△168)'), …]`**(31) · **`… 4개 …[(13, '본청약', '1순위 해당지역', '84', 416, 1377, '3.31'), …]`**(32) · **`… 1개 …[(5, '임의', '임의 2025940263', '확인 불가(타입 모호)', 6, 8, '1.33')] — 기존 [(1, '임의', '임의 2025940263', '53.5854', 6, 8, '1.33'), …]`**(70) — 실측 (b) 중복 행 수와 같다 · 순서 5건 **`저장 순서에 따라 경쟁률 행 키가 다르다: [('본청약', '1순위 기타지역', '105', …), ('본청약', '1순위 기타지역', '105.2083', …)…]`** · 표시 2건 `ModuleNotFoundError: No module named 'app.normalize.competition'` | 통과: 재정규화 행·출처·이벤트 그대로, 저장 순서 무관, 저장 = 원 면적 코드('84.9939'·'105.2083'), 표시 = '84'·'105' |
| **N13** 데이터 · D23-2 | 계약 마이그레이션 **`0016`**(데이터만, 앱 import 없음): 출처 행 `entity_key` 의 원 코드로 (단지, 구분, 회차, 원 코드)가 같은 행을 하나로 — 가장 앞 id 남김, 값은 가장 늦은 행, 같은 출처 행 삭제·다른 출처 행은 남는 행으로(상충 묶음 이름도), 필드마다 chosen 하나, `change_event`·`fact_demotion`·`human_check` 참조 이전, `type_code` = 원 코드. downgrade 는 데이터 그대로 | `tests/contracts/test_core10_migrations.py::test_sqlite_0016_merges_n13_duplicates_and_roundtrips` · `::test_postgres_0016_…`(임베디드 PG) | **`assert [(657, '1순위 해…10, '(△127)')] == …` · `Left contains 2 more items, first extra item: (1909, '2순위 해당지역', '확인 불가(타입 모호)', 8, 2, '(△0)')`**(0016 없음 — 중복 그대로) | 통과(SQLite·PG): 중복 2건 정리·원 코드 복원·이벤트 이전, 0015 로 내려도·다시 올려도 같음, autogenerate diff 0 |
| **N14** major(게이트) · D23-3 | `normalize/store._carry_compare_marks`: 같은 원문이 같은 자리(엔티티·필드·발췌 위치)에 **같은 값**을 다시 내면 그 출처 행의 `COMPARE_ADOPTED`·`COMPARE_SIDE` 표식을 이번 후보 reason 에 다시 붙인다(`fields.compare_mark`·`with_mark` — `with_tag` 와 같은 문자열). 값이 바뀌면 옮기지 않는다 | `tests/normalize/test_core10_n14_compare_marks.py::test_renormalize_keeps_compare_marks_and_value[side·adopted]`(같은 rank 1차·1차 상충 → compare same_fact 채택 → 병기 쪽·채택 쪽 원문 재정규화) · `::test_changed_value_on_renormalize_is_a_new_conflict_not_silent`(회귀 방지) + 속성 테스트(실데이터) | **`재정규화가 compare 표식을 지웠다(N14): 값 2028-09 → None, 바뀐 출처 행 [(1, 2, '2028-03', '확인됨', '판정기 compare 병기 jl_? — same_fact — 우선순위 채택', False, …), …]`**(side) · **`… 값 2028-09 → None, 바뀐 출처 행 [(3, 3, '2028-09', '확인됨', '판정기 compare 채택 jl_? …(병기)', True, …)]`**(adopted) — R4 4차 결과서가 '위험(관찰 안 됨)'으로 적은 '확인됨' → '확인 불가' 가 실제로 난다 | 통과: 값·표식·출처 행 그대로, 이벤트 0. 값이 바뀌면 표식 없음 + 채택 보류 + 이벤트(수정 전에도 통과) |
| **N15** major · D23-4 | `collectors/applyhome/api.ApplyhomeApi.get`: 조건 없는 `totalCount` 0 → 실패 결과(`error` = `EMPTY_DATASET` 'empty_dataset: totalCount 0'), `parse_page` 실패, `raw.error_text_of`·`failure_kind`(내용 실패 머리) → 실패 행(http 200 · path 없음). 목록이면 그 시도 웹 경로(기존 규칙), 상세·경쟁률이면 웹 폴백. 수집기 `empty_datasets` | `tests/collectors/applyhome/test_core10_n15_empty_dataset.py` 5(녹화 `r4d_empty_dataset.json` — R4 4차 첫 시도 응답 그대로) | **`(200, True, None)`**(성공으로 봄) · **`assert (200, None, None) == (200, None, '…totalCount 0')`** · **`{'28': 'api', '41': 'api'}`**(웹 폴백 안 함) · **`[(200, 'apply….json', None)] == [(200, None, …)]`**(원 공고 다시 받기도 성공 행) · `test_no_match_with_nonempty_dataset_is_still_ok` 통과(회귀 방지) | 통과 |
| **N15** 잡 · D23-4 | `scheduler/collect`: `CollectResult.degraded`(stats `degraded_sources`), degraded 면 목록 diff·목록 단지 집합 기록 안 함. `handlers.handle_region_bootstrap`: 일일 수집 degraded → 주간 수집·판정·발행 없이 `JobRequeue`(30분, `EMPTY_DATASET_RETRIES` 6회 뒤 `JobError`), 지역 `bootstrapping` 그대로. `handle_collect_daily`: degraded → 재판정·발행(이월 포함) 없이 재큐잉 | `tests/scheduler/test_core10_n15_degraded.py` 3 | **`('빈 데이터셋 bootstrap 은 지연 재큐잉(재시도)이어야 한다(N15)', 'done', None, …)`**(R4 4차 첫 시도처럼 판정·발행) · `ImportError: cannot import name 'EMPTY_DATASET_RETRIES'` · **`('done', None)`**(daily 가 이월 발행) | 통과: bootstrap `queued`·`tools/call` 0·발행 0·지역 bootstrapping → 데이터셋이 돌아오면 같은 잡이 수집·판정·발행 · 6회 뒤 failed · daily 는 이전 발행 유지 |
| 계약 .18 | `CONTRACT_VERSION`·`info.version`·DECISIONS 5행, 스키마 설명 3(competition.type_code · raw_document.error_text · source_status reason), 생성물 재생성 | `test_core10_migrations.py::test_contract_version_is_18` + `test_openapi`·`test_protocols` 버전 단언 | `assert '2026-10-09.17' == '2026-10-09.18'` | 통과 |

수정 전 합계(`prefix_final_full.txt`): **실패 30 · 통과 3**(+ r4d-full 포함). 수정 전에도 통과하는 테스트(회귀 방지 — 의도):
`test_renormalize_is_idempotent[r4b]`(그 녹화에 경쟁률·compare 상충 없음), `test_core10_n14_compare_marks.py::test_changed_value_on_renormalize_is_a_new_conflict_not_silent`
(값이 바뀌면 표식을 옮기지 않고 이벤트 — 보존 규칙이 이 경로를 막지 않음), `test_core10_n15_empty_dataset.py::test_no_match_with_nonempty_dataset_is_still_ok`
(조건에 맞는 것만 0건은 정상).

## 2. 속성 테스트가 찾은 비멱등 지점

| # | 지점 | 세트(수정 전) | 처리 |
| --- | --- | --- | --- |
| 1 | 경쟁률 행 키가 그 시점 단지 주택형 대조 결과(`competition_type`) — 타입 행이 생기거나 이름이 바뀐(공고문 '84.9939' → '84') 뒤의 재정규화가 같은 경쟁률을 새 행으로(N13) | r4c(4행) · r4d(70) · r4d-full(70) | 수정(D23-2) + 0016 |
| 2 | 같은 원문 출처 행 reason 을 파서 값으로 다시 써 compare 채택·병기 표식 소실(N14) | r4(36행) · r4c · r4d(343 중 133) · r4d-full(585 중 375) | 수정(D23-3) |
| 3 | 접수 상태 행 note 의 '문구 해시 동일 — 이전 분류 복사(접수 행 n, 스냅샷 m)' — 다음 날 리비전이 복사 원본 행을 가리킨다 | r4d(다음 날 단계) | **결함 아님**(D10-2 설계 — 리비전마다 다른 행을 가리키고 쌓이지 않는다). 비교에서 그 표식만 뺀다(`_idem._note`) |
| 4 | 다음 날 재판정의 noul 호출 | r4d(다음 날 뒤 재판정) | **결함 아님**(기준일 상대 명제 — 목표월이 바뀐다. D18-6 은 같은 날 기준). 다음 날 단계는 수집 단계 `tools/call` 만 센다 |

그 밖의 정규화 테이블(단지·타입·납부 조건·잔여 이력·체크리스트·법정동·출처 행·판정기 추출/감사 행·접수 상태)에서 R4 4차 **전체** 원문
재정규화(같은 순서·섞은 순서 2회·다음 날)로 차이 0, 사실 이벤트 0 — 추가 비멱등 지점은 찾지 못했다.

관찰(결함 아님, 기록만): 실제 공고문 수집기는 공고문 행을 **처음 받을 때만** 그 번호의 단지에 단다(같은 원문을 다시 받으면 기존 행 그대로).
R4 4차에서 잔여 공고 자기 번호 단지(67~70 연수 서해그랑블 5단지 1~4차)는 공고문보다 늦게(미룬 잔여 공고 청약홈 원문 저장 때) 생겨 그 공고문 4건
(raw 634·635·638·640)이 단지에 달리지 않은 채 남는다 — 그 단지들은 판정 P1~P3 가 공고문을 읽지 않는다(멱등이지만 범위 밖 단지라 영향 작음).
재생 수집기는 실제 수집기와 같게 만들었다(처음 넣을 때만 단지에 단다).

## 3. 바뀐 기존 테스트·골든·픽스처와 이유

| 파일 | 바뀐 것 | 이유 |
| --- | --- | --- |
| `tests/normalize/test_applyhome_cmpet_real.py::test_letterless_house_ty_competition_matches_complex_types` · `::test_letterless_house_ty_ambiguous_area_is_not_matched` | 저장 행 `type_code` 대신 `display_type_codes` 결과(표시 주택형)로 '84A'·'84B'·'확인 불가(타입 모호)'·'84C' 단언, 저장 = 원 면적 코드 단언 추가 | D23-2(저장 = 원 코드, 표시 = 읽기 시점) |
| `tests/contracts/test_migrations.py::test_migration_head_is_0015` → `…_is_0016` | head `0016`, `0016 → 0015` | 계약 .18 데이터 마이그레이션 |
| `tests/contracts/test_openapi.py::test_contract_version`, `tests/contracts/test_protocols.py::test_contract_version_matches_changelog` | 버전 단언 .17 → .18 | 계약 .18 |
| `tests/api/test_core9_d22_5.py::test_contract_version_is_17` | 삭제(같은 일을 `test_core10_migrations.py::test_contract_version_is_18` 이 한다) | 계약 .18 |
| 새 `tests/normalize/fixtures/r4d_core10.zip` + `tests/normalize/_r4d.py` + `tests/scheduler/_idem.py` | R4 4차 녹화·재생 도구 | 속성 테스트·N13·N15 |
| 새 `tests/collectors/applyhome/fixtures/r4d_empty_dataset.json` | R4 4차 첫 시도 빈 데이터셋 응답(82바이트) | N15 |

회귀 골든(`expected_scores*.json`)·`contracts/fixtures/**`·API 골든(`tests/api/snapshots/**`)은 바꾸지 않았다.

## 4. 다음 R4 재시험(5차)에서 확인할 항목

`docs/runbook.md` §10-13 에 절차·SQL 을 적었다(00:00~01:00 KST 회피 · 시작 전 `totalCount` > 0 확인 포함). 요약:

1. **중복 경쟁률 0**(N13 critical): (b) 뒤 같은 단지·구분·회차·공급·접수인데 `type_code` 만 다른 행 0(4차 70). `competition.type_code` = 원 면적 코드,
   단지 상세 `competition[].type_code` = 표시 주택형.
2. **발행 결과 불변**: (a3) ↔ (b) ↔ (b) 뒤 재판정 리비전의 모든 Fact 비교 — 바뀐 공고 단지·신선도 KPI 밖 차이 0('경쟁률 Fact 생김'·'compare 근거 소실' 0).
3. **(b) 뒤 재판정 `tools/call` 0**(N14 게이트): 프록시 = 잡 = `judgment_log` 새 행 = 0(4차 4), '판정기 compare 채택' 출처 행 수 (b) 전후 같음(4차 (b) 뒤 7).
4. **빈 데이터셋**(N15): 정상 시간대 `error_text LIKE 'empty_dataset%'` 0 · `degraded_sources` 없음. (선택) 적재 시간대면 bootstrap `queued` · 판정 0 · 발행 0 →
   01:00 뒤 재시도가 발행.
5. (선택, 로컬) 5차 원문 전부로 `scripts/replay_manifest.py` → `test_renormalize_is_idempotent[r4d-full]` 통과.
6. 4차 확인 항목(§10-11 1~8) 회귀 — (a)(a2)(a3) `tools/call` 0, 판정기 추출 납부 조건 '확인됨' 유지, 46·47 법정동, 첫 적재 요약 한 줄.
7. 운영 DB(D19)에 `alembic upgrade head`(0016) 적용 — 운영 DB 는 비어 있어 정리할 중복이 없다(R4 DB 도 5차가 새로 비운다).

## 5. 하지 않은 것 / 가정 / 남은 위험

- **속성 테스트 범위**: 일일 단계(청약홈·공고문·공식 홈페이지 → `store`·잔여 이력·체크리스트·접수 상태)다. 주간 단계(실거래·분양권·미분양·입주물량·
  벤치마크·뉴스 호재·공고 예정 후보)는 수집기 적재(`load_trades` 등)·조립이라 재생하지 않았다(기존 단위 멱등 테스트만). R4 4차 (b)도 일일 단계였다.
- **R4 1~3차 녹화는 부분 녹화**다(그 DB 는 지워져 원문 전체의 raw_document 행이 남지 않았다). 4차만 전체 원문(로컬)으로 돌렸다.
- **`r4d-full` 은 저장소 밖**(원문 수십 MB)이라 CI·`pytest` 기본 실행에서는 skip 이다 — 로컬에서 수정 전 실패·수정 후 통과를 확인했다(§1).
- **표시 주택형 겹침 규칙**: 같은 회차에서 다른 원 코드가 같은 단지 주택형에 맞으면(웹 '84A' 행 + API '84.9582' 행) 이제 두 행으로 보인다(첫 행만 표시
  코드, 나머지는 원 코드). .17 은 저장 순서에 따라 한 행으로 합쳐지거나 두 행이 되었다(순서 의존). R4 실데이터는 API 경쟁률만 있어(웹 경쟁률은 API 실패
  폴백) 이 경우가 없었다.
- **0016** 은 출처 행이 없는 경쟁률 행(devseed·옛 데이터)의 `type_code` 를 바꾸지 않는다. 이미 발행된 R4 4차 리비전 5·6 저장본의 중복 행은 그대로(D11-1).
- **N15 판정 기준**은 `totalCount` 0 뿐이다 — 적재 중 일부만 찬 데이터셋(직전 대비 급감)은 잡지 못한다(R4_RESULT4 제안의 '직전 대비 급감'은 하지 않음 —
  정상 변동과 가르는 기준이 판단에 가깝다). 웹 폴백이 성공해도 degraded 로 보고 발행하지 않는다(D23-4 문구 그대로 — 웹 목록이 같은 적재를 쓰는지 모름).
  재큐잉 간격 30분·최대 6회는 관측(00:01~00:59) 기준 가정이다.
- **m-a**(판정 대상 유동성 입력 없음)는 D23 범위가 아니라 고치지 않았다.
- 프론트(`frontend/**`)는 바꾸지 않았다 — 계약 .18 FE 차이(F2 실패 사유 표시 · F3 재큐잉 표시)는 FE 라운드가 맞춘다(응답 모양은 같음).
