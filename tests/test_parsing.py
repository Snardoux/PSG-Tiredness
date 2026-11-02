"""Parsing tests (offline) on real excerpts of snapshot 2026-11-02 saved in tests/fixtures/."""

import io
from datetime import date
from pathlib import Path

import mwparserfromhell
import pandas as pd
import pytest

from psg_fatigue.parse import fd_matches
from psg_fatigue.parse.wiki_matches import (
    Score,
    UnknownCompetitionError,
    parse_overall_record,
    parse_page_matches,
    parse_score,
)
from psg_fatigue.quality import wikipedia_counts

FIXTURES = Path(__file__).parent / "fixtures"
EN_DASH, EM_DASH = "\u2013", "\u2014"


def _excerpt() -> mwparserfromhell.wikicode.Wikicode:
    return mwparserfromhell.parse((FIXTURES / "wiki_excerpt.wikitext").read_text("utf-8"))


def _excerpt_rows() -> pd.DataFrame:
    rows, _ = parse_page_matches(_excerpt(), "2025-26")
    return pd.DataFrame(rows)


def _row(competition: str, round_label: str) -> pd.Series:
    """The single excerpt row of a competition and round."""
    rows = _excerpt_rows()
    selected = rows[(rows["competition"] == competition) & (rows["round"] == round_label)]
    assert len(selected) == 1
    return selected.iloc[0]


# --- Scores (SPEC test 5) -------------------------------------------------------


@pytest.mark.parametrize("dash", [EN_DASH, "-", EM_DASH])
def test_score_parsing_accepts_every_dash(dash: str) -> None:
    assert parse_score(f"2{dash}1") == Score(2, 1)


def test_score_parsing_shootouts() -> None:
    # Shoot-out written inside the score, or in the separate `penaltyscore` parameter
    # (the form used by the real pages, e.g. the 2025 UEFA Super Cup box).
    assert parse_score(f"2{EN_DASH}2 (4{EN_DASH}3 p)") == Score(2, 2, 4, 3)
    assert parse_score(f"2{EN_DASH}2", f"4{EN_DASH}3") == Score(2, 2, 4, 3)


@pytest.mark.parametrize("unplayed", ["", "v", f"P{EN_DASH}P", "P-P"])
def test_score_parsing_unplayed(unplayed: str) -> None:
    assert parse_score(unplayed) is None


def test_score_parsing_rejects_unknown_text() -> None:
    with pytest.raises(ValueError, match="Unrecognised score"):
        parse_score("abandoned")


# --- Match boxes and competitions (SPEC test 8) -----------------------------------


def test_wiki_competition_mapping_excludes_friendlies() -> None:
    rows, friendlies = parse_page_matches(_excerpt(), "2025-26")
    assert friendlies == 1  # the Mallorca pre-season friendly
    assert [row["competition"] for row in rows] == [
        "Ligue 1",
        "Ligue 1",
        "Coupe de France",
        "UEFA Champions League",
        "UEFA Super Cup",
    ]


def test_wiki_unknown_heading_raises() -> None:
    real_box = str(_excerpt().filter_templates(matches="Football box collapsible")[0])
    page = mwparserfromhell.parse(f"==Statistics==\n{real_box}\n")
    with pytest.raises(UnknownCompetitionError, match="Statistics"):
        parse_page_matches(page, "2025-26")


def test_league_match_from_psg_perspective() -> None:
    first = _row("Ligue 1", "1")  # Nantes 0-1 Paris Saint-Germain
    assert first["match_date"] == date(2025, 8, 17)
    assert (first["matchday"], first["venue"], first["opponent"]) == (1, "A", "Nantes")
    assert (first["psg_goals"], first["opp_goals"], first["psg_result"]) == (1, 0, "W")
    assert first["decided_by"] == "FT"


def test_postponed_league_match_keeps_its_actual_date() -> None:
    postponed = _row("Ligue 1", "26")  # v Nantes, postponed from 15 March 2026
    assert postponed["matchday"] == 26
    assert postponed["match_date"] == date(2026, 4, 22)
    assert postponed["rescheduled"]
    assert postponed["venue"] == "H"


def test_cup_shootout_final_and_unplayed_fixture() -> None:
    cup = _row("Coupe de France", "Round of 64")
    assert (cup["competition"], cup["round"], cup["venue"]) == (
        "Coupe de France",
        "Round of 64",
        "A",
    )
    super_cup = _row("UEFA Super Cup", "Final")
    assert super_cup["venue"] == "N"
    assert (super_cup["psg_goals"], super_cup["opp_goals"]) == (2, 2)
    assert (super_cup["decided_by"], super_cup["psg_shootout"], super_cup["opp_shootout"]) == (
        "PEN",
        4,
        3,
    )
    assert super_cup["psg_result"] == super_cup["wiki_result"] == "D"
    future = _row("UEFA Champions League", "4")  # at Villarreal, 3 Nov 2026: after snapshot
    assert not future["played"]
    assert future["match_date"] == date(2026, 11, 3)
    assert pd.isna(future["psg_goals"])


# --- Overall record and count reconciliation ------------------------------------


def test_overall_record_reads_every_competition() -> None:
    record = pd.DataFrame(parse_overall_record(_excerpt(), "2025-26"))
    # The table declares c=5 but lists 6 competitions: all six must be read.
    assert len(record) == 6
    assert record["played"].sum() == 56
    assert record.set_index("competition").loc["Ligue 1", "played"] == 34


def test_overall_record_unwraps_nowrap_template() -> None:
    page = mwparserfromhell.parse((FIXTURES / "wiki_overview_2026-27.wikitext").read_text("utf-8"))
    record = pd.DataFrame(parse_overall_record(page, "2026-27")).set_index("competition")
    assert "FIFA Intercontinental Cup" in record.index  # written {{nowrap|[[...]]}}
    assert record.loc["Ligue 1", "played"] == 9


def test_count_reconciliation_flags_a_mismatch() -> None:
    rows = _excerpt_rows()
    rows["match_date"] = pd.to_datetime(rows["match_date"])
    record = pd.DataFrame(parse_overall_record(_excerpt(), "2025-26"))
    counts = wikipedia_counts(rows, record).set_index("competition")
    # The excerpt holds 2 of the 34 league matches listed in the Overall record.
    assert counts.loc["Ligue 1", "parsed_played"] == 2
    assert counts.loc["Ligue 1", "status"] == "MISMATCH"


# --- football-data CSV -----------------------------------------------------------


def _fd_excerpt_raw() -> pd.DataFrame:
    return fd_matches.read_f1_csv(FIXTURES / "fd_F1_2526_excerpt.csv")


def test_fd_reading_handles_bom_and_types() -> None:
    table = fd_matches.type_f1_table(_fd_excerpt_raw(), "2025-26")
    assert list(table.columns[:4]) == ["season", "match_date", "kickoff_time_uk", "home_team"]
    nantes = table[(table["home_team"] == "Nantes") & (table["away_team"] == "Paris SG")].iloc[0]
    assert nantes["match_date"] == pd.Timestamp("2025-08-17")
    assert (nantes["home_goals"], nantes["away_goals"], nantes["ft_result"]) == (0, 1, "A")
    assert nantes["odds_avgc_a"] > 1.0


def test_fd_missing_odds_columns_are_added_empty() -> None:
    raw = _fd_excerpt_raw().drop(columns=["PSCH", "PSCD", "PSCA"])  # as in the 2026-27 file
    table = fd_matches.type_f1_table(raw, "2026-27")
    assert table["odds_psc_h"].isna().all()
    assert table["odds_avgc_h"].notna().all()


def test_fd_rejects_rows_outside_ligue_1() -> None:
    raw = _fd_excerpt_raw()
    raw.loc[0, "Div"] = "F2"
    with pytest.raises(fd_matches.FootballDataFormatError, match="Div F1"):
        fd_matches.type_f1_table(raw, "2025-26")


def test_fd_dates_fall_back_to_two_digit_years() -> None:
    dates = fd_matches.parse_fd_dates(pd.Series(["17/08/2025", "17/08/25"]))
    assert (dates == pd.Timestamp("2025-08-17")).all()
    with pytest.raises(fd_matches.FootballDataFormatError):
        fd_matches.parse_fd_dates(pd.Series(["2025-08-17"]))


def test_fd_decoding_without_bom() -> None:
    text = fd_matches.decode_csv((FIXTURES / "fd_F1_2526_excerpt.csv").read_bytes())
    assert text.startswith("Div,")  # BOM removed
    assert pd.read_csv(io.StringIO(text)).shape[0] == 8
