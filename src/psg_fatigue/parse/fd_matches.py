"""Read football-data.co.uk Ligue 1 files into one typed table.

Input grain: one raw CSV per season (`fd_F1_<code>.csv`); one row = one Ligue 1 match
(all clubs). Output grain: unchanged, one row per Ligue 1 match, typed and renamed to
snake_case (`interim/fd_l1`). Only the columns used by the analysis are kept.
"""

import io
import logging
from pathlib import Path

import pandas as pd

from psg_fatigue import config

logger = logging.getLogger(__name__)

# Result and statistics columns: original name -> snake_case name.
BASE_COLUMNS = {
    "Date": "match_date",
    "Time": "kickoff_time_uk",  # UK time, informational only (never used for joins)
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "FTR": "ft_result",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_sot",
    "AST": "away_sot",
}
# 1X2 odds families, in the fallback order of SPEC §4: closing average, Pinnacle closing,
# Bet365 closing, then pre-closing average. `AvgCH` -> `odds_avgc_h`, etc.
ODDS_FAMILIES = {"AvgC": "avgc", "PSC": "psc", "B365C": "b365c", "Avg": "avg"}
ODDS_COLUMNS = {
    f"{prefix}{side}": f"odds_{name}_{side.lower()}"
    for prefix, name in ODDS_FAMILIES.items()
    for side in ("H", "D", "A")
}
USED_COLUMNS = {**BASE_COLUMNS, **ODDS_COLUMNS}
COUNT_COLUMNS = ["home_goals", "away_goals", "home_shots", "away_shots", "home_sot", "away_sot"]


class FootballDataFormatError(ValueError):
    """The CSV does not have the expected football-data Ligue 1 format."""


def decode_csv(content: bytes) -> str:
    """Decode a raw CSV: UTF-8 (with or without BOM) first, Latin-1 as a fallback."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("CSV is not valid UTF-8, decoding as Latin-1")
        return content.decode("latin-1")


def read_f1_csv(path: Path) -> pd.DataFrame:
    """Read one raw F1.csv as text columns, dropping fully empty rows and columns."""
    raw = pd.read_csv(io.StringIO(decode_csv(path.read_bytes())), dtype=str)
    raw.columns = [column.strip() for column in raw.columns]
    return raw.dropna(how="all").dropna(axis="columns", how="all")


def parse_fd_dates(values: pd.Series) -> pd.Series:
    """Parse `dd/mm/yyyy` dates, falling back to `dd/mm/yy`; any failure raises."""
    dates = pd.to_datetime(values, format="%d/%m/%Y", errors="coerce")
    short = dates.isna()
    dates[short] = pd.to_datetime(values[short], format="%d/%m/%y", errors="coerce")
    if dates.isna().any():
        bad = values[dates.isna()].unique().tolist()
        raise FootballDataFormatError(f"Unparseable dates: {bad[:5]}")
    return dates


def type_f1_table(raw: pd.DataFrame, season: str) -> pd.DataFrame:
    """Check and type one season: `Div == F1`, dates, counts as integers, odds as floats.

    Used columns missing from the file are added empty (their absence is reported by
    the quality step, never assumed).
    """
    if "Div" not in raw.columns or not raw["Div"].eq("F1").all():
        raise FootballDataFormatError(f"{season}: rows outside Div F1 or no Div column")
    table = raw.reindex(columns=list(USED_COLUMNS)).rename(columns=USED_COLUMNS)
    table["match_date"] = parse_fd_dates(table["match_date"])
    for column in COUNT_COLUMNS:
        table[column] = pd.to_numeric(table[column]).astype("Int64")
    for column in ODDS_COLUMNS.values():
        table[column] = pd.to_numeric(table[column]).astype("float64")
    table.insert(0, "season", season)
    return table


def parse_fd_snapshot(snapshot_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read every season file of the snapshot.

    Returns the typed Ligue 1 table (one row per match) and the column availability
    table (one row per season x used column, plus the file's total column count).
    """
    tables = []
    availability = []
    for season, code in config.FD_SEASON_CODES.items():
        raw = read_f1_csv(snapshot_dir / f"fd_F1_{code}.csv")
        typed = type_f1_table(raw, season)
        logger.info("football-data %s: %d rows read, %d rows kept", season, len(raw), len(typed))
        tables.append(typed)
        for column in USED_COLUMNS:
            availability.append(
                {
                    "season": season,
                    "column": column,
                    "present": column in raw.columns,
                    "n_columns_in_file": len(raw.columns),
                }
            )
    fd_l1 = pd.concat(tables, ignore_index=True)
    fd_l1 = fd_l1.sort_values(["match_date", "home_team"], kind="stable").reset_index(drop=True)
    return fd_l1, pd.DataFrame(availability)
