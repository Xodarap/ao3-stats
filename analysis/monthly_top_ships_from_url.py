"""Scrape an AO3 works listing URL and report the top ship per month by hits."""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

from analysis.monthly_ship_hits import ShipNormalizer, compute_monthly_ship_hits
from analysis.monthly_top_ships import compute_monthly_top_ships
from ao3_stats.works_metadata import fetch_page, scrape_works

_WORKS_TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+Works", re.IGNORECASE)
_WORKS_PER_PAGE = 20


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape an AO3 works listing URL, aggregate hits by month and ship, "
            "and report the top ship for each month."
        )
    )
    parser.add_argument("search_url", help="AO3 works listing URL to scrape.")
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        help=(
            "Number of pages to scrape. If omitted or set to 0, pages are inferred "
            "from the works total shown on the first page."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional CSV path for monthly top-ship results.",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="Optional CSV path for raw scraped metadata.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of monthly rows to output.",
    )
    return parser.parse_args(argv)


def infer_page_count(search_url: str) -> int:
    """Infer page count from the first listing page's works total."""
    html = fetch_page(search_url)
    match = _WORKS_TOTAL_RE.search(html)
    if match is None:
        return 1
    total_works = int(match.group(1).replace(",", ""))
    return max(1, math.ceil(total_works / _WORKS_PER_PAGE))


def scrape_metadata_dataframe(search_url: str, pages: int, delay: float) -> pd.DataFrame:
    """Scrape listing metadata into a DataFrame."""
    rows: list[dict[str, object]] = []
    for page_works in scrape_works(search_url, pages=pages, delay=delay):
        for work in page_works:
            rows.append(
                {
                    "ships": "; ".join(work.ships),
                    "hits": work.hits,
                    "date": work.date,
                    "url": work.url,
                }
            )

    return pd.DataFrame(rows)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    pages = args.pages if args.pages and args.pages > 0 else infer_page_count(args.search_url)
    metadata = scrape_metadata_dataframe(args.search_url, pages=pages, delay=max(0.0, args.delay))

    if metadata.empty:
        raise ValueError("No works were scraped; cannot compute monthly top ships.")

    normalizer = ShipNormalizer(metadata["ships"])
    pivot = compute_monthly_ship_hits(metadata, normalizer=normalizer)
    monthly_top = compute_monthly_top_ships(pivot)

    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be a positive integer when provided.")
        monthly_top = monthly_top.head(args.limit)

    if args.metadata_output is not None:
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        metadata.to_csv(args.metadata_output, index=False)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        monthly_top.to_csv(args.output, index=False)
    else:
        monthly_top.to_csv(sys.stdout, index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
