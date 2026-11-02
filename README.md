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
