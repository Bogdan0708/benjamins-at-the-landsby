# Demand Forecast

Reads a Cubigo sales export (covers history) and an OpenTable bookings export,
and produces a one-page forecast of **next week's covers, by day and daypart**
(Lunch / Afternoon / Evening), as a grouped bar chart plus a full table.

## Not a model — a transparent weighted moving average

This is **deliberately not machine learning**. Each cell is the weighted mean
of the **three most recent past occurrences** of that weekday and daypart,
most-recent first, using the weights in `config.json` (default `0.5, 0.3, 0.2`).
If fewer than three occurrences exist, it uses as many as are available and
renormalises the weights so they still sum to 1.

A manager can reproduce every number by hand from the three source dates shown
in the table's "Basis" column. The only two knobs are:

- **`weights`** — how much each of the three recent weeks counts.
- **`event_adjustments`** — a list of `{date, multiplier}`. If a forecast date
  matches, that whole day's covers are multiplied (e.g. a private function or a
  bank-holiday lift) and the day is flagged on the page.

"On the books" shows the current OpenTable party-size total for each service as
a cross-check; it is **not** part of the average.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_demand_forecast.py
```

Writes `demand-forecast.html` in this folder.

## Test it

```bash
python3 -m unittest test_demand_forecast
```

The tests confirm the weights renormalise to 1, independently recompute one
full (weekday, daypart) cell straight from the CSV, check the forecast week is
the seven days immediately after the last history date, exercise a partial-cell
renormalisation and an event override, and guard against the committed HTML
drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/demand-forecast/`) — all paths are relative to it.

## What a cover is

A cover is one unique `(date, check_id)` pair. Each check's daypart comes from
its time via `benjamins_common.daypart`. Rows with a malformed time are skipped
and counted in the data-quality footer; rows with an unparseable date are
excluded from history and noted in the footer.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`cubigo-sales.csv` and `opentable-bookings.csv`, same columns).
2. Edit `config.json` — set `site_name`, `currency`, `weights`, and any
   `event_adjustments` for known one-offs in the coming week.
3. Run `python3 build_demand_forecast.py`.

**Never change the deterministic numeric path** (the covers/averaging logic in
`build_demand_forecast.py` and the vendored `benjamins_common.py`). The same
input must always produce the same output; the tests depend on it.
