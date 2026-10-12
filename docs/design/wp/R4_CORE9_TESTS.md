# R4-CORE9 — R4 3차 재시험 결함 수정 테스트·수정 전 실패 확인 (2026-10-12)

원문: `docs/design/wp/R4_RESULT3.md` §10(N8~N12·m-a·m-b), 결정 `docs/design/DECISIONS.md` **D22**. 브랜치 `wp/r4-core9`(main `623620a` 기준),
계약 **2026-10-09.17**(이 브랜치가 냄 — `contracts/CHANGELOG.md` 맨 위, FE 차이 표 F1~F6).

**방법.** 결함마다 테스트를 먼저 쓰고(커밋 `948f82e [R4-CORE9] 테스트 먼저: …`) 그 시점 코드로 돌려 실패를 확인한 뒤 고쳤다. 끝에
`git archive 623620a backend contracts`(수정 전 앱·계약)에 새 테스트·녹화만 얹어 **한 번 더** 돌린 실제 출력이 아래 "수정 전" 열이다
(scratchpad `core9/prefix_final.txt`). 실데이터 재현은 R4 3차 재시험 원문(scratchpad `r4c/raw`, 공개 분양 정보)을 녹화 픽스처
`backend/tests/normalize/fixtures/r4c_core9/`(50건 — 청약홈 API·웹 상세, 공고문 추출 텍스트·표, **PDF 바이너리 제외**, 공고문 행 `path` =
텍스트 추출본)로 넣어 재생했다. 넣기 전 키·토큰 검사(`serviceKey`·`authorization`·`bearer`·`api_key`·`token=`·`X-NCP-APIGW` 정규식, URL 포함)
통과분만 넣었다. R4 DB(`subscription_analyzer_r4`)는 조사·녹화용 SELECT 만 했다(읽기 전용 연결, 접속 주소는 루트 `.env` 에서 스크립트로 읽고
출력하지 않음). 실제 판정기·외부 사이트는 부르지 않았다(가짜 판정기 `SynthJev` — 전송 계층 `tools/call` 계수 — 와 녹화 재생).

## 1. 결함별 수정·테스트·수정 전 실패

| 결함 · 결정 | 수정 | 테스트 | 수정 전(623620a) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **N9** critical · D22-1 | `normalize/store._reparse_existing`: 이번 파싱이 같은 자리(엔티티·필드·`excerpt_start`)를 여전히 판정기에 물으면(`needs_extract`) **같은 원문의 판정기 추출·감사 출처 행을 후보로 유지**(`_is_judged_row`). 파서가 이제 값을 읽으면 판정 행은 후보가 아니다 — 값이 바뀌면 resolve·`write_chosen` 이 change_event | `tests/scheduler/test_core9_n9_reextract.py::test_same_day_daily_keeps_judged_extract_facts_on_r4c_replay[r4c-order]`(R4 3차 실제 순서: bootstrap → (a) 재판정 → (b) 같은 날 daily → (a2) 재판정, 6단지 원문 재생) · `[bootstrap-daily-rejudge]`(D22-1 완료 기준 순서) · `tests/normalize/test_core9_n9_store.py::test_restore_same_notice_keeps_judged_row_chosen`(저장 단위 — 중흥S-클래스 계약금 비율 jl_241·jl_242) · `::test_parser_value_change_on_renormalize_emits_change_event`(회귀 방지) | `[r4c-order]` **`재정규화가 판정기 추출 출처 행을 내렸다(N9): {('2026000065', 'balance_pct'): (…, '30', '확인됨', False), ('2025000253', 'down_payment_pct'): (…, '10', '확인됨', False), … 7건}`**(R4 3차 6건 + 같은 공고문 잔금) · `[bootstrap-daily-rejudge]` `('… 이월해 발행', '사실 변경 — 재판정', 3)` — bootstrap 의 판정 단계 critical 이벤트(m-b) 때문에 daily 가 이월 대신 재판정을 걸어 N9 가 가려짐 · 저장 단위 **`(False, '확인됨', '판정기 추출 jl_241·감사 jl_242')`**(chosen False) | 통과: (b) 뒤 판정 행 chosen·'확인됨' 그대로, 발행 저장본 판정 Fact 동일 · '출처 누락' 수 동일, change_event 0, (a2) `tools/call` 0 |
| **N8** major(게이트) · D22-2 | `scheduler/pipeline._inclusion_changed`: 미분류여도 직전 판정(같은 판정기 버전·같은 항목 텍스트)이 review·manual_review 면 다시 보내지 않는다(판정 뒤 미분류로 되돌린 단지 — 범위 경계 → 미분류 — 는 그대로 보낸다). `_p4`: 배치 항목 단지 id 순 | `tests/scheduler/test_core9_n8_review_batch.py::test_same_snapshot_rejudge_three_times_sends_no_tools_call`(가짜 판정기가 단지 2·5 를 review — 같은 스냅샷 재판정 3회 연속) · `::test_review_complex_with_changed_input_is_sent_alone` · `::test_inclusion_batch_items_are_in_complex_id_order`(회귀 방지) | **`1회째 같은 스냅샷 재판정 tools/call 1건: ['jev_classify'] · 포함 배치 [['complex:2', 'complex:5']]`**(R4 3차 (a) 와 같은 모양) · `[['complex:2', 'complex:5']] == [['complex:5']]` | 통과: 3회 모두 `tools/call` 0 · 잡 `tools_calls` 0 · `judgment_log` 새 행 0, 입력이 바뀐 review 단지만 단독 배치 |
| **N10·N7** major · D22-3 | `normalize/living_area.correct_dong`(보정 + change_event `complex·legal_dong_code` critical), 쓰는 곳 3: `store`(원 단지에 묶인 잔여 공고문 공급위치), `remaining.sync_remaining_events`(청약홈 잔여 공고 공급위치 — 원 공고 다시 받기 뒤), `collect` 실행 끝(원 단지 주소가 생기기 전에 저장된 잔여 공고문 공급위치 — `StoreResult.alt_addresses`). 첫 적재면 이벤트 대신 요약 수 | `tests/scheduler/test_core9_n10_dong.py` 3 — R4 3차 원문(원 공고 2021000189 'RC3BL'·2021000830 '396-11번지(…A17BL)' 다시 받기 + 잔여 공고 2025930055·2025930047·2025910191 청약홈 원문 + 원 번호 인용 잔여 공고문 603·608), 참조 표 3행 | **`2021000189: 첫 수집 안에서 법정동(다른 출처 주소) — None` / `assert None == '2829010400'`**(R4 3차 1회차 46 과 같다) · **`assert set() == {(1, None, '2829010400'), (2, None, '2818510600')}`**(운영 중 보정 이벤트 0 — 조용한 변경) | 통과: bootstrap 순서 그대로 첫 수집 안에서 당하동(2829010400)·송도동(2818510600), 순서 바꿔도 같음, 운영 중 수집은 이벤트 2건(critical, 재판정 대상) · 같은 날 재수집 이벤트 0 |
| **N11** minor · D22-4 | `judge/pipeline.is_other_site`, `judge/payloads.SITE_OTHER_CLASS`, `scheduler/pipeline._same_site_only`: '공식 홈페이지가 다른 단지'는 auto `other_complex` 만, review·unclear 는 새 사유 `SITE_UNCONFIRMED` '공식 홈페이지 동일성 미확인' | `tests/scheduler/test_core9_n11_site_reason.py` 5(매개) | **`('확인 불가', '공식 홈페이지가 다른 단지') == ('확인 불가', '공식 홈페이지 동일성 미확인')`**(other_complex·review · same_complex·review · unclear·auto · unclear·review 4건) | 통과(other_complex·auto 는 수정 전에도 통과 — 회귀 방지) |
| **N12** minor · D22-4 | `normalize/notice_parser._ORIG_NO_RE`: `최초\s*(?:입주자\s*모집\s*공고[^\n]{0,80}?)?주택관리번호는\s*<번호>` | `tests/normalize/test_core9_n12_cite.py` 3 — R4 3차 원문 rd654(2024940118 임의공급) | **`('2024940118', None) == ('2024940118', '2023000463')`** · **`잔여 공고 번호로 단지 행: ['2024940118']`** | 통과(원 2023000463 단지 쪽, 자기 번호 행 없음) |
| **m-b** · D22-4 | `scheduler/pipeline.run_pipeline`: 지역이 bootstrapping 이면 P1~P5 가 남긴 사실 값 변경 이벤트(`apply_extracted`·`apply_compare` 의 `change_events` → `PipelineResult.judged_events`)를 지우고 첫 적재 요약에 더한다(`collect.fold_into_first_load`). 첫 적재 요약은 같은 적재(지역·스냅샷)에 한 줄 | `test_core9_n9_reextract.py::test_bootstrap_folds_judge_stage_changes_into_first_load` | **`첫 적재 중 판정 단계 값 변경 이벤트 7건: [('payment_terms', 'balance_pct', None, '30', 'critical'), ('payment_terms', 'down_payment_pct', None, '10', 'critical'), …]`** | 통과(사실 이벤트 0, first_load 1줄, 잡 stats `pipeline.first_load_folded`) |
| **D22-5** 이름 출처 서랍 | `snapshot_view._PROV_RE`: `"(?:name_)?prov":` | `tests/api/test_core9_d22_5.py::test_published_revision_name_provenance_drawer_is_200` | **`{"code":"not_found","detail":"발행 리비전 13 저장본에 출처 fp_1222 없음"}` / `assert 404 == 200`** | 통과 |
| **D22-5** 가격 보류 사유 | `api/views.price_hold_reason`(현재 구매가가 쓰는 필드 — 현재 공고 `price_by_type[기준 타입]` 칸, 없으면 타입 행 — 의 chosen 출처 행이 보류 표식) → `price_range` 사유 '출처 상충 — compare 대기'. `analysis.scope.judge_scope(price_reason=…)` | `test_core9_d22_5.py::test_held_basis_price_reason_is_conflict_hold` | **`('price_low', {'v': None, 'label': '확인 불가', 'reason': '분양가 미공개', …})`** | 통과(상세·목록 가격 3칸·범위 사유) |
| **D22-5** 계약 .17 `judge_scope_reason` | `contracts/schemas/complex_row.json`·`complex.json`(선택 string\|null ≤200 + 예시), `api/views.scope_reason`(현재 사실 범위의 `analysis.scope` reason, 목록 행·상세 머리 같은 값), `CONTRACT_VERSION`·`info.version`·DECISIONS 5행 `.17`, 생성물 재생성 | `test_core9_d22_5.py::test_judge_scope_reason_in_list_row_and_detail_header`·`::test_judge_scope_reason_names_boundary_without_dong`·`::test_contract_version_is_17` | `[(1, None), (2, None), …]`(키 없음) · `KeyError: 'judge_scope_reason'` · `'2026-10-09.16' == '2026-10-09.17'` | 통과 |

수정 전 합계: **실패 19 · 통과 6**(prefix_final.txt). 수정 전에도 통과하는 테스트(회귀 방지 — 의도): `test_core9_n10_dong.py::test_order_does_not_matter`
(원 공고가 잔여 공고문보다 먼저 저장되면 .16 저장 경로가 이미 보정한다 — 순서를 바꿔도 같은 결과를 고정), `test_core9_n9_store.py::test_parser_value_change_on_renormalize_emits_change_event`(값이 실제로
바뀌면 이벤트 — 보존 규칙이 이 경로를 막지 않음), `test_core9_n8_review_batch.py::test_inclusion_batch_items_are_in_complex_id_order`(지금 사실 묶음
이 이미 단지 id 순 — 순서 무관을 고정), `test_core9_n11_site_reason.py::…[other_complex-auto-…]`(다른 단지 auto 사유 그대로),
`test_core9_n12_cite.py::test_own_number_sentence_is_not_a_citation`(자기 번호 문장 비인용).

## 2. 바뀐 기존 테스트·골든·픽스처와 이유

| 파일 | 바뀐 것 | 이유 |
| --- | --- | --- |
| `tests/contracts/test_openapi.py::test_contract_version`, `tests/contracts/test_protocols.py::test_contract_version_matches_changelog` | 버전 단언 .16 → .17 | 계약 .17 |
| `tests/api/test_core8_d21_8.py::test_contract_version_is_16` | 삭제(같은 일을 `test_core9_d22_5.py::test_contract_version_is_17` 이 한다) | 계약 .17 |
| `tests/scheduler/test_core8_n6_site_identity.py::test_review_identity_is_also_not_evidence` | 동일성 review 의 기대 사유 '공식 홈페이지가 다른 단지' → '공식 홈페이지 동일성 미확인'(status '확인 불가'·접수 근거 아님은 그대로) | D22-4 · N11 |
| `tests/scheduler/test_r3b_g2.py::test_c3_extract_over_32_fields_is_split_not_truncated` | 가짜 `apply_extracted` 결과(`type('A', …)`)에 `change_events: []` 추가 | 파이프라인이 추출 반영 결과의 `change_events` 를 모은다(m-b 첫 적재 접기 — 실제 `ExtractApplyResult` 에는 원래 있는 필드) |
| `tests/api/snapshots/list_r3c.json`·`list_r3c/rich_size1000.json` | API 골든 재생성(`UPDATE_GOLDEN=1 pytest tests/api/test_perf_r3c.py -k golden`) — 목록 행·상세 머리에 `judge_scope_reason` 키만 늘었다(바이트 수·sha256) | 계약 .17 F1 |
| 새 `tests/normalize/fixtures/r4c_core9/` + `tests/normalize/_r4c.py` | R4 3차 원문 50건(그룹 n9 30 · n10 9 · n10_orig 6 · n12 5), `docs.json` = raw_document 행(수집 순서), 공고문 `path` = 텍스트 추출본 | N9·N10·N12·m-b 재생. HTML·JSON 은 `.gitattributes` 로 LF 정규화되어 sha256 이 녹화와 다를 수 있다(내용 동일 — 재생은 행의 sha256 으로 찾는다) |

회귀 골든(`expected_scores*.json`)·`contracts/fixtures/**`(`judgments_synth` 녹화·매니페스트)는 바꾸지 않았다.

## 3. 다음 R4 재시험(4차)에서 확인할 항목

`docs/runbook.md` §10-11 에 절차·SQL 을 적었다. 요약:

1. 2회차 (a)·(a2)·(a3) 같은 스냅샷 재판정 `tools/call` 0(프록시 = 잡 = `judgment_log`) — 1회차 review(미분류) 단지가 있어도(N8, 게이트).
2. 같은 날 daily (b) 발행 리비전 `missing_provenance` = (a) 리비전, 판정기 추출 납부 조건 '확인됨' 그대로(N9 critical).
3. 3차 46·47 의 법정동이 bootstrap 직후 당하동·송도동, (b) 뒤 법정동 이벤트 0(N10). 운영 중 보정이면 `complex·legal_dong_code` 이벤트.
4. bootstrap 사실 이벤트 0(판정 단계 포함), `first_load` 한 줄, `pipeline.first_load_folded`(m-b).
5. 동일성 사유: '다른 단지' = auto other_complex 만, review·unclear = '동일성 미확인'(N11).
6. 2024940118 이 원 2023000463 의 잔여 공고 이력, 원 공고 다시 받기(N12).
7. `judge_scope_reason`(목록·상세), 발행 리비전 이름 출처 서랍 200, 보류 가격 사유 '출처 상충 — compare 대기'(D22-5).
8. 1회차 호출 수와 3차(571) 대비 차이 — 법정동이 1회차에 정해져 3차 (a2) 의 classify·rerank 가 1회차로 옮겨 온다(예상).

## 4. 하지 않은 것 / 가정 / 남은 위험

- **m-a**(판정 대상 단지 유동성 입력 없음 — 풍무역 푸르지오 더 마크 계약금%)는 D22 범위가 아니라 고치지 않았다.
- **N9 보존 조건**: 같은 원문 재파싱이 같은 `excerpt_start` 를 여전히 판정기에 물을 때만 판정 행을 유지한다. 파서 개정으로 발췌 위치가 바뀌면 그
  필드는 다음 재판정까지 '확인 불가'(이벤트가 남는다 — 조용한 변경 아님). OCR 판독 행은 원래 규칙(`_demote_superseded_ocr`) 그대로.
- **m-b 범위**: 판정 단계 이벤트는 P1~P5(추출 적용·compare 채택)만 접는다. 접수 상태 변경(`_intake_changes` — 이전 스냅샷이 없으면 없음)·판정기
  버전 이벤트(`judge·version`)는 그대로 남긴다(첫 적재 요약 대상 아님).
- **첫 적재 요약 한 줄**: bootstrap 의 일일·주간 수집이 각각 줄을 만들던 것을 같은 적재(지역·스냅샷)의 한 줄로 합쳤다(문구 그대로, 수만 더함).
- **N10**: 대체 주소는 원 단지에 묶인 잔여 공고(공고문·청약홈 잔여 공고)의 공급위치와 그 단지 주소 출처 행뿐이다(공식 홈페이지 페이지 텍스트의 주소는
  읽지 않음 — .16 과 같다). 수집 실행 끝 보정은 그 실행에서 저장한 원문만 본다(다른 날 저장된 잔여 공고문은 그 원문이 다시 저장될 때 store 경로가
  본다 — 같은 날 재수집도 공고문을 다시 정규화한다).
- **N8**: 판정기가 같은 입력에 review 를 내는 단지는 사람 확인(G7)이나 입력 변경 전까지 미분류로 남는다(재판정이 다시 묻지 않는다 — 설계).
- **judge_scope_reason**: 현재 사실 범위의 사유다 — 화면 범위(점수 실행 저장값)와 다르면 `rejudge_needed` true. 보고서(`reports/`)의 범위 사유에는
  `price_reason`(보류 사유)을 넘기지 않았다(보고서는 '분양가 미공개(공고 전)' 그대로 — 다음 라운드 후보).
- **이미 발행된 리비전**: .16 이전 발행 저장본의 이름 출처 서랍은 다시 발행하기 전까지 404(저장본 불변 — D11-1). 마이그레이션 없음.
- 프론트(`frontend/**`)는 바꾸지 않았다 — 계약 .17 FE 차이(F1~F6)와 FE10 e2e `test.fail` 표식 제거는 FE 라운드가 맞춘다(`npm run gen:api`·`gen:msw`).
