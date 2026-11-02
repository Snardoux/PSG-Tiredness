"""Smoke tests for the CLI parser and project configuration (no network)."""

import pytest

from psg_fatigue import config
from psg_fatigue.cli import build_parser


def test_wiki_page_title_uses_en_dash() -> None:
    title = config.wiki_page_title("2025-26")
    assert title == "2025\u201326 Paris Saint-Germain FC season"
    assert "-" not in title.split(" ")[0]  # no ASCII hyphen between the years


def test_every_analysis_season_has_a_football_data_file() -> None:
    assert set(config.FD_SEASON_CODES) == set(config.ANALYSIS_SEASONS)
    assert config.WIKI_SEASONS[0] == config.CONTEXT_SEASON


@pytest.mark.parametrize("command", ["collect", "build", "eda", "all"])
def test_parser_accepts_each_command(command: str) -> None:
    args = build_parser().parse_args([command])
    assert args.command == command


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_build_snapshot_can_be_overridden() -> None:
    args = build_parser().parse_args(["build", "--snapshot", "2026-11-02"])
    assert args.snapshot == "2026-11-02"
