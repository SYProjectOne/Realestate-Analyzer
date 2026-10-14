# 10 — 네이버 부동산 (fin.land.naver.com) 관찰 노트

- 관찰일: 2026-10-14 · 관찰자: Tier 1 서브에이전트(시세·분석 6곳 담당)
- 결과: **관찰 불가(robots.txt)**

## 사유
- `fin.land.naver.com/robots.txt`(2026-10-14 확인): `User-agent: *`는 `/` 허용(개인 영역·검색·API 경로만 금지)이지만, **ClaudeBot·anthropic-ai·Claude-User를 포함한 AI 에이전트 UA 그룹에 `Disallow: /`(전면 금지)**를 명시한다.
- CEO 규칙(관찰 전 robots 확인, AI 에이전트 UA 금지 시 열지 않음)에 따라 단지 상세·분양·실거래 페이지를 관찰하지 않았다.

## robots 확인 전에 생긴 기록 (근거로 쓰지 않음)
| evidence_id | 내용 | 처리 |
|---|---|---|
| naver-home-desktop / naver-home-mobile | 이전 세션 Playwright. 루트 주소가 404 안내 페이지(외부 도메인)로 넘어감 | **제외(robots + 내용 없음)** |
| naver-map-desktop | 이전 세션 Playwright. 같은 404 안내 페이지 | **제외(robots + 내용 없음)** |
| naver-complex-desktop / naver-complex-mobile | 이전 세션 Playwright. 같은 404 안내 페이지 | **제외(robots + 내용 없음)** |
| (스크린샷 없음) | 이번 세션에 REA 관찰 창으로 단지 주소를 연 탭이 1개 있었으나 스크린샷이 연결 끊김으로 실패했고, 그 뒤 robots 규칙이 내려와 다시 시도하지 않았다. 탭은 CEO 일괄 정리 때 닫혔다 | 기록 없음 |

## Phase 3에 주는 영향
- 메타 프롬프트가 이 사이트에 기대한 "국내 사용자에게 가장 익숙한 정보 순서"는 직접 근거가 없다.
- 대체 근거 후보(같은 국내 시세 계열): KB부동산 단지 상세의 탭 순서(시세 → 실거래 → 타입 → 예산 → 기본정보 → 주변, `10-kbland.md`), 리치고 단지 상세의 탭 순서(정보 → 매물 시세 → 세금 → 갈아타기, `10-richgo.md`), 호갱노노·아실 노트. "국내 습관 우선" 판단을 할 때 네이버를 근거로 인용하지 않도록 한다.
- 참고: KB 단지 상세는 평면도 링크를 네이버 부동산으로 연결한다(kbland-danji-rea-desktop) — 국내 서비스끼리 네이버를 기준 자료처로 쓰는 관행은 확인되지만, 네이버 화면 자체의 구조는 관찰하지 않았다.
