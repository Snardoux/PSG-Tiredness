"""Data quality investigation, run on the parsed tables before any data-changing step.

Input grain: `psg_calendar` (one PSG official fixture), `fd_l1` (one Ligue 1 match) and the
Wikipedia "Overall record" table (one season x competition). Output: tidy CSV files in
`reports/quality/` (counts, column availability, profiles, checks) and `quality_report.md`.
Failed count checks stop the build, after the reports have been written as evidence.
"""

import itertools
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from psg_fatigue import config
from psg_fatigue.odds import overround
from psg_fatigue.parse.fd_matches import ODDS_FAMILIES

logger = logging.getLogger(__name__)

ODDS_MIN, ODDS_MAX = 1.01, 50.0  # decimal odds outside (1.01, 50] are flagged
OVERROUND_MIN, OVERROUND_MAX = 0.0, 0.15
MAX_GOALS = 9
NEAR_DUPLICATE_DAYS = 3
MIN_REST_DAYS, MAX_REST_DAYS = 2, 30  # SPEC §10: unusual rest outside season starts

FD_PROFILE_COLUMNS = [
    "match_date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "ft_result",
    "home_shots",
    "away_shots",
    "home_sot",
    "away_sot",
    *[f"odds_{name}_{side}" for name in ODDS_FAMILIES.values() for side in "hda"],
]
CALENDAR_PROFILE_COLUMNS = [
    "competition",
    "round",
    "matchday",
    "match_date",
    "played",
    "venue",
    "opponent",
    "psg_goals",
    "opp_goals",
    "decided_by",
    "attendance",
]


class QualityCheckError(RuntimeError):
    """An expected count does not match: stop and investigate before going further."""


def _format_value(value: Any) -> str:
    """Readable min/max value for the profile tables."""
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value)


def profile(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """One row per season x column: dtype, rows, missing values, distinct values, min, max."""
    rows = []
    for season, group in table.groupby("season", sort=True):
        for column in columns:
            values = group[column]
            present = values.dropna()
            orderable = not pd.api.types.is_bool_dtype(values) and (
                pd.api.types.is_numeric_dtype(values)
                or pd.api.types.is_datetime64_any_dtype(values)
            )
            rows.append(
                {
                    "season": season,
                    "column": column,
                    "dtype": str(values.dtype),
                    "rows": len(values),
                    "missing": int(values.isna().sum()),
                    "missing_pct": round(100 * float(values.isna().mean()), 1),
                    "distinct": int(present.nunique()),
                    "min": _format_value(present.min()) if orderable and len(present) else "",
                    "max": _format_value(present.max()) if orderable and len(present) else "",
                }
            )
    return pd.DataFrame(rows)


def wikipedia_counts(calendar: pd.DataFrame, overall_record: pd.DataFrame) -> pd.DataFrame:
    """Parsed played/scheduled fixtures vs the page's Overall record, per season x competition.

    A total row per season ('All official competitions') is appended.
    """
    keys = ["season", "competition"]
    played = calendar[calendar["played"]].groupby(keys).size().rename("parsed_played")
    scheduled = calendar[~calendar["played"]].groupby(keys).size().rename("parsed_scheduled")
    record = overall_record.set_index(keys)["played"].rename("overall_record_played")
    counts = pd.concat([played, scheduled, record], axis=1).fillna(0).astype(int).reset_index()
    totals = counts.groupby("season", as_index=False)[
        ["parsed_played", "parsed_scheduled", "overall_record_played"]
    ].sum()
    totals["competition"] = "All official competitions"
    counts = pd.concat([counts, totals], ignore_index=True)
    counts["difference"] = counts["parsed_played"] - counts["overall_record_played"]
    counts["status"] = counts["difference"].map(lambda d: "ok" if d == 0 else "MISMATCH")
    is_total = counts["competition"] == "All official competitions"
    counts["_order"] = is_total.astype(int)
    counts = counts.sort_values(["season", "_order", "competition"]).drop(columns="_order")
    return counts.reset_index(drop=True)


def fd_counts(fd_l1: pd.DataFrame) -> pd.DataFrame:
    """Rows, PSG rows, date range and number of clubs per football-data season."""
    rows = []
    for season, group in fd_l1.groupby("season", sort=True):
        complete = season in config.COMPLETE_SEASONS
        is_psg = (group["home_team"] == config.FD_PSG_LABEL) | (
            group["away_team"] == config.FD_PSG_LABEL
        )
        expected_rows = config.L1_MATCHES_PER_SEASON if complete else None
        expected_psg = config.PSG_L1_MATCHES_PER_SEASON if complete else None
        ok = (len(group) == expected_rows and int(is_psg.sum()) == expected_psg) or not complete
        rows.append(
            {
                "season": season,
                "rows": len(group),
                "expected_rows": expected_rows,
                "psg_rows": int(is_psg.sum()),
                "expected_psg_rows": expected_psg,
                "clubs": len(set(group["home_team"]) | set(group["away_team"])),
                "first_date": group["match_date"].min().date().isoformat(),
                "last_date": group["match_date"].max().date().isoformat(),
                "status": ("ok" if ok else "MISMATCH") if complete else "partial season",
            }
        )
    counts = pd.DataFrame(rows)
    for column in ("expected_rows", "expected_psg_rows"):
        counts[column] = counts[column].astype("Int64")
    return counts


def paris_labels(fd_l1: pd.DataFrame) -> pd.DataFrame:
    """Club labels containing 'Paris' per season: PSG must be present and distinct from Paris FC."""
    rows = []
    for season, group in fd_l1.groupby("season", sort=True):
        labels = sorted(
            label for label in set(group["home_team"]) | set(group["away_team"]) if "Paris" in label
        )
        rows.append({"season": season, "labels": "; ".join(labels)})
    return pd.DataFrame(rows)


def near_duplicates(calendar: pd.DataFrame) -> pd.DataFrame:
    """Pairs of fixtures with the same competition and opponent within ±3 days."""
    dated = calendar.dropna(subset=["match_date", "opponent"]).sort_values("match_date")
    pairs = []
    for (competition, opponent), group in dated.groupby(["competition", "opponent"]):
        dates = group["match_date"].tolist()
        for previous, current in itertools.pairwise(dates):
            if (current - previous).days <= NEAR_DUPLICATE_DAYS:
                pairs.append(
                    {
                        "competition": competition,
                        "opponent": opponent,
                        "first_date": previous.date().isoformat(),
                        "second_date": current.date().isoformat(),
                    }
                )
    return pd.DataFrame(pairs, columns=["competition", "opponent", "first_date", "second_date"])


def odds_checks(fd_l1: pd.DataFrame) -> pd.DataFrame:
    """Per odds family: complete triples, odds outside (1.01, 50], overround outside [0, 0.15]."""
    rows = []
    for name in ODDS_FAMILIES.values():
        triple = fd_l1[[f"odds_{name}_{side}" for side in "hda"]]
        complete = triple.notna().all(axis=1)
        values = triple.to_numpy(dtype=float)  # NaN compares False: missing odds not flagged
        margin = overround(triple.iloc[:, 0], triple.iloc[:, 1], triple.iloc[:, 2])[complete]
        rows.append(
            {
                "odds_family": name,
                "complete_triples": int(complete.sum()),
                "incomplete_triples": int((~complete).sum()),
                "odds_out_of_range": int(((values <= ODDS_MIN) | (values > ODDS_MAX)).sum()),
                "overround_out_of_range": int(
                    ((margin < OVERROUND_MIN) | (margin > OVERROUND_MAX)).sum()
                ),
                "overround_min": round(float(margin.min()), 4) if len(margin) else None,
                "overround_max": round(float(margin.max()), 4) if len(margin) else None,
            }
        )
    return pd.DataFrame(rows)


def rest_day_outliers(matches: pd.DataFrame) -> pd.DataFrame:
    """Unusual rest days: fewer than 2, or more than 30 for a match that does not open a season."""
    season_opener = (
        matches.groupby("season")["match_date"].transform("min") == matches["match_date"]
    )
    rest = matches["rest_days"]
    too_short = (rest < MIN_REST_DAYS).fillna(False)
    too_long = ((rest > MAX_REST_DAYS) & ~season_opener).fillna(False)
    outliers = matches[too_short | too_long][
        ["season", "match_date", "competition", "opponent", "rest_days"]
    ]
    return outliers.assign(match_date=outliers["match_date"].dt.strftime("%Y-%m-%d"))


def out_of_matchday_order(matches: pd.DataFrame) -> pd.DataFrame:
    """Ligue 1 matches whose date rank in the season differs from their matchday number.

    These are the rows whose rest days would be wrong if computed in matchday order.
    """
    league = matches[matches["competition"] == config.LEAGUE]
    date_rank = league.groupby("season")["match_date"].rank(method="first").astype(int)
    moved = league[date_rank != league["matchday"]]
    return moved[["season", "matchday", "match_date", "opponent", "rest_days"]].assign(
        date_rank=date_rank[moved.index], match_date=moved["match_date"].dt.strftime("%Y-%m-%d")
    )


def run_checks(
    calendar: pd.DataFrame, fd_l1: pd.DataFrame, matches: pd.DataFrame, snapshot_id: str
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Duplicates, near duplicates, unusual values and consistency checks.

    Returns one row per check (name, value, status) and the detail tables behind them.
    """
    played = calendar[calendar["played"]]
    rest_outliers = rest_day_outliers(matches)
    fd_key_dupes = fd_l1[fd_l1.duplicated(["match_date", "home_team", "away_team"], keep=False)]
    fd_pair_dupes = fd_l1[fd_l1.duplicated(["season", "home_team", "away_team"], keep=False)]
    cal_key_dupes = calendar.dropna(subset=["match_date"])
    cal_key_dupes = cal_key_dupes[
        cal_key_dupes.duplicated(["match_date", "competition", "opponent"], keep=False)
    ]
    near = near_duplicates(calendar)
    result_mismatch = played[played["psg_result"] != played["wiki_result"]]
    snapshot_date = pd.Timestamp(snapshot_id)
    unplayed_past = calendar[~calendar["played"] & (calendar["match_date"] < snapshot_date)]
    goals_fd = fd_l1[(fd_l1["home_goals"] > MAX_GOALS) | (fd_l1["away_goals"] > MAX_GOALS)]
    goals_wiki = played[(played["psg_goals"] > MAX_GOALS) | (played["opp_goals"] > MAX_GOALS)]
    sot_above_shots = fd_l1[
        (fd_l1["home_sot"] > fd_l1["home_shots"]) | (fd_l1["away_sot"] > fd_l1["away_shots"])
    ]
    odds = odds_checks(fd_l1)
    closing_avg = odds.set_index("odds_family").to_dict("index")["avgc"]  # reference odds

    def row(check: str, value: int, warn_only: bool = False) -> dict[str, Any]:
        status = "ok" if value == 0 else ("warning" if warn_only else "FAIL")
        return {"check": check, "value": value, "status": status}

    checks = pd.DataFrame(
        [
            row("F1 duplicates on (Date, HomeTeam, AwayTeam)", len(fd_key_dupes)),
            row("F1 same home/away pairing twice in a season", len(fd_pair_dupes)),
            row("calendar duplicates on (date, competition, opponent)", len(cal_key_dupes)),
            row("calendar near duplicates (same opponent+competition <= 3 days)", len(near)),
            row("Wikipedia result field != result from parsed score", len(result_mismatch)),
            row("unplayed fixtures dated before the snapshot", len(unplayed_past)),
            row("F1 matches with more than 9 goals for a team", len(goals_fd), warn_only=True),
            row("PSG matches with more than 9 goals for a team", len(goals_wiki), warn_only=True),
            row("F1 rows with shots on target > shots", len(sot_above_shots)),
            row(
                "closing-average odds outside (1.01, 50]",
                int(closing_avg["odds_out_of_range"]),
                warn_only=True,
            ),
            row(
                "closing-average overround outside [0, 0.15]",
                int(closing_avg["overround_out_of_range"]),
                warn_only=True,
            ),
            row(
                "rest days < 2, or > 30 outside season openers (Luis Enrique era)",
                len(rest_outliers),
                warn_only=True,
            ),
        ]
    )
    details = {
        "near_duplicates": near,
        "odds_checks": odds,
        "rescheduled": played[played["rescheduled"]],
        "rest_outliers": rest_outliers,
        "out_of_matchday_order": out_of_matchday_order(matches),
    }
    return checks, details


def markdown_table(table: pd.DataFrame) -> str:
    """Render a small DataFrame as a GitHub-flavoured Markdown table."""
    if table.empty:
        return "_(none)_"
    header = "| " + " | ".join(str(column) for column in table.columns) + " |"
    separator = "|" + "---|" * len(table.columns)
    body = [
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in record) + " |"
        for record in table.itertuples(index=False)
    ]
    return "\n".join([header, separator, *body])


def build_report(
    snapshot_id: str,
    wiki_counts: pd.DataFrame,
    fd_count_table: pd.DataFrame,
    fd_columns: pd.DataFrame,
    fd_profile: pd.DataFrame,
    excluded: pd.DataFrame,
    labels: pd.DataFrame,
    checks: pd.DataFrame,
    details: dict[str, pd.DataFrame],
) -> str:
    """Assemble quality_report.md from the generated tables (numbers only, no opinions)."""
    availability = fd_columns.pivot(index="column", columns="season", values="present")
    availability = availability.loc[list(fd_columns["column"].unique())]  # keep file order
    availability = availability.map(lambda present: "yes" if present else "**no**").reset_index()
    n_columns = fd_columns.groupby("season")["n_columns_in_file"].first().reset_index()
    missing = fd_profile[fd_profile["missing"] > 0][["season", "column", "missing", "rows"]]
    rescheduled = details["rescheduled"][
        ["season", "competition", "round", "match_date", "opponent"]
    ].assign(match_date=lambda t: t["match_date"].dt.date.astype(str))
    sections = [
        "# Data quality report",
        "",
        f"Generated by `uv run psg-fatigue build` from raw snapshot `{snapshot_id}`. "
        "Numbers only; decisions are logged in `docs/QUALITY_NOTE.md`.",
        "",
        "## 1. Wikipedia: parsed matches vs each page's Overall record",
        "",
        "`overall_record_played` = W + D + L of the page's `Fb overview2` table. "
        "Scheduled = fixtures listed but not yet played.",
        "",
        markdown_table(wiki_counts),
        "",
        "## 2. football-data.co.uk: rows per season",
        "",
        markdown_table(fd_count_table),
        "",
        "Club labels containing 'Paris' (PSG must be distinct from Paris FC):",
        "",
        markdown_table(labels),
        "",
        "## 3. football-data.co.uk: columns used, availability per season",
        "",
        markdown_table(n_columns),
        "",
        markdown_table(availability),
        "",
        "## 4. Missing values in the columns used (football-data)",
        "",
        markdown_table(missing),
        "",
        "## 5. Odds: completeness, range and bookmaker margin per family",
        "",
        markdown_table(details["odds_checks"]),
        "",
        "## 6. Duplicates, near duplicates, unusual values, consistency",
        "",
        markdown_table(checks),
        "",
        "Near duplicates (same competition and opponent within 3 days):",
        "",
        markdown_table(details["near_duplicates"]),
        "",
        "## 7. Rest days (Luis Enrique era, all official matches)",
        "",
        "Unusual values: fewer than 2 days, or more than 30 days for a match that does not "
        "open a season:",
        "",
        markdown_table(details["rest_outliers"]),
        "",
        "Ligue 1 matches played out of matchday order (their date rank differs from their "
        "matchday): rest days computed in matchday order would be wrong for them.",
        "",
        markdown_table(details["out_of_matchday_order"]),
        "",
        "## 8. Rows excluded or flagged",
        "",
        "Friendlies excluded from the calendar (not official matches):",
        "",
        markdown_table(excluded),
        "",
        "Played matches whose box notes a postponement or a new date "
        "(rest days are computed on actual dates, not matchdays):",
        "",
        markdown_table(rescheduled),
        "",
    ]
    return "\n".join(sections)


def write_csv(table: pd.DataFrame, path: Path) -> None:
    """Write a CSV with Unix line endings (deterministic output)."""
    table.to_csv(path, index=False, lineterminator="\n")


def run_quality(
    calendar: pd.DataFrame,
    overall_record: pd.DataFrame,
    excluded: pd.DataFrame,
    fd_l1: pd.DataFrame,
    fd_columns: pd.DataFrame,
    matches: pd.DataFrame,
    snapshot_id: str,
    out_dir: Path,
) -> None:
    """Write every quality output, then stop the build if an expected count does not match."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wiki_counts = wikipedia_counts(calendar, overall_record)
    fd_count_table = fd_counts(fd_l1)
    fd_profile = profile(fd_l1, FD_PROFILE_COLUMNS)
    labels = paris_labels(fd_l1)
    checks, details = run_checks(calendar, fd_l1, matches, snapshot_id)

    write_csv(wiki_counts, out_dir / "wikipedia_counts.csv")
    write_csv(fd_count_table, out_dir / "fd_counts.csv")
    write_csv(fd_columns, out_dir / "fd_columns.csv")
    write_csv(fd_profile, out_dir / "profile_fd_l1.csv")
    write_csv(profile(calendar, CALENDAR_PROFILE_COLUMNS), out_dir / "profile_psg_calendar.csv")
    write_csv(checks, out_dir / "quality_checks.csv")
    report = build_report(
        snapshot_id,
        wiki_counts,
        fd_count_table,
        fd_columns,
        fd_profile,
        excluded,
        labels,
        checks,
        details,
    )
    (out_dir / "quality_report.md").write_text(report, "utf-8")
    logger.info("Quality reports written to %s", out_dir.as_posix())
    assert_expected_counts(wiki_counts, fd_count_table, labels, checks)


def assert_expected_counts(
    wiki_counts: pd.DataFrame,
    fd_count_table: pd.DataFrame,
    labels: pd.DataFrame,
    checks: pd.DataFrame,
) -> None:
    """Raise QualityCheckError listing every failed count or consistency check."""
    problems = []
    for record in wiki_counts[wiki_counts["status"] != "ok"].itertuples():
        problems.append(
            f"Wikipedia {record.season} {record.competition}: parsed {record.parsed_played} "
            f"played vs Overall record {record.overall_record_played}"
        )
    league = wiki_counts[
        (wiki_counts["competition"] == config.LEAGUE)
        & wiki_counts["season"].isin(config.COMPLETE_SEASONS)
    ]
    for record in league[league["parsed_played"] != config.PSG_L1_MATCHES_PER_SEASON].itertuples():
        problems.append(f"Wikipedia {record.season}: {record.parsed_played} Ligue 1 matches")
    for record in fd_count_table[fd_count_table["status"] == "MISMATCH"].itertuples():
        problems.append(
            f"football-data {record.season}: {record.rows} rows, {record.psg_rows} PSG rows"
        )
    for record in labels.itertuples():
        if config.FD_PSG_LABEL not in str(record.labels).split("; "):
            problems.append(f"football-data {record.season}: label {config.FD_PSG_LABEL} missing")
    for record in checks[checks["status"] == "FAIL"].itertuples():
        problems.append(f"Check failed: {record.check} ({record.value})")
    if problems:
        raise QualityCheckError("Quality checks failed:\n  " + "\n  ".join(problems))
    logger.info("All count and consistency checks passed")
