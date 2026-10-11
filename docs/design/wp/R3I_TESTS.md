# R3i CORE7 — 리뷰 ID별 테스트와 수정 전 실패 확인 (9차 리뷰 `R3_REVIEW9.md`, 계약 .14)

9차 리뷰 지적: 지난 라운드의 "수정 전 실패 확인" 표가 저장소에 없었다. 이 문서가 R3i 의 그 표다.

## 확인 방법(재현 가능)

1. **수정 전 코드** = main `3a4141d`(R3i 배정 커밋). `git archive 3a4141d backend contracts` 를 임시 폴더에 풀고, R3i 의 새·보강 테스트 파일
   7개(`tests/api/test_r3i_core7.py`·`test_r3i_discount.py`, `tests/contracts/test_r3i_migrations.py`, `tests/core/test_r3i_redact.py`·
   `test_r3i_checkpointer.py`·`test_r3h_checkpointer.py`, `tests/normalize/test_r3g_k1_discount.py`)만 이 브랜치 것으로 덮어쓴 뒤 같은 venv 로
   `PYTHONPATH=. python -m pytest -p no:randomly <파일들> --junitxml=pre_junit.xml`(`app.__file__` 이 임시 폴더를 가리키는 것 확인).
   결과: **66 실패 / 212 통과** (52.9s). 아래 표 '수정 전 실패' = 그 junit 의 테스트별 결과, '실패 단언' = 첫 실패 메시지 첫 줄.
2. **수정 뒤** = 이 브랜치 최종 커밋, 전체 스위트(`--junitxml`)의 같은 테스트 결과.
3. 수정 전에 통과하는 테스트(가드·보강)는 '아니오'로 숨기지 않는다. 그중 9차 m19(약한 테스트) 보강분은 **변이**로 따로 확인했다(아래 '변이 확인').

리뷰 재현 스크립트(scratchpad `r9/a`·`b`·`c`·`r`)는 위 테스트로 옮겼다: `r9/b/crash_backfill.py`·`concurrent_backfill.py`·`newcx.py`·`mutate.py`
→ `test_r3i_migrations.py`, `r9/b/test_r9_carry.py`·`r9/c/test_r9c_carry.py` → `test_major3_*`, `r9/c/test_r9c.py` → m8·m10·m9(=리뷰 m12 표기)·m11,
`r9/c/test_r9c_ckpt.py` → m12, `r9/a/*` → major 4·m2·m4, `r9/r/probe_redact.py` → m17.

## 리뷰 ID별 테스트(수정 전 = 3a4141d, 수정 뒤 = 전체 스위트 A junit)

| 리뷰 ID | 테스트 | 수정 전 실패 | 실패 단언(수정 전, 한 줄) | 수정 뒤 |
| --- | --- | --- | --- | --- |
| major 1·2 / D17-1·D17-2 (SQLite) | ``test_sqlite_r3i_backfill`` | 예 (1/1) | AssertionError: 새 행 쓰기 중: 발행 순간 서랍이 지워지거나 지금 사실로 바뀌었다 ['cs_11', 'cs_110', 'cs_112', 'cs_113', 'cs_117'] (서랍 0/1660) | 1/1 통과 |
| major 1·2 / D17-1·D17-2 (임베디드 PG 16) | ``test_postgres_r3i_backfill`` | 예 (1/1) | AssertionError: 새 행 쓰기 중: 발행 순간 서랍이 지워지거나 지금 사실로 바뀌었다 ['cs_11', 'cs_110', 'cs_112', 'cs_113', 'cs_117'] (서랍 0/1660) | 1/1 통과 |
| m5 (SQLite) | ``test_sqlite_m5_report_score_ids`` | 예 (1/1) | AssertionError: 0014 변환 = 옛 행 id → API 서랍 id(sc_<실행>_<단지>_<성분>·st_<실행>_<단지>), 원래 JSON 바이트 | 1/1 통과 |
| m5 (PG) | ``test_postgres_m5_report_score_ids`` | 예 (1/1) | AssertionError: 0014 변환 = 옛 행 id → API 서랍 id(sc_<실행>_<단지>_<성분>·st_<실행>_<단지>), 원래 JSON 바이트 | 1/1 통과 |
| m1 (SQLite) | ``test_sqlite_m1_0013_keeps_compare_mark`` | 예 (1/1) | AssertionError: 공고문 자동 추출 — 조건 확인 필요 | 1/1 통과 |
| m1 (PG) | ``test_postgres_m1_0013_keeps_compare_mark`` | 예 (1/1) | AssertionError: 공고문 자동 추출 — 조건 확인 필요 | 1/1 통과 |
| 0014 왕복 (SQLite) | ``test_sqlite_0014_roundtrip`` | 예 (1/1) | AssertionError: assert 'backfilled_at' in {'done', 'id', 'kind', 'rows', 'scenario', 'shape_version', ...} | 1/1 통과 |
| 0014 왕복 (PG) | ``test_postgres_0014_roundtrip`` | 예 (1/1) | AssertionError: assert 'backfilled_at' in {'done', 'id', 'kind', 'rows', 'scenario', 'shape_version', ...} | 1/1 통과 |
| major 3 / D17-3 ready 멱등 | ``test_major3_crash_after_last_run_retry_publishes`` | 예 (1/1) | AssertionError: ('failed', 'failed', 'RuntimeError: worker killed after last run commit, before status=ready commit') | 1/1 통과 |
| major 3 / D17-3 재시도 | ``test_major3_failed_carry_is_retried_and_later_write_published`` | 예 (1/1) | AssertionError: failed | 1/1 통과 |
| major 3 / D17-3 재등록 | ``test_major3_terminal_failure_reregisters_deferred_writes`` | 예 (1/1) | AttributeError: module 'app.scheduler.handlers' has no attribute 'PUBLISH_ERROR_RETRY_MAX' | 1/1 통과 |
| D17-5 · m15 체크리스트 | ``test_d17_5_checklist_patch_leaves_publish_job`` | 예 (1/1) | AssertionError: {"id":4,"complex_id":10,"complex_name":"풍무역 롯데캐슬 시그니처","kind":"중도금","title":"중도금 1회차 납부일(임의공급 계약자)","due_date":"2026-10-15","status":"… | 1/1 통과 |
| D17-5 · m15 지역 이름 | ``test_d17_5_region_name_patch_leaves_publish_job`` | 예 (1/1) | AssertionError: {"region":{"id":1,"name":"R3i 새 이름","query_text":"송도, 검단, 계양구, 김포시","selections":[{"kind":"legal_dong","code":"2818510600","full_name"… | 1/1 통과 |
| m8 | ``test_m8_catalyst_coordinate_precision_resend_is_unchanged`` | 예 (2/2) | AssertionError: {"catalyst":{"id":44,"name":"R3i 정밀 37.1234567","kind":"교통","stage":"계획","stage_prob":{"v":null,"label":"확인 불가","reason":"미판정","prov":… | 2/2 통과 |
| m9 | ``test_m9_implicit_compare_pending_is_503`` | 예 (1/1) | AssertionError: {"id":2,"job_name":"report","kind":"manual","payload":{"snapshot_id":13,"format":"html"},"scheduled_at":"2026-10-12T06:19:54+09:00","s… | 1/1 통과 |
| m10 | ``test_m10_checked_at_error_comes_first`` | 예 (2/3) | AssertionError: [['body', 'kind'], ['body', 'checked_at']] | 3/3 통과 |
| m13 | ``test_m13_lease_lost_writer_writes_nothing`` | 예 (1/1) | AssertionError: 임대를 잃은 보유자가 저장본 145행을 썼다 | 1/1 통과 |
| m14 | ``test_m14_catalyst_patch_without_snapshot_is_200`` | 예 (1/1) | AssertionError: {"catalyst":{"id":44,"name":"R3i 빈 지역 호재","kind":"교통","stage":"계획","stage_prob":{"v":null,"label":"확인 불가","reason":"미판정","prov":null,"… | 1/1 통과 |
| m6 단계 격리 | ``test_m6_backfill_isolates_human_check_migration`` | 예 (1/1) | RuntimeError: human check migration failed | 1/1 통과 |
| m6 worker 재시도 | ``test_m6_worker_retries_backfill`` | 예 (1/1) | AttributeError: module 'app.scheduler.runner' has no attribute 'LoopState' | 1/1 통과 |
| m11 | ``test_m11_requeue_and_stale_counters_kept`` | 예 (1/1) | AssertionError: {'snapshot_id': 12, 'published': False, 'contradicted': 0, 'publish_in_progress': 'job:1', ...} | 1/1 통과 |
| m16 기다림 | ``test_m16_once_waits_for_requeued_job`` | 예 (1/1) | AssertionError: assert 'queued' == 'done' | 1/1 통과 |
| m16 종료 코드 | ``test_m16_once_exits_nonzero_when_requeued_left`` | 예 (1/1) | AttributeError: <module 'app.scheduler.runner' from 'C:\\Users\\USER\\AppData\\Local\\Temp\\claude\\c--Users-USER-Desktop-SY-program-Realestate\\ae35f… | 1/1 통과 |
| major 4 / D17-4 | ``test_major4_new_notice_without_discount_keeps_human_discount`` | 예 (1/1) | AssertionError: None | 1/1 통과 |
| D17-4 계약금 | ``test_d17_4_new_notice_without_down_payment_keeps_human_value`` | 예 (1/1) | AssertionError: {'v': None, 'label': '확인 불가', 'reason': '값 없음', 'prov': None, ...} | 1/1 통과 |
| D17-4 같은 값(가드) | ``test_d17_4_new_notice_same_value_keeps`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| D17-4 다른 값 D12-1(가드) | ``test_d17_4_new_notice_other_value_supersedes`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| m4 옛 공고 entity_id | ``test_m4_human_discount_on_old_notice_applies_to_current`` | 예 (1/1) | AssertionError: None | 1/1 통과 |
| m4 기준 타입 변경(가드) | ``test_m4_basis_type_change_does_not_carry_discount`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| D17-4 · m3 기준 타입 표시 필드 | ``test_d17_4_human_check_response_has_basis_type`` | 예 (1/1) | KeyError: 'basis_type_code' | 1/1 통과 |
| m2 형식 | ``test_m2_discount_format_rejected`` | 예 (15/15) | AssertionError: ('１０,０００,０００', '{"id":1,"complex_id":1,"field":"discount","entity":"payment_terms","entity_id":1,"value_text":"１０,０００,...ull,"complex_… | 15/15 통과 |
| m2 받는 꼴(가드) | ``test_m2_discount_format_accepted`` | 아니오 (5/5 통과 — 가드·보강) | — | 5/5 통과 |
| m2 할인 ≥ 가격 | ``test_m2_discount_not_below_price`` | 예 (1/1) | AssertionError: (1245000000, '{"id":1,"complex_id":1,"field":"discount","entity":"payment_terms","entity_id":1,"value_text":"124500000...ull,"complex_… | 1/1 통과 |
| m2 · F9 다른 칸 함께 | ``test_m2_discount_and_other_field_errors`` | 예 (1/1) | AssertionError: [['body', 'kind']] | 1/1 통과 |
| m17 camelCase·pass | ``test_m17_key_names`` | 예 (4/7) | AssertionError: accessKey=AKIAABCDEFGHIJKL | 7/7 통과 |
| m17 과잉 가림 없음(가드) | ``test_m17_key_names_not_overmatched`` | 아니오 (6/6 통과 — 가드·보강) | — | 6/6 통과 |
| m17 키 없는 토큰 | ``test_m17_keyless_tokens`` | 예 (9/9) | AssertionError: error: upstream said sk-ant-api03-abcdefghijklmnopqrstuvwxyz was rejected | 9/9 통과 |
| m17 dict 숫자 값 | ``test_m17_sensitive_key_numeric_values`` | 예 (3/6) | AssertionError: {'password': 12345678} | 6/6 통과 |
| m17 bearer 산문 | ``test_m17_bearer_prose_not_masked`` | 예 (3/4) | AssertionError: assert 'the bearer [...] were issued' == 'the bearer c...s were issued' | 4/4 통과 |
| m17 bearer 토큰(가드) | ``test_m17_bearer_tokens_still_masked`` | 아니오 (4/4 통과 — 가드·보강) | — | 4/4 통과 |
| m12 | ``test_m12_checkpoint_failures_are_logged_and_fall_back`` | 예 (1/1) | AttributeError: <module 'app.core.db' from 'C:\\Users\\USER\\AppData\\Local\\Temp\\claude\\c--Users-USER-Desktop-SY-program-Realestate\\ae35f7d2-c8d4-… | 1/1 통과 |
| m19 체크포인터 assert 보강 | ``test_postgres_or_memory_is_noop`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| m19 할인 후보 출력 단언 | ``test_k1_review_phrases_not_confirmed`` | 아니오 (20/20 통과 — 가드·보강) | — | 20/20 통과 |
| m19 퍼징 목록 후보 단언 | ``test_k1_reviewer_fuzz_cases`` | 아니오 (151/151 통과 — 가드·보강) | — | 151/151 통과 |
| m19 퍼징 복원(hypothesis) | ``test_k1_property_candidates_are_estimates`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| m19 퍼징 복원(허용 꼴 후보) | ``test_k1_property_canonical_is_estimate_candidate`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| m19 m21 docstring | ``test_m21_flip_takes_write_lock_before_reading`` | 아니오 (1/1 통과 — 가드·보강) | — | 1/1 통과 |
| D17-6 · m18 묶음 사이 양보 | ``test_d17_6_write_yield_after_lock_held`` | 예 (1/1) | AttributeError: module 'app.core.db' has no attribute 'time' (``WriteYield`` 없음) | 1/1 통과 |
| D17-6 · m18 D14-5 부하(1000 단지 × 5) | ``test_d14_5_publish_job_1000x5_under_30s_and_api_writes_wait_under_1s`` | 부하 의존 — 9차 리뷰 전체 스위트(부하)에서 실패: "API 쓰기 최대 2.522s > 1.0s"(SQL 실행 잠금 대기 2.509s) | (리뷰 원문) | 아래 '측정' |

## 변이 확인(9차 m19 — 수정 전에도 통과하는 '약한 테스트' 보강분)

수정 대상 코드가 아니라 **테스트**가 약했던 항목이라 수정 전 코드에서는 통과가 맞다. 대신 같은 수정 전 코드에 변이를 넣고 예전 테스트와
보강 테스트를 나란히 돌렸다(`mut_src` = 3a4141d + 변이 2개, 17.4s, 23 실패 / 345 통과):

| 변이 | 예전 테스트(3a4141d) | 보강 테스트(이 브랜치) |
| --- | --- | --- |
| 공고문 파서 할인 줄 함수가 후보를 아예 내지 않음(`_discount_line` → None) | `test_r3g_k1_discount.py` **전부 통과**(후보 미출력도 통과 — 9차 지적 그대로) | 실패 22: `test_k1_review_phrases_not_confirmed` 19/20, `test_k1_reviewer_fuzz_cases` 2(예전 허용 꼴 2줄), `test_k1_property_canonical_is_estimate_candidate` 1 |
| SQLite 메모리 DB 에도 체크포인터를 켬(`file_db` 조건 삭제) | `test_postgres_or_memory_is_noop` 통과(assert 없음) | 실패 1(`sqlite-checkpointer` 스레드가 생김) |
| m21 전환 잠금 UPDATE 삭제(9차 리뷰가 직접 확인) | 실패하되 docstring 이 실패 이유를 틀리게 적음 | docstring 바로잡음(다른 연결 커밋이 **성공**해 `other_committed` 단언이 실패) |

`test_r3h_migrations` 의 빈 곳(서랍 바이트·중단·동시·발행 뒤 사실 변경)은 새 파일 `tests/contracts/test_r3i_migrations.py` 가 SQLite·임베디드
Postgres 둘 다에서 본다(위 표 major 1·2 행 — 수정 전 실패 확인). e2e `charts-gallery C05` 부하 시간 초과는 FE8 몫(`e2e/**`·`frontend/**`).

## 수정 뒤 전체 실행(완료 기준)

| 실행 | 결과 | 비고 |
| --- | --- | --- |
| 전체 pytest A(`-p no:randomly -m "not live" --junitxml`) — `python scripts/tasks.py regress` 와 동시 | **3860 통과 / 0 실패**(1528s) | 같은 시간 regress 3회 연속(각 T01–T18 PASS·e2e 3/3) |
| 전체 pytest B(같은 명령) — regress 와 동시 | **3860 통과 / 0 실패**(1597s) | 같은 시간 regress 3회 연속(각 T01–T18 PASS·e2e 3/3) |

## 측정(D14-5 / D17-6 — `tests/api/test_r3f_perf_publish.py`, devseed 16 + 합성 1,000 단지 × 시나리오 5, 기준 잡 ≤30s·API 쓰기 대기 ≤1s 그대로)

| 실행 | 잡 | API 쓰기 최대 / p50 (건수) | SQL 실행 최대(잠금 대기) / COMMIT 최대 | 묶음 쓰기 잠금 최대 · 묶음 수 · 양보 | 이월 단계 잠금 최대 · 단계 |
| --- | --- | --- | --- | --- | --- |
| 전체 스위트 A 안(+ regress) | 16.48s | 0.189s / 0.004s (301) | 0.185s / 0.000s | 0.042s · 19 · 1 | 0.046s · 8 |
| 전체 스위트 B 안(+ regress) | 16.63s | 0.196s / 0.004s (300) | 0.192s / 0.003s | 0.039s · 19 · 1 | 0.048s · 8 |
| 별도 1(테스트 단독 + regress 동시, 시스템 CPU 82%·메모리 84%) | 22.95s | 0.258s / 0.004s (403) | 0.254s / 0.028s | 0.050s · 19 · 1 | 0.053s · 8 |
| 별도 2(같은 조건, CPU 83%·메모리 86%) | 22.46s | 0.263s / 0.004s (396) | 0.258s / 0.054s | 0.029s · 19 · 1 | 0.061s · 8 |

9차 리뷰 실패(전체 스위트 부하 API 쓰기 2.522s — SQL 실행 잠금 대기 2.509s)의 원인은 묶음·이월 단계가 끝나자마자 다음 묶음이 쓰기 잠금을 다시 잡아
SQLite 바쁨 처리기(1~100ms 간격 재시도)로 기다리던 API 쓰기가 계속 놓친 것이다. 수정(`core.db.WriteYield`): 잠금을 이어서 0.2초 넘게
들었으면 다음 묶음 전에 0.12초 쉰다(최대 재시도 간격 100ms 보다 길게) — 잡 stats `write_yields`. 기준(30s·1s)은 그대로다.
