"""Scrape AO3 ship kudos totals using only the standard library."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Set, Tuple
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
    words: int
    chapters: int
    collections: int
    comments: int
    bookmarks: int
    hits: int
    unique_authors: int


@dataclass
class PageStats:
    """Aggregate statistics extracted from a single works listing page."""

    kudos: int = 0
    works: int = 0
    words: int = 0
    chapters: int = 0
    collections: int = 0
    comments: int = 0
    bookmarks: int = 0
    hits: int = 0
    authors: Set[str] = field(default_factory=set)


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


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _WorksParser(HTMLParser):
    """Parse AO3 works listing pages to extract kudos data."""

    def __init__(self) -> None:
        super().__init__()
        self.kudos_total = 0
        self.words_total = 0
        self.chapters_total = 0
        self.collections_total = 0
        self.comments_total = 0
        self.bookmarks_total = 0
        self.hits_total = 0
        self.work_count = 0
        self.unique_authors: Set[str] = set()
        self._capture_field: Optional[str] = None
        self._field_buffer: List[str] = []
        self._in_next_li = False
        self.has_next_page = False
        self._in_work = False
        self._work_tag_stack: List[str] = []
        self._current_work_authors: Set[str] = set()
        self._capture_author = False
        self._author_buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "li" and "work" in class_names:
            self._in_work = True
            self._work_tag_stack = [tag]
            self._current_work_authors = set()
        elif self._in_work and tag not in VOID_TAGS:
            self._work_tag_stack.append(tag)

        if tag == "dd":
            field = self._extract_stat_field(class_names)
            if field:
                self._capture_field = field
                self._field_buffer = []

        if tag == "li" and "next" in class_names:
            self._in_next_li = True

        if self._in_next_li and tag == "a":
            # AO3 only includes the "next" link when a subsequent page is available.
            self.has_next_page = True

        if self._in_work and tag == "a":
            rel_values = set((attrs_dict.get("rel") or "").split())
            if "author" in rel_values:
                self._capture_author = True
                self._author_buffer = []

    @staticmethod
    def _extract_stat_field(class_names: Set[str]) -> Optional[str]:
        for candidate in (
            "kudos",
            "words",
            "chapters",
            "collections",
            "comments",
            "bookmarks",
            "hits",
        ):
            if candidate in class_names:
                return candidate
        return None

    @staticmethod
    def _parse_int(text: str) -> Optional[int]:
        cleaned = text.strip().replace(",", "")
        if not cleaned or cleaned in {"-", "—", "?"}:
            return 0
        if cleaned.isdigit():
            return int(cleaned)
        return None

    @staticmethod
    def _parse_chapters(text: str) -> int:
        cleaned = text.split("/", 1)[0].strip().replace(",", "")
        if not cleaned or cleaned in {"-", "—", "?"}:
            return 0
        if cleaned.isdigit():
            return int(cleaned)
        return 0

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field and tag == "dd":
            text = "".join(self._field_buffer)
            field = self._capture_field
            self._capture_field = None
            self._field_buffer = []
            if field == "chapters":
                value = self._parse_chapters(text)
            else:
                value = self._parse_int(text)
                if value is None:
                    value = 0

            if field == "kudos":
                self.kudos_total += value
            elif field == "words":
                self.words_total += value
            elif field == "chapters":
                self.chapters_total += value
            elif field == "collections":
                self.collections_total += value
            elif field == "comments":
                self.comments_total += value
            elif field == "bookmarks":
                self.bookmarks_total += value
            elif field == "hits":
                self.hits_total += value

        if tag == "li" and self._in_next_li:
            self._in_next_li = False

        if self._capture_author and tag == "a":
            author = "".join(self._author_buffer).strip()
            if author:
                self._current_work_authors.add(author)
            self._capture_author = False
            self._author_buffer = []

        if self._in_work:
            if self._work_tag_stack:
                self._work_tag_stack.pop()
            if not self._work_tag_stack:
                self._in_work = False
                if self._current_work_authors:
                    self.unique_authors.update(self._current_work_authors)
                self.work_count += 1
                self._current_work_authors = set()

    def handle_data(self, data: str) -> None:
        if self._capture_field:
            self._field_buffer.append(data)
        if self._capture_author:
            self._author_buffer.append(data)


def _encode_tag(tag: str) -> str:
    """Encode an AO3 tag to its URL slug form."""

    for old, new in TAG_REPLACEMENTS:
        tag = tag.replace(old, new)
    return quote(tag, safe="*")


def _fetch_tag_page(
    tag: str,
    page: int,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[PageStats, bool]:
    # Relationship tags encode special characters using `*x*` sequences.
    encoded_tag = _encode_tag(tag)
    url = f"{BASE_URL}/tags/{encoded_tag}/works"
    params = {
        "work_search[sort_column]": "hits",
        "work_search[sort_direction]": "desc",
    }
    if page > 1:
        params["page"] = page
    if date_from:
        params["work_search[date_from]"] = date_from
    if date_to:
        params["work_search[date_to]"] = date_to
    if params:
        url = f"{url}?{urlencode(params)}"

    LOGGER.info("Fetching %s page %s", tag, page)
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _WorksParser()
    parser.feed(html)
    page_stats = PageStats(
        kudos=parser.kudos_total,
        works=parser.work_count,
        words=parser.words_total,
        chapters=parser.chapters_total,
        collections=parser.collections_total,
        comments=parser.comments_total,
        bookmarks=parser.bookmarks_total,
        hits=parser.hits_total,
        authors=set(parser.unique_authors),
    )
    return page_stats, parser.has_next_page


def scrape_tag_kudos(
    tag: str,
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> TagKudosStats:
    """Scrape kudos totals for a single relationship tag."""

    total_kudos = 0
    total_words = 0
    total_chapters = 0
    total_collections = 0
    total_comments = 0
    total_bookmarks = 0
    total_hits = 0
    works = 0
    unique_authors: Set[str] = set()
    page = 1
    date_from_str = date_from.isoformat() if date_from else None
    date_to_str = date_to.isoformat() if date_to else None

    while True:
        if max_pages is not None and page > max_pages:
            break
        page_stats, has_next = _fetch_tag_page(
            tag,
            page,
            date_from=date_from_str,
            date_to=date_to_str,
        )
        if page_stats.works == 0:
            break
        total_kudos += page_stats.kudos
        total_words += page_stats.words
        total_chapters += page_stats.chapters
        total_collections += page_stats.collections
        total_comments += page_stats.comments
        total_bookmarks += page_stats.bookmarks
        total_hits += page_stats.hits
        works += page_stats.works
        unique_authors.update(page_stats.authors)
        if not has_next:
            break
        page += 1
        time.sleep(delay)

    return TagKudosStats(
        tag=tag,
        kudos=total_kudos,
        works=works,
        words=total_words,
        chapters=total_chapters,
        collections=total_collections,
        comments=total_comments,
        bookmarks=total_bookmarks,
        hits=total_hits,
        unique_authors=len(unique_authors),
    )


def scrape_multiple_tags(
    tags: Iterable[str],
    *,
    max_pages: Optional[int] = None,
    delay: float = REQUEST_DELAY,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Dict[str, TagKudosStats]:
    """Scrape multiple tags and return a mapping of tag to totals."""

    results: Dict[str, TagKudosStats] = {}
    for tag in tags:
        results[tag] = scrape_tag_kudos(
            tag,
            max_pages=max_pages,
            delay=delay,
            date_from=date_from,
            date_to=date_to,
        )
        time.sleep(delay)
    return results
