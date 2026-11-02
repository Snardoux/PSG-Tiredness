"""Quality checks and CLI error handling (offline), on real excerpts in tests/fixtures/."""

from pathlib import Path

import pandas as pd
import pytest

from psg_fatigue import quality
from psg_fatigue.cli import main
from psg_fatigue.features import build_match_features
from psg_fatigue.parse.fd_matches import read_f1_csv, type_f1_table

FIXTURES = Path(__file__).parent / "fixtures"


def _features() -> pd.DataFrame:
    calendar = pd.read_csv(FIXTURES / "psg_calendar_2025-26.csv", parse_dates=["match_date"])
    calendar["matchday"] = calendar["matchday"].astype("Int64")
    return build_match_features(calendar)


def _fd_excerpt(season: str) -> pd.DataFrame:
    return type_f1_table(read_f1_csv(FIXTURES / "fd_F1_2526_excerpt.csv"), season)


# --- Quality checks ------------------------------------------------------------------


def test_incomplete_season_stops_the_build() -> None:
    # The 10-row excerpt labelled as a complete season must fail the 306-row check...
    counts = quality.fd_counts(_fd_excerpt("2023-24"))
    assert counts.loc[0, "status"] == "MISMATCH"
    labels = quality.paris_labels(_fd_excerpt("2023-24"))
    checks = pd.DataFrame(columns=["check", "value", "status"])
    wiki_ok = pd.DataFrame(columns=["season", "competition", "parsed_played", "status"])
    with pytest.raises(quality.QualityCheckError, match="10 rows"):
        quality.assert_expected_counts(wiki_ok, counts, labels, checks)
    # ...while the partial current season is only reported.
    assert quality.fd_counts(_fd_excerpt("2026-27")).loc[0, "status"] == "partial season"


def test_paris_labels_keep_both_clubs_apart() -> None:
    labels = quality.paris_labels(_fd_excerpt("2025-26"))
    assert labels.loc[0, "labels"] == "Paris FC; Paris SG"


def test_out_of_matchday_order_lists_postponed_sequences() -> None:
    moved = quality.out_of_matchday_order(_features())
    # Matchday 26 (Nantes) and 29 (Lens) were postponed: matchdays 27 to 33 shift around them.
    assert sorted(moved["matchday"].tolist()) == [26, 27, 28, 29, 30, 31, 32, 33]
    nantes = moved[moved["opponent"] == "Nantes"].iloc[0]
    assert (nantes["matchday"], nantes["date_rank"]) == (26, 29)


def test_rest_day_outliers_spare_season_openers() -> None:
    features = _features()
    # The Super Cup (31 days after the Club World Cup final) opens 2025-26: not an outlier.
    assert quality.rest_day_outliers(features).empty
    mid_season = features.index[features["opponent"] == "Lyon"][0]
    features.loc[mid_season, "rest_days"] = 35
    flagged = quality.rest_day_outliers(features)
    assert flagged["opponent"].tolist() == ["Lyon"]


def test_near_duplicates_detect_a_placeholder_and_its_replay() -> None:
    calendar = pd.read_csv(FIXTURES / "psg_calendar_2025-26.csv", parse_dates=["match_date"])
    assert quality.near_duplicates(calendar).empty
    replay = calendar[calendar["opponent"] == "Lens"].iloc[[0]].copy()
    replay["match_date"] += pd.Timedelta(days=2)
    pairs = quality.near_duplicates(pd.concat([calendar, replay]))
    assert pairs["opponent"].tolist() == ["Lens"]


# --- CLI ------------------------------------------------------------------------------


def test_cli_build_with_unknown_snapshot_fails_cleanly() -> None:
    assert main(["build", "--snapshot", "1900-01-01"]) == 1


def test_cli_register_manual_needs_an_existing_snapshot() -> None:
    assert main(["collect", "--register-manual", "1900-01-01"]) == 1


def test_cli_refuses_to_run_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["eda"]) == 1
