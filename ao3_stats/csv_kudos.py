"""Command-line utility to scrape kudos totals for tags from a CSV list."""
from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Sequence, Set

from .scraper import TagKudosStats, scrape_tag_kudos

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    input_csv: Path
    output_csv: Path
    max_pages: int | None
    delay: float
    start_date: date | None
    end_date: date | None


def parse_args(argv: Sequence[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape kudos totals for relationship tags listed in a CSV file."
        )
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="CSV file containing a 'relationship' column with AO3 tags to scrape.",
    )
    parser.add_argument(
        "output_csv",
        type=Path,
        help=(
            "Destination CSV file. Results are appended incrementally so rerunning "
            "will resume from the last completed tag."
        ),
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Maximum number of works pages to fetch per tag (default: all pages).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between page requests (default: 1.0).",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=None,
        help="Only include works posted on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="Only include works posted on or before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("--start-date must be before or equal to --end-date")

    return Config(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        max_pages=args.pages,
        delay=args.delay,
        start_date=args.start_date,
        end_date=args.end_date,
    )


def read_relationships(path: Path) -> Iterator[str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "relationship" not in reader.fieldnames:
            raise ValueError(
                "Input CSV must contain a 'relationship' column."
            )
        for row in reader:
            relationship = (row.get("relationship") or "").strip()
            if relationship:
                yield relationship


def load_completed(path: Path) -> Set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "relationship" not in reader.fieldnames:
            return set()
        return {
            (row.get("relationship") or "").strip()
            for row in reader
            if row.get("relationship")
        }


def ensure_output(path: Path, fieldnames: Sequence[str]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()


def append_result(path: Path, fieldnames: Sequence[str], row: dict[str, object]) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writerow(row)
        handle.flush()


def scrape_relationship(relationship: str, cfg: Config) -> TagKudosStats:
    LOGGER.info("Scraping %s", relationship)
    return scrape_tag_kudos(
        relationship,
        max_pages=cfg.max_pages,
        delay=cfg.delay,
        date_from=cfg.start_date,
        date_to=cfg.end_date,
    )


def main(argv: Sequence[str] | None = None) -> int:
    cfg = parse_args(argv)

    relationships = list(read_relationships(cfg.input_csv))
    completed = load_completed(cfg.output_csv)
    fieldnames = (
        "relationship",
        "kudos",
        "works",
        "words",
        "chapters",
        "collections",
        "comments",
        "bookmarks",
        "hits",
        "unique_authors",
    )
    ensure_output(cfg.output_csv, fieldnames)

    for relationship in relationships:
        if relationship in completed:
            LOGGER.info("Skipping %s (already completed)", relationship)
            continue
        stats = scrape_relationship(relationship, cfg)
        append_result(
            cfg.output_csv,
            fieldnames,
            {
                "relationship": relationship,
                "kudos": stats.kudos,
                "works": stats.works,
                "words": stats.words,
                "chapters": stats.chapters,
                "collections": stats.collections,
                "comments": stats.comments,
                "bookmarks": stats.bookmarks,
                "hits": stats.hits,
                "unique_authors": stats.unique_authors,
            },
        )
        completed.add(relationship)

    LOGGER.info("Finished processing %d relationship tags", len(relationships))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
