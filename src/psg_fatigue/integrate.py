"""Join football-data PSG matches (odds) with Wikipedia Ligue 1 matches (load features).

Input grain: left = `fd_psg`, one PSG Ligue 1 match from football-data (PSG perspective);
right = Ligue 1 rows of the Wikipedia calendar with load features, one PSG Ligue 1 match.
Output grain: one PSG Ligue 1 match present in both sources (expected relationship 1:1),
plus `reports/quality/integration_report.{json,md}`.
"""

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from psg_fatigue import config

logger = logging.getLogger(__name__)

TEAM_NAME_COLUMNS = ["wikipedia_name", "footballdata_name", "canonical"]
# Words dropped when comparing club names across sources (SPEC §6).
NOISE_WORDS = frozenset({"fc", "as", "ogc", "rc", "stade", "olympique"})
JOIN_KEY = ["match_date", "opponent_canonical"]


class TeamMappingError(ValueError):
    """A club name has no (or an ambiguous) entry in config/team_names.csv."""


# --- Team names -------------------------------------------------------------------


def normalise_team_name(name: str) -> str:
    """Comparison key of a club name: no accents, lowercase, 'saint' -> 'st', no noise words.

    'Saint-Étienne' and 'St Etienne' both give 'st etienne'. 'Paris FC' gives 'paris'
    and 'Paris SG' gives 'paris sg': they stay different.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).split()
    words = ["st" if word == "saint" else word for word in words]
    return " ".join(word for word in words if word not in NOISE_WORDS)


def suggest_team_mapping(wikipedia_names: list[str], footballdata_names: list[str]) -> pd.DataFrame:
    """Candidate mapping by exact equality of normalised names (to be reviewed by hand).

    Names without an exact candidate get an empty partner: no fuzzy guess is made, so a
    wrong pairing such as Paris FC -> Paris SG cannot be suggested.
    """
    by_key = {normalise_team_name(name): name for name in footballdata_names}
    rows = []
    for wiki_name in sorted(set(wikipedia_names)):
        fd_name = by_key.pop(normalise_team_name(wiki_name), "")
        rows.append({"wikipedia_name": wiki_name, "footballdata_name": fd_name})
    for fd_name in sorted(by_key.values()):
        rows.append({"wikipedia_name": "", "footballdata_name": fd_name})
    mapping = pd.DataFrame(rows, columns=["wikipedia_name", "footballdata_name"])
    mapping["canonical"] = mapping["wikipedia_name"]
    return mapping


def load_team_names(path: Path) -> pd.DataFrame:
    """Read the reviewed mapping and check it is complete and one-to-one."""
    mapping = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(mapping.columns) != TEAM_NAME_COLUMNS:
        raise TeamMappingError(f"{path}: columns must be {TEAM_NAME_COLUMNS}")
    for column in TEAM_NAME_COLUMNS:
        if (mapping[column] == "").any():
            raise TeamMappingError(f"{path}: empty values in column {column}")
        if mapping[column].duplicated().any():
            raise TeamMappingError(f"{path}: duplicated values in column {column}")
    return mapping


def to_canonical(names: pd.Series, mapping: pd.DataFrame, source_column: str) -> pd.Series:
    """Translate club names of one source to canonical names; fail on any unmapped name."""
    lookup = dict(zip(mapping[source_column], mapping["canonical"], strict=True))
    unmapped = sorted(set(names) - set(lookup))
    if unmapped:
        raise TeamMappingError(
            f"Names missing from {config.TEAM_NAMES_CSV.as_posix()} ({source_column}): {unmapped}"
        )
    return names.map(lookup)


# --- Join -------------------------------------------------------------------------

SUFFIXES = ("_fd", "_wiki")


class IntegrationError(RuntimeError):
    """The join broke the expected grain (rows multiplied or keys duplicated)."""


def join_sources(left: pd.DataFrame, right: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join football-data PSG matches (left) to Wikipedia Ligue 1 matches (right), 1:1.

    1. Exact join on (match_date, opponent_canonical), validated one-to-one.
    2. Rows left over on both sides are retried with a one-day tolerance on the date
       (same opponent, unique candidate); `join_method` records which step matched.
    3. Anything still unmatched is reported and excluded.
    Overlapping columns get the suffixes `_fd` (left) and `_wiki` (right). The output
    `match_date` is the Wikipedia date (the one used for rest days).
    """
    left = left.assign(fd_row=range(len(left)))
    right = right.assign(wiki_row=range(len(right)))

    exact = left.merge(right, on=JOIN_KEY, how="inner", validate="one_to_one", suffixes=SUFFIXES)
    exact["match_date_fd"] = exact["match_date"]
    exact["join_method"] = "exact"

    left_rest = left[~left["fd_row"].isin(exact["fd_row"])]
    right_rest = right[~right["wiki_row"].isin(exact["wiki_row"])]
    candidates = left_rest.merge(right_rest, on="opponent_canonical", suffixes=SUFFIXES)
    candidates = candidates.rename(columns={"match_date_wiki": "match_date"})
    one_day_apart = (candidates["match_date_fd"] - candidates["match_date"]).abs() == pd.Timedelta(
        days=1
    )
    tolerant = candidates[one_day_apart]
    # A row with two possible partners is ambiguous: keep unique pairs only.
    unique_pair = ~tolerant["fd_row"].duplicated(keep=False) & ~tolerant["wiki_row"].duplicated(
        keep=False
    )
    tolerant = tolerant[unique_pair].assign(join_method="plus_minus_1d")

    joined = pd.concat([exact, tolerant], ignore_index=True)
    joined = joined.sort_values("match_date", kind="stable").reset_index(drop=True)
    joined["score_check_ok"] = (
        (joined["psg_goals_fd"] == joined["psg_goals_wiki"])
        & (joined["opp_goals_fd"] == joined["opp_goals_wiki"])
        & (joined["venue_fd"] == joined["venue_wiki"])
    ).astype(bool)

    unmatched_left = left[~left["fd_row"].isin(joined["fd_row"])]
    unmatched_right = right[~right["wiki_row"].isin(joined["wiki_row"])]
    report = integration_report(left, right, joined, unmatched_left, unmatched_right)
    if report["row_multiplication"]:
        raise IntegrationError(f"Join broke the one-row-per-match grain: {report}")
    logger.info(
        "Join: %d left, %d right -> %d matched (%d exact, %d at +/-1 day), "
        "%d left-only, %d right-only",
        len(left),
        len(right),
        len(joined),
        report["matched_exact"],
        report["matched_plus_minus_1d"],
        len(unmatched_left),
        len(unmatched_right),
    )
    return joined.drop(columns=["fd_row", "wiki_row"]), report


def _match_list(table: pd.DataFrame, date_column: str = "match_date") -> list[dict[str, str]]:
    """Short description of matches for the report: date, season, opponent."""
    season = "season" if "season" in table.columns else "season_fd"
    return [
        {
            "match_date": row[date_column].date().isoformat(),
            "season": str(row[season]),
            "opponent": str(row["opponent_canonical"]),
        }
        for _, row in table.iterrows()
    ]


def integration_report(
    left: pd.DataFrame,
    right: pd.DataFrame,
    joined: pd.DataFrame,
    unmatched_left: pd.DataFrame,
    unmatched_right: pd.DataFrame,
) -> dict[str, Any]:
    """Counts and lists that prove the join kept one row per match (SPEC §7)."""
    mismatches = joined[~joined["score_check_ok"]]
    return {
        "left_source": "football-data.co.uk, PSG Ligue 1 matches (fd_psg)",
        "right_source": "Wikipedia, PSG Ligue 1 played matches with load features",
        "join_key": JOIN_KEY,
        "left_rows": len(left),
        "right_rows": len(right),
        "matched_exact": int((joined["join_method"] == "exact").sum()),
        "matched_plus_minus_1d": int((joined["join_method"] == "plus_minus_1d").sum()),
        "matched_total": len(joined),
        "match_rate_left_pct": round(100 * len(joined) / len(left), 1) if len(left) else None,
        "match_rate_right_pct": round(100 * len(joined) / len(right), 1) if len(right) else None,
        "left_only_rows": len(unmatched_left),
        "right_only_rows": len(unmatched_right),
        # Grain: every left row and every right row is used at most once.
        "row_multiplication": bool(
            joined["fd_row"].duplicated().any() or joined["wiki_row"].duplicated().any()
        ),
        "rows_after_join_le_left_rows": len(joined) <= len(left),
        "score_or_venue_mismatches": len(mismatches),
        "plus_minus_1d_matches": _match_list(
            joined[joined["join_method"] == "plus_minus_1d"], date_column="match_date_fd"
        ),
        "left_only": _match_list(unmatched_left),
        "right_only": _match_list(unmatched_right),
        "score_or_venue_mismatch_rows": _match_list(mismatches),
        "rows_dropped": [
            {
                "reason": "football-data match without Wikipedia partner",
                "rows": len(unmatched_left),
            },
            {
                "reason": "Wikipedia match without football-data partner",
                "rows": len(unmatched_right),
            },
        ],
    }


def write_integration_report(report: dict[str, Any], out_dir: Path) -> None:
    """Write the report as JSON (machine-readable) and Markdown (human-readable)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "integration_report.json").write_text(text, "utf-8")

    summary_keys = [
        "left_rows",
        "right_rows",
        "matched_exact",
        "matched_plus_minus_1d",
        "matched_total",
        "match_rate_left_pct",
        "match_rate_right_pct",
        "left_only_rows",
        "right_only_rows",
        "row_multiplication",
        "rows_after_join_le_left_rows",
        "score_or_venue_mismatches",
    ]
    lines = [
        "# Integration report",
        "",
        "Generated by `uv run psg-fatigue build`.",
        "",
        f"- Left: {report['left_source']}",
        f"- Right: {report['right_source']}",
        f"- Key: `({', '.join(report['join_key'])})`, expected relationship 1:1 "
        "(`pd.merge(validate='one_to_one')`), then a +/-1 day retry for leftovers.",
        "",
        "| metric | value |",
        "|---|---|",
        *[f"| {key} | {report[key]} |" for key in summary_keys],
        "",
    ]
    for title, key in [
        (
            "Matched with a one-day date difference (football-data date shown)",
            "plus_minus_1d_matches",
        ),
        ("football-data matches without Wikipedia partner (excluded)", "left_only"),
        ("Wikipedia matches without football-data partner (excluded)", "right_only"),
        ("Score or venue disagreements between the sources", "score_or_venue_mismatch_rows"),
    ]:
        rows = report[key]
        lines += [f"## {title}", ""]
        if rows:
            lines += ["| match_date | season | opponent |", "|---|---|---|"]
            lines += [f"| {r['match_date']} | {r['season']} | {r['opponent']} |" for r in rows]
        else:
            lines.append("_(none)_")
        lines.append("")
    (out_dir / "integration_report.md").write_text("\n".join(lines), "utf-8")
