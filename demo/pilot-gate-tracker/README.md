# Pilot Gate Tracker

A RAG (red / amber / green) panel that evaluates a trading week against
pre-agreed **gates**. This is the mechanism for the plan's Sunday-lunch pilot:
the gates, their green/amber thresholds, and each metric's direction of merit
are fixed in `config.json` *before* a pilot week runs, so when the pilot is live
each week's figures plug straight in and the panel turns green, amber or red
against the same yardsticks. The output is a single printable HTML page showing
the **latest trading week** as a worked example.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## What it measures

The latest week is the maximum week-ending Sunday key in `manual-kpis.json`.
Cubigo dates are bucketed into weeks with `week_ending` (weeks end on Sunday).
For that week:

- **Covers** (guests) — one guest count per unique `(date, check_id)`, summed.
- **Spend per head** — week net revenue ÷ covers.
- **Labour as % of net** — week labour cost (from `manual-kpis.json`) ÷ net.
- **Guest satisfaction** — mean of `(food + service + value) / 3` over the
  week's `flash-survey.csv` rows (scores 1–5).
- **Repeat bookings** — **not yet tracked**: there is no source for this in the
  data, so it is shown greyed-out, never estimated. This mirrors the dashboard's
  zero-vs-None policy: an indicator with no source is shown as not-yet-tracked.

### RAG rules

Thresholds come from `config["gates"]`. Direction of merit is explicit per
metric in the code:

- **Higher is better** (covers, spend per head, satisfaction): green if value
  ≥ green threshold; amber if ≥ amber (but below green); else red.
- **Lower is better** (labour %): green if value ≤ green threshold; amber if
  ≤ amber; else red.

## A cover is a guest

A cover is a **guest**, not a check. The guest count for each unique
`(date, check_id)` is `int(float(covers))` from the first numeric-covers row of
that check, and those are summed. A check whose covers value is non-numeric is
malformed: the validator raises and the row is skipped and counted in the
page's data-quality footer rather than crashing the report.

## Run it

```bash
python3 build_pilot_gate_tracker.py
```

Writes `pilot-gate-tracker.html` in this folder.

## Test it

```bash
python3 -m unittest test_pilot_gate_tracker
```

The tests independently recompute the latest week's covers, spend per head,
labour %, and satisfaction from the raw files; assert each gate's RAG status
follows the threshold-and-direction rule (including that labour % is
lower-is-better); confirm repeat bookings is untracked with no numeric value;
and guard against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/pilot-gate-tracker/`) — all paths are relative to it.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`cubigo-sales.csv`, `flash-survey.csv`, `manual-kpis.json`, same columns
   and JSON shape). `manual-kpis.json` is keyed by week-ending Sunday (ISO);
   each week carries at least `labour_cost`.
2. Edit `config.json` — set `site_name` and the `gates` (the green/amber
   thresholds you've agreed for the pilot).
3. Run `python3 build_pilot_gate_tracker.py`. The latest week in
   `manual-kpis.json` is evaluated.

**Never change the deterministic numeric path** (the covers / spend-per-head /
labour-% / satisfaction and RAG logic in `build_pilot_gate_tracker.py` and the
vendored `benjamins_common.py`). The same input must always produce the same
output; the tests depend on it.
