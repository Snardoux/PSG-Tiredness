"""Frozen raw snapshot: write downloaded files once, record provenance, verify integrity.

Output grain: one folder `data/raw/<snapshot_id>/` = one extraction; `manifest.json`
holds one entry per raw file (URL, UTC timestamp, HTTP status, bytes, sha256, revid).
An existing snapshot is never overwritten; `register_manual` may only add missing files.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psg_fatigue import config
from psg_fatigue.collect import footballdata, wikipedia
from psg_fatigue.collect.http import FetchedFile, make_session, utc_now_iso

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"


class SnapshotError(RuntimeError):
    """Raised when a snapshot is missing, already exists, or fails its integrity check."""


def today_snapshot_id() -> str:
    """Snapshot id for a collection run today: the UTC date, YYYY-MM-DD."""
    return datetime.now(UTC).date().isoformat()


def sha256_hex(content: bytes) -> str:
    """Hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(content).hexdigest()


def manifest_entry(fetched: FetchedFile) -> dict[str, Any]:
    """Provenance record of one raw file, as stored in manifest.json."""
    return {
        "file": fetched.file_name,
        "source": fetched.source,
        "season": fetched.season,
        "url": fetched.url,
        "method": fetched.method,
        "retrieved_at_utc": fetched.retrieved_at_utc,
        "http_status": fetched.http_status,
        "bytes": len(fetched.content),
        "sha256": sha256_hex(fetched.content),
        **fetched.extra,
    }


def read_manifest(snapshot_dir: Path) -> dict[str, Any]:
    """Load the manifest of a snapshot folder."""
    path = snapshot_dir / MANIFEST_NAME
    if not path.is_file():
        raise SnapshotError(f"No {MANIFEST_NAME} in {snapshot_dir}")
    manifest: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return manifest


def write_manifest(snapshot_dir: Path, manifest: dict[str, Any]) -> None:
    """Write the manifest as indented UTF-8 JSON (stable, diff-friendly)."""
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (snapshot_dir / MANIFEST_NAME).write_text(text, "utf-8")


def write_snapshot(snapshot_dir: Path, snapshot_id: str, files: list[FetchedFile]) -> None:
    """Create the snapshot folder and write every file plus the manifest.

    Refuses to touch an existing folder: a snapshot is immutable once written.
    """
    if snapshot_dir.exists():
        raise SnapshotError(f"Snapshot {snapshot_dir} already exists; it will not be overwritten")
    snapshot_dir.mkdir(parents=True)
    for fetched in files:
        (snapshot_dir / fetched.file_name).write_bytes(fetched.content)
    manifest = {
        "snapshot_id": snapshot_id,
        "created_at_utc": utc_now_iso(),
        "user_agent": config.USER_AGENT,
        "files": [manifest_entry(fetched) for fetched in files],
    }
    write_manifest(snapshot_dir, manifest)
    logger.info("Snapshot %s written: %d files + %s", snapshot_id, len(files), MANIFEST_NAME)


def manual_download_instructions(snapshot_id: str, seasons: list[str]) -> str:
    """Exact steps for the manual fallback when automated download is blocked."""
    lines = ["Download these files by hand (browser) and save them unchanged as:"]
    for season in seasons:
        code = config.FD_SEASON_CODES[season]
        target = config.RAW_DIR / snapshot_id / footballdata.fd_file_name(code)
        lines.append(f"  {footballdata.fd_url(code)}  ->  {target.as_posix()}")
    lines.append(f"Then run: uv run psg-fatigue collect --register-manual {snapshot_id}")
    return "\n".join(lines)


def create_snapshot(snapshot_id: str) -> list[str]:
    """Collect both sources online and write the snapshot.

    Everything is downloaded in memory first, so a missing Wikipedia page leaves no
    partial folder behind. Returns the seasons whose football-data download was blocked.
    """
    snapshot_dir = config.RAW_DIR / snapshot_id
    if snapshot_dir.exists():
        raise SnapshotError(f"Snapshot {snapshot_dir} already exists; it will not be overwritten")
    session = make_session()
    wiki_files = wikipedia.fetch_all_pages(session)
    fd_files, blocked = footballdata.download_all_seasons(session)
    write_snapshot(snapshot_dir, snapshot_id, wiki_files + fd_files)
    return blocked


def register_manual(snapshot_id: str) -> int:
    """Hash football-data files saved by hand into an existing snapshot; add them to its manifest.

    Files already in the manifest must still match their recorded hash. Returns the number
    of newly registered files.
    """
    snapshot_dir = config.RAW_DIR / snapshot_id
    manifest = read_manifest(snapshot_dir)
    known = {entry["file"]: entry for entry in manifest["files"]}
    added = 0
    missing = []
    for season, code in config.FD_SEASON_CODES.items():
        file_name = footballdata.fd_file_name(code)
        path = snapshot_dir / file_name
        if file_name in known:
            if sha256_hex(path.read_bytes()) != known[file_name]["sha256"]:
                raise SnapshotError(f"{path} changed since it was recorded; refusing to continue")
            continue
        if not path.is_file():
            missing.append(season)
            continue
        content = path.read_bytes()
        if not footballdata.looks_like_f1_csv(content):
            raise SnapshotError(f"{path} does not look like a football-data CSV file")
        fetched = FetchedFile(
            file_name=file_name,
            source="football-data",
            season=season,
            url=footballdata.fd_url(code),
            method="manual",
            http_status=None,
            retrieved_at_utc=utc_now_iso(),  # registration time (download done by hand)
            content=content,
        )
        manifest["files"].append(manifest_entry(fetched))
        added += 1
    if missing:
        raise SnapshotError(manual_download_instructions(snapshot_id, missing))
    write_manifest(snapshot_dir, manifest)
    logger.info("Registered %d manually downloaded file(s) in snapshot %s", added, snapshot_id)
    return added


def expected_files() -> set[str]:
    """Raw file names a complete snapshot must contain (5 Wikipedia pages + 4 CSV files)."""
    wiki = {f"wiki_{season}.json" for season in config.WIKI_SEASONS}
    fd = {footballdata.fd_file_name(code) for code in config.FD_SEASON_CODES.values()}
    return wiki | fd


def verify_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    """Offline integrity check: every expected file is listed and matches its size and sha256."""
    manifest = read_manifest(snapshot_dir)
    entries = {entry["file"]: entry for entry in manifest["files"]}
    missing = sorted(expected_files() - set(entries))
    if missing:
        raise SnapshotError(f"Snapshot {snapshot_dir} is incomplete; missing: {missing}")
    for file_name, entry in sorted(entries.items()):
        path = snapshot_dir / file_name
        if not path.is_file():
            raise SnapshotError(f"{path} is listed in the manifest but absent")
        content = path.read_bytes()
        if len(content) != entry["bytes"] or sha256_hex(content) != entry["sha256"]:
            raise SnapshotError(f"{path} does not match its manifest entry (bytes/sha256)")
    logger.info("Snapshot %s verified: %d files match the manifest", snapshot_dir, len(entries))
    return manifest
