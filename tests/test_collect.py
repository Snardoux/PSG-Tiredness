"""Collection and snapshot tests, offline, on real API/CSV excerpts saved in tests/fixtures/."""

import json
import re
from pathlib import Path

import pytest

from psg_fatigue import config
from psg_fatigue.collect import snapshot
from psg_fatigue.collect.footballdata import looks_like_f1_csv
from psg_fatigue.collect.http import FetchedFile
from psg_fatigue.collect.wikipedia import MissingPageError, check_parse_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _fetched(file_name: str, content: bytes) -> FetchedFile:
    return FetchedFile(
        file_name=file_name,
        source="test",
        season="2025-26",
        url="https://example.invalid/" + file_name,
        method="download",
        http_status=200,
        retrieved_at_utc="2026-11-02T20:00:00+00:00",
        content=content,
    )


def _complete_file_set() -> list[FetchedFile]:
    return [_fetched(name, name.encode()) for name in sorted(snapshot.expected_files())]


def test_parse_payload_returns_revid() -> None:
    payload = json.loads((FIXTURES / "wiki_api_parse_excerpt.json").read_text("utf-8"))
    assert check_parse_payload(payload, "2025-26 page") == 1381451969


def test_missing_page_fails_loudly_despite_http_200() -> None:
    # Real API answer for a non-existent title: HTTP 200 with an "error" object.
    payload = json.loads((FIXTURES / "wiki_api_missing_page.json").read_text("utf-8"))
    with pytest.raises(MissingPageError, match="missingtitle"):
        check_parse_payload(payload, "missing page")


def test_f1_csv_detection_handles_bom_and_rejects_html() -> None:
    real_head = (FIXTURES / "fd_F1_2425_head.csv").read_bytes()
    assert real_head.startswith(b"\xef\xbb\xbf")  # this season's file starts with a BOM
    assert looks_like_f1_csv(real_head)
    assert not looks_like_f1_csv(b"<!DOCTYPE html><html><body>Access denied</body></html>")


def test_snapshot_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-02"
    snapshot.write_snapshot(target, "2026-11-02", _complete_file_set())
    with pytest.raises(snapshot.SnapshotError, match="already exists"):
        snapshot.write_snapshot(target, "2026-11-02", _complete_file_set())


def test_verify_snapshot_detects_a_modified_file(tmp_path: Path) -> None:
    target = tmp_path / "snap"
    snapshot.write_snapshot(target, "snap", _complete_file_set())
    manifest = snapshot.verify_snapshot(target)
    assert len(manifest["files"]) == 9  # 5 Wikipedia pages + 4 football-data files
    (target / "fd_F1_2526.csv").write_bytes(b"edited by hand")
    with pytest.raises(snapshot.SnapshotError, match="does not match"):
        snapshot.verify_snapshot(target)


def test_verify_snapshot_detects_a_missing_source_file(tmp_path: Path) -> None:
    files = [f for f in _complete_file_set() if f.file_name != "wiki_2026-27.json"]
    snapshot.write_snapshot(tmp_path / "snap", "snap", files)
    with pytest.raises(snapshot.SnapshotError, match=re.escape("wiki_2026-27.json")):
        snapshot.verify_snapshot(tmp_path / "snap")


def test_register_manual_adds_hand_downloaded_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    without_fd = [f for f in _complete_file_set() if not f.file_name.startswith("fd_")]
    snapshot.write_snapshot(tmp_path / "snap", "snap", without_fd)
    real_head = (FIXTURES / "fd_F1_2425_head.csv").read_bytes()
    for code in config.FD_SEASON_CODES.values():
        (tmp_path / "snap" / f"fd_F1_{code}.csv").write_bytes(real_head)

    assert snapshot.register_manual("snap") == 4
    manifest = snapshot.verify_snapshot(tmp_path / "snap")
    manual = [entry for entry in manifest["files"] if entry["method"] == "manual"]
    assert len(manual) == 4
    assert all(entry["http_status"] is None for entry in manual)
    assert snapshot.register_manual("snap") == 0  # idempotent: nothing new to add
