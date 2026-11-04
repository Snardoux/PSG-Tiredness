# Tableau workbook — specification and refresh instructions

Workbook: `tableau/psg_fatigue.twbx` — packaged workbook with **live text connections to CSV files
embedded in the package** (no `.hyper` extract), so it opens without the repository.
Built in Tableau Desktop from the pipeline outputs — no indicator is recomputed differently in Tableau.
The embedded CSV files are byte-identical to the repository files of snapshot `2026-11-02`.

## Data sources (relative to the repository)
| Tableau data source | File | Grain |
|---|---|---|
| `L1 analytical` | `data/processed/psg_l1_analytical.csv` | one PSG Ligue 1 match |
| `All matches` | `data/processed/psg_matches_all.csv` | one PSG official match |
| `Bucket summary` | `reports/eda/summary_by_bucket.csv` | one definition × bucket × KPI, with n and 90 % CI (computed in Python) |
| `Season start` | `reports/eda/season_start.csv` | one season × match index in the start window |

Confidence intervals come from the Python pipeline (`Bucket summary`), never recomputed in Tableau, so that the workbook and the pipeline outputs stay consistent.

## Dashboards and views
**Dashboard 1 · Load and results**
1. **Calendar load** (`All matches`) — official played matches by season (rows) and competition, x = match date shifted onto a common season axis (`Season Date`), colour = competition. Filter: season (all four selected by default) and `played = true`.
2. **Performance under load** (`L1 analytical`) — win rate, points per match and shots-on-target difference by `Load bucket (param)`, with the number of matches.

**Dashboard 2 · Did the market see it coming?**
3. **« Market vs reality »** (`L1 analytical`) — dumbbell: mean implied win probability vs actual win rate by `Load bucket (param)`.
4. **Did the market see it coming?** (`Bucket summary`) — mean residual by bucket with its 90 % CI (`ci_low`, `mean`, `ci_high`), KPI filtered to `mean_residual`, definition chosen by the parameter (`Definition (param)`).
5. **Season start** (`Season start`) — cumulative residual over the first 8 Ligue 1 matches, one line per season (colour = season), label = season and summer break days.

A sixth worksheet, **Check** (not on a dashboard), shows the number of matches, win rate, implied win probability and mean residual by bucket, to compare with `reports/eda/EDA_REPORT.md` (28 high-load matches, mean residual +0.084 at threshold 3).

Both dashboards show the `Rest threshold` parameter control. Titles state the unit (%, points, probability 0–1, days).

## Calculated fields (affect results — keep this list in sync with the workbook)
| Name | Data source | Formula | Note |
|---|---|---|---|
| `Win rate` | L1 analytical | `AVG([psg_win])` | share of wins |
| `Implied win prob.` | L1 analytical | `AVG([p_win_implied])` | margin-free |
| `Mean residual` | L1 analytical | `AVG([residual_win])` | actual − implied |
| `Points per match` | L1 analytical | `AVG([psg_points])` | |
| `SOT difference` | L1 analytical | `AVG([sot_diff])` | shots on target, PSG − opponent |
| `Matches (n)` | L1 analytical | `COUNTD([match_id])` | |
| `Load bucket (param)` | L1 analytical | `IF ISNULL([rest_days]) THEN "Unknown" ELSEIF [rest_days] <= [Rest threshold] THEN "High (≤" + STR([Rest threshold]) + " days)" ELSE "Normal (≥" + STR([Rest threshold] + 1) + " days)" END` | parameter `Rest threshold` (integer list: **3** = pipeline definition, default; 4 = sensitivity) |
| `Definition (param)` | Bucket summary | `[definition] = (IF [Rest threshold] = 4 THEN "alt4" ELSE "primary" END)` | keeps the Python rows of the definition matching the parameter |
| `Load level` | Bucket summary | `IF STARTSWITH([bucket], "High") THEN "High" ELSE "Normal" END` | short label |
| `CI width` | Bucket summary | `[ci_high] - [ci_low]` | |
| `Season Date` | All matches | `DATEADD('year', 1999 - INT(LEFT([season], 4)), [match_date])` | display only: aligns every season on one date axis |
| *(none for view 5)* | Season start | `cum_residual` is computed in Python (`season_start.csv`) | no table calculation, so the workbook matches the pipeline exactly |

Filters and controls that change results: the `Rest threshold` parameter (both dashboards) and the season filter (calendar view only). Default state of the delivered workbook: all seasons, threshold 3.

## How to open, reconnect and refresh
1. Open `tableau/psg_fatigue.twbx` in Tableau Desktop or Tableau Reader (the embedded CSV files open without the repository).
2. After re-running the pipeline (`uv run psg-fatigue all`): *Data → <data source> → Edit Data Source…* → *Edit Connection* → select the CSV under `data/processed/` or `reports/eda/` of your clone (repeat for the four data sources) → *Data → Refresh*.
3. Re-save as packaged workbook (*File → Export Packaged Workbook…*) to update the `.twbx`.
