"""Integration tests (offline) on real excerpts of snapshot 2026-11-02.

Left: the PSG rows of `fd_F1_2526_excerpt.csv` (6 PSG matches, including both Paris FC
derbies, plus Paris FC matches against other clubs). Right: the 34 Ligue 1 matches of the
parsed 2025-26 calendar. Team names come from the reviewed `config/team_names.csv`.
"""

from pathlib import Path

import pandas as pd
import pytest

from psg_fatigue import config
from psg_fatigue.features import build_match_features
from psg_fatigue.integrate import (
    TeamMappingError,
    join_sources,
    load_team_names,
    suggest_team_mapping,
    to_canonical,
)
from psg_fatigue.odds import psg_perspective
from psg_fatigue.parse.fd_matches import read_f1_csv, type_f1_table

FIXTURES = Path(__file__).parent / "fixtures"


def _fd_l1() -> pd.DataFrame:
    return type_f1_table(read_f1_csv(FIXTURES / "fd_F1_2526_excerpt.csv"), "2025-26")


def _left() -> pd.DataFrame:
    left = psg_perspective(_fd_l1(), config.FD_PSG_LABEL)
    mapping = load_team_names(config.TEAM_NAMES_CSV)
    left["opponent_canonical"] = to_canonical(left["opponent_fd"], mapping, "footballdata_name")
    return left


def _right() -> pd.DataFrame:
    calendar = pd.read_csv(FIXTURES / "psg_calendar_2025-26.csv", parse_dates=["match_date"])
    calendar["matchday"] = calendar["matchday"].astype("Int64")
    features = build_match_features(calendar)
    right = features[features["competition"] == config.LEAGUE].copy()
    mapping = load_team_names(config.TEAM_NAMES_CSV)
    right["opponent_canonical"] = to_canonical(right["opponent"], mapping, "wikipedia_name")
    return right


# --- PSG perspective (SPEC test 2) -------------------------------------------------


def _raw_odds(date: str, home: str, away: str) -> pd.Series:
    """Odds of one match of the raw excerpt (two matches can share a date)."""
    raw = _fd_l1()
    match = raw[
        (raw["match_date"] == pd.Timestamp(date))
        & (raw["home_team"] == home)
        & (raw["away_team"] == away)
    ]
    assert len(match) == 1
    return match.iloc[0]


def test_psg_perspective() -> None:
    view = _left().set_index("match_date")
    away_win = view.loc[pd.Timestamp("2025-08-17")]  # Nantes 0-1 Paris SG, FTR = "A"
    assert (away_win["venue"], away_win["opponent_fd"]) == ("A", "Nantes")
    assert (away_win["psg_result"], away_win["psg_win"], away_win["psg_points"]) == ("W", 1, 3)
    # Away match: PSG's win odds are the file's away odds, its loss odds the home odds.
    nantes_raw = _raw_odds("2025-08-17", "Nantes", "Paris SG")
    assert away_win["odds_avgc_win"] == nantes_raw["odds_avgc_a"]
    assert away_win["odds_avgc_loss"] == nantes_raw["odds_avgc_h"]
    away_draw = view.loc[pd.Timestamp("2025-10-05")]  # Lille 1-1 Paris SG
    assert (away_draw["psg_result"], away_draw["psg_points"]) == ("D", 1)
    home_loss = view.loc[pd.Timestamp("2026-03-06")]  # Paris SG 1-3 Monaco, FTR = "A"
    assert (home_loss["venue"], home_loss["psg_result"], home_loss["psg_points"]) == ("H", "L", 0)
    assert (
        home_loss["odds_avgc_win"] == _raw_odds("2026-03-06", "Paris SG", "Monaco")["odds_avgc_h"]
    )
    assert home_loss["sot_diff"] == home_loss["psg_sot"] - home_loss["opp_sot"]


# --- Team names --------------------------------------------------------------------


def test_paris_fc_is_never_mapped_to_psg() -> None:
    mapping = load_team_names(config.TEAM_NAMES_CSV)
    canonical = to_canonical(pd.Series(["Paris FC", "Paris SG"]), mapping, "footballdata_name")
    assert canonical.tolist() == ["Paris FC", "Paris Saint-Germain"]
    # Paris FC's matches against other clubs (Angers, Marseille) are not PSG matches.
    assert len(_left()) == 6
    assert set(_left()["opponent_fd"]) == {"Nantes", "Lille", "Paris FC", "Monaco"}


def test_suggested_mapping_never_guesses_between_paris_clubs() -> None:
    suggested = suggest_team_mapping(
        ["Paris FC", "Paris Saint-Germain", "Saint-Étienne"], ["Paris FC", "Paris SG", "St Etienne"]
    )
    pairs = dict(zip(suggested["wikipedia_name"], suggested["footballdata_name"], strict=True))
    assert pairs["Paris FC"] == "Paris FC"
    assert pairs["Saint-Étienne"] == "St Etienne"
    assert pairs["Paris Saint-Germain"] == ""  # left for manual review, not paired with Paris FC


def test_unmapped_name_stops_the_build() -> None:
    mapping = load_team_names(config.TEAM_NAMES_CSV)
    with pytest.raises(TeamMappingError, match="Paris Saint Germain"):
        to_canonical(pd.Series(["Paris Saint Germain"]), mapping, "wikipedia_name")


# --- Join (SPEC test 6) ------------------------------------------------------------


def test_join_preserves_grain() -> None:
    left, right = _left(), _right()
    joined, report = join_sources(left, right)
    assert len(joined) == len(left) == 6  # exactly one row per PSG league match
    assert joined["match_id"].is_unique
    assert report["matched_exact"] == 6
    assert report["right_only_rows"] == 34 - 6  # unmatched Wikipedia rows are reported
    assert not report["row_multiplication"]
    assert joined["score_check_ok"].all()
    derbies = joined[joined["opponent_canonical"] == "Paris FC"]
    assert len(derbies) == 2
    assert "Paris Saint-Germain" not in set(joined["opponent_canonical"])


def test_join_tolerates_one_day_and_reports_leftovers() -> None:
    left, right = _left(), _right()
    # Shift one real Wikipedia date by a day, as a late kick-off or a US local date would.
    derby = right["match_id"] == "2026-01-04_paris-fc"
    right.loc[derby, "match_date"] += pd.Timedelta(days=1)
    joined, report = join_sources(left, right)
    assert len(joined) == 6
    assert report["matched_plus_minus_1d"] == 1
    shifted = joined[joined["join_method"] == "plus_minus_1d"].iloc[0]
    assert shifted["match_date_fd"] == pd.Timestamp("2026-01-04")
    assert shifted["match_date"] == pd.Timestamp("2026-01-05")  # Wikipedia date kept

    # A football-data match without Wikipedia partner is reported and excluded.
    joined, report = join_sources(left, _right().query("match_id != '2026-03-06_monaco'"))
    assert len(joined) == 5
    assert report["left_only"] == [
        {"match_date": "2026-03-06", "season": "2025-26", "opponent": "Monaco"}
    ]


def test_join_rejects_duplicated_keys() -> None:
    right = _right()
    with pytest.raises(pd.errors.MergeError):
        join_sources(_left(), pd.concat([right, right.iloc[[0]]]))
