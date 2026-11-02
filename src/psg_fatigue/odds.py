"""Betting odds: bookmaker margin, margin-free probabilities, PSG perspective, ROI.

Input grain: one Ligue 1 match with decimal 1X2 odds (all clubs, `fd_l1`).
Output grain: one PSG Ligue 1 match seen from PSG (`fd_psg`): venue, opponent, goals,
shots, and every odds family expressed as PSG win / draw / loss.
"""

import pandas as pd

from psg_fatigue.parse.fd_matches import ODDS_FAMILIES

POINTS = {"W": 3, "D": 1, "L": 0}


def overround(home: pd.Series, draw: pd.Series, away: pd.Series) -> pd.Series:
    """Bookmaker margin of each 1X2 triple: sum of 1/odds minus 1 (NaN if any odds missing)."""
    return 1 / home + 1 / draw + 1 / away - 1


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
