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
python -m ao3_stats.csv_kudos data/ships_2025.csv data/ship_kudos_2025.csv --delay 1
```

The command writes results incrementally to `data/ship_kudos_2025.csv`, storing the
total kudos and works for each relationship tag.

## Visualising Viktor/Jayce share over time

To recreate the Viktor/Jayce share plot that weights the relationship by kudos, hits,
bookmarks, comments, words, and raw work counts—and to compare the top Arcane ships by
the naive average of those metrics—first ensure the `data/created_dates.csv` dataset from
the `data` branch is present locally. Then run:

```
python analysis/viktor_jayce_share.py
```

The script writes `figures/viktor_jayce_share.png` with the percentage of Viktor/Jayce
works per month under each weighting, `figures/top_ships_naive_average.png` with the
naive-average share for the top five ships (by average across the supplied metrics), and
`figures/total_hits.png` with the total number of hits across all Arcane works per month.
Use `--top-n` to change how many ships appear on the naive-average chart, and `--viktor-output`,
`--top-output`, or `--total-hits-output` to customise the output paths. Generated figures are not
tracked in the repository; regenerate them locally as needed.
