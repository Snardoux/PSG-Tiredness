"""Collect PSG season pages from English Wikipedia through the MediaWiki Action API.

Input grain: one season. Output grain: one raw JSON API response per season page
(`wiki_<season>.json`), kept byte for byte, with its revision id for provenance.
No pagination is needed: `action=parse` returns a whole page in one request.
"""

import json
import logging
import time
from typing import Any

import requests

from psg_fatigue import config
from psg_fatigue.collect.http import FetchedFile, get_with_retry, utc_now_iso

logger = logging.getLogger(__name__)


class MissingPageError(RuntimeError):
    """Raised when the API does not return the wikitext of a requested page."""


def api_params(title: str) -> dict[str, str]:
    """Query parameters of the `action=parse` call for one page (wikitext + revision id)."""
    return {
        "action": "parse",
        "page": title,
        "prop": "wikitext|revid",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    }


def check_parse_payload(payload: dict[str, Any], title: str) -> int:
    """Return the revision id of a successful `action=parse` response.

    The API answers HTTP 200 even for a missing page, with an `error` object instead
    of `parse`, so the body must be checked explicitly.
    """
    if "error" in payload:
        error = payload["error"]
        raise MissingPageError(
            f"Wikipedia API error for {title!r}: {error.get('code')} - {error.get('info')}"
        )
    parse = payload.get("parse")
    if not isinstance(parse, dict) or not parse.get("wikitext") or "revid" not in parse:
        raise MissingPageError(f"No wikitext/revid returned for {title!r}")
    return int(parse["revid"])


def fetch_season_page(session: requests.Session, season: str) -> FetchedFile:
    """Download one season page and check that it really contains wikitext."""
    title = config.wiki_page_title(season)
    response = get_with_retry(session, config.WIKI_API_URL, api_params(title))
    retrieved_at = utc_now_iso()
    payload = json.loads(response.content)
    revid = check_parse_payload(payload, title)
    resolved_title = str(payload["parse"]["title"])
    logger.info("Wikipedia %s: revid %d, %d bytes", resolved_title, revid, len(response.content))
    return FetchedFile(
        file_name=f"wiki_{season}.json",
        source="wikipedia",
        season=season,
        url=response.url,
        method="api",
        http_status=response.status_code,
        retrieved_at_utc=retrieved_at,
        content=response.content,
        extra={"title": resolved_title, "revid": revid},
    )


def fetch_all_pages(session: requests.Session) -> list[FetchedFile]:
    """Download every season page of `config.WIKI_SEASONS`, at most one request per second."""
    pages = []
    for index, season in enumerate(config.WIKI_SEASONS):
        if index > 0:
            time.sleep(config.REQUEST_INTERVAL_SECONDS)
        pages.append(fetch_season_page(session, season))
    return pages
