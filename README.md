# PSG under Luis Enrique — does fixture congestion beat the betting market?

Reproducible data pipeline (Data Foundations Project, M1 Madrid 2026–2027, individual work by
Sacha Nardoux). It collects two public sources, freezes them in a raw snapshot, checks their
quality, integrates them at the grain "one PSG Ligue 1 match", and produces the analytical table,
the exploratory analysis and the inputs of a Tableau dashboard — all from one command-line entry
point, `uv run psg-fatigue`.

**Result in one sentence:** after ≤ 3 rest days PSG's mean residual (actual win − win probability
implied by closing odds) is +0.084, 90 % CI [−0.063 ; +0.224] over 28 matches, so the pre-registered
decision rule is not met — *the data does not support a fatigue adjustment*
([`docs/FINDINGS.md`](docs/FINDINGS.md), [`reports/eda/decision.json`](reports/eda/decision.json)).

## Question and scope

Summary of [`docs/FRAMING.md`](docs/FRAMING.md):

| | |
|---|---|
| User | a football trader at a sports betting operator who sets PSG's 1X2 Ligue 1 odds |
| Decision | apply a "fatigue adjustment" to PSG's win probability after congested periods, or follow the market consensus |
| Question | under Luis Enrique, does fixture congestion reduce PSG's Ligue 1 results beyond what closing odds already anticipate? |
| Population | every official Ligue 1 match played by PSG, one row per match from PSG's perspective (111 matches); other official competitions are used only to measure load |
| Geography | French Ligue 1, home and away; load-generating matches may be abroad; odds = international market aggregate |
| Period | 5 July 2023 (appointment) → extraction on 2 November 2026: seasons 2023–24, 2024–25, 2025–26 and 2026–27 up to 30 October 2026 |
| High load | ≤ 3 rest days since the previous official match (sensitivity: ≤ 4 days; ≥ 4 matches in 14 days) |
| Reference odds | market-average closing odds (`AvgC`), margin removed proportionally; Bet365 closing as sensitivity |
| Decision rule (set before the results) | recommend an adjustment only if the high-load mean residual is negative and its 90 % bootstrap CI excludes zero |

## Repository layout

```
├── pyproject.toml, uv.lock, .python-version   # uv project (Python 3.12), tool configuration
├── config/team_names.csv                      # reviewed club-name mapping between the two sources
├── data/
│   ├── raw/2026-11-02/                        # frozen raw snapshot + manifest.json (committed)
│   ├── interim/                               # parsed Parquet tables (rebuilt, not committed)
│   └── processed/                             # analytical CSV files used by Tableau (committed)
├── reports/
│   ├── quality/                               # quality report, counts, profiles, integration report
│   └── eda/                                   # 7 figures, Tableau-ready tables, decision.json, EDA_REPORT.md
├── src/psg_fatigue/
│   ├── cli.py, config.py, pipeline.py         # entry point, constants and paths, offline steps
│   ├── collect/                               # http.py, wikipedia.py, footballdata.py, snapshot.py
│   ├── parse/                                 # wiki_matches.py, fd_matches.py
│   ├── quality.py, features.py, integrate.py  # quality checks, load features, join
│   └── odds.py, analysis.py, eda.py           # odds KPIs, statistics, figures and report
├── tests/                                     # pytest suite + fixtures (real excerpts of the snapshot)
├── tableau/                                   # packaged workbook + how to open / refresh it
└── docs/                                      # FRAMING, SPEC, SOURCES, QUALITY_NOTE, FINDINGS, TABLEAU
```

Each module's docstring states the grain of its input and output. The layout follows
[`docs/SPEC.md`](docs/SPEC.md) §1, with three small additions: `pipeline.py` (offline orchestration,
so that `cli.py` only parses arguments), `collect/http.py` (polite GET with retries) and
`collect/snapshot.py` (manifest, overwrite protection, integrity check).

## Setup

Requirement: [uv](https://docs.astral.sh/uv/). It installs Python 3.12 (pinned in `.python-version`)
if needed. **Run every command from the repository root.**

```bash
uv sync --frozen            # create .venv exactly from uv.lock
uv run psg-fatigue --help   # commands: collect | build | eda | all
```

## Rebuild everything from the raw snapshot (offline)

```bash
uv run psg-fatigue all      # = build then eda; no network access
```

| Command | Reads | Writes |
|---|---|---|
| `uv run psg-fatigue build` | `data/raw/<SNAPSHOT_ID>/` (default `2026-11-02`, or `--snapshot <id>`) | `data/interim/*.parquet`, `data/processed/*.csv`, `reports/quality/*` |
| `uv run psg-fatigue eda` | `data/processed/*.csv` | `reports/eda/*` |
| `uv run psg-fatigue all` | — | `build` then `eda` |

`build` first re-checks every raw file against the size and sha256 recorded in the manifest, and
stops (exit code 1) if an expected count fails: a complete Ligue 1 season ≠ 306 rows, PSG ≠ 34
league matches, Wikipedia parsed counts ≠ the page's "Overall record", or an unmapped club name.
Outputs are deterministic (sorted rows, bootstrap seed 42): two runs produce byte-identical files.

## Collect a new snapshot (online)

```bash
uv run psg-fatigue collect
```

Downloads the 5 Wikipedia season pages (MediaWiki API) and the 4 football-data files into a new
folder `data/raw/<UTC date>/` with its `manifest.json` (URL, UTC timestamp, HTTP status, bytes,
sha256, Wikipedia revision id). An existing snapshot is never overwritten. To analyse a new
snapshot, set `SNAPSHOT_ID` in `src/psg_fatigue/config.py` (or pass `--snapshot <id>` to `build`
and `all`). Numbers will differ from the reported ones: pages are edited and new matches are played.

If football-data.co.uk ever blocks the automated download, `collect` writes the Wikipedia part,
prints the exact URLs and target file names, and the files downloaded by hand are registered with
`uv run psg-fatigue collect --register-manual <snapshot_id>` (import and transformations stay
automated). This fallback was not needed for snapshot `2026-11-02`.

## Sources and access

| Source | Access | What it gives |
|---|---|---|
| Wikipedia, `2022–23` → `2026–27 Paris Saint-Germain FC season` pages | **API**: MediaWiki Action API `action=parse` (wikitext + revision id), 1 request/s, descriptive User-Agent; no pagination needed | every official PSG match (all competitions) with date, round, score, venue → load features |
| football-data.co.uk, `mmz4281/{2324,2425,2526,2627}/F1.csv` | **downloaded CSV files**, download and import automated | all Ligue 1 results, shots and 1X2 odds (closing average, Bet365, Pinnacle) → market expectations |

Owners, URLs, extraction timestamps, revision ids, hashes, reuse conditions, filters and coverage
are recorded in [`docs/SOURCES.md`](docs/SOURCES.md). Wikipedia text is CC BY-SA 4.0 (credit:
Wikipedia contributors); football-data files are offered free of charge (credit: Football-Data.co.uk).

## Data locations and main outputs

| Path | Content | Committed |
|---|---|---|
| `data/raw/2026-11-02/` | 5 raw API responses (`wiki_<season>.json`), 4 raw CSV files (`fd_F1_<code>.csv`), `manifest.json` | yes (needed to rebuild) |
| `data/interim/` | parsed tables: PSG calendar, Ligue 1 matches, PSG perspective, joined table | no (rebuilt by `build`) |
| `data/processed/psg_l1_analytical.csv` | **analytical output**: one PSG Ligue 1 match, PSG perspective, odds KPIs and load features (data dictionary: SPEC §12) | yes |
| `data/processed/psg_matches_all.csv` | one PSG official match, all competitions, with rest days | yes |
| `reports/quality/` | `quality_report.md`, `wikipedia_counts.csv`, `fd_counts.csv`, profiles, `integration_report.md/.json` | yes |
| `reports/eda/` | 7 figures (`fig*.png`), `summary_by_bucket.csv`, `sensitivity.csv`, `season_start.csv`, `calibration.csv`, `decision.json`, `EDA_REPORT.md` | yes |

## Tableau

The dashboard (`tableau/psg_fatigue.twbx`, packaged with extracts) reads the CSV files above; it
recomputes nothing that the pipeline already computes (confidence intervals come from
`summary_by_bucket.csv`). Specification of the views, calculated fields and filters:
[`docs/TABLEAU.md`](docs/TABLEAU.md). How to open, reconnect and refresh it:
[`tableau/README.md`](tableau/README.md).

## Code quality checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q
```

## Quality tooling scope

| Tool | Scope | Configuration (`pyproject.toml`) |
|---|---|---|
| Ruff lint | whole repository (`src/`, `tests/`), no excluded path | rules `E, F, W, I, B, UP, SIM, RUF, N` (project spec) plus `C4, PT, PTH, RET, ARG, ERA, PIE`; line length 100 |
| Ruff format | whole repository | default style, line length 100 |
| mypy | `src/` and `tests/` | `strict = true` and `warn_unreachable = true` |
| pytest | `tests/` (78 tests, offline) | fixtures in `tests/fixtures/` are real excerpts of snapshot `2026-11-02` |

- **Targeted exceptions: none.** There is no `# noqa`, no `# type: ignore`, no per-file
  ignore and no global exclude. Any future exception must carry its error code and a
  one-line justification comment, and be listed in this section.
- **Third-party typing:** `pandas-stubs` and `types-requests` are dev dependencies;
  `mwparserfromhell` and `matplotlib` ship their own type information, so mypy needs no
  module override.
- **Not covered by tests:** the functions that perform HTTP requests
  (`collect/http.py`, the download functions of `collect/wikipedia.py` and
  `collect/footballdata.py`) only run during `collect`; tests never use the network.
  What can be checked offline is tested: API error detection, CSV detection, snapshot
  writing, manifest verification and manual registration.
- **Coverage** (informational, not a gate): 79% of statements, measured with
  `uv run --with pytest-cov pytest --cov=psg_fatigue`.

## Documentation

| Document | Content |
|---|---|
| [`docs/FRAMING.md`](docs/FRAMING.md) | user, decision, question, population, geography, period, decision rule |
| [`docs/SPEC.md`](docs/SPEC.md) | technical contract: grains, schemas, joins, features, KPIs, tests |
| [`docs/SOURCES.md`](docs/SOURCES.md) | source records (access, dates, revids, hashes, terms, coverage) |
| [`docs/QUALITY_NOTE.md`](docs/QUALITY_NOTE.md) | one-page quality note + decision log |
| [`docs/FINDINGS.md`](docs/FINDINGS.md) | three findings, answer, sensitivity, limitations, hypotheses |
| [`docs/TABLEAU.md`](docs/TABLEAU.md) | dashboard specification and refresh procedure |

## Contributions

Individual work by **Sacha Nardoux** (framing, specification, verification of every phase,
dashboard, git history).

## Use of AI

The code, tests and first drafts of the documentation were generated with **Claude Code**
(Anthropic's AI coding assistant) from my specification (`docs/FRAMING.md`, `docs/SPEC.md`),
phase by phase. I checked each phase myself before committing it: the counts against the sources
(manifest, 306 rows per season, 34 PSG league matches, 56 official matches in 2025–26), the
club-name mapping row by row, the integration report, the figures, and every sentence of
`docs/FINDINGS.md` and `docs/QUALITY_NOTE.md`. All git commands and commits were run by me.
