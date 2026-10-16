# R11 Wave 2 — page agent brief (shared)

Base: main `4bd5e87` (R11-BE contract .22, R11-CHARTS, and R11-SHELL are all merged).

## Read first
- `AGENTS.md`
- `docs/design/DECISIONS.md` (D30 entirely; also D7, D25, D28, D29)
- `docs/design/wp/R11_PLAN.md` (definition of done, the ko.json namespace rule)
- `frontend/src/components/README.md` (the shared primitives from R11-SHELL: Card, StatusPill, SectionHeader, FactList/FactRow, BigNumber, KeepNote, Banner, Skeleton, StateCard, jobNameText/jobStepText, LABEL_HELP, plus the Badge tones)
- `frontend/src/charts/README.md` (new chart props: pass `asof` to every chart, and `source` to override the footer; C06 takes `orientation="horizontal"`; C08 takes `asof` for the as-of line; C02 `height` is now a minimum)
- `contracts/CHANGELOG.md`, entry `2026-10-09.22`:
  - `market.unsold_latest`
  - `gap.comps_median` and `gap.comps_median_unadjusted`
  - the winning-points range, which is already in `competition_summary.winning_score_min/max`
  - the complex count, which is the list `total`
  - claim status counts, which you get by counting the claims list (no status filter)
- Your boards: `docs/design/ui-benchmark/50-mockup/boards/<Board>.dc.html`. The yellow dashed outlines and "고침" tags show what was fixed. **Do not render those marks in the product.**
- Your checklists: `docs/design/ui-benchmark/50-mockup/coverage/coverage-<Board>.md` and `fixes/fixes-<Board>.md`.

## Rules
- The screens must match the boards: layout, hierarchy, question-style headings, one big number per card, plain words, status pills, and the "구현할 때 지금 동작 그대로 유지" behaviours.
- **No feature may be lost.** Every coverage row must work.
- **The UI computes nothing new and writes no judgement sentences** (rules 3 and 5). Show server values and server strings as they arrive. Counting rows is allowed (D25-3), and so is mapping a value to display text in ko.json.
- **FactCell formats every number.** Labels and the provenance underline must never vanish. An empty value shows "확인 불가(사유)".
- **Strings live only in ko.json.** Put them under your own namespace (`page.G1.*` and so on). Do not edit shared keys (`app.*`, `header.*`, `label.*`, `glossary.*`, `provenance.*`, `job.*`, `badge.*`, `chart.*`). If you need one changed, put the request in your report.
- **Don't change routes, URL query keys, or anchors** (`#intake-queue`, `#human-check`, the G3 tab hashes).
- **Mobile read-only (D7):** the `data-write` hiding stays.
- **Keep the gates green:** the entry-chunk guard (450kB), T16 perf, lighthouse (mobile ≥ the existing threshold; currently about 85), and the jitter test.
- **No new libraries.**
- **Ownership:** edit only your pages (`frontend/src/pages/<yours>`), their tests, your ko namespace, your coverage and fixes files, and e2e specs that cover your pages (`frontend/e2e/**`, root `e2e/flows/**`). If a shared component needs a change, don't edit it; write a request in your report, or wrap it locally.

## Definition of done
1. **Tests column.** Fill the `테스트` column in your coverage files. For every row, name the test that guards it (new or existing). Write new tests where needed.
2. **Existing tests.** Delete none. Update selectors and wording only where needed, and list every test you changed in your report.
3. **Frontend gates** (`cd frontend && npm ci`, then):
   - `npm run typecheck`
   - `npm run lint`
   - `npm test`
   - `npm run build`
   - `npm run e2e:pages`
   - `npm run e2e:api` (your screens)
   - `npx playwright test charts-gallery` (must stay green)
   - `npm run lighthouse`
4. **Repo-root gate:** `python scripts/tasks.py regress`.
5. **Self-check against the board.**
   - Start the app from your worktree with MSW (`npm run dev:msw`) or against the API fixtures.
   - Take a Playwright screenshot at 1440 and at 420 width. Save it outside the repo, in the session scratchpad.
   - Compare it with the board and fix the visible differences.
   - Stop every dev server you started before you finish. Leftover vite/esbuild processes lock the worktree.

## Process
- **Branch.** First run `git checkout -b wp/r11-<you>`. Use the commit prefix `[R11-<YOU>]` and end each commit with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push, and never commit to main.
- **Main moves.** Other page agents work in parallel, so main will advance. Before you finish, `git merge main` (or rebase) and re-run the gates.
- **Secrets.** Never print or commit secrets. The ops DB is read-only (port 5434). Don't touch the Postgres instances on 5432 or 5433.

## Final report (AGENTS.md format, in Korean)
- branch tip
- screens done
- ko keys added or changed
- tests added or changed
- coverage rows without a test
- visible differences you could not fix (with reason)
- requests (shared keys or components, API)
