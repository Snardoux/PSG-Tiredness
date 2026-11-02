# Tableau workbook — specification and refresh instructions

Workbook: `tableau/psg_fatigue.twbx` (packaged workbook **with extracts**, opens without the repository).
Built in Tableau Desktop from the pipeline outputs — no indicator is recomputed differently in Tableau.

## Data sources (relative to the repository)
| Tableau data source | File | Grain |
|---|---|---|
| `L1 analytical` | `data/processed/psg_l1_analytical.csv` | one PSG Ligue 1 match |
| `All matches` | `data/processed/psg_matches_all.csv` | one PSG official match |
| `Bucket summary` | `reports/eda/summary_by_bucket.csv` | one bucket × KPI, with n and 90 % CI (computed in Python) |
| `Season start` | `reports/eda/season_start.csv` | one season × match index in the start window |

Confidence intervals come from the Python pipeline (`Bucket summary`), never recomputed in Tableau, so that the workbook and the pipeline outputs stay consistent.

## Views (one dashboard, four views)
1. **Calendar load** — timeline of official matches (x = date, colour = competition, shape = Ligue 1 vs other); tooltip: opponent, score, rest days. Filter: season.
2. **Performance under load** — bars of win rate, points per match and shots-on-target difference by `load_bucket`, with `n` labels.
3. **Did the market see it coming?** — dumbbell: mean implied win probability vs actual win rate by bucket; error bars for the mean residual (from `Bucket summary`).
4. **The post-Club World Cup start** — cumulative residual over the first 8 Ligue 1 matches per season; 2025–26 highlighted; summer break days in the label.

Global filters: season, venue (H/A), previous competition. Titles state the unit (%, points, probability 0–1, days).

## Calculated fields (affect results — keep this list in sync with the workbook)
| Name | Formula | Note |
|---|---|---|
| `Win rate` | `AVG([psg_win])` | share of wins |
| `Implied win prob.` | `AVG([p_win_implied])` | margin-free |
| `Mean residual` | `AVG([residual_win])` | actual − implied |
| `Points per match` | `AVG([psg_points])` | |
| `Load bucket (param)` | `IF ISNULL([rest_days]) THEN "Unknown" ELSEIF [rest_days] <= [Rest threshold] THEN "High" ELSE "Normal" END` | parameter `Rest threshold` (integer, default **3** = pipeline definition; 4 = sensitivity) |
| *(none for view 4)* | `cum_residual` is computed in Python (`season_start.csv`) | no table calculation, so the workbook matches the pipeline exactly |

Filters that change results: season filter, venue filter, and the `Rest threshold` parameter. Default state of the delivered workbook: all seasons, both venues, threshold 3.

## How to open, reconnect and refresh
1. Open `tableau/psg_fatigue.twbx` in Tableau Desktop (the packaged extract opens without the repository).
2. After re-running the pipeline (`uv run psg-fatigue all`), refresh: *Data → <data source> → Edit Data Source…* → point each connection to the CSV under `data/processed/` or `reports/eda/` of your clone → *Data → Refresh All Extracts*.
3. Re-save as packaged workbook (*File → Export Packaged Workbook…*) to update the `.twbx`.
