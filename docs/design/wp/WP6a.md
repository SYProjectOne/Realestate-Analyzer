# WP6a 프론트 화면 (G0~G8) — 작업 지시

소유: `frontend/src/pages/**`, `frontend/src/app/**`(라우팅·레이아웃), `frontend/src/mocks/handlers.extra.ts`, `frontend/src/i18n/ko.json`(화면 문자열 추가), `frontend/e2e/pages/**`. **`src/components/`·`src/charts/`·`src/lib/`는 WP6b 소유** — 사용만 하고 고치지 않는다(스텁이어도 props 계약대로). 없는 컴포넌트는 페이지 폴더 안 로컬 컴포넌트로 + 보고에 "공통화 제안".
참조: RA §5 WP6 카드, **§7-1 전부**, §4-2, DECISIONS D2-5(G0·G0-2), D7, meta §2-6; `frontend/src/components/README.md`, `frontend/src/charts/README.md`.

## 할 일
G0 지역 입력(자동완성·후보 다중 선택·분석 시작·JobProgress), G0-2 생활권 편집, G1~G8을 RA §7-1 표의 컴포넌트·API·상호작용대로. 데이터는 MSW(계약 예시). 필터는 URL 쿼리, 탭은 URL 해시, 상황·기준일 전역 공유, G5 zod 폼 + 가중치 슬라이더 합 1 + 실행 폴링 2초 + escaped 배너, G7 사람 확인 폼 → 배지 갱신 + 재판정 토스트 + degraded 전역 배너, G8 contradicted 시 버튼 비활성 + 사유. G2 TanStack Table + 가상 스크롤. 모바일 ≤768px G1·G2·G3 읽기 전용, 다크 테마. 차트 갤러리 라우트(`/__charts`, dev 전용)를 `src/charts/gallery/`의 컴포넌트로 등록(6b가 만듦; 없으면 라우트만 준비).

## 완료 기준
- [ ] 10 라우트 렌더 + Playwright(MSW) 화면별 핵심 요소 테스트
- [ ] 숫자 셀 클릭 → 출처 패널
- [ ] lint(FactCell 밖 숫자 렌더 금지 규칙)·typecheck 0 오류
- [ ] G2 1,000행 가상 스크롤 렌더 테스트
- [ ] Lighthouse 성능 80 이상(build + preview + lighthouse CLI; 도구 추가는 보고에 명시)
