"""Augment works metadata CSV files with per-work creation dates."""

from __future__ import annotations

import argparse
import csv
import logging
import time
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)

BASE_HEADERS = {"User-Agent": "ao3-stats-created-date/1.0"}
DEFAULT_DELAY = 1.0


class _PublishedDateParser(HTMLParser):
    """Parse an AO3 work page to extract the published date."""

    def __init__(self) -> None:
        super().__init__()
        self._pending_label = False
        self._capturing_value = False
        self._buffer: List[str] = []
        self.published: str = ""

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "dt" and "published" in class_names:
            self._pending_label = True
            return

        if tag == "dd" and "published" in class_names and self._pending_label:
            self._pending_label = False
            self._capturing_value = True
            self._buffer = []
            datetime_value = attrs_dict.get("datetime", "")
            if datetime_value:
                self.published = datetime_value.strip()
            return

        if tag == "time" and self._capturing_value:
            datetime_value = attrs_dict.get("datetime", "")
            if datetime_value and not self.published:
                self.published = datetime_value.strip()

    def handle_data(self, data: str) -> None:
        if self._capturing_value:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "dd" and self._capturing_value:
            if not self.published:
                text_value = "".join(self._buffer).strip()
                if text_value:
                    self.published = " ".join(text_value.split())
            self._capturing_value = False
            self._buffer = []


def _augment_work_url(url: str) -> str:
    """Ensure the work URL includes the flags needed to view metadata."""

    parsed = urlparse(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"view_full_work", "view_adult"}
    ]
    query_pairs.append(("view_full_work", "true"))
    query_pairs.append(("view_adult", "true"))
    new_query = urlencode(query_pairs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def fetch_work_page(url: str) -> str:
    """Download the HTML for a work page."""

    request = Request(url, headers=BASE_HEADERS)
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def extract_published_date(html: str) -> str:
    parser = _PublishedDateParser()
    parser.feed(html)
    return parser.published


def write_rows(path: str, fieldnames: Sequence[str], rows: Iterable[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def enrich_created_dates(
    rows: Iterable[dict[str, str]],
    delay: float,
) -> Iterable[dict[str, str]]:
    cache: Dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        work_url = row.get("url", "").strip()
        if not work_url:
            LOGGER.warning("Row %s missing work URL; skipping", index)
            row["created"] = ""
            yield row
            continue

        cached = cache.get(work_url)
        if cached is not None:
            row["created"] = cached
            yield row
            continue

        augmented_url = _augment_work_url(work_url)
        LOGGER.info("Fetching work %s: %s", index, augmented_url)
        try:
            html = fetch_work_page(augmented_url)
        except URLError as exc:
            LOGGER.error("Failed to fetch %s: %s", augmented_url, exc)
            created = ""
        else:
            created = extract_published_date(html)
            if not created:
                LOGGER.warning("Could not find created date for %s", augmented_url)

        cache[work_url] = created
        row["created"] = created
        yield row
        if delay:
            time.sleep(delay)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy a works metadata CSV and add each work's created date.",
    )
    parser.add_argument("input", help="Source works metadata CSV file.")
    parser.add_argument(
        "--output",
        default="works_with_created.csv",
        help="Destination CSV file (default: %(default)s).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay in seconds between work requests (default: %(default)s).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    input_path = args.input
    output_path = args.output
    delay = max(0.0, args.delay)

    with open(input_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise SystemExit("Input CSV must include headers")
        fieldnames = list(reader.fieldnames)
        if "created" not in fieldnames:
            fieldnames.append("created")

        enriched_rows = enrich_created_dates(reader, delay)
        write_rows(output_path, fieldnames, enriched_rows)

    LOGGER.info("Wrote created dates to %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
