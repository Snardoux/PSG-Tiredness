"""Calendar load features of PSG's official matches.

Input grain: one PSG official fixture, played or scheduled, all competitions and seasons
(`interim/psg_calendar`, including the 2022-23 context season).
Output grain: one PSG official *played* match of the Luis Enrique era, all competitions,
with its load features. Everything is computed on actual dates, never on matchday numbers.
"""

import logging
import re
import unicodedata

import numpy as np
import pandas as pd

from psg_fatigue import config

logger = logging.getLogger(__name__)

HIGH_LOAD_LABEL = f"High (≤{config.HIGH_LOAD_MAX_REST_DAYS} days)"
NORMAL_LOAD_LABEL = f"Normal (≥{config.HIGH_LOAD_MAX_REST_DAYS + 1} days)"
UNKNOWN_LOAD_LABEL = "Unknown"


def rest_days(match_dates: pd.Series) -> pd.Series:
    """Calendar days since the previous official match (first value is NA).

    Dates must be sorted. Two official matches on the same date are impossible, so equal
    dates raise ValueError rather than producing a rest of 0 days.
    """
    if not match_dates.is_monotonic_increasing:
        raise ValueError("Match dates must be sorted in ascending order")
    duplicated = match_dates[match_dates.duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Two official matches on the same date: {duplicated.dt.date.tolist()}")
    days: pd.Series = match_dates.diff().dt.days
    return days.astype("Int64")


def matches_in_previous_days(match_dates: pd.Series, window_days: int) -> pd.Series:
    """Number of official matches in the `window_days` days before each match.

    The window is [date - window_days, date): a match exactly `window_days` days earlier
    counts, the match itself does not. Dates must be sorted and unique (see `rest_days`).
    """
    dates = match_dates.to_numpy(dtype="datetime64[D]")
    window_starts = dates - np.timedelta64(window_days, "D")
    first_in_window = np.searchsorted(dates, window_starts, side="left")
    counts = np.arange(len(dates)) - first_in_window
    return pd.Series(counts, index=match_dates.index, dtype="Int64")


def load_bucket(rest: float | None) -> str:
    """Primary load bucket of a match from its rest days (FRAMING: high load = rest <= 3)."""
    if rest is None or pd.isna(rest):
        return UNKNOWN_LOAD_LABEL
    return HIGH_LOAD_LABEL if rest <= config.HIGH_LOAD_MAX_REST_DAYS else NORMAL_LOAD_LABEL


def next_fixture_features(played: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    """For each played match: days to the next fixture (played or scheduled), its competition,
    and whether a Champions League match follows within 4 days (rotation risk)."""
    fixture_dates = fixtures["match_date"].to_numpy(dtype="datetime64[D]")
    played_dates = played["match_date"].to_numpy(dtype="datetime64[D]")
    next_position = np.searchsorted(fixture_dates, played_dates, side="right")
    has_next = next_position < len(fixture_dates)
    safe_position = np.minimum(next_position, len(fixture_dates) - 1)
    gap_days = (fixture_dates[safe_position] - played_dates).astype(int)

    ucl = fixtures["competition"] == "UEFA Champions League"
    ucl_dates = fixtures.loc[ucl, "match_date"].to_numpy(dtype="datetime64[D]")
    window_end = played_dates + np.timedelta64(config.UCL_ROTATION_WINDOW_DAYS, "D")
    ucl_after = np.searchsorted(ucl_dates, window_end, side="right") - np.searchsorted(
        ucl_dates, played_dates, side="right"
    )
    # The last fixture of the calendar has no next fixture: NA instead of a fake value.
    next_rest = pd.Series(gap_days, index=played.index, dtype="Int64").where(has_next)
    next_competition = pd.Series(
        fixtures["competition"].to_numpy()[safe_position], index=played.index
    ).where(has_next)
    return pd.DataFrame(
        {
            "next_rest_days": next_rest,
            "next_competition": next_competition,
            f"ucl_within_{config.UCL_ROTATION_WINDOW_DAYS}d_after": ucl_after > 0,
        },
        index=played.index,
    )


def summer_breaks(played: pd.DataFrame) -> pd.Series:
    """Days between the last official match of the previous season and the first of each season.

    Season-level variable (index: season); the first season of the table has no break (NA).
    """
    bounds = played.groupby("season")["match_date"].agg(["min", "max"]).sort_index()
    return (bounds["min"] - bounds["max"].shift()).dt.days.astype("Int64")


def slugify(text: str) -> str:
    """ASCII, lowercase, hyphen-separated version of a name ('Saint-Étienne' -> 'saint-etienne')."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def build_match_features(calendar: pd.DataFrame) -> pd.DataFrame:
    """Load features of every played official match, restricted to the Luis Enrique era.

    The context season (2022-23) is used for the first rest-day and summer-break values,
    then dropped from the output.
    """
    played = calendar[calendar["played"]].sort_values("match_date").reset_index(drop=True)
    fixtures = calendar.dropna(subset=["match_date"]).sort_values("match_date")
    features = played.copy()
    features["rest_days"] = rest_days(played["match_date"])
    features["prev_competition"] = played["competition"].shift()
    features["prev_venue"] = played["venue"].shift()
    features["matches_last_14d"] = matches_in_previous_days(
        played["match_date"], config.LOAD_WINDOW_DAYS
    )
    features = features.join(next_fixture_features(played, fixtures))

    rest = features["rest_days"]
    features["high_load"] = (rest <= config.HIGH_LOAD_MAX_REST_DAYS).fillna(False).astype(bool)
    features["high_load_alt4"] = (
        (rest <= config.ALT_HIGH_LOAD_MAX_REST_DAYS).fillna(False).astype(bool)
    )
    features["high_load_14d"] = (
        (features["matches_last_14d"] >= config.HIGH_LOAD_MIN_MATCHES_IN_WINDOW)
        .fillna(False)
        .astype(bool)
    )
    features["load_bucket"] = rest.astype("Float64").map(load_bucket)
    features["summer_break_days"] = features["season"].map(summer_breaks(played)).astype("Int64")

    is_league = features["competition"] == config.LEAGUE
    league_index = features[is_league].groupby("season")["match_date"].rank(method="first")
    features["league_match_index"] = league_index.astype("Int64")  # NA for other competitions
    features["season_start_window"] = (
        (features["league_match_index"] <= config.SEASON_START_WINDOW_MATCHES)
        .fillna(False)
        .astype(bool)
    )
    features["post_cwc_start"] = features["season_start_window"] & (
        features["season"] == config.POST_CWC_SEASON
    )
    features["match_id"] = (
        features["match_date"].dt.strftime("%Y-%m-%d") + "_" + features["opponent"].map(slugify)
    )
    if features["match_id"].duplicated().any():
        raise ValueError("match_id is not unique")

    in_era = features["match_date"] >= pd.Timestamp(config.LUIS_ENRIQUE_APPOINTMENT)
    result = features[in_era].reset_index(drop=True)
    logger.info(
        "Load features: %d played matches in, %d Luis Enrique era matches out (%d Ligue 1)",
        len(played),
        len(result),
        int((result["competition"] == config.LEAGUE).sum()),
    )
    return result
