# PSG under Luis Enrique — does fixture congestion beat the betting market?

Reproducible data pipeline (individual project, Sacha Nardoux). Framing in
[`docs/FRAMING.md`](docs/FRAMING.md), technical contract in [`docs/SPEC.md`](docs/SPEC.md).

> Work in progress: the full README (scope, sources, data locations, Tableau,
> quality tooling scope, contributions, use of AI) is written at the end of the project.

## Setup and commands

Run every command from the repository root.

```bash
uv sync --frozen          # create the environment from uv.lock (Python 3.12)
uv run psg-fatigue --help
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
