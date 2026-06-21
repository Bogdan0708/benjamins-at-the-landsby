# Cubigo–Square Reconciliation

Reconciles **card-settlement coverage**, not total takings. At a later-living
venue most residents bill to a monthly account rather than paying by card, so
the Square card settlement is *expected* to sit below the Cubigo total till
every day. A naive "till net must equal settled net" check would flag every
trading day. This tool instead checks that card settlement covers a sensible,
configurable *proportion* of the till — and that the two systems agree on which
days traded.

The output is a single printable HTML report plus a machine-readable
`mismatches.csv` listing only the exception days for follow-up.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_cubigo_square_recon.py
```

Writes `cubigo-square-recon.html` and `mismatches.csv` in this folder.
Run the build script and the tests from inside the tool directory
(`demo/cubigo-square-recon/`) — all paths are relative to it.

## Test it

```bash
python3 -m unittest test_cubigo_square_recon
```

The tests independently recompute one in-band day's till net, Square gross and
coverage ratio; confirm a date present in only one system surfaces as a
coverage-gap exception; check the Square fee-integrity check matches an
independent recompute on every Square row (no false pass/fail); assert every
ratio-band exception truly lies outside the band while a known in-band day is
not flagged; confirm `mismatches.csv` has exactly one row per exception day;
and guard against the committed HTML drifting from the renderer.

## The reconciliation model

For each date present in **either** system, the tool computes:

- **till_net** — sum of valid `net` values from the Cubigo export for that date.
  Rows with an unreadable `net` are skipped and counted in the data-quality
  footer rather than crashing the report.
- the **Square row** for that date — `gross`, `fees`, `net`.
- **ratio** = `square_gross / till_net` (card-settlement *gross* over till net).

A day is an **exception** if it trips any of three independent checks:

1. **Coverage ratio band** — `ratio` falls outside the configured
   `ratio_band` `[low, high]`. The default `0.80`–`0.95` reflects a venue
   where roughly 80–95% of till value settles to card and the rest goes to
   resident accounts.
2. **Coverage gap** — a date in Cubigo with no Square row
   ("no card settlement for trading day"), or a Square row whose date has no
   Cubigo trading rows ("settlement with no till trading").
3. **Square fee integrity** — `abs(gross − fees − net)` exceeds `fee_tolerance`
   (default `0.01`), i.e. the settlement row does not internally add up.

A day may trip more than one check; on the page and in the CSV the reasons are
joined with "; ". For a coverage gap the missing side's value and the ratio are
left empty (blank in the CSV, `—` on the page).

The summary line reports the days reconciled (those that have a ratio) and the
mean / min / max ratio across them, plus the exception count.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`cubigo-sales.csv` and `square-settlements.csv`, same columns).
2. Edit `config.json`:
   - `site_name`, `currency` — labelling.
   - `ratio_band` — `[low, high]` coverage band. **This is the key knob.**
     A site where almost everything is paid by card tightens toward
     `[0.98, 1.00]`; an account-billing venue like this one keeps a lower band
     (e.g. `[0.80, 0.95]`) so normal resident-account days don't flag.
   - `fee_tolerance` — the penny threshold for the Square fee-integrity check.
3. Run `python3 build_cubigo_square_recon.py`.

**Never change the deterministic numeric path** (the per-day till / ratio / gap /
fee logic in `build_cubigo_square_recon.py` and the vendored
`benjamins_common.py`). The same input must always produce the same output;
the tests depend on it.
