"""Statistics and EDA tests (offline) on the real 2025-26 rows of the processed tables.

Fixtures `psg_l1_analytical_2025-26.csv` (34 Ligue 1 matches) and
`psg_matches_all_2025-26.csv` (56 official matches) are copied from data/processed/.
"""

import json
import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

from psg_fatigue import analysis
from psg_fatigue.eda import run_eda
from psg_fatigue.features import HIGH_LOAD_LABEL, NORMAL_LOAD_LABEL

FIXTURES = Path(__file__).parent / "fixtures"


def _analytical() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "psg_l1_analytical_2025-26.csv", parse_dates=["match_date"])


def test_summary_by_bucket_is_tidy_and_consistent() -> None:
    table = _analytical()
    summary = analysis.summary_by_bucket(table)
    assert list(summary.columns) == [
        "definition",
        "bucket",
        "kpi",
        "n",
        "mean",
        "ci_low",
        "ci_high",
    ]
    win = summary[(summary["definition"] == "primary") & (summary["kpi"] == "win_rate")]
    win = win.set_index("bucket")
    assert set(win.index) == {HIGH_LOAD_LABEL, NORMAL_LOAD_LABEL}
    assert win["n"].sum() == len(table)  # every match in exactly one bucket
    high = table[table["high_load"]]
    assert win.loc[HIGH_LOAD_LABEL, "mean"] == pytest.approx(high["psg_win"].mean())
    assert (summary["ci_low"] <= summary["mean"]).all()
    assert (summary["mean"] <= summary["ci_high"]).all()


def test_sensitivity_covers_every_definition() -> None:
    table = _analytical()
    sensitivity = analysis.sensitivity(table).set_index("definition")
    assert list(sensitivity.index) == ["primary", "alt4", "14d", "b365c"]
    assert sensitivity.loc["primary", "n_high"] == int(table["high_load"].sum())
    assert sensitivity.loc["14d", "n_high"] == int(table["high_load_14d"].sum())
    # The Bet365 sensitivity keeps the primary split but uses its own residual column.
    b365c_high = table.loc[table["high_load"], "residual_win_b365c"].mean()
    assert sensitivity.loc["b365c", "high_mean_residual"] == pytest.approx(b365c_high)
    for record in sensitivity.itertuples():
        expected = analysis.RECOMMEND if record.rule_satisfied else analysis.DO_NOT_RECOMMEND
        assert record.conclusion == expected


def test_bootstrap_difference_handles_an_empty_bucket() -> None:
    diff, low, high = analysis.bootstrap_difference_ci(pd.Series([], dtype=float), pd.Series([0.1]))
    assert math.isnan(diff)
    assert math.isnan(low)
    assert math.isnan(high)


def test_season_start_cumulates_residuals_in_date_order() -> None:
    window = analysis.season_start(_analytical())
    assert window["match_index"].tolist() == list(range(1, 9))
    assert window["match_date"].is_monotonic_increasing
    assert window["cum_residual"].iloc[-1] == pytest.approx(window["residual_win"].sum())
    assert (window["summer_break_days"] == 31).all()  # 2025: Club World Cup final -> Super Cup


def test_calibration_bins_cover_every_match() -> None:
    table = _analytical()
    calibration = analysis.calibration(table)
    assert calibration["n"].sum() == len(table)
    assert calibration["mean_implied_win_prob"].is_monotonic_increasing


def test_eda_end_to_end_writes_every_output(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    for name in ("psg_l1_analytical", "psg_matches_all"):
        shutil.copy(FIXTURES / f"{name}_2025-26.csv", processed / f"{name}.csv")
    out = tmp_path / "eda"
    decision = run_eda(processed, out)

    figures = sorted(path.name for path in out.glob("fig*.png"))
    assert len(figures) == 7
    for table in ("summary_by_bucket", "sensitivity", "season_start", "calibration"):
        assert (out / f"{table}.csv").is_file()
    saved = json.loads((out / "decision.json").read_text("utf-8"))
    assert saved == decision
    assert saved["n_matches"] == 34
    assert saved["conclusion"] in (analysis.RECOMMEND, analysis.DO_NOT_RECOMMEND)
    assert "## Decision rule" in (out / "EDA_REPORT.md").read_text("utf-8")
