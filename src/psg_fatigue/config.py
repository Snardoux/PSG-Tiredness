"""Project constants: seasons, source URLs, snapshot id, load thresholds and paths.

Every path is relative to the repository root. Commands must be run from the
repository root (the folder that contains `pyproject.toml`); `ensure_repo_root()`
checks this before any command runs.
"""

from datetime import date
from pathlib import Path

# --- Snapshot -----------------------------------------------------------------
# Frozen raw snapshot analysed by `build` (folder name under data/raw/).
# Set after the first successful `collect`; None until then.
SNAPSHOT_ID: str | None = None

# --- Period and seasons (see docs/FRAMING.md) ---------------------------------
LUIS_ENRIQUE_APPOINTMENT = date(2023, 7, 5)

# 2022-23 is collected only to date PSG's last official match before the period.
CONTEXT_SEASON = "2022-23"
ANALYSIS_SEASONS: tuple[str, ...] = ("2023-24", "2024-25", "2025-26", "2026-27")
WIKI_SEASONS: tuple[str, ...] = (CONTEXT_SEASON, *ANALYSIS_SEASONS)

# --- Source 1: Wikipedia (MediaWiki Action API) ---------------------------------
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
EN_DASH = "\u2013"  # written as an escape: it looks like a hyphen but is not
CONTACT_EMAIL = "snardoux@albertschool.com"
USER_AGENT = (
    f"psg-fatigue-student-project/0.1 (Albert School M1 data project; contact: {CONTACT_EMAIL})"
)
REQUEST_INTERVAL_SECONDS = 1.0  # Wikimedia etiquette: at most 1 request per second
MAX_RETRIES = 4
REQUEST_TIMEOUT_SECONDS = 30


def wiki_page_title(season: str) -> str:
    """Return the English Wikipedia page title of a PSG season, e.g. for '2025-26'.

    Wikipedia titles use an en dash (U+2013) between the two years, not a hyphen.
    """
    start, end = season.split("-")
    return f"{start}{EN_DASH}{end} Paris Saint-Germain FC season"


# --- Source 2: football-data.co.uk (downloaded CSV files) ---------------------
FD_URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{code}/F1.csv"
FD_SEASON_CODES: dict[str, str] = {
    "2023-24": "2324",
    "2024-25": "2425",
    "2025-26": "2526",
    "2026-27": "2627",
}

# --- Load definitions (see docs/FRAMING.md, do not change without the author) --
HIGH_LOAD_MAX_REST_DAYS = 3  # primary: Champions League Wednesday -> Ligue 1 Saturday
ALT_HIGH_LOAD_MAX_REST_DAYS = 4  # sensitivity
LOAD_WINDOW_DAYS = 14
HIGH_LOAD_MIN_MATCHES_IN_WINDOW = 4  # sensitivity: >= 4 official matches in 14 days
SEASON_START_WINDOW_MATCHES = 8  # first 8 PSG Ligue 1 matches of a season

# --- Statistics -----------------------------------------------------------------
BOOTSTRAP_RESAMPLES = 10_000
RANDOM_SEED = 42
CI_LEVEL = 0.90

# --- Paths (relative to the repository root) -----------------------------------
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = Path("reports")
QUALITY_DIR = REPORTS_DIR / "quality"
EDA_DIR = REPORTS_DIR / "eda"
TEAM_NAMES_CSV = Path("config") / "team_names.csv"
FIXTURES_DIR = Path("tests") / "fixtures"


class NotAtRepoRootError(RuntimeError):
    """Raised when a command is not run from the repository root."""


def ensure_repo_root() -> None:
    """Fail with a clear message unless the current directory is the repository root."""
    pyproject = Path("pyproject.toml")
    if not pyproject.is_file() or 'name = "psg-fatigue"' not in pyproject.read_text("utf-8"):
        raise NotAtRepoRootError(
            f"Run psg-fatigue from the repository root (the folder containing the project's "
            f"pyproject.toml). Current directory: {Path.cwd().name!r}"
        )
