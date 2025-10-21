"""Generate a vertical video showing how the top AO3 ships change over time."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import animation
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "data" / "created_dates.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "analysis" / "top_ships_tiktok.mp4"


@dataclass
class AnimationConfig:
    """Container describing the animation output parameters."""

    top_n: int = 15
    top_k: int = 10
    fps: int = 12
    bitrate_kbps: int = 6_000
    steps_per_month: int = 1
    output_path: Path = DEFAULT_OUTPUT_PATH


def load_monthly_counts(data_path: Path, top_n: int = 12) -> pd.DataFrame:
    """Return a cumulative monthly count table for the most popular ships."""
    raw = pd.read_csv(data_path)

    # Filter out rows missing ship information or creation dates
    raw = raw.dropna(subset=["ships", "created"]).copy()
    raw["created"] = pd.to_datetime(raw["created"], errors="coerce")
    raw = raw.dropna(subset=["created"])

    # Split the semicolon separated ship list and explode into individual rows
    raw["ships"] = raw["ships"].str.split(";")
    exploded = raw.explode("ships")
    exploded["ships"] = exploded["ships"].str.strip()
    exploded = exploded[exploded["ships"].str.len() > 0]

    exploded["month"] = exploded["created"].dt.to_period("M").dt.to_timestamp()

    monthly_counts = (
        exploded.groupby(["month", "ships"], as_index=False)
        .size()
        .rename(columns={"size": "monthly_works"})
    )

    totals = (
        monthly_counts.groupby("ships")["monthly_works"].sum().nlargest(top_n).index
    )
    filtered = monthly_counts[monthly_counts["ships"].isin(totals)]

    first_month = filtered["month"].min().to_period("M").to_timestamp()
    last_month = filtered["month"].max().to_period("M").to_timestamp()
    all_months = pd.date_range(first_month, last_month, freq="MS")

    table = (
        filtered.pivot_table(
            index="month", columns="ships", values="monthly_works", aggfunc="sum"
        )
        .reindex(all_months, fill_value=0)
        .sort_index()
    ).fillna(0)

    cumulative = table.cumsum()
    cumulative.index.name = "month"
    return cumulative


def assign_colors(labels: Iterable[str]) -> Dict[str, str]:
    """Return a deterministic mapping from labels to colors."""

    labels = list(labels)
    if not labels:
        return {}

    cmap = plt.colormaps["tab20"].resampled(len(labels))
    return {label: cmap(i) for i, label in enumerate(labels)}


def interpolate_counts(counts: pd.DataFrame, steps_per_month: int) -> pd.DataFrame:
    """Return interpolated values for smoother animation transitions."""

    if steps_per_month <= 1 or len(counts) < 2:
        return counts

    frames = []
    for idx in range(len(counts) - 1):
        start = counts.iloc[idx]
        end = counts.iloc[idx + 1]
        for step in range(steps_per_month):
            fraction = step / steps_per_month
            frames.append(start + (end - start) * fraction)
    frames.append(counts.iloc[-1])

    interpolated = pd.DataFrame(frames, columns=counts.columns)
    interpolated.index = pd.RangeIndex(len(interpolated))
    return interpolated


def millions_formatter(value: float, _: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{int(value)}"


def frame_labels(months: List[pd.Timestamp], steps_per_month: int) -> List[str]:
    if steps_per_month <= 1:
        return [month.strftime("%B %Y") for month in months]

    labels: List[str] = []
    for idx in range(len(months) - 1):
        start = months[idx].strftime("%B %Y")
        end = months[idx + 1].strftime("%B %Y")
        for step in range(steps_per_month):
            if step == 0:
                labels.append(start)
            else:
                labels.append(f"{start} → {end}")
    labels.append(months[-1].strftime("%B %Y"))
    return labels


def build_animation(counts: pd.DataFrame, config: AnimationConfig) -> None:
    raw_counts = counts.copy()
    months = raw_counts.index.to_list()
    smoothed_counts = interpolate_counts(raw_counts, config.steps_per_month)
    labels = frame_labels(months, config.steps_per_month)

    if len(smoothed_counts) != len(labels):
        raise ValueError("Label and frame count mismatch; check interpolation settings.")

    ships = raw_counts.columns.to_list()
    colors = assign_colors(ships)

    deltas = smoothed_counts.diff().fillna(smoothed_counts)

    width_inches = 9
    height_inches = 16
    dpi = 120
    plt.rcParams.update({
        "font.size": 14,
        "font.family": "DejaVu Sans",
        "text.color": "#111111",
        "axes.labelcolor": "#111111",
        "axes.edgecolor": "#111111",
        "xtick.color": "#111111",
        "ytick.color": "#111111",
    })
    fig, ax = plt.subplots(figsize=(width_inches, height_inches), dpi=dpi)
    fig.patch.set_facecolor("#f7f5f2")
    ax.set_facecolor("#f7f5f2")

    raw_max = raw_counts.values.max()
    max_value = max(1000, math.ceil(raw_max / 1000) * 1000 if raw_max > 0 else 1000)
    formatter = FuncFormatter(millions_formatter)

    lead_text = fig.text(
        0.5,
        0.92,
        "",
        ha="center",
        va="bottom",
        fontsize=16,
        fontweight="bold",
        color="#333333",
    )

    def update(frame_index: int) -> None:
        ax.clear()
        ax.set_facecolor("#f7f5f2")

        values = smoothed_counts.iloc[frame_index]
        top = values.nlargest(config.top_k)[::-1]
        y_pos = list(range(len(top)))

        bars = ax.barh(
            y=y_pos,
            width=top.values,
            color=[colors.get(label, "#4c72b0") for label in top.index],
            height=0.6,
        )

        delta = deltas.iloc[frame_index]
        for bar, ship in zip(bars, top.index):
            width = bar.get_width()
            change = int(round(delta[ship]))
            change_prefix = "↑" if change > 0 else "↓" if change < 0 else "→"
            ax.text(
                width + max_value * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{int(round(width)):,} works {change_prefix}{abs(change):,}",
                va="center",
                ha="left",
                fontsize=12,
                color="#222222",
            )

        ax.set_xlim(0, max_value)
        ax.xaxis.set_major_formatter(formatter)
        ax.set_xlabel("Total AO3 works")
        ax.set_title(
            "Top AO3 Ships Over Time",
            fontsize=22,
            fontweight="bold",
            loc="left",
            pad=20,
        )
        ax.text(
            0,
            1.03,
            labels[frame_index],
            transform=ax.transAxes,
            fontsize=19,
            fontweight="bold",
        )
        ax.text(
            0,
            1.0,
            "Cumulative AO3 works (fanfic count)",
            transform=ax.transAxes,
            fontsize=12,
            color="#555555",
        )
        ax.set_yticks(y_pos)
        ax.set_yticklabels(
            [f"#{len(top) - idx}. {label}" if len(label) <= 38 else f"#{len(top) - idx}. {label[:35]}…" for idx, label in enumerate(top.index)]
        )
        ax.grid(axis="x", linestyle="--", alpha=0.2)
        ax.invert_yaxis()
        for spine in ax.spines.values():
            spine.set_visible(False)

        if len(top) > 0:
            leader = top.index[-1]
            leader_count = int(round(top.iloc[-1]))
            lead_text.set_text(f"{leader} leads with {leader_count:,} works")
        else:
            lead_text.set_text("")

    if not animation.writers.is_available("ffmpeg"):
        raise RuntimeError(
            "FFmpeg writer unavailable. Install ffmpeg to export MP4 animations."
        )

    interval_ms = 1000 / config.fps
    anim = FuncAnimation(fig, update, frames=len(smoothed_counts), interval=interval_ms)
    writer = "ffmpeg"
    anim.save(
        config.output_path,
        writer=writer,
        dpi=dpi,
        fps=config.fps,
        bitrate=config.bitrate_kbps,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a vertical bar-chart race showing AO3 ship popularity.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to the created_dates.csv export (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination MP4 file (default: %(default)s)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=AnimationConfig.top_n,
        help="Number of ships to consider overall (default: %(default)s)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=AnimationConfig.top_k,
        help="Number of ships visible at once (default: %(default)s)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=AnimationConfig.fps,
        help="Frames per second for the final video (default: %(default)s)",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        default=AnimationConfig.bitrate_kbps,
        help="FFmpeg bitrate in kbps (default: %(default)s)",
    )
    parser.add_argument(
        "--steps-per-month",
        type=int,
        default=AnimationConfig.steps_per_month,
        help="In-between frames to smooth transitions (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AnimationConfig(
        top_n=max(1, args.top_n),
        top_k=max(1, args.top_k),
        fps=max(1, args.fps),
        bitrate_kbps=max(1, args.bitrate),
        steps_per_month=max(1, args.steps_per_month),
        output_path=args.output.resolve(),
    )

    counts = load_monthly_counts(args.data.resolve(), top_n=config.top_n)
    counts = counts.sort_index()

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    build_animation(counts, config)
    print(f"Saved animation to {config.output_path}")


if __name__ == "__main__":
    main()
