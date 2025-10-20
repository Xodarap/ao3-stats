# ao3-stats

A small scraper that sums the kudos for specific AO3 relationship (ship) tags.

## Usage

Run the scraper for your chosen relationship tags. To keep load on AO3 reasonable,
the default configuration only fetches a single page (20 works) per tag.

```
python -m ao3_stats "Aldebaran | Al*s*Priscilla Barielle" --pages 2
```

Use `--pages` to inspect more works per tag, `--delay` to adjust the pause between
requests, and `--json` for machine-readable output. You can also restrict results to
works posted within a specific time range with `--start-date` and `--end-date`.

### Batch scraping from CSV

To recreate the 2025 ship stats with kudos totals, first populate `data/ships_2025.csv`
with the relationships you want to analyse (a header row named `relationship` followed
by one ship per line). Then run the batch scraper, which resumes automatically if it is
interrupted:

```
uv run python -m ao3_stats.csv_kudos data/ships_2025.csv data/ship_kudos_2025.csv --delay 1
```

If you prefer the shorter command you originally tried, the repository now ships with
an alias so the following works too:

```
uv run python -m compileall data/ships_2025.csv data/ship_kudos_2025.csv --delay 1
```

The command writes results incrementally to `data/ship_kudos_2025.csv`, storing the
total kudos and works for each relationship tag. Because the alias simply delegates to
`ao3_stats.csv_kudos`, you receive the exact same CSV output (including words, chapters,
bookmarks, hits, etc.) that the longer command produces.
