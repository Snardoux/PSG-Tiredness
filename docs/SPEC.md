# Technical specification

This document is the contract for the pipeline. Read `FRAMING.md` first.

---

## 1. Repository layout

```
psg-fatigue/
├── CLAUDE.md
├── README.md
├── pyproject.toml            # uv project, ruff/mypy/pytest config, [project.scripts]
├── uv.lock
├── .python-version           # 3.12
├── .gitignore
├── config/
│   └── team_names.csv        # name mapping Wikipedia <-> football-data.co.uk (committed, reviewed)
├── data/
│   ├── raw/<snapshot_id>/    # immutable snapshot + manifest.json (committed)
│   ├── interim/              # parsed, typed tables (gitignored, rebuilt by `build`)
│   └── processed/            # analytical outputs used by Tableau (committed)
├── reports/
│   ├── quality/              # generated quality + integration reports (committed)
│   └── eda/                  # generated figures (.png) and tables (.csv) + EDA_REPORT.md (committed)
├── src/psg_fatigue/
│   ├── __init__.py
│   ├── cli.py                # argparse entry point: collect | build | eda | all
│   ├── config.py             # constants: seasons, page titles, URLs, snapshot id, thresholds, paths
│   ├── collect/
│   │   ├── wikipedia.py      # MediaWiki API fetch + manifest entries
│   │   └── footballdata.py   # F1.csv download + manifest entries
│   ├── parse/
│   │   ├── wiki_matches.py   # wikitext -> one row per official PSG match
│   │   └── fd_matches.py     # CSV -> typed Ligue 1 matches
│   ├── quality.py            # profiling + checks -> reports/quality/
│   ├── features.py           # calendar load features (rest days, 14-day count, summer break...)
│   ├── odds.py               # margin removal, PSG perspective, ROI
│   ├── integrate.py          # name mapping + join + integration report
│   ├── analysis.py           # KPIs by bucket, bootstrap CIs, decision rule
│   └── eda.py                # figures + tables + EDA_REPORT.md
├── tests/
│   ├── fixtures/             # small wikitext snippets and CSV extracts (real excerpts)
│   └── test_*.py
├── tableau/
│   ├── psg_fatigue.twbx      # built manually in Tableau Desktop (packaged, with extract)
│   └── README.md             # how to open / reconnect / refresh
└── docs/                     # FRAMING, SPEC, SOURCES, QUALITY_NOTE, TABLEAU, FINDINGS
```

`config.py` resolves paths relative to the repository root (`Path.cwd()` with a check that `pyproject.toml` exists; fail with a clear message otherwise). README states that commands run from the repository root.

## 2. Commands and data flow

| Command | Network | Reads | Writes |
|---|---|---|---|
| `collect` | yes | Wikipedia API, football-data.co.uk | `data/raw/<YYYY-MM-DD>/…` + `manifest.json`. Refuses to overwrite an existing snapshot dir. Prints the new snapshot id. |
| `build` | **no** | `data/raw/<snapshot_id>/` (default `config.SNAPSHOT_ID`, overridable with `--snapshot`) | `data/interim/*.parquet` (or csv), `data/processed/*.csv`, `reports/quality/*` |
| `eda` | **no** | `data/processed/` | `reports/eda/*` |
| `all` | **no** | — | `build` then `eda` |

After the first successful collection, set `config.SNAPSHOT_ID` to that snapshot id and commit it (this freezes the analysed version).

## 3. Source 1 — Wikipedia season pages (collected via API)

**Pages** (English Wikipedia, titles use an en dash `–`):
`2022–23 Paris Saint-Germain FC season` (context only), `2023–24 …`, `2024–25 …`, `2025–26 …`, `2026–27 Paris Saint-Germain FC season`.

**Access**: MediaWiki Action API
`GET https://en.wikipedia.org/w/api.php?action=parse&page=<title>&prop=wikitext|revid&format=json&formatversion=2&redirects=1`
- Send a descriptive `User-Agent` (Wikimedia policy), e.g. `psg-fatigue-student-project/0.1 (Albert School M1; contact: <set in config>)`.
- Save the raw JSON response per page (`wiki_<season>.json`) and record `revid` in the manifest. The revid makes the snapshot re-fetchable exactly (`oldid=<revid>`).
- No pagination is needed for `action=parse` (one page per call): state this explicitly in SOURCES.md.
- 1 request per second max; retry with backoff on 5xx/429; fail loudly on 404/missing page.

**Parsing** (`mwparserfromhell`):
1. First, inspect the real wikitext of all pages and copy representative snippets to `tests/fixtures/` (a Ligue 1 match, a penalty shoot-out final, a postponed match, a Coupe de France match, an unplayed future fixture).
2. Walk sections; the competition of a match is the nearest heading among the competition headings (map: `Ligue 1`, `Coupe de France`, `Trophée des Champions`, `UEFA Champions League`, `UEFA Super Cup`, `FIFA Club World Cup`, `FIFA Intercontinental Cup`). Matches under `Friendlies` / `Pre-season` are **excluded**. Unknown headings → error listing them.
3. Match blocks are `{{Football box collapsible …}}` templates (normalise template name: lowercase, strip, accept close variants; log any other match-like template found).
4. Extract: `date` (handle `{{Start date|Y|M|D|…}}` and plain text), `round`, `team1`, `team2`, `score`, `penaltyscore` / penalties, `aet`, `stadium`, `location`, `attendance`, `referee`. Strip wiki markup with `strip_code()`; normalise dashes (`–`, `—`, `-`).
5. Score parsing: `"2–1"` → (2, 1); `"2–2 (4–3 p)"` or `penaltyscore=4–3` → regulation (2, 2) + shoot-out flag; `"v"`, `"P–P"`, empty → **unplayed** (kept in calendar table with `played=False`, never in results).
6. PSG side: `team1` is the home/first-named team. Venue = `H` / `A` from PSG's position, `N` for neutral-venue competitions or finals (Trophée des Champions, Super Cup, Intercontinental Cup, Club World Cup, Champions League final, Coupe de France final).
7. Known edge cases to cover: postponed league matches played out of matchday order (2025–26: matchday 26 vs Nantes played 22 Apr 2026; matchday 29 vs Lens played 13 May 2026); Marseille–PSG 2025–26 moved by one day; Paris FC (in Ligue 1 since 2025–26) vs PSG in both Ligue 1 and Coupe de France; Club World Cup 2025 matches (USA local dates).

**Validation**: per season and competition, the count of played matches must equal the page's "Overall record" table (`Pld`). Known reference for 2025–26: Ligue 1 34, Coupe de France 2, Trophée des Champions 1, Champions League 17, Super Cup 1, Intercontinental Cup 1 → 56. For complete seasons, Ligue 1 must be 34. Write the comparison to `reports/quality/wikipedia_counts.csv`.

## 4. Source 2 — football-data.co.uk Ligue 1 files (downloaded file, automated import)

**Files**: `https://www.football-data.co.uk/mmz4281/{code}/F1.csv` with codes `2324`, `2425`, `2526`, `2627`.
- `collect` downloads them with a `User-Agent`, saves bytes unchanged (`fd_F1_<code>.csv`), records URL/status/sha256 in the manifest.
- If the site blocks automated download, the user downloads the same files manually into the snapshot folder; `collect --register-manual` then hashes them into the manifest. The **import and all transformations stay automated** (this is allowed by the brief).

**Reading** (`parse/fd_matches.py`):
- Encoding: try `utf-8-sig`, then `latin-1`. Drop fully empty rows/columns (trailing commas).
- `Date`: parse `%d/%m/%Y`, fallback `%d/%m/%y`. `Time` kept as text (UK time, informational only).
- Assert `Div == "F1"` for all rows; add `season` (`2023-24` …).
- Columns used: `Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HS, AS, HST, AST`, odds `AvgCH, AvgCD, AvgCA`, `B365CH, B365CD, B365CA`, `PSCH, PSCD, PSCA`, `AvgH, AvgD, AvgA`. Inspect the header first; record which columns exist per season in the quality report; never assume.
- Expected: **306 rows** per complete season (18 teams). PSG label must be verified from the data (expected `Paris SG`); assert it is distinct from `Paris FC`.

**Reference odds per row** (record `odds_source`): `AvgC*` → else `PSC*` → else `B365C*` → else `Avg*` (pre-closing, flagged). Rows with no complete 1X2 triple are excluded from odds KPIs and counted in the report.

## 5. Grain of every table

| Table | One row = | Expected rows |
|---|---|---|
| raw wiki JSON | one season page | 5 |
| raw `F1.csv` | one Ligue 1 match (all teams) | 306 × 3 + partial 2026/27 |
| `interim/psg_calendar` | one PSG official fixture (played or scheduled), all competitions | ≈ 230 played + scheduled |
| `interim/fd_l1` | one Ligue 1 match (all teams), typed | as raw |
| `interim/fd_psg` | one PSG Ligue 1 match, PSG perspective, with odds | 34 × 3 + partial |
| `processed/psg_matches_all.csv` | one PSG official **played** match, all competitions, with load features | ≈ 200+ (LE era) |
| `processed/psg_l1_analytical.csv` | **one PSG Ligue 1 match, PSG perspective** — the analytical output | ≈ 110 |
| `processed/summary_by_bucket.csv` | one load bucket × KPI (with n and 90 % CI) | small |

## 6. Team name mapping

`config/team_names.csv` with columns `wikipedia_name, footballdata_name, canonical`.
- Generate candidates automatically (normalise: lowercase, strip accents, remove `FC`, `AS`, `OGC`, `RC`, `Stade`, `Olympique`, punctuation), then review manually and commit.
- `build` fails with the list of unmapped names if any appear. Special attention: `Paris FC` vs `Paris SG`, `Saint-Étienne` vs `St Etienne`, `Le Havre`, `Clermont`, `Lens`, `Lyon`, `Marseille`, `Monaco`, `Brest`.

## 7. Integration (join) and checks

- Left: `fd_psg` (PSG Ligue 1 matches with odds). Right: Ligue 1 rows of `processed/psg_matches_all` (with load features).
- Key: `(match_date, opponent_canonical)`; expected relationship **1:1**. Use `pd.merge(..., validate="one_to_one", indicator=True)`.
- Unmatched rows: retry with ±1 day tolerance and log each one (`join_method = exact | plus_minus_1d`). Anything still unmatched is listed in the report and excluded.
- Cross-check on matched rows: goals and venue must agree between sources (`score_check_ok`). Report mismatches.
- Write `reports/quality/integration_report.json` and `.md`: rows in left/right, matched, left-only, right-only, match rate, duplicates check (row count after join == left count), score mismatches, rows dropped and why.

## 8. Features (calendar load) — `features.py`

Computed on **played official matches sorted by date** (plus scheduled fixtures for "next match" features):
- `rest_days`: days since previous official match (any competition). Previous match may come from 2022/23 context page.
- `prev_competition`, `prev_venue`.
- `matches_last_14d`: official matches in the 14 days before the match (excluded itself).
- `next_rest_days`, `next_competition`, `ucl_within_4d_after` (Champions League match ≤ 4 days later — rotation risk).
- `high_load` = `rest_days <= 3`; `high_load_alt4` = `rest_days <= 4`; `high_load_14d` = `matches_last_14d >= 4`.
- `load_bucket` label: `"High (≤3 days)"`, `"Normal (≥4 days)"`, `"Unknown"`.
- `summer_break_days` (season-level, attached to every match of the season).
- `season_start_window` (first 8 PSG Ligue 1 matches of the season by date) and `post_cwc_start` (= season 2025-26 and season_start_window).
- Optional sensitivity: `rest_days_excl_cdf_early` ignoring Coupe de France rounds before the round of 16.

## 9. KPIs and statistics — `odds.py`, `analysis.py`

Per match (PSG perspective): `overround = Σ 1/o − 1`; `p_win_implied`, `p_draw_implied`, `p_loss_implied`; `psg_win` (0/1), `psg_points`; `residual_win = psg_win − p_win_implied`; `brier_win = (p_win_implied − psg_win)²`; `roi_flat = odds_win − 1 if win else −1`; shots-on-target difference.

By bucket (high vs normal, and sensitivity definitions): n, win rate, points per match, mean implied win probability, mean residual, Brier score, ROI, SOT difference. **90 % bootstrap CI** (10 000 resamples, seed 42, percentile) for mean residual per bucket and for the difference high − normal. Season-start comparison: mean residual of `season_start_window` per season, 2025-26 highlighted.

Decision rule output (`reports/eda/decision.json`): high-load mean residual, CI, rule satisfied yes/no, and the sentence for the conclusion.

## 10. Quality investigation — `quality.py` (before changing data)

Write `reports/quality/profile_*.csv` and `quality_report.md` covering, for the variables used:
- dtypes; missing values per column (odds especially) per season;
- duplicates on business keys: F1 `(Date, HomeTeam, AwayTeam)`; calendar `(date, competition, opponent)`;
- near duplicates: same opponent and competition within ±3 days (postponed placeholder + played match);
- unusual values: odds ≤ 1.01 or > 50, overround outside [0, 0.15], rest days < 2 or > 30 outside season starts, goals > 9;
- count checks of §3 and §4.

Every data-changing decision goes into `docs/QUALITY_NOTE.md` appendix "Decision log" with: ID, issue, evidence (counts), decision, rows affected, alternative considered.

## 11. Tests (pytest, no network) — at least these

1. `test_margin_removal` — odds (1.25, 6.0, 11.0): probabilities sum to 1, order preserved, overround correct; invalid odds (≤1, NaN) raise.
2. `test_psg_perspective` — PSG away with `FTR="A"` → win; `p_win_implied` uses away odds; points 3/1/0.
3. `test_rest_days_postponed` — a postponed league match played after later matchdays: rest days follow dates, not matchdays; first match uses the context match; equal dates raise.
4. `test_load_buckets` — rest 3 → High, 4 → Normal, NaN → Unknown; 14-day count boundaries.
5. `test_score_parsing` — `"2–1"`, `"2–2 (4–3 p)"`, `"v"`, `"P–P"`, hyphen/en dash variants.
6. `test_join_preserves_grain` — fixture with a Paris FC match and PSG matches: exactly one row per PSG league match, Paris FC never mapped to PSG, unmatched rows reported, row count unchanged.
7. `test_roi_and_residual` — win at 1.30 → +0.30, loss → −1; residual sign.
8. `test_wiki_competition_mapping` — friendlies excluded, unknown heading raises.

## 12. Data dictionary — `processed/psg_l1_analytical.csv`

| Column | Type | Description |
|---|---|---|
| match_id | str | `<YYYY-MM-DD>_<opponent_canonical>` |
| season | str | e.g. `2025-26` |
| match_date | date | Europe/Paris calendar date |
| matchday | int | Ligue 1 round (from Wikipedia) |
| venue | str | `H` / `A` |
| opponent | str | canonical name |
| psg_goals, opp_goals | int | full-time goals |
| psg_result | str | `W` / `D` / `L` |
| psg_win | int | 1 if win |
| psg_points | int | 3/1/0 |
| psg_sot, opp_sot, sot_diff | int | shots on target |
| odds_win, odds_draw, odds_loss | float | reference odds (PSG perspective) |
| odds_source | str | `AvgC` / `PSC` / `B365C` / `Avg` |
| overround | float | bookmaker margin |
| p_win_implied, p_draw_implied, p_loss_implied | float | margin-free probabilities |
| p_win_implied_b365c | float | sensitivity |
| residual_win | float | `psg_win − p_win_implied` |
| brier_win | float | squared error |
| roi_flat | float | profit of a 1-unit bet on PSG win |
| rest_days | int | days since previous official match |
| prev_competition | str | competition of previous match |
| matches_last_14d | int | official matches in previous 14 days |
| next_rest_days, next_competition | int, str | following fixture |
| ucl_within_4d_after | bool | Champions League ≤ 4 days later |
| high_load, high_load_alt4, high_load_14d | bool | load definitions |
| load_bucket | str | High / Normal / Unknown |
| summer_break_days | int | season-level |
| season_start_window, post_cwc_start | bool | season-start flags |
| join_method, score_check_ok | str, bool | integration traceability |

`processed/psg_matches_all.csv`: `match_id, season, match_date, competition, round, venue, opponent, played, psg_goals, opp_goals, decided_by (FT/AET/PEN), rest_days, matches_last_14d, wiki_revid`.

## 13. EDA outputs — `eda.py` (all generated by code)

Figures (`reports/eda/*.png`, titled, axis units):
1. Calendar timeline: all official matches by date, coloured by competition, Ligue 1 matches marked.
2. Distribution of rest days for Ligue 1 matches (with thresholds 3 and 4).
3. Win rate / points per match / SOT difference by load bucket (with n and CI).
4. Mean implied win probability vs actual win rate by bucket (dumbbell).
5. Mean residual by bucket with 90 % CI; same for sensitivity definitions.
6. Season-start window: cumulative residual over the first 8 matches, one line per season, 2025-26 highlighted; summer break days annotated.
7. Calibration: actual win rate vs implied probability in bins.

Tables (tidy, Tableau-ready):
- `summary_by_bucket.csv` — `definition` (primary / alt4 / 14d / b365c), `bucket`, `kpi`, `n`, `mean`, `ci_low`, `ci_high`.
- `season_start.csv` — `season`, `match_index` (1–8), `match_date`, `opponent`, `residual_win`, `cum_residual`, `summer_break_days`.
- `sensitivity.csv` — decision-rule outcome under each definition.
- `decision.json` — primary decision-rule result.
`EDA_REPORT.md`: one section per figure with the factual numbers (n, rates, CIs) written by code; interpretation sentences are drafted in `docs/FINDINGS.md` and validated by the author.

## 14. Tooling configuration (pyproject excerpts)

```toml
[project]
name = "psg-fatigue"
requires-python = ">=3.12,<3.13"
dependencies = ["pandas>=2.2", "numpy>=1.26", "requests>=2.32", "mwparserfromhell>=0.6", "matplotlib>=3.8", "pyarrow>=15"]

[project.scripts]
psg-fatigue = "psg_fatigue.cli:main"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6", "mypy>=1.11", "pandas-stubs", "types-requests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF", "N"]

[tool.mypy]
files = ["src", "tests"]
strict = true
# Only if mwparserfromhell ships no type information: a module-level override,
# justified in README (third-party library without stubs), never a global ignore.

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## 15. Definition of done

- Fresh clone: `uv sync --frozen && uv run psg-fatigue all` rebuilds every processed file and report **without network**, deterministically.
- `ruff check`, `ruff format --check`, `mypy`, `pytest` all pass; ≥ 8 tests.
- Integration report shows match rate, unmatched rows, no row multiplication; Wikipedia counts reconcile with "Overall record".
- `docs/SOURCES.md` filled with real extraction date, revids, sha256, coverage.
- `docs/QUALITY_NOTE.md` ≤ 1 page + decision log appendix, filled with real numbers.
- `docs/FINDINGS.md` drafted with the three findings, the decision-rule result and limitations.
- `tableau/README.md` and `docs/TABLEAU.md` ready; processed CSVs ready for Tableau.
- README complete (see brief): question & scope, setup/run commands, source access, data locations, Tableau instructions, quality tooling scope, contributions, use of AI.
