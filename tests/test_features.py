"""Load-feature tests (offline) on the real parsed calendar of 2025-26.

Fixture `psg_calendar_2025-26.csv`: every 2025-26 fixture parsed from snapshot 2026-11-02,
plus the 2025 Club World Cup final (last match of the 2024-25 page) as context.
"""

from pathlib import Path

import pandas as pd
import pytest

from psg_fatigue.features import (
    HIGH_LOAD_LABEL,
    NORMAL_LOAD_LABEL,
    UNKNOWN_LOAD_LABEL,
    build_match_features,
    load_bucket,
    matches_in_previous_days,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _calendar() -> pd.DataFrame:
    calendar = pd.read_csv(FIXTURES / "psg_calendar_2025-26.csv", parse_dates=["match_date"])
    calendar["matchday"] = calendar["matchday"].astype("Int64")
    return calendar


def _features() -> pd.DataFrame:
    return build_match_features(_calendar()).set_index("match_id")


# --- Rest days (SPEC test 3) ------------------------------------------------------


def test_rest_days_postponed() -> None:
    features = _features()
    # Matchday 26 v Nantes, postponed to 22 April 2026, came 3 days after matchday 30 v Lyon:
    # rest follows the dates, not the matchday numbers.
    nantes = features.loc["2026-04-22_nantes"]
    assert (nantes["matchday"], nantes["rest_days"]) == (26, 3)
    assert features.loc["2026-04-19_lyon", "matchday"] == 30
    # Matchday 29 at Lens (13 May) came 3 days after matchday 33 v Brest (10 May).
    assert features.loc["2026-05-13_lens", "rest_days"] == 3


def test_rest_days_first_match_uses_context_match() -> None:
    features = _features()
    # The 2025 UEFA Super Cup (13 Aug) follows the Club World Cup final (13 Jul), which is
    # listed on the previous season's page.
    super_cup = features.loc["2025-08-13_tottenham-hotspur"]
    assert super_cup["rest_days"] == 31
    assert super_cup["prev_competition"] == "FIFA Club World Cup"
    assert features.loc["2025-08-17_nantes", "summer_break_days"] == 31


def test_rest_days_equal_dates_raise() -> None:
    calendar = _calendar()
    duplicated = pd.concat([calendar, calendar.iloc[[3]]]).sort_values("match_date")
    with pytest.raises(ValueError, match="same date"):
        build_match_features(duplicated)


# --- Load buckets and windows (SPEC test 4) ----------------------------------------


@pytest.mark.parametrize(
    ("rest", "label"),
    [
        (3, HIGH_LOAD_LABEL),
        (4, NORMAL_LOAD_LABEL),
        (None, UNKNOWN_LOAD_LABEL),
        (float("nan"), UNKNOWN_LOAD_LABEL),
    ],
)
def test_load_buckets(rest: float | None, label: str) -> None:
    assert load_bucket(rest) == label


def test_load_buckets_fourteen_day_window_boundaries() -> None:
    # Real dates of spring 2026: Toulouse 3 Apr, Liverpool 8 and 14 Apr, Lyon 19 Apr, Nantes 22 Apr.
    dates = pd.Series(
        pd.to_datetime(["2026-04-03", "2026-04-08", "2026-04-14", "2026-04-19", "2026-04-22"])
    )
    # 22 Apr: 8 Apr is exactly 14 days before -> counted. 19 Apr: 3 Apr is 16 days before -> not.
    assert matches_in_previous_days(dates, 14).tolist() == [0, 1, 2, 2, 3]


def test_load_flags_on_real_matches() -> None:
    features = _features()
    assert features.loc["2026-04-22_nantes", "high_load"]
    assert features.loc["2026-04-22_nantes", "load_bucket"] == HIGH_LOAD_LABEL
    lorient = features.loc["2026-05-02_lorient"]  # 4 days after Bayern Munich at home
    assert (lorient["high_load"], lorient["high_load_alt4"]) == (False, True)
    # Angers away (25 Apr) was followed 3 days later by Bayern Munich in the Champions League.
    assert features.loc["2026-04-25_angers", "ucl_within_4d_after"]
    assert not features.loc["2026-04-19_lyon", "ucl_within_4d_after"]


def test_season_start_window_flags_first_eight_league_matches() -> None:
    features = _features()
    league = features[features["competition"] == "Ligue 1"]
    window = league[league["season_start_window"]]
    assert len(window) == 8
    assert window["post_cwc_start"].all()  # 2025-26 is the post-Club World Cup season
    assert window.index.min() == "2025-08-17_nantes"
