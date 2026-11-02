"""Parse Wikipedia season pages into PSG's calendar of official matches.

Input grain: one raw API response per season page (`wiki_<season>.json`).
Output grain: one row per PSG official fixture, played or scheduled, all competitions
(`interim/psg_calendar`). Friendlies are excluded. Each page's "Overall record" table is
also parsed (one row per season x competition) to reconcile the match counts.
"""

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import mwparserfromhell
import pandas as pd
from mwparserfromhell.nodes import Heading, Template
from mwparserfromhell.wikicode import Wikicode

from psg_fatigue import config

logger = logging.getLogger(__name__)

# Names of the match template (normalised: lowercase, single spaces).
MATCH_TEMPLATES = frozenset({"football box collapsible", "footballbox collapsible", "football box"})
OVERVIEW_TEMPLATE = "fb overview2"
# Layout templates whose first parameter is the visible text (strip_code would drop it).
WRAPPER_TEMPLATES = frozenset({"nowrap", "no wrap", "small"})
MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"})  # en/em dash, minus
UNPLAYED_SCORES = frozenset({"", "v", "vs", "p-p", "tbd", "postponed"})
TWO_LEGGED_FINALS = ("UEFA Champions League", "Coupe de France")  # final = neutral venue


class UnknownCompetitionError(ValueError):
    """A match box sits under headings that name no known competition."""


@dataclass(frozen=True)
class Score:
    """A played match score as written in the box (team1 first)."""

    goals1: int
    goals2: int
    shootout1: int | None = None
    shootout2: int | None = None


def template_name(template: Template) -> str:
    """Normalised template name: lowercase, underscores as spaces, single spaces."""
    return " ".join(str(template.name).replace("_", " ").lower().split())


def clean_text(value: Wikicode | str) -> str:
    """Plain text of a wikitext value: unwrap layout templates, drop markup, collapse spaces."""
    code = mwparserfromhell.parse(str(value))
    for template in code.filter_templates(recursive=False):
        if template_name(template) in WRAPPER_TEMPLATES and template.has(1):
            code.replace(template, template.get(1).value)
    return " ".join(code.strip_code().split())


def param_text(template: Template, name: str) -> str:
    """Clean text of a template parameter, or '' if the parameter is absent."""
    return clean_text(template.get(name).value) if template.has(name) else ""


def parse_match_date(text: str) -> date | None:
    """'17 August 2025' -> date(2025, 8, 17). Date ranges ('19-21 December 2026') give None."""
    match = re.fullmatch(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", text.strip())
    if match is None or match.group(2) not in MONTHS:
        return None
    return date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))


def box_date(box: Template) -> tuple[date | None, str]:
    """Date of a match box and its original text; handles `{{Start date|Y|M|D}}`."""
    if not box.has("date"):
        return None, ""
    value = box.get("date").value
    for template in value.filter_templates():
        if template_name(template) == "start date":
            year, month, day = (int(param_text(template, str(i))) for i in (1, 2, 3))
            return date(year, month, day), clean_text(value)
    text = clean_text(value)
    return parse_match_date(text), text


def parse_score(score: str, penaltyscore: str = "") -> Score | None:
    """Parse a box score. None means the match has not been played (yet).

    '2-1' -> Score(2, 1); '2-2 (4-3 p)' or penaltyscore '4-3' -> regulation (2, 2) plus a
    shoot-out; 'v', 'P-P' or empty -> None. Any other text raises ValueError.
    Wikipedia writes scores with an en dash; hyphens and em dashes are accepted too.
    """
    text = " ".join(score.translate(DASHES).split())
    if text.lower() in UNPLAYED_SCORES:
        return None
    match = re.fullmatch(r"(\d+) ?- ?(\d+)(?: ?\((\d+) ?- ?(\d+) ?p\.?\))?", text)
    if match is None:
        raise ValueError(f"Unrecognised score: {score!r}")
    goals1, goals2 = int(match.group(1)), int(match.group(2))
    if match.group(3) is not None:
        return Score(goals1, goals2, int(match.group(3)), int(match.group(4)))
    if penaltyscore.strip():
        shootout = re.fullmatch(
            r"(\d+) ?- ?(\d+)", " ".join(penaltyscore.translate(DASHES).split())
        )
        if shootout is None:
            raise ValueError(f"Unrecognised penalty score: {penaltyscore!r}")
        return Score(goals1, goals2, int(shootout.group(1)), int(shootout.group(2)))
    return Score(goals1, goals2)


def resolve_competition(headings: list[str]) -> str | None:
    """Competition of a match box from its enclosing headings (outermost first).

    The nearest heading naming a competition wins. None means a friendly (excluded).
    """
    for title in reversed(headings):
        if title in config.OFFICIAL_COMPETITIONS:
            return title
        if title in config.EXCLUDED_HEADINGS:
            return None
    raise UnknownCompetitionError(f"Match box under unknown headings: {headings}")


def match_venue(competition: str, round_label: str, psg_is_team1: bool) -> str:
    """'N' for neutral-venue competitions and finals, otherwise 'H'/'A' from PSG's position."""
    is_final = competition in TWO_LEGGED_FINALS and round_label == "Final"
    if competition in config.NEUTRAL_COMPETITIONS or is_final:
        return "N"
    return "H" if psg_is_team1 else "A"


def result_letter(goals_for: int, goals_against: int) -> str:
    """'W' / 'D' / 'L' from one team's point of view (shoot-outs count as draws)."""
    if goals_for > goals_against:
        return "W"
    return "D" if goals_for == goals_against else "L"


def iter_match_boxes(code: Wikicode) -> Iterator[tuple[list[str], Template]]:
    """Yield (enclosing headings, match box) in page order, for top-level match boxes."""
    stack: dict[int, str] = {}
    for node in code.nodes:
        if isinstance(node, Heading):
            stack = {level: title for level, title in stack.items() if level < node.level}
            stack[node.level] = clean_text(node.title)
        elif isinstance(node, Template) and template_name(node) in MATCH_TEMPLATES:
            yield [stack[level] for level in sorted(stack)], node


def box_to_row(box: Template, competition: str, season: str, page_order: int) -> dict[str, Any]:
    """One match box -> one calendar row, from PSG's point of view."""
    team1, team2 = param_text(box, "team1"), param_text(box, "team2")
    psg_is_team1, psg_is_team2 = team1 == config.WIKI_PSG_NAME, team2 == config.WIKI_PSG_NAME
    if psg_is_team1 and psg_is_team2:
        raise ValueError(f"PSG on both sides of a match box: {team1} v {team2}")
    match_date, date_text = box_date(box)
    round_label = param_text(box, "round")
    score = parse_score(param_text(box, "score"), param_text(box, "penaltyscore"))
    has_psg = psg_is_team1 or psg_is_team2
    if score is not None and (match_date is None or not has_psg):
        raise ValueError(f"Played match without a date or without PSG: {box}")

    psg_goals = opp_goals = psg_shootout = opp_shootout = None
    psg_result = None
    if score is not None:
        psg_goals, opp_goals = (
            (score.goals1, score.goals2) if psg_is_team1 else (score.goals2, score.goals1)
        )
        psg_result = result_letter(psg_goals, opp_goals)
        if score.shootout1 is not None:
            psg_shootout, opp_shootout = (
                (score.shootout1, score.shootout2)
                if psg_is_team1
                else (score.shootout2, score.shootout1)
            )
    decided_by: str | None  # FT / AET / PEN, None if not played
    if psg_shootout is not None:
        decided_by = "PEN"
    elif param_text(box, "aet"):
        decided_by = "AET"
    else:
        decided_by = "FT" if score is not None else None

    attendance_digits = re.sub(r"\D", "", param_text(box, "attendance"))
    note = param_text(box, "note").lower()
    return {
        "season": season,
        "competition": competition,
        "round": round_label,
        # Ligue 1 matchday number; a non-numeric league round raises ValueError on purpose.
        "matchday": int(round_label) if competition == config.LEAGUE else None,
        "match_date": match_date,
        "date_text": date_text,
        "played": score is not None,
        "venue": match_venue(competition, round_label, psg_is_team1) if has_psg else None,
        "team1": team1,
        "team2": team2,
        "opponent": (team2 if psg_is_team1 else team1) if has_psg else None,
        "psg_goals": psg_goals,
        "opp_goals": opp_goals,
        "psg_result": psg_result,
        "wiki_result": param_text(box, "result") or None,
        "decided_by": decided_by,
        "psg_shootout": psg_shootout,
        "opp_shootout": opp_shootout,
        "stadium": param_text(box, "stadium"),
        "location": param_text(box, "location"),
        "attendance": int(attendance_digits) if attendance_digits else None,
        "referee": param_text(box, "referee"),
        # Only "postponed" marks a new date: some notes say "originally scheduled for 15:00"
        # about a kick-off delay of a few minutes (2025 Club World Cup semi-final).
        "rescheduled": "postponed" in note,
        "page_order": page_order,
    }


def parse_page_matches(code: Wikicode, season: str) -> tuple[list[dict[str, Any]], int]:
    """All official match rows of one page, plus the number of friendlies excluded."""
    rows: list[dict[str, Any]] = []
    friendlies = 0
    n_boxes = 0
    for page_order, (headings, box) in enumerate(iter_match_boxes(code)):
        n_boxes += 1
        competition = resolve_competition(headings)
        if competition is None:
            friendlies += 1
            continue
        rows.append(box_to_row(box, competition, season, page_order))
    # Guard: every match box of the page must be a top-level node seen by the walk above.
    n_all = sum(1 for t in code.filter_templates() if template_name(t) in MATCH_TEMPLATES)
    if n_all != n_boxes:
        raise ValueError(f"{season}: {n_all - n_boxes} match box(es) nested in other markup")
    others = {
        template_name(t)
        for t in code.filter_templates()
        if "football box" in template_name(t) or "footballbox" in template_name(t)
    } - MATCH_TEMPLATES
    if others:
        logger.warning("%s: other match-like templates ignored: %s", season, sorted(others))
    return rows, friendlies


def parse_overall_record(code: Wikicode, season: str) -> list[dict[str, Any]]:
    """Rows of the page's 'Overall record' table (`Fb overview2`): played = W + D + L."""
    overviews = [t for t in code.filter_templates() if template_name(t) == OVERVIEW_TEMPLATE]
    if len(overviews) != 1:
        raise ValueError(f"{season}: expected one Overall record table, found {len(overviews)}")
    overview = overviews[0]
    rows = []
    index = 1
    while overview.has(f"c{index}"):  # the `c` count parameter is not always up to date
        competition = param_text(overview, f"c{index}")
        if competition not in config.OFFICIAL_COMPETITIONS:
            raise UnknownCompetitionError(f"{season}: unknown competition {competition!r}")
        wins, draws, losses = (int(param_text(overview, f"{k}{index}") or 0) for k in "wdl")
        rows.append(
            {
                "season": season,
                "competition": competition,
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "played": wins + draws + losses,
            }
        )
        index += 1
    return rows


def load_page(path: Path) -> tuple[Wikicode, int]:
    """Parsed wikitext and revision id of a raw `action=parse` JSON file."""
    payload = json.loads(path.read_text("utf-8"))
    return mwparserfromhell.parse(payload["parse"]["wikitext"]), int(payload["parse"]["revid"])


def parse_wiki_snapshot(snapshot_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse every season page of the snapshot.

    Returns the calendar (one row per official fixture), the Overall record table
    (one row per season x competition) and the friendlies excluded (one row per season).
    """
    match_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    for season in config.WIKI_SEASONS:
        code, revid = load_page(snapshot_dir / f"wiki_{season}.json")
        rows, friendlies = parse_page_matches(code, season)
        for row in rows:
            row["wiki_revid"] = revid
        match_rows += rows
        record_rows += parse_overall_record(code, season)
        excluded_rows.append({"season": season, "friendlies_excluded": friendlies})
        logger.info(
            "Wikipedia %s: %d official fixtures (%d played), %d friendlies excluded",
            season,
            len(rows),
            sum(row["played"] for row in rows),
            friendlies,
        )
    calendar = pd.DataFrame(match_rows)
    calendar["match_date"] = pd.to_datetime(calendar["match_date"])
    for column in ("matchday", "psg_goals", "opp_goals", "psg_shootout", "opp_shootout"):
        calendar[column] = calendar[column].astype("Int64")
    calendar["attendance"] = calendar["attendance"].astype("Int64")
    calendar = calendar.sort_values(
        ["match_date", "season", "page_order"], na_position="last", kind="stable"
    ).reset_index(drop=True)
    return calendar, pd.DataFrame(record_rows), pd.DataFrame(excluded_rows)
