# 50. New-screen mockups (Phase 4.5)

Created 2026-10-15. Inputs were `30-proposal.md`, `40-result.md`, and the user's feedback: "Pretty, readable, intuitive, like the sites we studied with REA. The current UI is too backend-oriented." The live canvas is the private claude.ai Design artifact https://claude.ai/artifact/Gg5vnE3FtQ2TVb81PyXkef. The canvas is the source of truth for any later edits.

`boards/` is a copy of the canvas files: `canvas.json` plus one `.dc.html` per screen. The numbers come from live Incheon data (snapshot 8, as-of 2026-10-14). Places where the live data had zero rows (contradicted claims, share links, reports) are shown as `[value]` placeholders instead of invented numbers.

| Board | Current screen |
|---|---|
| Coverage | Summary of where each current feature moved (789 features) |
| Main | G1 home |
| List, ListTable | G2 complex list (card view / table view, all filters, compare tray) |
| Detail, DetailTabs, Mobile | G3 complex detail (header, all 7 tabs, mobile) |
| Compare | G4 compare (sensitivity redesigned as "does the ranking change if a weight moves 10%p?") |
| Scenario | G5 scenario |
| Market | G6 regional market |
| Ops | G7 data and operations |
| Reports | G8 reports, plus the share-link landing |
| RegionNew, LivingAreas | G0 region input, G0-2 living areas |
| Shell | App shell: header selectors, banners, provenance drawer, token dialog, job progress, badges, empty/error states |
| Glossary | Glossary |

## Feature coverage

The rule is to change only layout, order, names and collapsing. No current feature is removed. The Coverage board lists features per screen and the drawings that were skipped (5 items whose behaviour stays):

- the dev-only chart gallery
- the discount column, which does not apply to the sample complex
- two empty tabs drawn the same way as other empty states
- one unused i18n key
- keyboard and scroll behaviour

The line-by-line coverage tables lived in the session scratchpad and were lost when that folder was cleaned on 2026-10-16. When the implementation round starts, rebuild them as the implementation checklist: re-extract features from `frontend/src/pages/*` and map each one to a board section. Each line gets a test.

## Not done yet

- Boards were not rendered in the real canvas runtime. Agents checked layout with a stub renderer only.
- No frontend code was changed. Implementation waits for the user's approval of the look.
