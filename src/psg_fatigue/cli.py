"""Command-line entry point: `uv run psg-fatigue collect | build | eda | all`.

- collect: online, writes a new immutable snapshot under data/raw/<YYYY-MM-DD>/.
- build:   offline, raw snapshot -> data/interim -> data/processed + reports/quality.
- eda:     offline, data/processed -> reports/eda.
- all:     offline, build then eda.
"""

import argparse
import logging
import sys

from psg_fatigue import config

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Define the CLI commands and their options."""
    parser = argparse.ArgumentParser(
        prog="psg-fatigue",
        description=(
            "PSG under Luis Enrique: does fixture congestion beat the betting market? "
            "Run every command from the repository root."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity (default: INFO)",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    collect = commands.add_parser(
        "collect", help="online: download sources into a new raw snapshot"
    )
    collect.add_argument(
        "--register-manual",
        metavar="SNAPSHOT_ID",
        help=(
            "hash football-data CSV files downloaded by hand into "
            "data/raw/<SNAPSHOT_ID>/ and add them to its manifest"
        ),
    )

    snapshot_help = f"raw snapshot id to read (default: config.SNAPSHOT_ID = {config.SNAPSHOT_ID})"
    build = commands.add_parser("build", help="offline: raw snapshot -> processed tables")
    build.add_argument("--snapshot", default=config.SNAPSHOT_ID, help=snapshot_help)

    commands.add_parser("eda", help="offline: processed tables -> figures and EDA tables")

    run_all = commands.add_parser("all", help="offline: build then eda")
    run_all.add_argument("--snapshot", default=config.SNAPSHOT_ID, help=snapshot_help)

    return parser


def run_command(args: argparse.Namespace) -> int:
    """Dispatch a parsed command. Returns the process exit code."""
    command: str = args.command
    # Pipeline steps are wired in as they are implemented (phases 1 to 4).
    logger.error("Command %r is not implemented yet.", command)
    return 2


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging, check the working directory, run the command."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        config.ensure_repo_root()
    except config.NotAtRepoRootError as error:
        logger.error("%s", error)
        return 1
    return run_command(args)


if __name__ == "__main__":
    sys.exit(main())
