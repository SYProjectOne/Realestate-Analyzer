# app/analysis

- **주인**: WP4
- **읽기 허용**: WP5, WP8
- 쓰기 금지 이유(RA §2): 점수는 한 곳에서만 계산한다(ADR-11)

## 범위 (RA §2·§5·§6)

§6 수식의 순수 함수: `price.py`, `gap.py`, `ladder.py`, `score.py`, `sensitivity.py`, `scenarios.py`, `types.py`.
DB 접근 없음, 같은 입력 = 같은 결과. 모든 component 에 `formula_text`.

- `ScoreEngine.run(snapshot, scenario, inputs) -> ScoreRunResult`, `RequirementPrecalc.evaluate(complex, scenario)` (RA §4-3).
- 판정 값은 봉투 형태 입력으로 받는다(WP3 코드 불필요).
- 날짜 차이는 `app.core.time.d_day` 를 쓴다.

## 규칙

- 이 디렉터리와 `backend/tests/analysis/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
