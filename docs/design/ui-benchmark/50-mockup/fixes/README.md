# 50-mockup fixes (2026-10-16)

The user asked to fix the mockups and mark every change. The rules are in `BRIEF.md`. A fix was made for any of these reasons:
- the wording changed the meaning
- the screen computed a value or wrote a sentence itself (rules 3 and 5)
- a filter had no contract support
- a visible item was missing
- a tooltip was missing
- a behaviour could not be drawn (listed in a "구현할 때 지금 동작 그대로 유지" box at the bottom of each board)

**Marking on the boards:** each fixed block has a yellow dashed outline and a yellow pill "고침 XX-n". A yellow banner at the top of each board gives the fix count.

| Board | Code | Fixes | Log |
|---|---|---|---|
| Shell | SH | 21 | fixes-Shell.md |
| Main | HM | 17 | fixes-Main.md |
| Glossary | GL | 6 | fixes-Glossary.md |
| Detail | DT | 7 | fixes-Detail.md |
| DetailTabs | DX | 13 | fixes-DetailTabs.md |
| Mobile | MB | 5 | fixes-Mobile.md |
| List | LS | 3 | fixes-List.md |
| ListTable | LT | 8 | fixes-ListTable.md |
| Compare | CP | 22 | fixes-Compare.md |
| Scenario | SC | 10 | fixes-Scenario.md |
| Reports | RP | 7 | fixes-Reports.md |
| Market | MK | 17 | fixes-Market.md |
| Ops | OP | 14 | fixes-Ops.md |
| RegionNew | RN | 4 | fixes-RegionNew.md |
| LivingAreas | LA | 3 | fixes-LivingAreas.md |
| **Total** | | **157** | |

## Still open (decide at implementation)

- **Needs API data.** These values have no field in the API they come from today. The mockup shows `[값]` with an "API 필요" note.
  - G6: the region-wide unsold total. It exists only in the dashboard KPI, not in the market API.
  - G3: the neighbourhood trade median and the winning-points range in the header.
  - G1: the "공식 자료 n곳" count.
  - G7: the contradicted-claim breakdown.
- **Server wording.**
  - Requirement reasons contain `P_mid`.
  - Judge-scope reasons contain English class names such as `public_sale`.
  - Fixing either needs a server-side text change (WP4). The screen must show server strings unchanged.
- **Small leftovers.**
  - Job and step names have no plain-language mapping.
  - Two names need unifying: '접수 일정 미정' vs '접수 미정', and the Reports field name '공식 홈페이지 팝업' vs ko.json '공식 홈페이지 안내문'.
  - The List desktop cards show no score, but List is sorted by score.
  - Where the mobile menu goes (top or bottom) is undecided.
- **Not rendered in the real canvas runtime.** Agents checked the structure with scripts and the layout in Chrome, using a stub renderer.
