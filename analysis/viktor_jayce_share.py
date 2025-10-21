"""Generate Arcane ship share plots over time with different weighting metrics."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd


VICTOR_JAYCE_SHIPS = (
    "Jayce/Viktor (League of Legends)",
    "Viktor/Jayce (League of Legends)",
)


def load_created_dates(path: Path) -> pd.DataFrame:
    """Load and clean the created dates dataset."""
    df = pd.read_csv(path)
    df = df.dropna(subset=["created"])
    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df = df.dropna(subset=["created"])

    numeric_columns = ["words", "collections", "comments", "kudos", "bookmarks", "hits"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["works"] = 1.0
    df["month"] = df["created"].dt.to_period("M").dt.to_timestamp()
    df["ship_list"] = (
        df["ships"]
        .fillna("")
        .str.split(";")
        .apply(lambda ships: [ship.strip() for ship in ships if ship.strip()])
    )
    return df


def monthly_totals(df: pd.DataFrame, weight_columns: Iterable[str]) -> pd.DataFrame:
    """Aggregate monthly totals for the requested weight columns."""
    totals = df.groupby("month")[list(weight_columns)].sum().sort_index()
    return totals


def ship_monthly_totals(df: pd.DataFrame, weight_columns: Iterable[str]) -> pd.DataFrame:
    """Aggregate monthly totals for every ship present in the dataset."""
    exploded = df.explode("ship_list")
    if exploded.empty:
        raise ValueError("No ships found in dataset after exploding ship list.")

    exploded = exploded.loc[exploded["ship_list"].notna() & (exploded["ship_list"] != "")]
    if exploded.empty:
        raise ValueError("Ship list contains only empty values after cleaning.")

    grouped = (
        exploded.groupby(["month", "ship_list"])[list(weight_columns)].sum().sort_index()
    )
    return grouped


def compute_ship_shares(
    monthly_ship_totals: pd.DataFrame,
    month_totals: pd.DataFrame,
    weight_columns: Iterable[str],
) -> pd.DataFrame:
    """Return a DataFrame with per-ship share percentages for each weight."""
    share_frames: list[pd.DataFrame] = []
    months_index = month_totals.index

    for column in weight_columns:
        ship_values = (
            monthly_ship_totals[column]
            .unstack("ship_list")
            .reindex(months_index, fill_value=0.0)
            .sort_index(axis=1)
        )
        denominator = month_totals[column].replace({0: pd.NA})
        share = ship_values.divide(denominator, axis=0).fillna(0.0) * 100.0
        share.columns = pd.MultiIndex.from_product([[column], share.columns])
        share_frames.append(share)

    return pd.concat(share_frames, axis=1).sort_index()


def plot_shares(
    shares: pd.DataFrame, output_path: Path, title: str, ylabel: str = "Share of monthly total (%)"
) -> None:
    """Render the share plot and save it to ``output_path``."""
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)

    for column in shares.columns:
        ax.plot(shares.index, shares[column], label=column.capitalize())

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Work creation month")
    if not shares.empty:
        ax.set_ylim(0, min(100, shares.max().max() * 1.1))
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(title="Weighting")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_top_ships(average_shares: pd.DataFrame, top_n: int, output_path: Path) -> None:
    """Plot the naive-average share for the top ``top_n`` ships."""
    ship_order = average_shares.mean(axis=0).nlargest(top_n).index
    if len(ship_order) == 0:
        raise ValueError("No ships available to plot for naive-average chart.")
    top_shares = average_shares.loc[:, ship_order]

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    for ship in ship_order:
        ax.plot(top_shares.index, top_shares[ship], label=ship)

    ax.set_title(f"Naive average share of top {top_n} ships")
    ax.set_ylabel("Naive average share (%)")
    ax.set_xlabel("Work creation month")
    if not top_shares.empty:
        ax.set_ylim(0, min(100, top_shares.max().max() * 1.1))
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(title="Ship")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_monthly_series(
    series: pd.Series, output_path: Path, title: str, ylabel: str
) -> None:
    """Plot a single monthly time series."""
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.plot(series.index, series.values)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Work creation month")
    if not series.empty:
        upper = series.max()
        if upper > 0:
            ax.set_ylim(0, upper * 1.1)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def extract_viktor_jayce_share(
    shares: pd.DataFrame, weight_columns: Iterable[str],
) -> pd.DataFrame:
    """Return Viktor/Jayce shares for the provided weight columns."""
    def _get_ship(ship: str) -> pd.DataFrame:
        try:
            return shares.xs(ship, level=1, axis=1, drop_level=False)
        except KeyError:
            return pd.DataFrame()

    viktor_share = _get_ship(VICTOR_JAYCE_SHIPS[0])
    if viktor_share.empty and len(VICTOR_JAYCE_SHIPS) > 1:
        for alt in VICTOR_JAYCE_SHIPS[1:]:
            viktor_share = _get_ship(alt)
            if not viktor_share.empty:
                break
    if viktor_share.empty:
        raise ValueError("Could not find Viktor/Jayce shares in computed data.")

    viktor_share = viktor_share.droplevel(1, axis=1)
    return viktor_share.reindex(columns=list(weight_columns), fill_value=0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/created_dates.csv"),
        help="Path to the created_dates.csv dataset",
    )
    parser.add_argument(
        "--viktor-output",
        type=Path,
        default=Path("figures/viktor_jayce_share.png"),
        help="Where to save the Viktor/Jayce weighting comparison figure",
    )
    parser.add_argument(
        "--top-output",
        type=Path,
        default=Path("figures/top_ships_naive_average.png"),
        help="Where to save the naive-average top ship figure",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="How many ships to include in the naive-average plot",
    )
    parser.add_argument(
        "--total-hits-output",
        type=Path,
        default=Path("figures/total_hits.png"),
        help="Where to save the total hits time series",
    )
    args = parser.parse_args()

    weight_columns = ["works", "kudos", "hits", "bookmarks", "comments", "words"]

    df = load_created_dates(args.data)
    totals = monthly_totals(df, weight_columns)
    ship_totals = ship_monthly_totals(df, weight_columns)
    ship_shares = compute_ship_shares(ship_totals, totals, weight_columns)

    viktor_share = extract_viktor_jayce_share(ship_shares, weight_columns)
    plot_shares(
        viktor_share,
        args.viktor_output,
        "Share of Viktor/Jayce works by weighting metric",
    )

    average_shares = ship_shares.T.groupby(level=1).mean().T.fillna(0.0)
    plot_top_ships(average_shares, args.top_n, args.top_output)

    plot_monthly_series(
        totals["hits"],
        args.total_hits_output,
        "Total hits across all works over time",
        "Monthly hits",
    )


if __name__ == "__main__":
    main()
