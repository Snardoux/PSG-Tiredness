"""Betting odds: bookmaker margin, margin-free probabilities, PSG perspective, ROI.

Input grain: one Ligue 1 match with decimal 1X2 odds. Output grain: unchanged (one match).
"""

import pandas as pd


def overround(home: pd.Series, draw: pd.Series, away: pd.Series) -> pd.Series:
    """Bookmaker margin of each 1X2 triple: sum of 1/odds minus 1 (NaN if any odds missing)."""
    return 1 / home + 1 / draw + 1 / away - 1
