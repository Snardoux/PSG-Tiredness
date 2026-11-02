"""Statistics behind the findings: KPIs by load bucket, bootstrap CIs, decision rule.

Input grain: one PSG Ligue 1 match (`processed/psg_l1_analytical.csv`).
Output grains: one load definition x bucket x KPI (`summary_by_bucket`); one load
definition (`sensitivity`); one season x match of the season-start window (`season_start`);
one season (`season_start_summary`); one implied-probability bin (`calibration`).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from psg_fatigue import config
from psg_fatigue.features import HIGH_LOAD_LABEL, NORMAL_LOAD_LABEL

# KPI name -> column of the analytical table (PSG perspective, one row per match).
KPIS = {
    "win_rate": "psg_win",
    "points_per_match": "psg_points",
    "implied_win_prob": "p_win_implied",
    "mean_residual": "residual_win",
    "brier": "brier_win",
    "roi_flat": "roi_flat",
    "sot_diff": "sot_diff",
}
CALIBRATION_BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 1.0]  # chosen from the observed range 0.29-0.89
DECISION_RULE = (
    "Recommend a fatigue adjustment only if the mean residual in high-load matches is "
    "negative and its 90% bootstrap confidence interval excludes zero."
)
RECOMMEND = "Recommend a fatigue adjustment"
DO_NOT_RECOMMEND = "The data does not support an adjustment"


@dataclass(frozen=True)
class LoadDefinition:
    """One way of splitting matches into high and normal load (primary or sensitivity)."""

    name: str
    description: str
    flag: str  # boolean column of the analytical table: True = high load
    high_label: str
    normal_label: str
    kpis: dict[str, str] = field(default_factory=lambda: dict(KPIS))


DEFINITIONS = (
    LoadDefinition("primary", "rest days <= 3", "high_load", HIGH_LOAD_LABEL, NORMAL_LOAD_LABEL),
    LoadDefinition(
        "alt4", "rest days <= 4", "high_load_alt4", "High (≤4 days)", "Normal (≥5 days)"
    ),
    LoadDefinition(
        "14d",
        ">= 4 official matches in the previous 14 days",
        "high_load_14d",
        "High (≥4 matches in 14 days)",
        "Normal (<4 matches in 14 days)",
    ),
    # Same split as primary, but implied probabilities from Bet365 closing odds.
    LoadDefinition(
        "b365c",
        "rest days <= 3, Bet365 closing odds",
        "high_load",
        HIGH_LOAD_LABEL,
        NORMAL_LOAD_LABEL,
        kpis={
            "implied_win_prob": "p_win_implied_b365c",
            "mean_residual": "residual_win_b365c",
        },
    ),
)


def bootstrap_mean_ci(
    values: np.ndarray | pd.Series,
    resamples: int = config.BOOTSTRAP_RESAMPLES,
    level: float = config.CI_LEVEL,
    seed: int = config.RANDOM_SEED,
) -> tuple[float, float, float]:
    """Mean and percentile bootstrap confidence interval of the mean: (mean, low, high)."""
    data = np.asarray(values, dtype=float)
    if len(data) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = rng.choice(data, size=(resamples, len(data)), replace=True).mean(axis=1)
    tail = 100 * (1 - level) / 2
    low, high = np.percentile(means, [tail, 100 - tail])
    return float(data.mean()), float(low), float(high)


def bootstrap_difference_ci(
    first: np.ndarray | pd.Series,
    second: np.ndarray | pd.Series,
    resamples: int = config.BOOTSTRAP_RESAMPLES,
    level: float = config.CI_LEVEL,
    seed: int = config.RANDOM_SEED,
) -> tuple[float, float, float]:
    """Difference of means (first - second) with a bootstrap CI; groups resampled separately."""
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    if len(a) == 0 or len(b) == 0:  # e.g. no high-load match under a definition
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means_a = rng.choice(a, size=(resamples, len(a)), replace=True).mean(axis=1)
    means_b = rng.choice(b, size=(resamples, len(b)), replace=True).mean(axis=1)
    tail = 100 * (1 - level) / 2
    low, high = np.percentile(means_a - means_b, [tail, 100 - tail])
    return float(a.mean() - b.mean()), float(low), float(high)


def rule_satisfied(mean_residual: float, ci_high: float) -> bool:
    """Decision rule: negative mean residual whose CI excludes zero (so its upper bound < 0)."""
    return bool(mean_residual < 0 and ci_high < 0)


def known_load(table: pd.DataFrame) -> pd.DataFrame:
    """Matches whose rest days are known (the 'Unknown' bucket is excluded from comparisons)."""
    return table[table["rest_days"].notna()]


def summary_by_bucket(table: pd.DataFrame) -> pd.DataFrame:
    """One row per definition x bucket x KPI: n, mean and 90% bootstrap CI (tidy, Tableau-ready)."""
    rows = []
    data = known_load(table)
    for definition in DEFINITIONS:
        high = data[definition.flag].astype(bool)
        for bucket, in_bucket in ((definition.high_label, high), (definition.normal_label, ~high)):
            for kpi, column in definition.kpis.items():
                values = data.loc[in_bucket, column].dropna()
                mean, low, upper = bootstrap_mean_ci(values)
                rows.append(
                    {
                        "definition": definition.name,
                        "bucket": bucket,
                        "kpi": kpi,
                        "n": len(values),
                        "mean": mean,
                        "ci_low": low,
                        "ci_high": upper,
                    }
                )
    return pd.DataFrame(rows)


def sensitivity(table: pd.DataFrame) -> pd.DataFrame:
    """Decision-rule outcome under each load definition (one row per definition)."""
    rows = []
    data = known_load(table)
    for definition in DEFINITIONS:
        residual = data[definition.kpis["mean_residual"]]
        high = data[definition.flag].astype(bool)
        high_values, normal_values = residual[high].dropna(), residual[~high].dropna()
        high_mean, high_low, high_upper = bootstrap_mean_ci(high_values)
        normal_mean, normal_low, normal_upper = bootstrap_mean_ci(normal_values)
        diff, diff_low, diff_upper = bootstrap_difference_ci(high_values, normal_values)
        satisfied = rule_satisfied(high_mean, high_upper)
        rows.append(
            {
                "definition": definition.name,
                "description": definition.description,
                "n_high": len(high_values),
                "n_normal": len(normal_values),
                "high_mean_residual": high_mean,
                "high_ci_low": high_low,
                "high_ci_high": high_upper,
                "normal_mean_residual": normal_mean,
                "normal_ci_low": normal_low,
                "normal_ci_high": normal_upper,
                "diff_high_minus_normal": diff,
                "diff_ci_low": diff_low,
                "diff_ci_high": diff_upper,
                "rule_satisfied": satisfied,
                "conclusion": RECOMMEND if satisfied else DO_NOT_RECOMMEND,
            }
        )
    return pd.DataFrame(rows)


def decision(table: pd.DataFrame, sensitivity_table: pd.DataFrame) -> dict[str, Any]:
    """Primary decision-rule result, as written to decision.json."""
    primary = sensitivity_table.set_index("definition").to_dict("index")["primary"]

    def rounded(value: Any) -> float:
        return round(float(value), 4)

    return {
        "question": (
            "Under Luis Enrique, does fixture congestion reduce PSG's Ligue 1 results beyond "
            "what closing odds already anticipate?"
        ),
        "high_load_definition": f"rest days <= {config.HIGH_LOAD_MAX_REST_DAYS}",
        "reference_odds": "market-average closing odds (AvgC), margin removed proportionally",
        "residual": "psg_win - p_win_implied",
        "n_matches": len(table),
        "n_unknown_load": int(table["rest_days"].isna().sum()),
        "n_high_load": int(primary["n_high"]),
        "n_normal_load": int(primary["n_normal"]),
        "high_load_mean_residual": rounded(primary["high_mean_residual"]),
        "high_load_ci90": [rounded(primary["high_ci_low"]), rounded(primary["high_ci_high"])],
        "normal_load_mean_residual": rounded(primary["normal_mean_residual"]),
        "normal_load_ci90": [rounded(primary["normal_ci_low"]), rounded(primary["normal_ci_high"])],
        "difference_high_minus_normal": rounded(primary["diff_high_minus_normal"]),
        "difference_ci90": [rounded(primary["diff_ci_low"]), rounded(primary["diff_ci_high"])],
        "rule": DECISION_RULE,
        "rule_satisfied": bool(primary["rule_satisfied"]),
        "conclusion": str(primary["conclusion"]),
        "bootstrap": {
            "resamples": config.BOOTSTRAP_RESAMPLES,
            "seed": config.RANDOM_SEED,
            "level": config.CI_LEVEL,
            "method": "percentile",
        },
    }


def season_start(table: pd.DataFrame) -> pd.DataFrame:
    """First 8 Ligue 1 matches of each season with the cumulative residual (computed here,
    not in Tableau, so that the workbook matches the pipeline exactly)."""
    window = table[table["season_start_window"].astype(bool)].sort_values(["season", "match_date"])
    result = window[
        [
            "season",
            "league_match_index",
            "match_date",
            "opponent",
            "psg_result",
            "p_win_implied",
            "residual_win",
            "summer_break_days",
        ]
    ].rename(columns={"league_match_index": "match_index"})
    result["cum_residual"] = result.groupby("season")["residual_win"].cumsum()
    order = ["season", "match_index", "match_date", "opponent", "psg_result", "p_win_implied"]
    return result[[*order, "residual_win", "cum_residual", "summer_break_days"]].reset_index(
        drop=True
    )


def season_start_summary(window: pd.DataFrame) -> pd.DataFrame:
    """One row per season: results and mean residual of the season-start window."""
    rows = []
    for season, group in window.groupby("season", sort=True):
        mean, low, upper = bootstrap_mean_ci(group["residual_win"])
        rows.append(
            {
                "season": season,
                "n": len(group),
                "wins": int((group["psg_result"] == "W").sum()),
                "win_rate": float((group["psg_result"] == "W").mean()),
                "mean_implied_win_prob": float(group["p_win_implied"].mean()),
                "mean_residual": mean,
                "ci_low": low,
                "ci_high": upper,
                "cum_residual_after_8": float(group["residual_win"].sum()),
                "summer_break_days": int(group["summer_break_days"].iloc[0]),
            }
        )
    return pd.DataFrame(rows)


def calibration(table: pd.DataFrame) -> pd.DataFrame:
    """Actual win rate vs mean implied probability in implied-probability bins."""
    bins = pd.cut(table["p_win_implied"], CALIBRATION_BINS, right=False)
    rows = []
    for interval, group in table.groupby(bins, observed=True, sort=True):
        mean, low, upper = bootstrap_mean_ci(group["psg_win"])
        rows.append(
            {
                "bin": f"[{interval.left:.1f}, {interval.right:.1f})",
                "n": len(group),
                "mean_implied_win_prob": float(group["p_win_implied"].mean()),
                "actual_win_rate": mean,
                "ci_low": low,
                "ci_high": upper,
            }
        )
    return pd.DataFrame(rows)
