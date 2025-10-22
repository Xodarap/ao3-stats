"""Scrape detailed AO3 work metadata into a CSV file."""

from __future__ import annotations

import argparse
import csv
import logging
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlparse, urlencode, urlunparse
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://archiveofourown.org"
DEFAULT_DELAY = 1.0
DEFAULT_PAGES = 1


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


@dataclass
class WorkMetadata:
    """Metadata describing a single AO3 work from a listing page."""

    work_id: str
    title: str
    authors: List[str]
    ships: List[str]
    language: str
    words: int
    chapters: str
    collections: int
    comments: int
    kudos: int
    bookmarks: int
    hits: int
    date: str
    url: str


class _WorkListParser(HTMLParser):
    """Parse AO3 work listing pages and extract metadata for each work."""

    def __init__(self) -> None:
        super().__init__()
        self.works: List[WorkMetadata] = []
        self._current_work: Optional[Dict[str, object]] = None
        self._work_stack: List[str] = []
        self._capture_title = False
        self._title_buffer: List[str] = []
        self._capture_author = False
        self._author_buffer: List[str] = []
        self._capture_field: Optional[str] = None
        self._field_buffer: List[str] = []
        self._capture_ship = False
        self._ship_buffer: List[str] = []
        self._capture_date = False
        self._date_buffer: List[str] = []
        self._in_heading = False
        self._in_relationships = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "li" and "work" in class_names:
            self._begin_work(attrs_dict)
            return

        if self._current_work is None:
            return

        if tag not in VOID_TAGS:
            self._work_stack.append(tag)

        if tag == "h4" and "heading" in class_names:
            self._in_heading = True

        if tag == "a":
            rel_values = set((attrs_dict.get("rel") or "").split())
            if "author" in rel_values:
                self._capture_author = True
                self._author_buffer = []
            elif self._in_heading and not self._capture_title and attrs_dict.get("href", "").startswith("/works/"):
                self._capture_title = True
                self._title_buffer = []
                self._current_work["url"] = BASE_URL + attrs_dict["href"]
            elif self._in_relationships and "tag" in class_names:
                self._capture_ship = True
                self._ship_buffer = []

        if tag == "dd":
            field = self._extract_stat_field(class_names)
            if field:
                self._capture_field = field
                self._field_buffer = []

        if tag == "li" and "relationships" in class_names:
            self._in_relationships = True

        if tag == "p" and "datetime" in class_names:
            self._capture_date = True
            self._date_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._current_work is None:
            return

        if tag == "a":
            if self._capture_title:
                self._current_work["title"] = self._clean_text(self._title_buffer)
                self._capture_title = False
            elif self._capture_author:
                author = self._clean_text(self._author_buffer)
                if author:
                    self._current_work.setdefault("authors", []).append(author)
                self._capture_author = False
            elif self._capture_ship:
                ship = self._clean_text(self._ship_buffer)
                if ship:
                    self._current_work.setdefault("ships", []).append(ship)
                self._capture_ship = False

        if tag == "dd" and self._capture_field:
            value = self._clean_text(self._field_buffer)
            self._assign_field(self._capture_field, value)
            self._capture_field = None

        if tag == "p" and self._capture_date:
            self._current_work["date"] = self._clean_text(self._date_buffer)
            self._capture_date = False

        if tag == "h4" and self._in_heading:
            self._in_heading = False

        if tag == "li" and self._in_relationships:
            # Closing the relationships list item.
            self._in_relationships = False

        if self._work_stack and tag == self._work_stack[-1]:
            self._work_stack.pop()

        if not self._work_stack:
            self._finish_work()

    def handle_data(self, data: str) -> None:
        if not data or self._current_work is None:
            return

        if self._capture_title:
            self._title_buffer.append(data)
        elif self._capture_author:
            self._author_buffer.append(data)
        elif self._capture_field:
            self._field_buffer.append(data)
        elif self._capture_ship:
            self._ship_buffer.append(data)
        elif self._capture_date:
            self._date_buffer.append(data)

    def _begin_work(self, attrs: Dict[str, Optional[str]]) -> None:
        work_id = (attrs.get("id") or "").replace("work_", "")
        self._current_work = {
            "work_id": work_id,
            "title": "",
            "authors": [],
            "ships": [],
            "language": "",
            "words": 0,
            "chapters": "",
            "collections": 0,
            "comments": 0,
            "kudos": 0,
            "bookmarks": 0,
            "hits": 0,
            "date": "",
            "url": "",
        }
        self._work_stack = ["li"]

    def _finish_work(self) -> None:
        if self._current_work is None:
            return

        work = WorkMetadata(
            work_id=str(self._current_work.get("work_id", "")),
            title=str(self._current_work.get("title", "")),
            authors=list(self._current_work.get("authors", [])),
            ships=list(self._current_work.get("ships", [])),
            language=str(self._current_work.get("language", "")),
            words=int(self._current_work.get("words", 0)),
            chapters=str(self._current_work.get("chapters", "")),
            collections=int(self._current_work.get("collections", 0)),
            comments=int(self._current_work.get("comments", 0)),
            kudos=int(self._current_work.get("kudos", 0)),
            bookmarks=int(self._current_work.get("bookmarks", 0)),
            hits=int(self._current_work.get("hits", 0)),
            date=str(self._current_work.get("date", "")),
            url=str(self._current_work.get("url", "")),
        )
        self.works.append(work)
        self._current_work = None
        self._work_stack = []

    def _assign_field(self, field: str, value: str) -> None:
        if self._current_work is None:
            return

        if field == "language":
            self._current_work["language"] = value
        elif field == "chapters":
            self._current_work["chapters"] = value.replace("\n", " ").strip()
        else:
            self._current_work[field] = self._parse_int(value)

    @staticmethod
    def _extract_stat_field(class_names: set[str]) -> Optional[str]:
        for candidate in (
            "language",
            "words",
            "chapters",
            "collections",
            "comments",
            "kudos",
            "bookmarks",
            "hits",
        ):
            if candidate in class_names:
                return candidate
        return None

    @staticmethod
    def _clean_text(parts: Sequence[str]) -> str:
        text = "".join(parts).strip()
        return " ".join(text.split())

    @staticmethod
    def _parse_int(text: str) -> int:
        cleaned = text.strip().replace(",", "")
        if not cleaned or cleaned in {"-", "—", "?"}:
            return 0
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        return int(digits) if digits else 0


def _url_with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "page"
    ]
    query_pairs.append(("page", str(page)))
    new_query = urlencode(query_pairs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def fetch_page(url: str) -> str:
    req = Request(url, headers={"User-Agent": "ao3-stats-metadata/1.0"})
    with urlopen(req) as response:
        return response.read().decode("utf-8")


def parse_works(html: str) -> List[WorkMetadata]:
    parser = _WorkListParser()
    parser.feed(html)
    return parser.works


def scrape_works(
    search_url: str, pages: int, delay: float, start_page: int = 1
) -> List[WorkMetadata]:
    works: List[WorkMetadata] = []
    for offset in range(pages):
        page_number = start_page + offset
        page_url = _url_with_page(search_url, page_number)
        LOGGER.info("Fetching page %s: %s", page_number, page_url)
        html = fetch_page(page_url)
        page_works = parse_works(html)
        if page_number > 1 and not page_works:
            LOGGER.info("No works returned on page %s; stopping early.", page_number)
            break
        works.extend(page_works)
        if page_number != pages:
            time.sleep(delay)
    return works


def write_csv(path: str, works: Sequence[WorkMetadata]) -> None:
    fieldnames = [
        "work_id",
        "title",
        "authors",
        "ships",
        "language",
        "words",
        "chapters",
        "collections",
        "comments",
        "kudos",
        "bookmarks",
        "hits",
        "date",
        "url",
    ]
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for work in works:
            writer.writerow(
                {
                    "work_id": work.work_id,
                    "title": work.title,
                    "authors": "; ".join(work.authors),
                    "ships": "; ".join(work.ships),
                    "language": work.language,
                    "words": work.words,
                    "chapters": work.chapters,
                    "collections": work.collections,
                    "comments": work.comments,
                    "kudos": work.kudos,
                    "bookmarks": work.bookmarks,
                    "hits": work.hits,
                    "date": work.date,
                    "url": work.url,
                }
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape AO3 work metadata for a search URL and save it as a CSV file."
        )
    )
    parser.add_argument(
        "search_url",
        help="AO3 works search URL, e.g. the filtered Arcane listing.",
    )
    parser.add_argument(
        "--output",
        default="works_metadata.csv",
        help="Destination CSV file (default: %(default)s).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_PAGES,
        help="Number of listing pages to fetch (default: %(default)s).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay in seconds between page requests (default: %(default)s).",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Listing page number to start fetching from (default: %(default)s).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    works = scrape_works(
        args.search_url,
        max(1, args.pages),
        max(0.0, args.delay),
        max(1, args.start_page),
    )
    write_csv(args.output, works)
    LOGGER.info("Wrote %s works to %s", len(works), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

