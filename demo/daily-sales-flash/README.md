# Daily Sales Flash

Reads a Cubigo sales export and produces a one-page flash report comparing
**yesterday vs the same weekday one week earlier**, with the day's top and
slowest-moving items by net revenue. The output is a single printable HTML page.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_daily_sales_flash.py
```

Writes `daily-sales-flash.html` in this folder.

## Test it

```bash
python3 -m unittest test_daily_sales_flash
```

The tests independently recount covers from the CSV, confirm the comparison
day is the same weekday one week earlier, check that top/slow sellers are
present, and guard against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/daily-sales-flash/`) — all paths are relative to it.

## What a cover is

A cover is one unique `(date, check_id)` pair. Rows missing a `check_id`, or
with an unreadable `net`, are skipped and counted in the page's data-quality
footer rather than crashing the report.

## Production adoption

1. Replace the files in `sample-data/` with your real Cubigo export
   (`cubigo-sales.csv`, same columns).
2. Edit `config.json` — set `site_name`, `currency`, and `report_date`
   (the day to report on; its same-weekday-prior week must also have data).
3. Run `python3 build_daily_sales_flash.py`.

**Never change the deterministic numeric path** (the covers/net/ranking logic
in `build_daily_sales_flash.py` and the vendored `benjamins_common.py`). The
same input must always produce the same output; the tests depend on it.
