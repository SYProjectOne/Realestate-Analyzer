# 10 — Redfin (Tier 3, 미국)

**관찰 불가(봇 확인 화면)** — 2026-10-14

| evidence_id | 시도 | 결과 |
|---|---|---|
| redfin-home-desktop | Playwright 헤드리스 Chromium, https://www.redfin.com/ | HTTP 405, 페이지 제목 "Human Verification"(사람 확인 화면) |
| (PNG 미저장) REA ev_6d851323… | REA 관찰 Chrome(9333), 같은 URL | 같은 사람 확인 화면(제목 "Human Verification") |

- robots.txt: `/`는 `*`·ClaudeBot·anthropic-ai·Claude-User 모두 허용(차단 원인은 robots가 아니라 봇 확인 장치).
- 메타 프롬프트 §3-1 6번에 따라 우회(확인 통과 시도, 다른 UA, 쿠키 주입)를 하지 않았다. 매물 상세, 핵심 수치 요약 바, Redfin Estimate 신뢰 범위 패턴은 관찰하지 못했다.
- 대체 근거: 추정치 라벨·범위 패턴은 다른 사이트에서도 따로 근거를 찾지 못했다. Zillow 상세는 robots 때문에 제외했다(`10-zillow.md` 참고). 이 범주("추정치의 신뢰 범위 표기")는 이번 Tier 3 관찰로 확보한 근거가 없다.
