# CLAUDE.md — Project rules for Claude Code

Project: **PSG under Luis Enrique — does fixture congestion beat the betting market?**
Course: Data Foundations Project (Python Environments & Engineering Workflows, SQL & Dashboards, Advanced EDA), M1 Madrid 2026-2027.
Author: Sacha Nardoux (individual work). Submission deadline: **Wed 4 Nov 2026, 23:59** (Europe/Madrid).

Read these before writing any code:
1. `docs/FRAMING.md` — decision, question, population, geography, period, decision rule.
2. `docs/SPEC.md` — architecture, grains, schemas, joins, features, KPIs, tests, outputs.
3. `docs/SOURCES.md` — the two sources and how to record provenance.
4. `docs/QUALITY_NOTE.md` and `docs/TABLEAU.md` — documents to fill at the end.

## Non-negotiable constraints (from the course brief)

- **uv** manages the environment. Commit `pyproject.toml`, `uv.lock`, `.python-version` (Python 3.12).
- The **whole pipeline** (collection, cleaning, integration, preparation of the analytical output, EDA outputs) lives in readable Python under `src/psg_fatigue/`, with one entry point: `uv run psg-fatigue <command>`. **No pipeline logic in notebooks.** No notebook at all unless it only imports project functions.
- **Two sources only**: Wikipedia (MediaWiki Action API) and football-data.co.uk (`F1.csv`). Do not scrape any other site (no Transfermarkt, FBref, Flashscore, Sofascore, psg.fr) without asking the user first.
- **Frozen raw snapshot**: collection writes immutable files to `data/raw/<snapshot_id>/` plus a `manifest.json` (URL, timestamp UTC, HTTP status, bytes, sha256, Wikipedia revid). Never overwrite an existing snapshot. `build` must run **offline** from the snapshot.
- **Ruff + mypy** run clean on `src/` and `tests/`. No blanket `exclude`, no file-level `# noqa`/`# type: ignore`. A targeted ignore is allowed only with an error code and a one-line justification comment, and it must be listed in README → "Quality tooling scope".
- **pytest**: at least 3 meaningful business-logic tests (target 8, see SPEC §11). No network in tests: use fixtures under `tests/fixtures/`.
- **No absolute paths** anywhere (code, README, config). All paths are relative to the repository root.
- `.gitignore` excludes `.venv/`, caches (`__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`), `.env`, OS files, Tableau temp files. Keep `data/raw/` (small, needed for rebuild) and `data/processed/` (needed by Tableau) **committed**.
- Do not fabricate data, counts, or results. If a source fails or a check does not match expectations, stop and report with evidence.

## Commands (must work from a fresh clone)

```bash
uv sync --frozen                                   # environment
uv run psg-fatigue collect                         # online: new snapshot in data/raw/<YYYY-MM-DD>/
uv run psg-fatigue build                           # offline: raw snapshot -> data/interim -> data/processed
uv run psg-fatigue eda                             # offline: figures + tables in reports/eda/
uv run psg-fatigue all                             # build + eda (offline)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q
```

## Coding conventions

- Python 3.12, type hints everywhere, small pure functions for business logic (they are what tests target).
- pandas for transformations; no SQL needed. Every transformation step logs row counts in/out.
- `logging` (not print) in the pipeline; INFO level by default.
- Deterministic outputs: sorted rows, fixed random seed (42) for bootstrap.
- Names: snake_case columns, English labels in data; dates as ISO `YYYY-MM-DD` (Europe/Paris calendar date).
- Each module has a module docstring stating the grain of its input and output.

## Git workflow

- Commit after each phase with a clear message (`feat: ...`, `fix: ...`, `test: ...`, `docs: ...`, `chore: ...`).
- Use short-lived feature branches (`feat/collection`, `feat/integration`, `feat/eda`, `docs/final`) merged into `main` with `--no-ff`, so the history shows the workflow.
- Never commit secrets. No API keys are needed in this project.

## When to stop and ask the user

- A source is unreachable, changed format, or a Wikipedia season page is missing.
- An expected count does not match (e.g. a complete Ligue 1 season ≠ 306 rows, PSG ≠ 34 league matches).
- A decision changes the framing (definition of high load, odds reference, population).
