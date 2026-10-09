# WP4 분석 엔진 — 작업 지시

소유: `backend/app/analysis/`, `backend/tests/analysis/`, `contracts/fixtures/incheon_gimpo_2026-10-08/expected_scores_v2.json`(골든 draft).
참조: RA §3 분석 테이블, §4-3 `ScoreEngine`·`RequirementPrecalc`, §5 WP4 카드, **§6 전부**, §9 T1·T2·T4·T9·T10·T11·T12; DECISIONS D1 #2·#3·#4.

## 할 일
`types.py`(dataclass 입력), `price.py`(§6-1), `gap.py`(§6-2 비교군·대체·연식 보정·**이상치 1.5×IQR 제외 + comparable_set 기록**(T4)·점수), `ladder.py`(§6-3 목표 시점·연율), `score.py`(§6-4 6 component + move_in, 가중 합, 동점 |ΔS|<0.05 공동 순위, decide conf<0.6 상위 2 tie, null component → 종합 미계산 "미판정"; rerank는 한 judgment_seq 값만 + `delta_rerank` §6-5), `sensitivity.py`(§6-6 12 변형), `scenarios.py`(내장 5 + 요건 사전 계산 §6-7 근거 문자열). 모든 component에 `formula_text`. **순수 함수(DB 접근 없음)**. 판정 값은 봉투 형태 입력 — status review/escaped/blocked는 사용하지 않는다(RA §4-1: WP4가 걸러냄).

## 완료 기준
- [ ] `contracts/fixtures/incheon_gimpo_2026-10-08/expected_scores.json` 재현(±0.01) (T1)
- [ ] conf 0.48 decide → tie=true (T2)
- [ ] 엘리프 전매 요건 사전 계산 = 충족 + 근거 문자열
- [ ] T4 이상치, T9 유동성 D/5 항 2→1, T10 연율, T11 대체·보정(라벨 "추정(대체·보정 c=0.015)", 보정/미보정 둘 다), T12 민감도 TOP5 변동
- [ ] 모든 component formula_text 비어 있지 않음
- [ ] 같은 입력 = 같은 결과(hypothesis 속성 테스트)
- [ ] `expected_scores_v2.json` draft: §6-4 식으로 16개 단지를 다시 계산한 값 + (a)와의 차이 설명 — 입력은 보고서 수치(`docs/source/incheon_gimpo_report.md`), "사람 확인 대기" 표시
