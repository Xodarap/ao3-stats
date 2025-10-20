"""Scrape AO3 relationship statistics using only the standard library."""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelationshipStats:
    """Aggregate statistics for a relationship tag."""

    name: str
    kudos: int


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
    """Parse AO3 works listing pages to extract relationship and kudos data."""

    def __init__(self) -> None:
        super().__init__()
        self.works: List[Dict[str, Optional[int] | List[str]]] = []
        self._current_work: Optional[Dict[str, Optional[int] | List[str]]] = None
        self._in_work = False
        self._work_depth = 0
        self._capture_kudos = False
        self._kudos_buffer: List[str] = []
        self._capture_relationship = False
        self._relationship_buffer: List[str] = []
        self._in_next_li = False
        self.has_next_page = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "li" and {"work", "blurb", "group"}.issubset(class_names):
            self._current_work = {"relationships": [], "kudos": None}
            self.works.append(self._current_work)
            self._in_work = True
            self._work_depth = 0
            return

        if tag == "li" and "next" in class_names:
            self._in_next_li = True

        if self._in_work:
            self._work_depth += 1
            if tag == "dd" and "kudos" in class_names:
                self._capture_kudos = True
                self._kudos_buffer = []
            elif tag == "li" and "relationships" in class_names:
                self._capture_relationship = True
                self._relationship_buffer = []

        if self._in_next_li and tag == "a":
            # AO3 only includes the "next" link when a subsequent page is available.
            self.has_next_page = True

    def handle_endtag(self, tag: str) -> None:
        if self._capture_kudos and tag == "dd":
            text = "".join(self._kudos_buffer).strip().replace(",", "")
            if text.isdigit():
                assert self._current_work is not None
                self._current_work["kudos"] = int(text)
            self._capture_kudos = False
            self._kudos_buffer = []

        if self._capture_relationship and tag == "li":
            text = "".join(self._relationship_buffer).strip()
            if text:
                assert self._current_work is not None
                relationships = self._current_work["relationships"]
                assert isinstance(relationships, list)
                relationships.append(text)
            self._capture_relationship = False
            self._relationship_buffer = []

        if tag == "li" and self._in_next_li:
            self._in_next_li = False

        if self._in_work:
            if self._work_depth > 0:
                self._work_depth -= 1
            else:
                if tag == "li":
                    self._in_work = False
                    self._current_work = None

    def handle_data(self, data: str) -> None:
        if self._capture_kudos:
            self._kudos_buffer.append(data)
        if self._capture_relationship:
            self._relationship_buffer.append(data)


def _parse_kudos(value: Optional[int]) -> Optional[int]:
    return value if isinstance(value, int) else None


def _parse_relationships(value: Optional[int] | List[str]) -> List[str]:
    return value if isinstance(value, list) else []


def _encode_tag(tag: str) -> str:
    """Encode an AO3 tag to its URL slug form."""

    for old, new in TAG_REPLACEMENTS:
        tag = tag.replace(old, new)
    return quote(tag, safe="*")


def _fetch_tag_page(tag: str, page: int) -> Tuple[List[Dict[str, Optional[int] | List[str]]], bool]:
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
    return parser.works, parser.has_next_page


def scrape_relationship_kudos(
    tag: str,
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
) -> Dict[str, RelationshipStats]:
    """Scrape aggregate kudos for relationships under a given tag."""

    counter: Counter[str] = Counter()
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        works, has_next = _fetch_tag_page(tag, page)
        if not works:
            break
        for work in works:
            kudos = _parse_kudos(work.get("kudos"))
            if kudos is None:
                continue
            for relationship in _parse_relationships(work.get("relationships")):
                counter[relationship] += kudos
        if not has_next:
            break
        page += 1
        time.sleep(delay)

    return {
        name: RelationshipStats(name=name, kudos=kudos)
        for name, kudos in counter.most_common()
    }


def scrape_multiple_tags(
    tags: Iterable[str],
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
) -> Dict[str, List[RelationshipStats]]:
    """Scrape multiple tags and return a mapping of tag to sorted stats."""

    results: Dict[str, List[RelationshipStats]] = {}
    for tag in tags:
        stats_map = scrape_relationship_kudos(tag, max_pages=max_pages, delay=delay)
        results[tag] = list(stats_map.values())
        time.sleep(delay)
    return results
