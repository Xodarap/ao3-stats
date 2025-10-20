# ao3-stats

A small scraper that aggregates AO3 relationship (ship) statistics by total kudos.

## Usage

Run the scraper for your chosen tags. To keep load on AO3 reasonable, the default
configuration only fetches a single page (20 works) per tag.

```
python -m ao3_stats "Harry Potter - J. K. Rowling" --pages 2 --top 5
```

Use `--pages` to inspect more works per tag and `--delay` to adjust the pause between
requests.
