# R11 — Implement the new-screen mockups (multi-agent plan)

Written 2026-10-16 by the CEO. The user's request: "이제 목업대로 완벽히 구현해 보자. 멀티에이전트로 구현 계획 세우고 착수." The decisions behind this plan are D30 in `docs/design/DECISIONS.md`.

## Sources (in priority order)
1. `docs/design/DECISIONS.md` (D30 and every earlier decision)
2. The common rules in `AGENTS.md` (judging belongs only to the judge; values carry source and label; no hardcoded region names; strings live only in ko.json)
3. The mockup boards: `docs/design/ui-benchmark/50-mockup/boards/*.dc.html` (live canvas: https://claude.ai/artifact/Gg5vnE3FtQ2TVb81PyXkef)
4. The coverage tables, used as the implementation checklist: `50-mockup/coverage/coverage-*.md` (1,996 rows)
5. The fix logs: `50-mockup/fixes/fixes-*.md`

The yellow dashed outlines and "고침" tags exist only in the mockups. **Do not put them in the product.**

## Waves and agents (8 implementation agents + CEO integration)

Every agent works in its own git worktree on a `wp/r11-*` branch. Only the CEO merges to main, then pushes, then **removes the worktree right away**.

### Wave 1 — foundation (3 agents in parallel)
| Agent | Branch | Owner | Scope |
|---|---|---|---|
| R11-BE | wp/r11-be | WP4·WP5 (+ contract .22 as CEO delegate) | D30-5/6: check whether the 4 "API 필요" items are already in the API. Add only what is truly missing (contract `2026-10-09.22`). Server wording fixes: `P_mid` → "중간 가격"; Korean labels for class names in judge-scope reasons. |
| R11-SHELL | wp/r11-shell | WP6b (layout·components·app·index.css·tailwind) | Design tokens (light and dark), IBM Plex Sans KR (self-hosted), header (app name, menus, sub-bar with region / as-of date / scenario selectors), mobile bottom nav, banners, token dialog, toasts, provenance drawer, LabelBadge / IntakeBadge / other badges, Term popover, QueryState / empty states, ChartFrame shell. Shared primitives the pages will use: Card, StatPill, SectionHeader (question-style heading), FactRow, KeepNote. Glossary page. Board: Shell plus Glossary. |
| R11-CHARTS | wp/r11-charts | WP6b (frontend/src/charts) | Restyle C01–C10 to the boards: plain-language axes, legend placement (fixes the C04 overlap), tooltips, tick marks, C10 redesign ("does the ranking change if a weight moves 10%p?"), the C06 stacked bar. Re-take the win32 chart snapshots. |

R11-SHELL and R11-CHARTS do not overlap: charts own only `src/charts`. ChartFrame belongs to R11-CHARTS; it renders the frame tokens that R11-SHELL defines.

### Wave 2 — pages (5 agents in parallel, starting after R11-SHELL is merged)
| Agent | Branch | Screens | Boards |
|---|---|---|---|
| R11-HOME | wp/r11-home | G1 + G2 | Main, List, ListTable |
| R11-DETAIL | wp/r11-detail | G3 (desktop + mobile) | Detail, DetailTabs, Mobile |
| R11-ANALYZE | wp/r11-analyze | G4 + G5 | Compare, Scenario |
| R11-MARKETOPS | wp/r11-marketops | G6 + G7 | Market, Ops |
| R11-SETUP | wp/r11-setup | G8 + share + G0 + G0-2 | Reports, RegionNew, LivingAreas |

If R11-CHARTS or R11-BE is not merged yet, a page agent rebases once they are.

**ko.json conflict rule:** each agent adds and changes keys only under its own namespace (`page.G1.*` and so on). Shared keys (`app.*`, `label.*`, `glossary.*`, `header.*`) belong to R11-SHELL only. If a page needs a shared key, it writes a request in its report. The CEO resolves merge conflicts.

### Wave 3 — CEO integration
- Merge in this order: BE → SHELL → CHARTS → pages. Resolve conflicts.
- Run `python scripts/tasks.py regress` (backend + e2e flows), frontend `npm ci / typecheck / lint / test / build / audit / e2e / e2e:api / lighthouse`, T16 perf, and the entry-chunk guard (450kB).
- Linux chart snapshots: take the CI artifact actuals as the baseline (D25-9).
- Push to origin main and confirm CI passes. Remove every worktree and merged branch.
- Restart the GUI dev server (package-lock changed, so the launcher reinstalls).
- Ops smoke check: look at the live Incheon screens in the observation Chrome with REA (open one tab → capture → close).

## Definition of done (for every page agent)
1. **The coverage table is the checklist.** Add a `테스트` column to your `coverage-<Board>.md`. For every row, write the test that guards it: a new test name or an existing one. Rows that cannot be drawn (behaviours) get the existing behaviour test name. If none exists, write a new test.
2. **No existing tests deleted.** If a name or structure changed, update the selector but keep the meaning of the test (acceptance, provenancePreserved, rejudgeNeeded, judgeScope, e2e flows). Report every changed test name.
3. **Rule tests pass:** no Hangul literals (ko.json only), no empty labels, banned words absent (a new test: no banned word in ko.json values except the existing "보장 아님" and quoted titles), provenance underline preserved, `data-write` hiding on mobile.
4. **Gates pass:** `npm run typecheck && npm run lint && npm test && npm run build`; e2e and e2e:api for your pages; lighthouse (mobile ≥ the existing threshold); T16 perf; entry-chunk guard.
5. **Report** in the AGENTS.md format. Include changed or added ko keys, changed test names, coverage rows left uncovered (with reasons), and requests (new API fields or shared keys).

## Gates the CEO checks
- After Wave 1: SHELL + CHARTS + BE are merged, CI is green, and screenshots of the shell, glossary and charts match the boards.
- After Wave 2: every page is merged, the coverage `테스트` column is filled, CI is green.
- Final: REA live-observation screenshots and a 10-line report.
