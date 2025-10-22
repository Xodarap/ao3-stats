"""Generate a month-by-ship pivot table of total hits."""
from __future__ import annotations

import argparse
import difflib
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Sequence

import pandas as pd


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
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help=(
            "If provided, limit the output to the top K ships ranked by total hits. "
            "All other ships are omitted from the pivot table."
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


_CONNECTOR_RE = re.compile(r"\s*([/&])\s*")


def _clean_ship_part(part: str) -> str:
    """Return a ship component with fandom parentheses removed."""

    part = part.strip()
    if not part:
        return ""

    # Drop any parenthetical fandom qualifiers, even if the closing parenthesis
    # is missing in the source data.
    part = re.sub(r"\s*\([^)]*\)", "", part)
    part = re.sub(r"\s*\([^)]*$", "", part)

    # Collapse repeated whitespace left behind by the removals.
    part = re.sub(r"\s+", " ", part)
    return part.strip()


def _tokenize_ship(ship: str) -> tuple[list[str], list[str]]:
    """Split a ship into cleaned parts and the connectors between them."""

    parts: list[str] = []
    connectors: list[str] = []
    last_index = 0

    for match in _CONNECTOR_RE.finditer(ship):
        part = _clean_ship_part(ship[last_index:match.start()])
        connector = match.group(1)

        if part:
            parts.append(part)
            connectors.append(connector)
        elif connectors:
            # Multiple connectors in a row: keep only the most recent one.
            connectors[-1] = connector

        last_index = match.end()

    final_part = _clean_ship_part(ship[last_index:])
    if final_part:
        parts.append(final_part)
    elif connectors:
        connectors.pop()

    # Ensure we only keep connectors that have a following part.
    if connectors and len(connectors) >= len(parts):
        connectors = connectors[: max(len(parts) - 1, 0)]

    return parts, connectors


def _join_ship(parts: list[str], connectors: list[str]) -> str:
    """Rebuild a ship string from parts and connectors."""

    if not parts:
        return ""

    result: list[str] = [parts[0]]
    for connector, part in zip(connectors, parts[1:]):
        if connector == "/":
            result.append("/")
            result.append(part)
        elif connector == "&":
            result.append(" & ")
            result.append(part)
        else:
            result.append(f" {connector} ")
            result.append(part)

    return "".join(result)


def canonicalize_ship(ship: str) -> str:
    """Normalize ship strings while preserving connector semantics."""

    ship = ship.strip()
    if not ship:
        return ""

    # Apply Unicode normalization first to standardize punctuation variants.
    ship = unicodedata.normalize("NFKC", ship)

    parts, connectors = _tokenize_ship(ship)
    if not parts:
        return ""

    return _join_ship(parts, connectors)


def _split_part(part: str) -> tuple[str, str]:
    """Return the base name and suffix (parenthetical context) for a ship part."""
    if not part:
        return "", ""

    # Preserve any parenthetical context so it can be reattached to the canonical base.
    pieces = re.split(r"(\s*\([^)]*\))", part)
    base = pieces[0].strip()
    suffix = "".join(pieces[1:])
    return base, suffix


def _base_key(text: str) -> str:
    """Return a normalized key for matching base character names."""
    return re.sub(r"[^0-9a-z]+", "", unicodedata.normalize("NFKC", text).lower())


class ShipNormalizer:
    """Canonicalize ship names using frequency-aware fuzzy matching for typos."""

    def __init__(
        self,
        ships: pd.Series,
        *,
        fuzzy_threshold: float = 0.85,
        min_direct_count: int = 5,
        min_candidate_count: int = 10,
        frequency_multiplier: int = 5,
    ) -> None:
        self._fuzzy_threshold = fuzzy_threshold
        self._min_direct_count = min_direct_count
        self._min_candidate_count = min_candidate_count
        self._frequency_multiplier = frequency_multiplier

        normalized_ships = (
            ships.fillna("")
            .astype(str)
            .str.split(";")
            .explode()
            .dropna()
            .str.strip()
        )
        normalized_ships = normalized_ships[normalized_ships != ""]
        normalized_ships = normalized_ships.apply(canonicalize_ship)

        base_counts: Counter[str] = Counter()
        key_to_base: dict[str, str] = {}
        suffix_counts: dict[str, Counter[str]] = {}

        for ship in normalized_ships:
            parts, _ = _tokenize_ship(ship)
            for part in parts:
                base, suffix = _split_part(part)
                if not base:
                    continue
                base_counts[base] += 1
                key = _base_key(base)
                current = key_to_base.get(key)
                if current is None or base_counts[base] > base_counts[current]:
                    key_to_base[key] = base
                suffix_counter = suffix_counts.setdefault(base, Counter())
                suffix_counter[suffix] += 1

        self._base_counts = base_counts
        self._key_to_base = key_to_base
        self._preferred_suffix = {
            base: max(
                counts.items(),
                key=lambda item: (item[1], len(item[0]), item[0]),
            )[0]
            for base, counts in suffix_counts.items()
        }
        self._common_bases = [
            base
            for base in sorted(
                base_counts,
                key=lambda name: (-base_counts[name], name.lower()),
            )
            if base_counts[base] >= self._min_direct_count
        ]

    def normalize(self, ship: str) -> str:
        """Normalize a raw ship string and correct common typos."""
        canonical = canonicalize_ship(ship)
        if not canonical:
            return ""

        parts, connectors = _tokenize_ship(canonical)

        corrected_parts: list[str] = []
        for part in parts:
            base, suffix = _split_part(part)
            if not base:
                continue
            corrected_base = self._normalize_base(base)
            preferred_suffix = self._preferred_suffix.get(corrected_base, suffix)
            corrected_parts.append(corrected_base + preferred_suffix)

        return _join_ship(corrected_parts, connectors)

    def _normalize_base(self, base: str) -> str:
        key = _base_key(base)
        candidate = self._key_to_base.get(key)
        if candidate:
            candidate_count = self._base_counts[candidate]
            if candidate_count >= self._min_direct_count:
                return candidate

        fuzzy_candidate = self._fuzzy_match_base(base)
        if fuzzy_candidate:
            return fuzzy_candidate

        return candidate if candidate else base

    def _fuzzy_match_base(self, base: str) -> str | None:
        if not self._common_bases:
            return None

        matches = difflib.get_close_matches(
            base,
            self._common_bases,
            n=1,
            cutoff=self._fuzzy_threshold,
        )
        if not matches:
            return None

        candidate = matches[0]
        candidate_count = self._base_counts[candidate]
        base_count = self._base_counts.get(base, 0)
        if candidate_count >= max(self._min_candidate_count, base_count * self._frequency_multiplier):
            return candidate
        return None


def canonicalize_ship_list(
    ships: list[str],
    *,
    normalizer: ShipNormalizer | None = None,
) -> list[str]:
    """Return a list of canonical ship strings, dropping any empties."""
    canonical: list[str] = []
    for ship in ships:
        if normalizer is not None:
            normalized = normalizer.normalize(ship)
        else:
            normalized = canonicalize_ship(ship)
        if normalized:
            canonical.append(normalized)
    return canonical


def explode_ships(
    df: pd.DataFrame,
    *,
    normalizer: ShipNormalizer | None = None,
) -> pd.DataFrame:
    """Return a DataFrame with one row per (work, ship) pair."""
    ships_series = (
        df["ships"]
        .fillna("")
        .astype(str)
        .str.split(";")
        .apply(canonicalize_ship_list, normalizer=normalizer)
    )
    exploded = df.copy()
    exploded["ship"] = ships_series
    exploded = exploded.explode("ship")
    exploded = exploded.dropna(subset=["ship"])
    exploded = exploded.loc[exploded["ship"] != ""]
    return exploded


def compute_ship_hits_by_period(
    df: pd.DataFrame,
    *,
    freq: str,
    normalizer: ShipNormalizer | None = None,
) -> pd.DataFrame:
    """Aggregate total hits per ship for periods derived from the created date."""

    df = df.copy()
    df["period"] = df["created"].dt.to_period(freq).astype(str)
    exploded = explode_ships(df, normalizer=normalizer)

    if exploded.empty:
        raise ValueError("No ship data available after exploding ship list.")

    grouped = (
        exploded.groupby(["period", "ship"], sort=True)["hits"].sum().sort_index()
    )
    pivot = grouped.unstack(fill_value=0).sort_index(axis=1)
    return pivot


def compute_monthly_ship_hits(
    df: pd.DataFrame,
    *,
    normalizer: ShipNormalizer | None = None,
) -> pd.DataFrame:
    """Aggregate total hits per month for each ship."""

    return compute_ship_hits_by_period(df, freq="M", normalizer=normalizer)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    df = load_created_dates(args.input)
    normalizer = ShipNormalizer(df["ships"])
    pivot = compute_monthly_ship_hits(df, normalizer=normalizer)

    if args.top_k is not None:
        if args.top_k < 1:
            raise ValueError("--top-k must be a positive integer when provided.")
        totals = pivot.sum(axis=0)
        top_columns = totals.nlargest(args.top_k).index
        pivot = pivot.loc[:, top_columns]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        pivot.to_csv(args.output)
    else:
        pivot.to_csv(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
