"""Utilities for aggregating AO3 stats."""

__all__ = [
    "scrape_tag_kudos",
    "scrape_multiple_tags",
]

from .scraper import scrape_multiple_tags, scrape_tag_kudos
