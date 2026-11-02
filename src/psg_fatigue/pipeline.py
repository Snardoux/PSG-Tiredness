"""Offline pipeline steps behind `psg-fatigue build | eda | all` (no network access).

build: raw snapshot (verified against its manifest) -> parsed tables in data/interim/
       -> quality reports -> load features -> join of the two sources -> odds KPIs
       -> data/processed/.
eda:   data/processed/ -> statistics, figures and tables in reports/eda/.
"""

import logging

import pandas as pd

from psg_fatigue import config, eda, quality
from psg_fatigue.collect.snapshot import verify_snapshot
from psg_fatigue.features import build_match_features
from psg_fatigue.integrate import (
    join_sources,
    load_team_names,
    to_canonical,
    write_integration_report,
)
from psg_fatigue.odds import add_odds_kpis, psg_perspective
from psg_fatigue.parse.fd_matches import parse_fd_snapshot
from psg_fatigue.parse.wiki_matches import parse_wiki_snapshot

logger = logging.getLogger(__name__)

# processed/psg_matches_all.csv: one PSG official played match (SPEC §12).
MATCHES_ALL_COLUMNS = [
    "match_id",
    "season",
    "match_date",
    "competition",
    "round",
    "venue",
    "opponent",
    "played",
    "psg_goals",
    "opp_goals",
    "psg_result",
    "decided_by",
    "rest_days",
    "matches_last_14d",
    "wiki_revid",
]
# processed/psg_l1_analytical.csv: one PSG Ligue 1 match, PSG perspective (SPEC §12).
# Source column in the joined table -> output column. Goals, venue and result come from
# football-data; the integration report shows they agree with Wikipedia on every row.
ANALYTICAL_COLUMNS = {
    "match_id": "match_id",
    "season_fd": "season",
    "match_date": "match_date",
    "matchday": "matchday",
    "venue_fd": "venue",
    "opponent_canonical": "opponent",
    "psg_goals_fd": "psg_goals",
    "opp_goals_fd": "opp_goals",
    "psg_result_fd": "psg_result",
    "psg_win": "psg_win",
    "psg_points": "psg_points",
    "psg_sot": "psg_sot",
    "opp_sot": "opp_sot",
    "sot_diff": "sot_diff",
    "odds_win": "odds_win",
    "odds_draw": "odds_draw",
    "odds_loss": "odds_loss",
    "odds_source": "odds_source",
    "overround": "overround",
    "p_win_implied": "p_win_implied",
    "p_draw_implied": "p_draw_implied",
    "p_loss_implied": "p_loss_implied",
    "p_win_implied_b365c": "p_win_implied_b365c",
    "residual_win": "residual_win",
    "residual_win_b365c": "residual_win_b365c",
    "brier_win": "brier_win",
    "roi_flat": "roi_flat",
    "rest_days": "rest_days",
    "prev_competition": "prev_competition",
    "matches_last_14d": "matches_last_14d",
    "next_rest_days": "next_rest_days",
    "next_competition": "next_competition",
    "ucl_within_4d_after": "ucl_within_4d_after",
    "high_load": "high_load",
    "high_load_alt4": "high_load_alt4",
    "high_load_14d": "high_load_14d",
    "load_bucket": "load_bucket",
    "summer_break_days": "summer_break_days",
    "league_match_index": "league_match_index",
    "season_start_window": "season_start_window",
    "post_cwc_start": "post_cwc_start",
    "join_method": "join_method",
    "score_check_ok": "score_check_ok",
}


def write_interim(table: pd.DataFrame, name: str) -> None:
    """Save an intermediate table as Parquet (keeps dtypes; rebuilt by every build)."""
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    path = config.INTERIM_DIR / f"{name}.parquet"
    table.to_parquet(path, index=False)
    logger.info("Wrote %s (%d rows)", path.as_posix(), len(table))


def write_processed(table: pd.DataFrame, name: str) -> None:
    """Save a Tableau-ready CSV: ISO dates, Unix line endings, fixed column order."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PROCESSED_DIR / f"{name}.csv"
    decimals = dict.fromkeys(table.select_dtypes("float").columns, 6)  # dates untouched
    table.round(decimals).to_csv(path, index=False, lineterminator="\n", date_format="%Y-%m-%d")
    logger.info("Wrote %s (%d rows, %d columns)", path.as_posix(), len(table), table.shape[1])


def run_build(snapshot_id: str) -> None:
    """Rebuild every derived table and report from the frozen raw snapshot."""
    snapshot_dir = config.RAW_DIR / snapshot_id
    verify_snapshot(snapshot_dir)

    # 1. Parse both sources.
    calendar, overall_record, excluded = parse_wiki_snapshot(snapshot_dir)
    fd_l1, fd_columns = parse_fd_snapshot(snapshot_dir)
    write_interim(calendar, "psg_calendar")
    write_interim(fd_l1, "fd_l1")

    # 2. Load features (one played official match, Luis Enrique era).
    matches = build_match_features(calendar)

    # 3. Quality investigation (stops the build if an expected count does not match).
    quality.run_quality(
        calendar,
        overall_record,
        excluded,
        fd_l1,
        fd_columns,
        matches,
        snapshot_id,
        config.QUALITY_DIR,
    )

    # 4. Integration: football-data PSG matches (odds) x Wikipedia Ligue 1 matches (load).
    mapping = load_team_names(config.TEAM_NAMES_CSV)
    fd_psg = psg_perspective(fd_l1, config.FD_PSG_LABEL)
    fd_psg["opponent_canonical"] = to_canonical(fd_psg["opponent_fd"], mapping, "footballdata_name")
    wiki_l1 = matches[matches["competition"] == config.LEAGUE].copy()
    wiki_l1["opponent_canonical"] = to_canonical(wiki_l1["opponent"], mapping, "wikipedia_name")
    joined, report = join_sources(fd_psg, wiki_l1)
    write_integration_report(report, config.QUALITY_DIR)
    write_interim(fd_psg, "fd_psg")
    write_interim(joined, "l1_joined")

    # 5. Odds KPIs and processed outputs.
    analytical = add_odds_kpis(joined)[list(ANALYTICAL_COLUMNS)].rename(columns=ANALYTICAL_COLUMNS)
    write_processed(matches[MATCHES_ALL_COLUMNS], "psg_matches_all")
    write_processed(analytical, "psg_l1_analytical")


def run_eda() -> None:
    """Compute the statistics and draw the figures from data/processed/ (offline)."""
    eda.run_eda(config.PROCESSED_DIR, config.EDA_DIR)
