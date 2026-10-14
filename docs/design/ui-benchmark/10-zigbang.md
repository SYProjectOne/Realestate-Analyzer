# 10 — 직방 (zigbang.com) 관찰 노트

- 관찰일: 2026-10-14 · 관찰자: Tier 1 서브에이전트(시세·분석 6곳 담당)
- 결과: **관찰 불가(robots.txt)** — 아파트 상세·분양 탭 모두

## 사유
- `www.zigbang.com/robots.txt`(2026-10-14 확인, curl 기본 UA는 CloudFront 403이라 일반 브라우저 UA로 파일만 1회 받음):
  - 파일 첫 줄에 "명시적 서면 허가 없는 크롤링 금지" 고지가 있다.
  - 검색엔진·SNS 미리보기 봇 목록에만 `/` 허용(그마저 `/danji`, `/apt/complex` 등 단지 경로는 금지).
  - **`User-agent: *`는 `Disallow: /`(전면 금지)**. ClaudeBot·anthropic-ai·Claude-User 전용 그룹은 없으므로 `*`가 적용된다 → 금지.
- 따라서 아파트 단지 상세(`/home/apt/danjis/...`)와 분양 탭을 열지 않았다. 이번 세션에 REA 관찰 창으로 단지 상세 탭을 한 번 열었으나(robots 규칙 전달 전), 스크린샷·접근성 관찰은 하지 않았고 탭은 CEO 일괄 정리 때 닫혔다.

## robots 확인 전에 생긴 기록 (근거로 쓰지 않음)
| evidence_id | 내용 | 처리 |
|---|---|---|
| zigbang-home-desktop | 이전 세션 Playwright 홈 | **제외(robots)** |
| zigbang-home-mobile | 이전 세션 Playwright. 앱 스토어 이동 페이지로 넘어감 | **제외(robots + 내용 없음)** |
| zigbang-apt-desktop | 이전 세션 Playwright. 아파트 탭 이동 실패, 홈과 같은 화면 | **제외(robots + 내용 없음)** |

## Phase 3에 주는 영향
- 메타 프롬프트가 기대한 "모바일 우선 카드, 쉬운 용어"는 직방에서 근거를 얻지 못했다.
- 대체 근거 후보: 청약홈 모바일(쉬운 동사형 카드 제목, `10-applyhome.md`), 리치고 단지 상세(대화체 설명 문장, `10-richgo.md`), 리치고 모바일·다방·땅집고 노트(Tier 2). 이 범주를 Phase 3에서 쓸 때 직방을 사이트 수에 넣지 않는다.
