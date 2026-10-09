# WP6b 프론트 차트·공통 컴포넌트 (C1~C10) — 작업 지시

소유: `frontend/src/charts/**`, `frontend/src/components/**`, `frontend/src/lib/**`, 각 테스트. **`src/pages/`·`src/app/`는 WP6a 소유**. props/타입 계약(`src/components/README.md`, `src/charts/README.md`)은 바꾸지 말고 구현만(필요하면 하위 호환 확장 + 보고).
참조: RA §5 WP6 카드, **§7-2 전부**, §7 공통 규칙, meta §2-7(범위 = 점+위스커, 떠다니는 막대 금지, 색은 의미만, 라벨 병기, 차트 데이터 표로 열기), DECISIONS D7.

## 할 일
C1~C10 `buildOption(data)` 순수 함수 + 렌더 컴포넌트, 빈·특수 상태 전부(review 회색 "미해결", 비교군 없음(사유), 표본<3 배지, null component 빗금 "미판정", escaped 질문 텍스트, 이벤트 0 "본청약만", 결측 월 connectNulls=false 등). 공통 컴포넌트 완성: FactCell(포맷·라벨 배지·"사람" 접두·확인 불가(사유)), LabelBadge, IntakeBadge, ProvenancePanel(`/provenance/{id}` + 원문 발췌 하이라이트 + 상충 그룹), CachedBadge, TieBadge, MismatchBadge, UnstableBadge, ScenarioToggle, SnapshotPicker, RegionPicker, JobProgress, DataTableToggle, EmptyState. 라이트/다크. 차트 갤러리 컴포넌트 `src/charts/gallery/ChartGallery.tsx`(10개 차트 × 정상/빈/특수 상태).

## 완료 기준
- [ ] option 빌더 단위 테스트(C6 기여 합 = 종합 ±0.01, C1 markLine 0.15/0.85, C2 보정 중앙값 점선 점 등 차트마다 1개 이상)
- [ ] 차트 10개 각각 빈 데이터·라벨 배지 상태 스크린샷 테스트(Playwright로 갤러리 렌더 — 라우트 등록 전이면 테스트 전용 엔트리 html로)
- [ ] 컴포넌트 테스트(FactCell 클릭 → ProvenancePanel, 배지 텍스트)
- [ ] lint·typecheck 0 오류
