# ADR-06 프론트

- 상태: 채택 (RA v1 §1, DECISIONS D7)
- 결정: **React 18 + TypeScript + Vite, TanStack Query/Table(가상 스크롤), ECharts(echarts-for-react), Tailwind, React Router**
- 버린 대안: Next.js, Recharts

## 이유

- SSR 이 필요 없다(단일 사용자).
- ECharts 는 위스커·덤벨·스택·타임라인을 한 라이브러리로 그린다.

## 결과

- 정적 번들 → nginx(`infra/Dockerfile.web`, `infra/nginx.conf`), `/api/*` 는 api:8000 으로 경로 그대로 프록시.
- MSW 핸들러 = 계약 예시 응답 → API 없이 개발.
- 화면 공통 규칙(D7): "확인 불가(사유)", D± 날짜, 라이트/다크, 모바일 읽기 전용(G1·G2·G3), "투자 권유 아님 · 상대 비교",
  라벨은 텍스트 배지, 차트 데이터는 표로.
- 검사: `eslint` + `tsc --noEmit` + 테스트(CI `frontend` 잡).

## 바꿀 신호

없음.
