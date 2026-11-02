# Quality note (max. one page)

> Fill every `<fill>` with numbers from `reports/quality/`. Keep the main note to one printed page; the detailed log goes in the appendix.

## 1. Coverage
- Snapshot `<fill>`; Wikipedia revids recorded; 4 football-data files (sha256 in manifest).
- Ligue 1 file rows: 2023–24 `<fill>/306`, 2024–25 `<fill>/306`, 2025–26 `<fill>/306`, 2026–27 `<fill>` (partial, last date `<fill>`).
- PSG official matches parsed: `<fill>` (by competition in `wikipedia_counts.csv`); reconciliation with "Overall record": `<fill: all match / list gaps>`.
- Analysis population: `<fill>` PSG Ligue 1 matches, of which `<fill>` high-load (≤ 3 rest days).

## 2. Integration checks
- Left (football-data PSG) `<fill>` rows · Right (Wikipedia Ligue 1) `<fill>` rows · matched `<fill>` · **match rate `<fill>` %**.
- Join method: exact date `<fill>`, ±1 day `<fill>`; unmatched `<fill>` (listed in `integration_report.md`).
- Row multiplication check: rows after join = left rows ✔/✘. Score/venue agreement on matched rows: `<fill>` mismatches.

## 3. Key decisions and their impact
| Decision | Impact |
|---|---|
| Rest days on calendar dates, not matchday numbers (postponed matches 2025–26 MD26, MD29) | `<fill>` rows would otherwise get wrong rest values |
| Reference odds = market-average closing; fallback order recorded | `<fill>` rows use a fallback |
| Club World Cup 2025 dates kept as published (US local) | ±1 day uncertainty on `<fill>` rest values / summer break 2025 |
| Friendlies excluded from load | `<fill>` matches excluded |
| 2022–23 page used only as context for the first rest value | 1 value defined instead of missing |

## 4. What cannot be trusted
- **Small samples**: `<fill>` high-load matches → wide confidence intervals; differences of a few points of win rate are not distinguishable from noise.
- **Load ≠ fatigue**: rest days measure the club calendar, not player minutes, rotation, travel or international duty (international breaks, 2026 World Cup) — none observed.
- **Injuries are not observed**; closing odds already include publicly known absences, so the residual measures only what the market missed.
- **Wikipedia is user-edited**: Ligue 1 rows are cross-checked against football-data; other competitions are not independently verified.
- **Odds** are an international aggregate with publisher-defined closing time; not the odds of a French operator.
- **2026–27 is partial**; PSG's dominance compresses win probabilities near the ceiling (high implied probabilities, little variance).

---

## Appendix — Decision log
| ID | Issue | Evidence | Decision | Rows affected | Alternative considered |
|---|---|---|---|---|---|
| D01 | `<fill>` | `<fill>` | `<fill>` | `<fill>` | `<fill>` |
