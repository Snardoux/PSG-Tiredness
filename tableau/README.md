# Tableau workbook

`psg_fatigue.twbx` is a **packaged workbook with extracts**, built manually in Tableau Desktop by
Sacha Nardoux from the pipeline outputs. It opens on its own (the data is inside the package); the
full specification — views, calculated fields, filters, default state — is in
[`docs/TABLEAU.md`](../docs/TABLEAU.md).

## Data sources

All four are CSV files produced by `uv run psg-fatigue all`, at these paths relative to the
repository root. No join is done in Tableau: integration and confidence intervals are computed in
Python, so the workbook shows the same numbers as the reports.

| Tableau data source | File | One row = |
|---|---|---|
| `L1 analytical` | `data/processed/psg_l1_analytical.csv` | one PSG Ligue 1 match (111 rows) |
| `All matches` | `data/processed/psg_matches_all.csv` | one PSG official match, all competitions (188 rows) |
| `Bucket summary` | `reports/eda/summary_by_bucket.csv` | one load definition × bucket × KPI, with n and 90 % CI |
| `Season start` | `reports/eda/season_start.csv` | one season × match of the first-8 window |

File format: comma-separated, UTF-8, dates as `YYYY-MM-DD`, booleans as `True` / `False`.

## Open
1. Open `tableau/psg_fatigue.twbx` in Tableau Desktop (or Tableau Reader).
2. Check the default state before reading numbers: all seasons, both venues, parameter
   `Rest threshold` = **3** (the pipeline definition of high load; 4 = sensitivity).

## Reconnect (after cloning the repository elsewhere)
1. *Data → `<data source>` → Edit Data Source…*
2. If Tableau reports a missing file, choose *Edit Connection* and select the CSV listed above in
   your clone of the repository (paths are relative to the repository root).
3. Repeat for the four data sources.

## Refresh (after re-running the pipeline)
1. From the repository root: `uv run psg-fatigue all` (offline, rebuilds every CSV above from the
   frozen raw snapshot).
2. In Tableau: *Data → Refresh All Extracts*.
3. Check that the numbers in the views match `reports/eda/EDA_REPORT.md` (for example 28 high-load
   matches and a high-load mean residual of +0.084 with the snapshot `2026-11-02`).
4. Save the package again: *File → Export Packaged Workbook…* → `tableau/psg_fatigue.twbx`.
