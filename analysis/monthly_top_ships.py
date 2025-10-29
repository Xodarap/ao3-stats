"""Report the most popular ship per month by total hits."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

from analysis.monthly_ship_hits import (
    ShipNormalizer,
    compute_monthly_ship_hits,
    load_created_dates,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Return parsed command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Identify the most popular ship for each month and output the results "
            "sorted by monthly hits."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/created_dates.csv"),
        help="CSV file containing work metadata with created dates.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Optional path where the CSV of monthly top ships should be written. "
            "If omitted, results are printed to stdout."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optionally restrict the output to the first N rows after sorting by "
            "monthly hits."
        ),
    )
    return parser.parse_args(argv)


def compute_monthly_top_ships(pivot: pd.DataFrame) -> pd.DataFrame:
    """Return the top ship per month from a ship-by-month pivot table.

    The result includes the total hits for each ship across *all* months in the
    pivot so that the output can be globally ordered by overall popularity, not
    just the individual monthly hit count.
    """
    if pivot.empty:
        raise ValueError("Pivot table is empty; nothing to report.")

    top_ships = pivot.idxmax(axis=1)
    top_hits = pivot.max(axis=1)
    ship_totals = pivot.sum(axis=0)

    result = pd.DataFrame(
        {
            "month": pivot.index.to_list(),
            "ship": top_ships.to_list(),
            "monthly_hits": top_hits.to_list(),
            "ship_total_hits": top_ships.map(ship_totals).to_list(),
        }
    )

    result = result.sort_values(
        by=["ship_total_hits", "monthly_hits", "month"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    df = load_created_dates(args.input)
    normalizer = ShipNormalizer(df["ships"])
    pivot = compute_monthly_ship_hits(df, normalizer=normalizer)
    monthly_top = compute_monthly_top_ships(pivot)

    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be a positive integer when provided.")
        monthly_top = monthly_top.head(args.limit)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        monthly_top.to_csv(args.output, index=False)
    else:
        monthly_top.to_csv(sys.stdout, index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
