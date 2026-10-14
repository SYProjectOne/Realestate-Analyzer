# 10 — 아실 (asil.kr) — 관찰 불가(robots)

- 확인일: 2026-10-14 · 확인자: Tier 1 서브에이전트(공공·시세 6곳 담당)
- 판정: **관찰 불가(robots)**. 관찰 노트·패턴 없음.
- 사유: `https://asil.kr/robots.txt` 는 **`User-agent: *` 에 `Disallow: /`**, **`ClaudeBot` 에도 `Disallow: /`** 를 둔다(한 국내 검색엔진 UA만 허용). REA로 열지 않았다.
- 제외한 증거: 이 규칙이 내려오기 전(같은 날) Playwright로 홈 1페이지를 한 번 캡처했다 — `asil-home-desktop`, `asil-home-mobile` 와 그 접근성 텍스트. **이 증거는 제외(excluded)** 하며 패턴 근거로 쓰지 않는다. 파일은 저장소 밖 `C:\tmp\ui-bench\shots\` 에만 있다.
- 영향: "데이터 많은 화면을 표·차트로 나누는 법, 여러 단지 비교 UX"는 다른 허용 사이트에서 확인해야 한다. 필요하면 사람이 직접 보고 메모해 보완한다.
