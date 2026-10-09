# app/analysis

- **주인**: WP4 (R3 수정 라운드: F2)
- **읽기 허용**: WP5, WP7, WP8
- 쓰기 금지 이유(RA §2): 점수는 한 곳에서만 계산한다(ADR-11)

## 범위 (RA §2·§5·§6)

§6 수식의 순수 함수: `price.py`, `gap.py`, `ladder.py`, `score.py`, `sensitivity.py`, `scenarios.py`, `types.py`.
공용 규칙(R3, 파이프라인·API·보고서가 같은 함수를 부른다): `scope.py`(판정 범위 D9-1), `price_view.py`(현재 구매가 §6-1),
`complex_input.py`(사실 행 → `ComplexScoreInput`).
DB 접근 없음(ORM 행·DTO 를 받기만 한다 — Protocol 속성), 같은 입력 = 같은 결과. 모든 component 에 `formula_text`.

## 공용 함수 — 보고서(F4)·API·파이프라인 공통 (시그니처 고정)

### `app.analysis.scope` — 판정 범위 (meta §1-3-4, DECISIONS D9-1)

```python
JudgeScope = Literal["판정 대상", "참고", "보류", "미해결", "제외"]
SCOPE_TEXT: dict[JudgeScope, str]   # 표시 문구: "보류 — 공고 후 재판정", "참고 후보(순위만)", "미해결(분류 판정 미해결)" …

def judge_scope(*, inclusion_class: str | None, inclusion_decision: str | None,
                has_price: bool, intake_status: str | None) -> ScopeResult
# ScopeResult(scope: JudgeScope, reason: str) + .text .ladder .rerank .scored .decide

def pick_intake(rows: Iterable[R]) -> R | None        # 표시 접수 행(R = id·path·checked_at·status 를 가진 행)
def runs_ladder(scope) / in_rerank(scope) / is_scored(scope) / is_decide_candidate(scope) -> bool
def contract_scope(scope: JudgeScope) -> ContractScope   # 계약 .3 Literal(미해결 없음) → '제외'로; .4 이후 그대로
```

| 순서 | 조건 | 범위 | 사다리 | rerank | 점수 행 | decide |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `inclusion_class == '범위 경계'` | 제외 | × | × | × | × |
| 2 | classify auto + 제외 클래스(공공분양·공공/민간임대·비아파트·범위 밖) | 제외 | × | × | × | × |
| 3 | classify 미해결(decision ≠ auto, 클래스 미분류·manual_review) | 미해결 | × | × | × | × |
| 4 | 포함 확정 + 분양가 미공개 | 보류 | × | ○ | ○ | × |
| 5 | 포함 확정 + 가격 + 접수 확인 불가·불가·행 없음 | 참고 | × | ○ | ○ | × |
| 6 | 포함 확정 + 가격 + 접수 가능·미정 | 판정 대상 | ○ | ○ | ○ | ○ |

- `has_price` = `price_view.current_price(...).known`, `intake_status` = `pick_intake(그 스냅샷의 intake_status 행).status`.
- 표시 접수 행: human_check > official_popup > headless_shot, 같은 경로면 확인 **날짜**(앞 10자) 최근, 같은 날이면 id 큰 것.
  unofficial_ref 는 근거 아님.
- 보고서 사용 예: `judge_scope(inclusion_class=cx.inclusion_class, inclusion_decision=cx.inclusion_decision,
  has_price=current_price(types, payments).known, intake_status=(r.status if (r := pick_intake(rows)) else None)).scope`

### `app.analysis.price_view` — 현재 구매가 (§6-1, R3 M3)

```python
def basis_type(types: Iterable[T]) -> T | None                 # 84㎡에 가장 가까운 complex_type
def current_terms(terms: Iterable[P]) -> P | None              # effective_from → notice_no → id 최신
def current_price(types: Sequence[TypeRowLike], terms: Sequence[PaymentTermsLike]) -> PriceView
def mid_rounded(view: PriceView) -> int | None                 # 표시용 P_mid(원, 반올림)
```

`PriceView`: `basis_type_code, low_won, high_won, mid_won(Decimal), known, from_terms, terms_id, composition,
change_vs_first_pct, empty_reason('분양가 미공개')` + 출처 필드 `max_ref, floor_ref, extra_refs`(`FieldRef(entity,
entity_id, field, value)`) · `low_refs`·`high_refs`(그 값을 만든 필드들). 최신 공고 `payment_terms.price_by_type[기준
타입].max_price_won` 이 있으면 그 값(필드 `price_by_type.<타입>.max_price_won`), 없으면 complex_type. 발코니·필수 옵션은
complex_type. 라벨은 호출자가 ref 의 field_provenance 로 — 출처 행이 없으면 '확인 불가(출처 누락)'.

### `app.analysis.complex_input` — `ComplexScoreInput` 빌더 (R3 minor 20)

```python
def build_complex_input(cx, *, scope: JudgeScope, price: PriceView, asof_date: str, terms=None, payments=(),
                        intake=None, labels: Mapping[str, Label | None] | None = None, ladders=()) -> ComplexScoreInput
```
파이프라인(`scheduler.inputs.complex_input`)과 G5 미리보기(`api.views.score_input`)가 이것만 쓴다:
`has_priority_supply`(본청약 있으면 True, 공고가 전부 무순위·임의·선착순이면 False, 없으면 None),
`regulated`('규제'/'비규제' → bool, 그 밖 None), `immediate_move_in`(입주월 ≤ 기준일 월).

## 쓰는 법 (WP5·WP7·WP8)

| 필요한 것 | 호출 |
| --- | --- |
| score_run·score_component·score_total 행 | `AnalysisScoreEngine().run(snapshot, scenario, inputs)` (`ScoreEngine` Protocol) |
| + comparable_set 행·사다리 목표·민감도(C10) | `score.run_detailed(...)` → `.gaps[cid].members`, `.ladder_targets`, `.sensitivity` |
| 요건 사전 계산(decide 증거, G5 미리보기) | `scenarios.RequirementPrecalculator().evaluate(cx, scenario, asof_date=)`, `scenarios.precalc_rows(...)` |
| decide 동률(T2)·증거와 상이 | `score.decide_outcome(...)`, `scenarios.requirement_mismatch(pre, judge)` |
| 사다리 3시점·연율·명제 문장 | `ladder.ladder_targets`, `ladder.annualized`, `ladder.proposition_texts` |
| 내장 시나리오 5개(시드와 같음) | `scenarios.BUILTIN_SCENARIOS`, `scenarios.builtin("base")` |
| 미보정 gap%·미보정 중앙값(저장분) | `gap.unadjusted_from_flags(score_component.flags)` → `(Decimal \| None, int \| None)` (R3 W7) |

## R3 규칙 변경 (F2)

- 점수 대상 = `scope.is_scored`(제외·미해결 빼고). liquidity·move_in 라벨 = 입력 라벨 중 가장 약한 것(M2; null = 값이 있으면
  확인됨 — 계약 설명). 가격 출처 행이 없으면(price_label null) gap 라벨 '확인 불가' + reason '가격 출처 누락'(minor 24).
- `delta_rerank` = 이전 run 대비 **rerank 점수 차**(s = 10 × (N − rank)/(N − 1), §6-5 '점수 차이', minor 25).
- 점수 정밀도: 성분·종합 4자리(`score.SCORE_DECIMALS`), 표시 2자리(W12b). 저장 컬럼 scale 은 계약(F3).
- gap 성분 `flags` 에 `unadjusted_gap_pct=…`·`unadjusted_median_won=…` 태그(W7, 계약 컬럼이 생기기 전 영속 위치).

회귀: (a) `contracts/fixtures/.../expected_scores.json`(T1·T12), (b) `expected_scores_v2.json`(사람 확인 완료 골든) —
골든 입력은 judge_scope 를 내장하므로 D9-1 과 다른 단지는 `tests/analysis/test_scope.py` 의 차이 표로 기록한다.

## 규칙

- 이 디렉터리와 `backend/tests/analysis/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
