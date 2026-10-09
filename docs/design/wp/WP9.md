# WP9 회귀 픽스처 (라운드 1) — 작업 지시

소유: `contracts/fixtures/incheon_gimpo_2026-10-08/**`(단, `expected_scores.json`은 WP0 시드 — 고치면 사유를 `contracts/CHANGELOG.md`에; `expected_scores_v2.json`은 WP4), `contracts/fixtures/tools/`, `backend/tests/fixtures_contract/`, `e2e/`(R3용 골격만).
참조: RA §4-5, §9 전체(T1~T18이 요구하는 픽스처), §3; DECISIONS D3; 원천 `docs/source/incheon_gimpo_report.md`.

## 할 일
1. `complexes.json`: 보고서 단지 16개(인천 8 + 김포 8)를 RA §3 `complex`·`complex_type`·`payment_terms`·`competition`·`remaining_event` 형식 + Fact(라벨·출처 URL·확인일)로. 보고서에 없는 값은 "확인 불가(사유)".
2. `judgments/*.json`: 보고서 부록 A(호출 로그 #1~#132)와 각 절 판정 결과(noul 사다리, rerank 8→16, classify, compare, decide, verify)를 JudgmentEnvelope 녹화로. 파일명 = tool + input_hash. input_hash는 계약(`contracts/README.md`·`protocols.py`)의 canonical JSON 규칙 그대로 — 계산 스크립트 `contracts/fixtures/tools/hash.py`.
3. `raw/`: 공고문 txt 발췌, 해링턴 1,573 vs 1,769(T5), 임의공급 계약금 10%→5% 공고 2건(T9), 스위첸 홈페이지 403(T3), 팝업 이미지 동일/변경 쌍(T8), 메트로자이 11억 이상치 rtms(T4), 스위첸 대체 비교군 rtms(T11), provenance 지운 변형(T13), guard용 개인정보 payload(T14), 판정기 다운(T18) 시나리오.
4. `region.json`: 픽스처 지역 정의(D3) + 생활권 + 세대수(추정 라벨).
5. 픽스처마다 `contracts/schemas/` 스키마 검증 테스트; T1~T18 → 픽스처 매핑 표 `contracts/fixtures/incheon_gimpo_2026-10-08/README.md`.
6. 합성 1,000단지 생성 `contracts/fixtures/tools/synth.py`(T16).

## 완료 기준
- [ ] 모든 픽스처 스키마 검증 통과
- [ ] T1~T18 각각 필요한 픽스처 존재(매핑 표 + 존재 검사 테스트)
- [ ] 수치 필드 전부 라벨·출처 존재 검사
- [ ] synth.py 1,000단지 생성 + 스키마 통과
