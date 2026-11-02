"""Odds KPI and statistics tests (offline).

Formula checks use the odds triple given in SPEC §11; behaviour on data uses the PSG rows
of the real football-data excerpt `fd_F1_2526_excerpt.csv`.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from psg_fatigue import analysis, config
from psg_fatigue.odds import (
    InvalidOddsError,
    add_odds_kpis,
    implied_probabilities,
    psg_perspective,
    roi_flat,
)
from psg_fatigue.parse.fd_matches import read_f1_csv, type_f1_table

FIXTURES = Path(__file__).parent / "fixtures"


def _psg_rows() -> pd.DataFrame:
    fd_l1 = type_f1_table(read_f1_csv(FIXTURES / "fd_F1_2526_excerpt.csv"), "2025-26")
    return psg_perspective(fd_l1, config.FD_PSG_LABEL).set_index("match_date")


# --- Margin removal (SPEC test 1) --------------------------------------------------


def test_margin_removal() -> None:
    result = implied_probabilities(pd.Series([1.25]), pd.Series([6.0]), pd.Series([11.0])).iloc[0]
    assert result["p_win"] + result["p_draw"] + result["p_loss"] == pytest.approx(1.0)
    assert result["p_win"] > result["p_draw"] > result["p_loss"]  # order of the odds kept
    assert result["overround"] == pytest.approx(1 / 1.25 + 1 / 6 + 1 / 11 - 1)
    assert result["p_win"] == pytest.approx((1 / 1.25) / (1 / 1.25 + 1 / 6 + 1 / 11))


@pytest.mark.parametrize("bad_odds", [1.0, 0.5, float("nan")])
def test_margin_removal_rejects_invalid_odds(bad_odds: float) -> None:
    with pytest.raises(InvalidOddsError):
        implied_probabilities(pd.Series([bad_odds]), pd.Series([6.0]), pd.Series([11.0]))


# --- ROI and residual (SPEC test 7) ------------------------------------------------


def test_roi_and_residual() -> None:
    assert roi_flat(pd.Series([1, 0]), pd.Series([1.30, 1.30])).tolist() == pytest.approx(
        [0.30, -1.0]
    )
    kpis = add_odds_kpis(_psg_rows())
    away_win = kpis.loc[pd.Timestamp("2025-08-17")]  # Nantes 0-1 Paris SG
    assert away_win["odds_source"] == "AvgC"
    assert away_win["residual_win"] == pytest.approx(1 - away_win["p_win_implied"])
    assert away_win["residual_win"] > 0  # a win always beats its implied probability
    assert away_win["roi_flat"] == pytest.approx(away_win["odds_win"] - 1)
    home_loss = kpis.loc[pd.Timestamp("2026-03-06")]  # Paris SG 1-3 Monaco
    assert home_loss["residual_win"] == pytest.approx(-home_loss["p_win_implied"])
    assert home_loss["roi_flat"] == -1.0
    assert home_loss["brier_win"] == pytest.approx(home_loss["p_win_implied"] ** 2)


def test_reference_odds_fallback_order() -> None:
    rows = _psg_rows()
    first, second = rows.index[0], rows.index[1]
    # Remove the closing average on one real row: Pinnacle closing takes over; remove both on
    # another row: Bet365 closing takes over (SPEC §4 fallback order).
    rows.loc[[first, second], ["odds_avgc_win", "odds_avgc_draw", "odds_avgc_loss"]] = np.nan
    rows.loc[second, ["odds_psc_win", "odds_psc_draw", "odds_psc_loss"]] = np.nan
    kpis = add_odds_kpis(rows)
    assert kpis.loc[first, "odds_source"] == "PSC"
    assert kpis.loc[first, "odds_win"] == rows.loc[first, "odds_psc_win"]
    assert kpis.loc[second, "odds_source"] == "B365C"
    assert (kpis["odds_source"].iloc[2:] == "AvgC").all()


# --- Bootstrap and decision rule ----------------------------------------------------


def test_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    residuals = add_odds_kpis(_psg_rows())["residual_win"]
    first = analysis.bootstrap_mean_ci(residuals)
    assert first == analysis.bootstrap_mean_ci(residuals)  # seed 42: same result every run
    mean, low, high = first
    assert low < mean < high
    assert mean == pytest.approx(residuals.mean())


@pytest.mark.parametrize(
    ("mean", "ci_high", "expected"),
    [(-0.05, -0.01, True), (-0.05, 0.02, False), (0.08, 0.22, False)],
)
def test_decision_rule(mean: float, ci_high: float, expected: bool) -> None:
    assert analysis.rule_satisfied(mean, ci_high) is expected
