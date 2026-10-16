# 50-mockup Coverage Tables (rebuilt 2026-10-16)

Every feature in the current frontend source (`frontend/src`) was extracted line by line and mapped to a section of a mockup board in `../boards/`. The extraction rules are in `BRIEF.md`. Each file also has a separate table, "새로 더한 것" (new in the mockup).

A feature counts as **있음** (present) only if the mockup actually draws it. A feature the mockup describes in words but does not draw is counted as **문구로만** (described only).

| File | Current screen | Total | Present | Described only | On another board | Missing | Fixes |
|---|---|---|---|---|---|---|---|
| coverage-Shell.md | App shell (layout, components, _shared) | 299 | 202 | 43 | 54 | 0 | 21 |
| coverage-Main.md | G1 home | 156 | 119 | 7 | 30 | 0 | 17 |
| coverage-List.md | G2 complex list | 120 | 101 | 15 | 4 | 0 | 11 |
| coverage-Detail.md | G3 complex detail | 312 | 280 | 25 | 7 | 0 | 25 |
| coverage-Compare.md | G4 compare | 176 | 169 | 2 | 5 | 0 | 22 |
| coverage-Scenario.md | G5 scenario | 145 | 130 | 3 | 12 | 0 | 10 |
| coverage-Market.md | G6 regional market | 216 | 191 | 21 | 4 | 0 | 17 |
| coverage-Ops.md | G7 data and operations | 258 | 241 | 17 | 0 | 0 | 14 |
| coverage-Reports.md | G8 reports + share-link landing | 90 | 74 | 15 | 1 | 0 | 7 |
| coverage-RegionNew.md | G0 region input | 64 | 59 | 5 | 0 | 0 | 4 |
| coverage-LivingAreas.md | G0-2 living areas | 78 | 67 | 9 | 1 | 1 | 3 |
| coverage-Glossary.md | Glossary | 82 | 80 | 1 | 1 | 0 | 6 |
| **Total** | | **1,996** | **1,713** | **163** | **119** | **1** | **157** |

**Updated 2026-10-16 after the mockup fixes.** Before the fixes, 225 items were missing; now 1 is (LivingAreas #73 "공급 기준치", an i18n key the current code does not use). The "Fixes" column counts places changed in the mockup. The fix logs are in `../fixes/`, and every fix is marked on its board with a yellow dashed outline and a "고침 XX-n" tag. The sections below describe the 225 items as they stood **before** the fixes and how each one was handled.

## What the 225 missing items are

1. **Behaviour that a picture cannot show (most of them).** Examples: URL query persistence, debounce, disabling a button while saving, clearing inputs after save, character limits, Esc to close, scroll-to anchors, polling intervals, the default sort fallback.
   - Implementation keeps the current behaviour as it is.
   - Existing tests already guard most of these.
2. **Tooltips and chart details.** Examples: chart tooltips, axis ticks, legends, the year-adjusted median dot, C09/C06 table columns. These are hard to draw in a static mockup. Implementation keeps the current charts' details.
3. **Visible items the mockup omitted.** Examples:
   - G6: regulation items (resale, residency, loans, tax, land-transaction permits, other)
   - G2 mobile cards: tie, scope and rejudge badges
   - G3: the total-score "?" button and the short held-price note
   - G1: label badges and provenance underlines on several values
   - Dimming of closed or disabled rows
   - Light/dark theme and the mobile settings collapse
   These are added to the screen at implementation time.

## Must fix at implementation (mockup wording or design conflicts with the rules or the meaning)

- **Wording that changed the meaning.** Restore the meaning of the current code at implementation.
  - The "benchmark missing" notice: it means *the total score is not computed*. It does not mean "only this criterion is dropped".
  - The degraded banner: "unjudged mode".
  - The token-pinned banner: another tab changed the token.
  - The recompute banner: "may differ from the value at publish time".
  - The p10 copy: keep "보장 아님" (not guaranteed). The target point is not always "after move-in"; it can be as-of date + 3 or + 5 years.
  - The glossary "current purchase price": "only *confirmed* discounts".
  - The mobile bottom nav: keep the current three items (홈 · 단지 리스트 · 용어).
  - Label meanings: use one source string (Shell and Glossary currently differ).
- **Values the screen would have to compute or write itself.** Rules 3 and 5 forbid this. Take each value from the server, or drop it.
  - The "applied ÷ supply" formula and the overall-median line.
  - The plain-language status summary sentence.
  - The Market summary cards and the Ops "today" tiles: counting is allowed (D25-3 MetaValue). Labels and sources stay.
  - "맞음 19 · 사람 검토 5" in the contradicted-claims summary: the current API does not return this.
  - Judge-scope reasons: show the server string unchanged.
- **Needs a contract change.** These List chips have no matching filter:
  - "실거주 의무 없음" (no residency obligation): there is no filter key.
  - "되팔기 제한 곧 끝남" (resale restriction ending soon): there is no direct key.
  - Either drop them or request a WP5 contract change.
- **Keep the anchors.** Keep `#intake-queue`, `#human-check`, and the G3 tab hashes (`#price` and the others). Other screens link to them.
- **Default sort.** The List board's "접수 가능 먼저" (intake-open first) conflicts with the current default `-total`. Decide which one at implementation.
