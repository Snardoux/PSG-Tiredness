# Quality note (max. one page)

Numbers from `reports/quality/` (quality and integration reports) and `data/processed/`, snapshot `2026-11-02`.
The detailed decision log is in the appendix.

## 1. Coverage
- Snapshot `2026-11-02`; 5 Wikipedia revids recorded; 4 football-data files (sha256 in `data/raw/2026-11-02/manifest.json`, re-verified at every `build`).
- Ligue 1 file rows: 2023–24 **306/306**, 2024–25 **306/306**, 2025–26 **306/306**, 2026–27 **80** (partial, last date 2026-11-01).
- PSG official matches parsed: **238 played** (188 in the Luis Enrique era + 50 on the 2022–23 context page) and 32 scheduled; reconciliation with each page's "Overall record": **30 of 30** season × competition rows match, 2025–26 = 56 (`wikipedia_counts.csv`).
- Analysis population: **111** PSG Ligue 1 matches (34 × 3 + 9), of which **28** high-load (≤ 3 rest days).

## 2. Integration checks
- Left (football-data PSG) **111** rows · Right (Wikipedia Ligue 1) **111** rows · matched **111** · **match rate 100 %**.
- Join method: exact date **111**, ±1 day **0**; unmatched **0** on either side (`integration_report.md`).
- Row multiplication check: rows after join = left rows ✔ (111 = 111, each source row used once). Score / venue agreement on matched rows: **0** mismatches (result and season also agree on all 111 rows).

## 3. Key decisions and their impact
| Decision | Impact |
|---|---|
| Rest days on calendar dates, not matchday numbers (6 postponed Ligue 1 matches, e.g. 2025–26 MD26, MD29) | **14** Ligue 1 rows are played out of matchday order and would otherwise get wrong rest values |
| Reference odds = market-average closing (`AvgC`); fallback PSC → B365C → Avg recorded | **0** rows use a fallback (`AvgC` complete for 111/111); Pinnacle closing odds incomplete (153/306 missing in 2025–26, absent in 2026–27) |
| Club World Cup 2025 dates kept as published (US local) | at most ±1 day on the rest values of the 7 Club World Cup matches and of the 2025 Super Cup, and on the 2025 summer break (31 days); **0** Ligue 1 analysis rows affected |
| Friendlies excluded from load | **9** matches excluded in the Luis Enrique era (16 including the 2022–23 page) |
| 2022–23 page used only as context for the first rest value | 1 value defined instead of missing (12 Aug 2023 v Lorient: 70 days) and the 2023 summer break (70 days) |
| Penalty shoot-outs scored on the regulation / extra-time score (draw), shoot-out stored separately | 6 matches, none in Ligue 1 |

## 4. What cannot be trusted
- **Small samples**: 28 high-load matches (8 under the "≥ 4 matches in 14 days" definition) → the 90 % CI of the high-load mean residual is 0.29 wide; a win-rate difference of 6.3 points (75.0 % vs 68.7 %) is not distinguishable from noise.
- **Load ≠ fatigue**: rest days measure the club calendar, not player minutes, rotation, travel or international duty (international breaks, 2026 World Cup) — none observed.
- **Injuries are not observed**; closing odds already include publicly known absences, so the residual measures only what the market missed.
- **No control for opponent strength or venue**: bucket comparisons are raw averages.
- **Wikipedia is user-edited**: Ligue 1 rows are cross-checked against football-data (0 disagreements); other competitions are only reconciled with the page's own totals.
- **Odds** are an international aggregate with publisher-defined closing time; not the odds of a French operator.
- **2026–27 is partial** (9 Ligue 1 matches); PSG's dominance compresses win probabilities near the ceiling (median implied probability 0.69, maximum 0.89), leaving little variance to explain.

---

## Appendix — Decision log
| ID | Issue | Evidence | Decision | Rows affected | Alternative considered |
|---|---|---|---|---|---|
| D01 | The "Overall record" table has no "Pld" column | `Fb overview2` lists W, D, L per competition | Played = W + D + L | 30 season × competition rows reconciled, 30 match | Count from "Results summary" (Ligue 1 only) |
| D02 | Season pages list friendlies | 16 boxes under "Pre-season and friendlies" (7 in 2022–23, 9 in the era) | Excluded from the calendar and from load | 16 | Count friendlies as load (rejected: not official matches, FRAMING) |
| D03 | Postponed Ligue 1 matches are played out of matchday order | 6 postponed (2023–24 MD29, MD32; 2024–25 MD29; 2025–26 MD5 by one day, MD26, MD29); 14 matches out of order (`quality_report.md` §7) | Rest days and 14-day counts on actual dates | 14 | Matchday order (wrong rest for those rows) |
| D04 | A first "rescheduled" rule also caught "originally scheduled for 15:00 EDT" (2025 Club World Cup semi-final, 10-minute kick-off delay) | Match listed among postponements in the first quality report | Flag only notes containing "postponed" | 1 row unflagged | Keep both phrases (false positive) |
| D05 | Penalty shoot-outs | 6 boxes with `penaltyscore`; Wikipedia's own `result` field is D for all of them | Score = regulation / extra time, result D, `decided_by = PEN`, shoot-out score stored | 6 (no Ligue 1 row) | Count the shoot-out winner as a win |
| D06 | Club World Cup 2025 dates are US local dates | 7 matches in the USA (15 Jun – 13 Jul 2025) | Dates kept as published | ≤ ±1 day on 8 rest values and on the 2025 summer break; 0 Ligue 1 rows | Convert kick-off times to Europe/Paris dates |
| D07 | SPEC rule "Trophée des Champions = neutral venue" vs actual venues | 2023 edition at Parc des Princes, 2026 edition at Lens | Keep `venue = N` (SPEC rule) | 2 (venue not used by features or analysis) | H / A from team position |
| D08 | Scheduled fixture with a date range and no teams | 2026–27 Coupe de France round of 64, "19–21 December 2026" | Kept as scheduled without a date; not used | 1 | Use the first day of the range |
| D09 | Club names differ between sources | 24 clubs; only Saint-Étienne / St Etienne and Paris Saint-Germain / Paris SG differ | Exact matching of normalised names, manual review of the rest, `build` fails on any unmapped name (`config/team_names.csv`) | 24-row table | Fuzzy matching (rejected: could pair Paris FC with PSG) |
| D10 | Pinnacle closing odds incomplete | `PSC*` missing for 153/306 rows in 2025–26, column absent in 2026–27 (`fd_columns.csv`) | Reference `AvgC`; fallback PSC → B365C → Avg recorded in `odds_source` | 0 rows use a fallback | Pinnacle closing as reference |
| D11 | Both sources give goals, venue and result | 111 matched rows, 0 disagreements | Analytical table takes them from football-data | 0 | Take them from Wikipedia |
| D12 | Current season is partial | 2026–27: 9 Ligue 1 matches played by 30 Oct 2026, present in both sources | Included (period = appointment → extraction) | 9 | Exclude 2026–27 |
