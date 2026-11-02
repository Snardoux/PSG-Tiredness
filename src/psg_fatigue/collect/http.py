"""Polite HTTP access shared by the collectors (online only).

Grain: one HTTP GET -> one `FetchedFile` (raw bytes kept unchanged + provenance metadata).
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import requests

from psg_fatigue import config

logger = logging.getLogger(__name__)

# Temporary errors worth retrying; anything else (403, 404...) fails immediately.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class FetchedFile:
    """A downloaded file held in memory before it is written to the snapshot."""

    file_name: str  # name inside data/raw/<snapshot_id>/
    source: str  # "wikipedia" or "football-data"
    season: str  # e.g. "2025-26"
    url: str  # exact URL requested (with query string)
    method: str  # "api", "download" or "manual"
    http_status: int | None  # None for files downloaded by hand
    retrieved_at_utc: str
    content: bytes
    extra: dict[str, str | int] = field(default_factory=dict)  # e.g. Wikipedia title, revid


def utc_now_iso() -> str:
    """Current UTC time, ISO 8601, second precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def make_session() -> requests.Session:
    """Return a session that identifies the project with a descriptive User-Agent."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    return session


def _retry_after_seconds(response: requests.Response) -> float | None:
    """Read a numeric Retry-After header, if the server sent one."""
    value = response.headers.get("Retry-After", "")
    try:
        return float(value)
    except ValueError:
        return None


def get_with_retry(
    session: requests.Session, url: str, params: dict[str, str] | None = None
) -> requests.Response:
    """GET `url`, retrying with exponential backoff on 429/5xx and network errors.

    Any other non-2xx status raises `requests.HTTPError` at once: missing data fails loudly.
    """
    for attempt in range(config.MAX_RETRIES + 1):
        is_last_attempt = attempt == config.MAX_RETRIES
        backoff = 2.0**attempt
        try:
            response = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as error:
            if is_last_attempt:
                raise
            logger.warning("Network error on %s (%s), retrying in %.0f s", url, error, backoff)
            time.sleep(backoff)
            continue
        if response.status_code in RETRYABLE_STATUS and not is_last_attempt:
            wait = _retry_after_seconds(response) or backoff
            logger.warning("HTTP %d on %s, retrying in %.0f s", response.status_code, url, wait)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    raise AssertionError("unreachable: the last attempt either returns or raises")
