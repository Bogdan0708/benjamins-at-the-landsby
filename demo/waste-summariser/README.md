# Waste Summariser

Reads a kitchen **waste log** and the **Apicbase costings** export, joins them,
and produces a one-page weekly **cost-of-waste** report: a bar chart of waste
cost by week, a top-wasted-items table (item, quantity, cost), a by-reason
breakdown, and the total cost of waste shown prominently. The output is a single
printable HTML page. Waste you can see is waste you can cut.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_waste_summariser.py
```

Writes `waste-summariser.html` in this folder.

## Test it

```bash
python3 -m unittest test_waste_summariser
```

The tests independently recompute the total cost of waste from the raw join
(read both CSVs, join on item, sum `qty * unit_cost`), confirm the per-week
costs and the per-item costs each sum to that total, check the top-items
ordering is cost-descending and tie-stable, assert a wasted item absent from
Apicbase raises an error (referential integrity), confirm a non-numeric `qty`
row is skipped and counted, and guard against the committed HTML drifting from
the renderer.

Run the tests and the build script from inside the tool directory
(`demo/waste-summariser/`) — all paths are relative to it.

## How a waste row is costed

Each `waste-log.csv` row is `date,item,qty,reason`. Its cost is
`qty * unit_cost`, where `unit_cost` comes from `apicbase-costings.csv` keyed by
item. Costs are aggregated by **week ending** (the Sunday on or after the waste
date) and by item.

- A row with a non-numeric or non-positive `qty` is **skipped and counted** in
  the page's data-quality footer rather than crashing the report.
- A wasted item with **no Apicbase costing** is a data-quality failure: the
  report **aborts** (referential integrity), because miscosting waste is worse
  than reporting nothing. Fix the costings export, then re-run.

## Production adoption

1. Replace the files in `sample-data/` with your real exports:
   `waste-log.csv` (`date,item,qty,reason`) and `apicbase-costings.csv`
   (`item,category,unit_cost,allergens`), same columns.
2. Edit `config.json` — set `site_name` and `currency`.
3. Run `python3 build_waste_summariser.py`.

Every distinct item in the waste log must have a matching Apicbase costing
(item names must agree exactly), or the report will abort.

**Never change the deterministic numeric path** (the costing/aggregation/ranking
logic in `build_waste_summariser.py` and the vendored `benjamins_common.py`).
The same input must always produce the same output; the tests depend on it.
