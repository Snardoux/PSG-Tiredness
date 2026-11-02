"""Offline pipeline steps behind `psg-fatigue build | eda | all` (no network access).

build: raw snapshot (verified against its manifest) -> parsed tables in data/interim/
       -> quality reports in reports/quality/.
"""

import logging

import pandas as pd

from psg_fatigue import config, quality
from psg_fatigue.collect.snapshot import verify_snapshot
from psg_fatigue.parse.fd_matches import parse_fd_snapshot
from psg_fatigue.parse.wiki_matches import parse_wiki_snapshot

logger = logging.getLogger(__name__)


def write_interim(table: pd.DataFrame, name: str) -> None:
    """Save an intermediate table as Parquet (keeps dtypes; rebuilt by every build)."""
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    path = config.INTERIM_DIR / f"{name}.parquet"
    table.to_parquet(path, index=False)
    logger.info("Wrote %s (%d rows)", path.as_posix(), len(table))


def run_build(snapshot_id: str) -> None:
    """Rebuild every derived table and report from the frozen raw snapshot."""
    snapshot_dir = config.RAW_DIR / snapshot_id
    verify_snapshot(snapshot_dir)

    calendar, overall_record, excluded = parse_wiki_snapshot(snapshot_dir)
    fd_l1, fd_columns = parse_fd_snapshot(snapshot_dir)
    write_interim(calendar, "psg_calendar")
    write_interim(fd_l1, "fd_l1")

    quality.run_quality(
        calendar, overall_record, excluded, fd_l1, fd_columns, snapshot_id, config.QUALITY_DIR
    )
