"""Generate a month-by-ship pivot table of total hits."""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Sequence

import pandas as pd
import re


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a table where each row is a month, each column is a ship, and "
            "each value is the total number of hits for works featuring that ship "
            "in that month."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/created_dates.csv"),
        help="Path to the created dates CSV exported from AO3.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Optional path where the resulting CSV pivot table should be written. "
            "If omitted the table is printed to stdout."
        ),
    )
    return parser.parse_args(argv)


def load_created_dates(path: Path) -> pd.DataFrame:
    """Load the created dates dataset with the columns needed for aggregation."""
    df = pd.read_csv(path)
    df = df.dropna(subset=["created", "ships", "hits"])

    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df = df.dropna(subset=["created"])

    df["hits"] = pd.to_numeric(df["hits"], errors="coerce")
    df = df.dropna(subset=["hits"])

    return df


def canonicalize_ship(ship: str) -> str:
    """Normalize ship strings so variants like ``A/B`` and ``A & B`` combine."""
    ship = ship.strip()
    if not ship:
        return ""

    # Apply Unicode normalization first to standardize punctuation variants.
    ship = unicodedata.normalize("NFKC", ship)

    # Replace connectors ("/" or "&") with a single forward slash and tidy whitespace.
    ship = re.sub(r"\s*[/&]\s*", "/", ship)
    ship = re.sub(r"\s+", " ", ship)

    parts = [part.strip() for part in ship.split("/")]
    parts = [part for part in parts if part]
    return "/".join(parts)


def canonicalize_ship_list(ships: list[str]) -> list[str]:
    """Return a list of canonical ship strings, dropping any empties."""
    canonical: list[str] = []
    for ship in ships:
        normalized = canonicalize_ship(ship)
        if normalized:
            canonical.append(normalized)
    return canonical


def explode_ships(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with one row per (work, ship) pair."""
    ships_series = (
        df["ships"]
        .fillna("")
        .astype(str)
        .str.split(";")
        .apply(canonicalize_ship_list)
    )
    exploded = df.copy()
    exploded["ship"] = ships_series
    exploded = exploded.explode("ship")
    exploded = exploded.dropna(subset=["ship"])
    exploded = exploded.loc[exploded["ship"] != ""]
    return exploded


def compute_monthly_ship_hits(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate total hits per month for each ship."""
    df = df.copy()
    df["month"] = df["created"].dt.to_period("M").astype(str)
    exploded = explode_ships(df)

    if exploded.empty:
        raise ValueError("No ship data available after exploding ship list.")

    grouped = (
        exploded.groupby(["month", "ship"], sort=True)["hits"].sum().sort_index()
    )
    pivot = grouped.unstack(fill_value=0).sort_index(axis=1)
    return pivot


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    df = load_created_dates(args.input)
    pivot = compute_monthly_ship_hits(df)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        pivot.to_csv(args.output)
    else:
        pivot.to_csv(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
