"""Compatibility shim allowing ``python -m compileall`` to run the CSV kudos scraper."""
from __future__ import annotations

from typing import Sequence

from ao3_stats.csv_kudos import main as csv_main


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate to :mod:`ao3_stats.csv_kudos` for backwards-compatible CLI usage."""
    return csv_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
