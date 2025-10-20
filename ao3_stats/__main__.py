from __future__ import annotations

import argparse
import json
import logging
from typing import List

from .scraper import scrape_multiple_tags


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape AO3 relationship kudos totals.")
    parser.add_argument("tags", nargs="+", help="Tag names to scrape (e.g. fandoms)")
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
        "--top",
        type=int,
        default=10,
        help="Number of top relationships to show for each tag (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Logging level (default: WARNING)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))

    results = scrape_multiple_tags(args.tags, max_pages=args.pages, delay=args.delay)

    if args.json:
        serialisable = {
            tag: [stat.__dict__ for stat in stats]
            for tag, stats in results.items()
        }
        print(json.dumps(serialisable, indent=2))
    else:
        for tag, stats in results.items():
            print(f"\nTag: {tag}")
            for idx, stat in enumerate(stats[: args.top], start=1):
                print(f"{idx:>3}. {stat.name:<60} {stat.kudos:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
