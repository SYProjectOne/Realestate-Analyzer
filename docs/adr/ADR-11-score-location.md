# ADR-11 점수 계산 위치

- 상태: 채택 (RA v1 §1, §6)
- 결정: **worker 의 순수 함수 모듈(`app/analysis/`)에서만 계산, 결과는 `score_run` 테이블에 저장; 프론트는 표시만**
- 버린 대안: 프론트 계산

## 이유

같은 입력 = 같은 점수를 테스트로 보장하려면 한 곳에서만 계산해야 한다.

## 결과

- `app/analysis`(WP4)는 DB 접근 없는 순수 함수. 모든 component 에 `formula_text`.
- api(WP5)·보고서(WP8)는 `score_run` 을 읽기만 한다. 프론트는 `FactCell` 로 표시만.
- 회귀: `expected_scores.json` 재현(소수 2자리, `python scripts/tasks.py regress`).

## 바꿀 신호

없음.
