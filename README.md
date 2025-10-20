# ao3-stats

A small scraper that sums the kudos for specific AO3 relationship (ship) tags.

## Usage

Run the scraper for your chosen relationship tags. To keep load on AO3 reasonable,
the default configuration only fetches a single page (20 works) per tag.

```
python -m ao3_stats "Aldebaran | Al*s*Priscilla Barielle" --pages 2
```

Use `--pages` to inspect more works per tag, `--delay` to adjust the pause between
requests, and `--json` for machine-readable output.
