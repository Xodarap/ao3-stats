"""Generate monthly ship hit totals for KPop Demon Hunters works."""
from __future__ import annotations

"""Generate monthly ship hit totals for KPop Demon Hunters works."""

import argparse
from pathlib import Path

import pandas as pd

from monthly_ship_hits import ShipNormalizer, compute_monthly_ship_hits


def _strip_relationship_suffix(text: str) -> str:
    return text.rstrip().removesuffix("- Relationship").rstrip()


def _clean_ship_series(series: pd.Series) -> pd.Series:
    cleaned = []
    for value in series.fillna(""):
        parts = []
        for part in str(value).split(";"):
            cleaned_part = _strip_relationship_suffix(part.strip())
            if cleaned_part:
                parts.append(cleaned_part)
        cleaned.append("; ".join(parts))
    return pd.Series(cleaned, index=series.index)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a month-by-ship pivot table of total hits for works tagged "
            "with the KPop Demon Hunters (2025) event."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/kpop_demon_hunters_metadata.csv"),
        help="Path to the scraped works metadata CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/kpop_demon_hunters_monthly_ship_hits.csv"),
        help="Where to write the pivot table CSV.",
    )
    return parser.parse_args()


def load_metadata(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={"date": "created"})
    df = df[["created", "ships", "hits"]].copy()
    df["ships"] = _clean_ship_series(df["ships"])

    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df["hits"] = pd.to_numeric(df["hits"], errors="coerce")

    df = df.dropna(subset=["created", "ships", "hits"])
    return df


def main() -> int:
    args = parse_args()

    df = load_metadata(args.input)
    normalizer = ShipNormalizer(df["ships"])
    pivot = compute_monthly_ship_hits(df, normalizer=normalizer)

    totals = pivot.sum(axis=0)
    top_columns = totals.nlargest(10).index
    pivot = pivot.loc[:, top_columns]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pivot.to_csv(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
