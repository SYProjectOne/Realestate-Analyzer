# R5-NORM — 테스트와 수정 전 실패 확인 (`R5_FINAL.md` =====NORM, 계약 `2026-10-09.18` 유지)

브랜치 `wp/r5-norm`(main `1dec271` 에서). 소유: `backend/app/normalize`·`backend/app/analysis`·`backend/tests/{normalize,analysis}`.

## 확인 방법

- **수정 전** = 테스트 파일만 먼저 커밋한 상태(구현 없음)에서 그 파일만 `uv run pytest -p no:randomly <파일> -rA`.
  NORM 1 은 구현이 이미 있어(아래) 테스트만 더했고, 대신 **변이**(구현 한 줄을 지운 코드)로 테스트가 잡는지 확인했다.
- **수정 뒤** = 브랜치 끝 커밋, 전체 스위트 `uv run pytest -p no:randomly -m "not live"`.

## 항목별 테스트

| 항목 | 테스트 | 수정 전 | 수정 전 실패 단언(한 줄) | 수정 뒤 |
| --- | --- | --- | --- | --- |
| 1 이름 변경(major) | `tests/normalize/test_r5_norm1_rename.py::test_rename_keeps_row_and_records_former_name_and_event` | 통과(구현 있음 — `store.write_chosen`) · 변이(former_names 추가 줄 삭제) 시 실패 | `assert cx.former_names == [OLD]` | 통과 |
| 1 | `…::test_second_rename_appends_in_order_without_duplicates` | 통과 · 변이 시 실패 | `assert cx.former_names == [OLD, NEW]` | 통과 |
| 1 | `…::test_same_name_refetch_is_no_rename` | 통과(가드) | — | 통과 |
| 2a 스캔 | `tests/normalize/test_r5_norm2_scan_options.py::test_scan_notice_emits_unknown_scan_candidates_for_notice_rank1_fields` | **실패** | `assert rows and {(r.label, r.reason) …} == {("확인 불가", "스캔")}` — 스캔 원문 후보 0개 | 통과 |
| 2a | `…::test_scan_renormalize_is_idempotent` | 통과(가드: 후보 없을 때도 멱등) | — | 통과 |
| 2a | `…::test_scan_notice_of_unknown_complex_creates_nothing` | 통과(가드) | — | 통과 |
| 2a | `…::test_scan_without_complex_lookup_stays_empty` | 통과(가드: 판정기 추출 단계·벤치마크 경로 불변) | — | 통과 |
| 2b 필수 옵션 | `…::test_mandatory_option_table_is_parsed_per_type` | **실패** | `assert ((0.0, '확인됨') == (3210000, '확인됨')` — 미포함 보일러플레이트로 0원 | 통과 |
| 2b | `…::test_mandatory_option_table_in_man_won_is_scaled` | **실패** | 0원(같은 원인) | 통과 |
| 2b | `…::test_mandatory_option_without_readable_amount_is_unknown_not_zero` | **실패** | `{'74A': (0.0, '확인됨', None, False), …}` — 0원 확인됨 | 통과 |
| 2b | `…::test_boilerplate_only_notice_keeps_zero` | 통과(가드: 기존 동작) | — | 통과 |
| 2b | `…::test_recorded_must_check_boilerplate_is_not_mandatory[must-check·default-provided-duty·balcony-must-contract]` | 통과(가드: 녹화 공고문의 '반드시'·'(의무)' 문장) | — | 통과 |
| 2b | `…::test_no_recorded_notice_reads_as_mandatory_options` | 통과(가드: 녹화 공고문 41건 영향 0) | — | 통과 |
| 3a 표본 라벨 | `tests/analysis/test_r5_norm3_small_sample.py::test_one_or_two_new_build_trades_without_substitute_is_estimated_sample_n[1]`·`[2]` | **실패** | `assert '확인됨' == '추정'` | 통과 |
| 3a | `…::test_sample_reason_merges_with_price_source_missing` | **실패** | `('확인 불가', None)` ≠ `('확인 불가', '표본 1; 가격 출처 누락')` | 통과 |
| 3a | `…::test_score_component_carries_sample_label` | **실패** | `assert ('확인됨', None) == ('추정', '표본 2')` | 통과 |
| 3a | `…::test_score_formula_is_unchanged_by_sample_label`·`test_three_trades_keep_source_label`·`test_one_new_build_with_substitute_stays_substitute_label` | 통과(가드) | — | 통과 |
| 3a | `…::test_golden_v2_has_no_one_or_two_trade_comparable_set` | 통과(골든 영향 0 고정) | — | 통과 |
| 3b A·C 접수 AND | — (구현 안 함, 아래 영향 표) | — | — | — |

수정 전 실패 합계: 2a 1, 2b 3, 3a 4 = **8 실패**(나머지는 가드·변이 확인).

## 구현 요약

- **1** `normalize/store.py::write_chosen` 이 이미 RA §3 대로 한다(같은 주택관리번호 → 같은 행, 옛 이름 `former_names` 끝에 추가, change_event).
  빠진 것은 테스트였다 — 실제 녹화 청약홈 상세(`detail_2025000271.html`)의 이름 칸만 바꾼 원문으로 실제 파서를 거쳐 고정.
- **2a** `notice_parser.scan_candidates`: 스캔 원문(`error_text=scan`)이면 저장 단계가 준 단지 조회(`scan_types`, 같은 지역·주택관리번호의
  **이미 있는** 단지의 타입 코드)로 공고문 1순위 필드(단지: 전매·등기 해제·거주의무·재당첨·상한제 / 타입: 최고가·대표층가·발코니·필수 옵션)마다
  `label 확인 불가 + reason 스캔`(화면 '확인 불가(스캔)'). needs_extract 없음(글자 없음 → 판정기 요청 0). 값 있는 하위 출처(청약홈)는 resolver
  규칙 1 대로 그대로 채택되고 스캔 행은 병기, 공고문만 주는 필드는 스캔 행이 채택 출처. 모르는 단지·조회 없음(판정기 추출 단계·벤치마크
  아카이브)은 예전처럼 후보 없음 — 글자가 없어 잔여 공고인지 알 수 없으므로 새 단지 행을 만들지 않는다.
- **2b** `notice_parser._options`: '필수 선택품목'·'필수(유상)옵션'·'선택품목(필수)' 줄이 있으면 미포함 보일러플레이트로 0원을 만들지 않는다.
  그 줄부터 12줄 안의 '타입[·, 타입] 금액[단위]' 행(금액 하나로 끝나는 행)을 읽고(단위: 행 끝 > 블록 '(단위: …)' > 원 + `UNIT_ASSUMED`),
  못 읽은 타입은 '확인 불가'(reason '필수 선택품목 금액 해석 실패') + needs_extract. 본청약 공고만(기존 범위).
- **3a** `analysis/gap.py`: 신축 거래 1~2건·대체 없음 → `label 추정, reason '표본 n'`. 점수·식 그대로.

## 골든 영향 확인(항목 3 규칙)

방법: (1) 골든 생성기 `tests/analysis/_gen_expected_v2.py` 를 수정 전·후 코드로 각각 돌려(출력은 scratch 로 우회) 바이트 비교,
(2) `pytest -m regress tests`(수정 전 675 통과 / 수정 뒤 비교), (3) 골든 v2 입력 16단지 × 내장 시나리오 5개의 요건 사전 계산 덤프 비교.

| 변경 | 골든 v2 재생성 | regress | 판정 |
| --- | --- | --- | --- |
| 3a 표본 라벨 | 수정 전·후 **바이트 동일**(골든 입력의 신축 비교군 최소 45건, 1~2건 단지 없음) | 675 통과(수정 전과 같음, 실패 0) | **영향 없음 → 구현** |
| 3b A·C 접수 AND | 바이트 동일(골든은 base 시나리오만) | **3 실패**(아래) | **영향 있음 → 구현 안 함, CEO 결정 필요** |

### 3b 영향 표 (구현하지 않음)

제안 구현: `scenarios._access` 의 A(`priority_supply`)·C(`resale_before_exit`) 결과를 `_access_intake`(접수 상태)와 AND — 상태는 약한 쪽
(미충족 > 확인 불가 > 미입력 > 충족), 근거 문자열은 '접수 … → …; 상황 조건 … → …'. 상황 조건이 이미 미충족이면 그대로.

골든 입력(픽스처 16단지, 기준일 2026-10-08) 요건 사전 계산 `req_access_pre`:

| 상황 | 단지 | 필드 | 수정 전 → 수정 뒤 | 근거(수정 뒤) |
| --- | --- | --- | --- | --- |
| A | kaive_yubora(계양신도시 카이브 유보라) | access_pre | 충족 → 미충족 | 접수 미정(경로 미상) |
| A | grandforet(검단 센트레빌 그랑포레) | access_pre | 충족 → 미충족 | 접수 미정(경로 미상) |
| C | granter(더샵 송도그란테르) | access_pre | 충족 → 미충족 | 접수 미정(공식 팝업) |
| C | thesharp_ab23 | access_pre | 충족 → 미충족 | 접수 미정(공식 팝업) |
| C | gracent2 | access_pre | 충족 → 미충족 | 접수 미정(공식 팝업) |
| C | riverfront | access_pre | 충족 → 미충족 | 접수 미정(경로 미상) |
| C | lottecastle | access_pre | 충족 → 미충족 | 접수 미정(경로 미상) |
| C | gochon_centralxi | access_pre | 충족 → 미충족 | 접수 미정(경로 미상) |
| C | marinabay | access_pre | 충족 → 미충족 | 접수 불가(경로 미상) |
| C | switzen | access_pre | 충족 → 확인 불가 | 접수 상태 확인 불가 |
| C | harrington_1bl | access_pre | 충족 → 확인 불가 | 접수 상태 확인 불가 |
| C | gnheim | access_pre | 충족 → 확인 불가 | 접수 상태 확인 불가 |
| C | kaive_yubora | access_pre | 확인 불가 → 미충족 | 접수 미정 |
| C | grandforet | access_pre | 확인 불가 → 미충족 | 접수 미정 |
| C | elif·hannaedeul·cantavil | access_pre | 충족 → 충족(근거 문자열만 바뀜) | 접수 가능(공식 팝업) |
| C | granter(complex:1) | decision.mismatch (녹화 decide C: access supported) | false → **true**('증거와 상이' 배지) | 사전 미충족 vs 판정기 supported |
| A·C | decide 입력 4개(합성 녹화 decide 파일 4개) | input_hash | 바뀜 → 녹화 판정 미적중(review) | 사전 계산 근거가 decide 증거에 들어간다(RA §6-7) |

실패하는 테스트(모두 수정 전 통과):

| 테스트 | 실패 단언 | 원인 |
| --- | --- | --- |
| `tests/fixtures_contract/test_judgments_synth.py::test_recorder_is_reproducible` | judgments_synth 불일치 5개(`_index.json` + decide 4개) | A·C decide 입력 해시가 바뀜 → 합성 녹화 재생성 필요(`contracts/fixtures`, WP9) |
| `tests/regress/test_d91_scope.py::test_d91_scope_after_mock_rejudge_matches_readme` | `[('decide','decide:scenario_A'), ('decide','decide:scenario_C')] == []` | 녹화에 없는 payload → review |
| `tests/regress/test_t03_switzen_403.py::test_t03_human_check_rejudge_mock_judge_d91` | 합성 녹화에 없는 payload(→ review): A·C | 같음 |
| `tests/api/test_perf_r3c.py::test_list_responses_match_golden`(regress 아님, API 응답 골든) | `골든과 다른 응답: ['plain:compare', 'rich:compare', 'synth:compare']` | `/compare` 응답의 요건 사전 계산 문자열 |

결정에 필요한 것: (1) A·C 접근 조건에 접수 AND 를 넣을지(RA §6-7 문자 그대로면 넣는다 — 위 표대로 C 는 '접수 가능' 3단지만 충족),
(2) 넣으면 `contracts/fixtures/.../judgments_synth`(decide A·C)·`tests/api` 응답 골든 재생성과 CHANGELOG 사유(WP9·WP5 소유).
제안 패치(`scenarios.py` +47/−22)는 이 문서 끝 부록 — 결정 뒤 `git apply` 로 적용 가능(R5-NORM 브랜치 기준).

## 하지 않은 것

- 2a: 일부 스캔(`scan_partial:<p>`) 공고문은 기존대로(텍스트 쪽을 파싱, 못 읽은 필드는 '파싱 실패' 등 기존 사유). 어느 필드가 스캔 쪽에
  있었는지 알 수 없어 '스캔' 사유로 바꾸지 않았다. 스캔 원문의 납부 조건(payment_terms)은 공고일을 읽을 수 없어 공고 행을 만들 수 없으므로
  후보를 내지 않는다.
- 2b: 잔여(무순위·임의) 공고의 필수 옵션(예: 마리나베이 '필수옵션 에어컨·냉장고·타일')은 공고별 가격(`price_by_type`) 항목에 옵션이
  없어(계약) 다루지 않았다 — 필요하면 계약 변경 요청.

## 부록 — 3b 제안 패치(적용하지 않음)

```diff
diff --git a/backend/app/analysis/scenarios.py b/backend/app/analysis/scenarios.py
index 994ca69..93fa2d6 100644
--- a/backend/app/analysis/scenarios.py
+++ b/backend/app/analysis/scenarios.py
@@ -273,6 +273,51 @@ def _access_intake(c: ComplexScoreInput, asof_date: str, prefix: str) -> Require
 _REMAINDER_KINDS: Final = frozenset({"무순위", "임의", "선착순"})
 
 
+def _priority_supply(c: ComplexScoreInput) -> RequirementPre:
+    """A: 가점제 1순위 공급 존재."""
+    if c.has_priority_supply is None:
+        return _pre("확인 불가", "가점제 1순위 공급 여부 확인 불가")
+    if c.has_priority_supply:
+        return _pre("충족", "가점제 1순위 공급(본청약·예정 공고) 있음")
+    return _pre("미충족", "가점제 1순위 공급 없음(무순위·임의·선착순 경로만)")
+
+
+def _resale_before_exit(
+    c: ComplexScoreInput, sc: Scenario, rule: RequirementRule, asof_date: str
+) -> RequirementPre:
+    """C: 전매 종료 ≤ 목표 매도 시점(기준일 + 보유기간)."""
+    holding = _param(rule, sc, "holding_years")
+    if holding is None:
+        return _pre("미입력", "보유기간 미입력")
+    resale_months = _known(c.resale_months, c.resale_label)
+    if c.winner_date is None or resale_months is None:
+        return _pre("확인 불가", "전매제한 기간 확인 불가")
+    end = add_months_date(parse_date(c.winner_date), resale_months)
+    months = int((dec(holding) * 12).quantize(Decimal(1), rounding=ROUND_HALF_UP))
+    exit_ = add_months_date(parse_date(asof_date), months)
+    reg = " (등기 시 해제)" if c.resale_release_on_registration else ""
+    # 전매 종료 = 당첨일 + 기간 → 라벨은 두 입력 중 약한 것(R3 M2; winner_label 은 계약 .7)
+    end_label = resale_input_label(c.resale_label, c.winner_label)
+    head = f"전매 종료 {ym_of(end)}{reg}{_label_note(end_label)}"
+    tail = f"매도 시작 {ym_of(exit_)}(기준일 + 보유 {num(dec(holding), 1)}년)"
+    if end <= exit_:
+        return _pre("충족", f"{head} ≤ {tail}")
+    return _pre("미충족", f"{head} > {tail}")
+
+
+_PRE_ORDER: Final[dict[str, int]] = {"미충족": 0, "확인 불가": 1, "미입력": 2, "충족": 3}
+
+
+def _and_intake(c: ComplexScoreInput, asof_date: str, own: RequirementPre) -> RequirementPre:
+    """RA §6-7(R5-NORM 3b): A·C 접근 조건 = 상황 조건 AND ``intake_status ∈ {가능}``. 둘 중 약한 상태(미충족 > 확인 불가 >
+    미입력 > 충족), 근거는 둘 다."""
+    if own.status == "미충족":
+        return own  # 상황 조건이 이미 미충족 — AND 결과도 미충족(근거는 상황 조건 그대로)
+    intake = _access_intake(c, asof_date, "")
+    status = min((own.status, intake.status), key=lambda st: _PRE_ORDER[st])
+    return RequirementPre(status=status, evidence=f"{intake.evidence}; {own.evidence}")
+
+
 def _access(c: ComplexScoreInput, sc: Scenario, asof_date: str) -> RequirementPre:
     """§6-7 접근성. 공통 조건(R3 3차 RA 부분): 접수 경로가 비공식(unofficial_ref)뿐이면 어떤 상황이든 미충족(A·C 에도 AND).
     B·D(통장 없이·지금 계약)는 공급 경로도 본다 — 현재 공고가 무순위·임의·선착순이어야 한다(본청약 접수는 통장·가점 경로)."""
@@ -286,29 +331,9 @@ def _access(c: ComplexScoreInput, sc: Scenario, asof_date: str) -> RequirementPr
         if kind not in _REMAINDER_KINDS:
             return _pre("미충족", f"현재 공고 {kind}(통장·가점 경로) — 무순위·임의·선착순 공고 아님")
     if rule.code == "priority_supply":
-        if c.has_priority_supply is None:
-            return _pre("확인 불가", "가점제 1순위 공급 여부 확인 불가")
-        if c.has_priority_supply:
-            return _pre("충족", "가점제 1순위 공급(본청약·예정 공고) 있음")
-        return _pre("미충족", "가점제 1순위 공급 없음(무순위·임의·선착순 경로만)")
+        return _and_intake(c, asof_date, _priority_supply(c))
     if rule.code == "resale_before_exit":
-        holding = _param(rule, sc, "holding_years")
-        if holding is None:
-            return _pre("미입력", "보유기간 미입력")
-        resale_months = _known(c.resale_months, c.resale_label)
-        if c.winner_date is None or resale_months is None:
-            return _pre("확인 불가", "전매제한 기간 확인 불가")
-        end = add_months_date(parse_date(c.winner_date), resale_months)
-        months = int((dec(holding) * 12).quantize(Decimal(1), rounding=ROUND_HALF_UP))
-        exit_ = add_months_date(parse_date(asof_date), months)
-        reg = " (등기 시 해제)" if c.resale_release_on_registration else ""
-        # 전매 종료 = 당첨일 + 기간 → 라벨은 두 입력 중 약한 것(R3 M2; winner_label 은 계약 .7)
-        end_label = resale_input_label(c.resale_label, c.winner_label)
-        head = f"전매 종료 {ym_of(end)}{reg}{_label_note(end_label)}"
-        tail = f"매도 시작 {ym_of(exit_)}(기준일 + 보유 {num(dec(holding), 1)}년)"
-        if end <= exit_:
-            return _pre("충족", f"{head} ≤ {tail}")
-        return _pre("미충족", f"{head} > {tail}")
+        return _and_intake(c, asof_date, _resale_before_exit(c, sc, rule, asof_date))
     prefix = (
         f"통장·가점 없이 공식 경로({c.current_supply_kind}): "
         if rule.code == "official_path_no_account"
```
