"""Download football-data.co.uk Ligue 1 files (`F1.csv`), one per season.

Input grain: one season code (e.g. `2526`). Output grain: one raw CSV file per season
(`fd_F1_<code>.csv`), bytes unchanged. One row of the file = one Ligue 1 match.
"""

import logging
import time

import requests

from psg_fatigue import config
from psg_fatigue.collect.http import FetchedFile, get_with_retry, utc_now_iso

logger = logging.getLogger(__name__)


class DownloadBlockedError(RuntimeError):
    """Raised when the site refuses automated download (the manual fallback then applies)."""


def fd_file_name(code: str) -> str:
    """Name of the raw file for a season code, e.g. '2526' -> 'fd_F1_2526.csv'."""
    return f"fd_F1_{code}.csv"


def fd_url(code: str) -> str:
    """Download URL of the Ligue 1 file for a season code."""
    return config.FD_URL_TEMPLATE.format(code=code)


def looks_like_f1_csv(content: bytes) -> bool:
    """True if the bytes start like a football-data CSV (header begins with `Div,`).

    Guards against an HTML error or anti-bot page served with HTTP 200.
    """
    return content.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"Div,")


def download_season(session: requests.Session, season: str, code: str) -> FetchedFile:
    """Download one season file; raise `DownloadBlockedError` if access is refused."""
    url = fd_url(code)
    try:
        response = get_with_retry(session, url)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        if status in (401, 403):
            raise DownloadBlockedError(f"HTTP {status} for {url}") from error
        raise  # 404 and others: the file does not exist, a manual download would not help
    if not looks_like_f1_csv(response.content):
        raise DownloadBlockedError(f"{url} did not return a CSV file (anti-bot or error page?)")
    logger.info("football-data %s: %d bytes", fd_file_name(code), len(response.content))
    return FetchedFile(
        file_name=fd_file_name(code),
        source="football-data",
        season=season,
        url=response.url,
        method="download",
        http_status=response.status_code,
        retrieved_at_utc=utc_now_iso(),
        content=response.content,
    )


def download_all_seasons(session: requests.Session) -> tuple[list[FetchedFile], list[str]]:
    """Download every season of `config.FD_SEASON_CODES`.

    Returns the downloaded files and the list of seasons whose download was blocked.
    """
    files: list[FetchedFile] = []
    blocked: list[str] = []
    for index, (season, code) in enumerate(config.FD_SEASON_CODES.items()):
        if index > 0:
            time.sleep(config.REQUEST_INTERVAL_SECONDS)
        try:
            files.append(download_season(session, season, code))
        except DownloadBlockedError as error:
            logger.error("Automated download blocked: %s", error)
            blocked.append(season)
    return files, blocked
