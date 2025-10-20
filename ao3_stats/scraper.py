"""Scrape AO3 ship kudos totals using only the standard library."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TagKudosStats:
    """Aggregate kudos totals for a specific relationship tag."""

    tag: str
    kudos: int
    works: int


DEFAULT_HEADERS = {
    "User-Agent": (
        "ao3-stats-scraper/1.0 (+https://example.com; contact: local-run)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

BASE_URL = "https://archiveofourown.org"
REQUEST_DELAY = 1.0  # seconds between requests to avoid hammering the site.

# Matches the transformations applied by AO3's Tag#to_param implementation.
TAG_REPLACEMENTS = (
    ("/", "*s*"),
    ("&", "*a*"),
    (".", "*d*"),
    ("?", "*q*"),
    ("#", "*h*"),
)


class _WorksParser(HTMLParser):
    """Parse AO3 works listing pages to extract kudos data."""

    def __init__(self) -> None:
        super().__init__()
        self.kudos_values: List[int] = []
        self._capture_kudos = False
        self._kudos_buffer: List[str] = []
        self._in_next_li = False
        self.has_next_page = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "dd" and "kudos" in class_names:
            self._capture_kudos = True
            self._kudos_buffer = []

        if tag == "li" and "next" in class_names:
            self._in_next_li = True

        if self._in_next_li and tag == "a":
            # AO3 only includes the "next" link when a subsequent page is available.
            self.has_next_page = True

    def handle_endtag(self, tag: str) -> None:
        if self._capture_kudos and tag == "dd":
            text = "".join(self._kudos_buffer).strip().replace(",", "")
            if text.isdigit():
                self.kudos_values.append(int(text))
            self._capture_kudos = False
            self._kudos_buffer = []

        if tag == "li" and self._in_next_li:
            self._in_next_li = False

    def handle_data(self, data: str) -> None:
        if self._capture_kudos:
            self._kudos_buffer.append(data)


def _encode_tag(tag: str) -> str:
    """Encode an AO3 tag to its URL slug form."""

    for old, new in TAG_REPLACEMENTS:
        tag = tag.replace(old, new)
    return quote(tag, safe="*")


def _fetch_tag_page(tag: str, page: int) -> Tuple[List[int], bool]:
    # Relationship tags encode special characters using `*x*` sequences.
    encoded_tag = _encode_tag(tag)
    url = f"{BASE_URL}/tags/{encoded_tag}/works"
    if page > 1:
        url = f"{url}?{urlencode({'page': page})}"

    LOGGER.info("Fetching %s page %s", tag, page)
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _WorksParser()
    parser.feed(html)
    return parser.kudos_values, parser.has_next_page


def scrape_tag_kudos(
    tag: str,
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
) -> TagKudosStats:
    """Scrape kudos totals for a single relationship tag."""

    total_kudos = 0
    works = 0
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        kudos_values, has_next = _fetch_tag_page(tag, page)
        if not kudos_values:
            break
        total_kudos += sum(kudos_values)
        works += len(kudos_values)
        if not has_next:
            break
        page += 1
        time.sleep(delay)

    return TagKudosStats(tag=tag, kudos=total_kudos, works=works)


def scrape_multiple_tags(
    tags: Iterable[str],
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
) -> Dict[str, TagKudosStats]:
    """Scrape multiple tags and return a mapping of tag to totals."""

    results: Dict[str, TagKudosStats] = {}
    for tag in tags:
        results[tag] = scrape_tag_kudos(tag, max_pages=max_pages, delay=delay)
        time.sleep(delay)
    return results
