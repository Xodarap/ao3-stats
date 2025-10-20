from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from typing import List

from .scraper import scrape_multiple_tags


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape AO3 kudos totals for specific relationship tags."
    )
    parser.add_argument(
        "tags",
        nargs="+",
        help="Relationship tags to scrape (e.g. 'A/B' ships)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Maximum number of pages of works to scrape per tag (default: 1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between requests (default: 1.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        help="Only include works posted on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        help="Only include works posted on or before this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Logging level (default: WARNING)",
    )
    args = parser.parse_args(argv)
    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("--start-date must be before or equal to --end-date")
    return args


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))

    results = scrape_multiple_tags(
        args.tags,
        max_pages=args.pages,
        delay=args.delay,
        date_from=args.start_date,
        date_to=args.end_date,
    )

    if args.json:
        serialisable = {tag: stats.__dict__ for tag, stats in results.items()}
        print(json.dumps(serialisable, indent=2))
    else:
        for tag, stats in results.items():
            print(f"{tag}: {stats.kudos} kudos across {stats.works} works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
