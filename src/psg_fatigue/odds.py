"""Betting odds: bookmaker margin, margin-free probabilities, PSG perspective, ROI.

- `psg_perspective`: one Ligue 1 match with decimal 1X2 odds (all clubs, `fd_l1`) ->
  one PSG Ligue 1 match seen from PSG (`fd_psg`), every odds family as win / draw / loss.
- `add_odds_kpis`: one PSG Ligue 1 match -> same grain, plus reference odds, margin-free
  probabilities, residual, Brier score and flat-stake ROI.
"""

import numpy as np
import pandas as pd

from psg_fatigue.parse.fd_matches import ODDS_FAMILIES

POINTS = {"W": 3, "D": 1, "L": 0}
# Reference odds, in the fallback order of SPEC §4 (label stored in `odds_source`).
REFERENCE_ORDER = {"avgc": "AvgC", "psc": "PSC", "b365c": "B365C", "avg": "Avg"}


class InvalidOddsError(ValueError):
    """Decimal odds must be numbers greater than 1."""


def overround(home: pd.Series, draw: pd.Series, away: pd.Series) -> pd.Series:
    """Bookmaker margin of each 1X2 triple: sum of 1/odds minus 1 (NaN if any odds missing)."""
    return 1 / home + 1 / draw + 1 / away - 1


def implied_probabilities(win: pd.Series, draw: pd.Series, loss: pd.Series) -> pd.DataFrame:
    """Margin-free probabilities by proportional normalisation: p_i = (1/o_i) / sum_j (1/o_j).

    Returns `p_win`, `p_draw`, `p_loss` (summing to 1) and `overround`. Missing odds or odds
    <= 1 raise InvalidOddsError: incomplete triples must be filtered out before.
    """
    odds = pd.concat([win, draw, loss], axis=1)
    if odds.isna().to_numpy().any() or (odds <= 1).to_numpy().any():
        raise InvalidOddsError("Odds must be complete and greater than 1")
    inverse = 1 / odds
    total = inverse.sum(axis=1)
    return pd.DataFrame(
        {
            "p_win": inverse.iloc[:, 0] / total,
            "p_draw": inverse.iloc[:, 1] / total,
            "p_loss": inverse.iloc[:, 2] / total,
            "overround": total - 1,
        }
    )


def select_reference_odds(matches: pd.DataFrame) -> pd.DataFrame:
    """Per match, the first complete odds triple in the order AvgC -> PSC -> B365C -> Avg.

    Returns `odds_win`, `odds_draw`, `odds_loss` and `odds_source` (NA if no family is complete).
    """
    selected = pd.DataFrame(
        {"odds_win": np.nan, "odds_draw": np.nan, "odds_loss": np.nan, "odds_source": None},
        index=matches.index,
    )
    for family, label in REFERENCE_ORDER.items():
        triple = matches[[f"odds_{family}_{outcome}" for outcome in ("win", "draw", "loss")]]
        use = selected["odds_source"].isna() & triple.notna().all(axis=1)
        selected.loc[use, ["odds_win", "odds_draw", "odds_loss"]] = triple[use].to_numpy()
        selected.loc[use, "odds_source"] = label
    return selected


def roi_flat(psg_win: pd.Series, odds_win: pd.Series) -> pd.Series:
    """Profit of a 1-unit bet on a PSG win: odds - 1 if PSG wins, -1 otherwise."""
    return (odds_win - 1).where(psg_win == 1, -1.0)


def add_odds_kpis(matches: pd.DataFrame) -> pd.DataFrame:
    """Add reference odds, margin-free probabilities, residual, Brier score and flat ROI.

    Matches without any complete odds triple keep NA KPIs (they are counted, not dropped).
    `p_win_implied_b365c` / `residual_win_b365c` use Bet365 closing odds (sensitivity).
    """
    result = matches.join(select_reference_odds(matches))
    complete = result["odds_source"].notna()
    probabilities = implied_probabilities(
        result.loc[complete, "odds_win"],
        result.loc[complete, "odds_draw"],
        result.loc[complete, "odds_loss"],
    )
    result["overround"] = probabilities["overround"]
    result["p_win_implied"] = probabilities["p_win"]
    result["p_draw_implied"] = probabilities["p_draw"]
    result["p_loss_implied"] = probabilities["p_loss"]
    result["residual_win"] = result["psg_win"] - result["p_win_implied"]
    result["brier_win"] = (result["p_win_implied"] - result["psg_win"]) ** 2
    result["roi_flat"] = roi_flat(result["psg_win"], result["odds_win"]).where(complete)

    b365c = result[["odds_b365c_win", "odds_b365c_draw", "odds_b365c_loss"]].notna().all(axis=1)
    result["p_win_implied_b365c"] = implied_probabilities(
        result.loc[b365c, "odds_b365c_win"],
        result.loc[b365c, "odds_b365c_draw"],
        result.loc[b365c, "odds_b365c_loss"],
    )["p_win"]
    result["residual_win_b365c"] = result["psg_win"] - result["p_win_implied_b365c"]
    return result


def psg_perspective(fd_l1: pd.DataFrame, psg_label: str) -> pd.DataFrame:
    """Keep PSG's matches and express each one from PSG's side.

    For a home match PSG's win odds are the home odds; for an away match, the away odds.
    The result (W/D/L) comes from the full-time result `FTR` (H/D/A) and the venue.
    """
    is_home = fd_l1["home_team"] == psg_label
    psg = fd_l1[is_home | (fd_l1["away_team"] == psg_label)]
    home = is_home[psg.index]

    def side(home_column: str, away_column: str) -> pd.Series:
        """PSG's value: the home column when PSG is at home, the away column otherwise."""
        return psg[home_column].where(home, psg[away_column])

    view = pd.DataFrame(
        {
            "season": psg["season"],
            "match_date": psg["match_date"],
            "venue": home.map({True: "H", False: "A"}),
            "opponent_fd": side("away_team", "home_team"),
            "psg_goals": side("home_goals", "away_goals"),
            "opp_goals": side("away_goals", "home_goals"),
            "psg_shots": side("home_shots", "away_shots"),
            "opp_shots": side("away_shots", "home_shots"),
            "psg_sot": side("home_sot", "away_sot"),
            "opp_sot": side("away_sot", "home_sot"),
        }
    )
    psg_won = psg["ft_result"] == home.map({True: "H", False: "A"})  # FTR names the winner
    view["psg_result"] = "L"
    view.loc[psg["ft_result"] == "D", "psg_result"] = "D"
    view.loc[psg_won, "psg_result"] = "W"
    view["psg_win"] = (view["psg_result"] == "W").astype(int)
    view["psg_points"] = view["psg_result"].map(POINTS).astype(int)
    view["sot_diff"] = view["psg_sot"] - view["opp_sot"]
    for name in ODDS_FAMILIES.values():
        view[f"odds_{name}_win"] = side(f"odds_{name}_h", f"odds_{name}_a")
        view[f"odds_{name}_draw"] = psg[f"odds_{name}_d"]
        view[f"odds_{name}_loss"] = side(f"odds_{name}_a", f"odds_{name}_h")
    return view.reset_index(drop=True)
