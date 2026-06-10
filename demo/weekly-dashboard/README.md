# Weekly dashboard — working demonstration

A one-page weekly dashboard for Benjamin's at The Landsby, built from ordinary
CSV exports. **All data in `sample-data/` is synthetic** — generated for
demonstration and watermarked as such on the output page. No real trading
figures appear anywhere.

The synthetic period represents roughly weeks 1–8 *after* the plan's month-1
baseline, so leading indicators deliberately show early trajectory rather than
the baseline itself — for example, review counts have grown from the ~15
baseline towards the 12-month target of 100+.

## Run it

    python3 build_dashboard.py

Writes `dashboard.html`. Open it in any browser; Ctrl+P prints the one page.

## Test it

    python3 -m unittest test_dashboard -v

The tests independently recompute the headline totals from the raw CSVs via a
separate code path and assert the dashboard's figures match — including that
covers are counted once per check (keyed by date + `check_id`, robust to check
numbers resetting daily), never once per line item.

## Files

| File | What it is |
|---|---|
| `build_dashboard.py` | The only script. Python standard library only. |
| `config.json` | Site name and target bands. The bands shipped here are sector-norm placeholders — the plan agrees real bands with management in month 1; edit this file when they are. Adapting the tool to another site means editing this file. |
| `sample-data/cubigo-sales.csv` | 8 weeks of line-item sales. One row per item; `covers` is a check-level value repeated per row. |
| `sample-data/opentable-bookings.csv` | Bookings with seated/no-show status. |
| `sample-data/square-settlements.csv` | Daily card settlement totals. |
| `sample-data/flash-survey.csv` | QR flash-survey responses (food/service/value, 1–5). |
| `sample-data/manual-kpis.json` | Hand-entered weekly figures: labour cost/hours, review counts, Google Business Profile views/clicks, enquiries. |
| `make_sample_data.py` | Deterministic generator (fixed seed) that produced `sample-data/`. Re-run it to regenerate identical files. |

## Deliberate imperfections

The sample data contains three malformed rows and one missing trading day
(Tuesday 2 June). The dashboard skips unreadable rows, counts them, and
discloses both in the page footer — data quality is reported, never hidden.

## In production

Replace the files in `sample-data/` with real exports from Cubigo, OpenTable,
Square and the survey tool, update `manual-kpis.json` weekly, and run the same
command. Nothing else changes.
