# Daily Briefing

Builds a one-page **pre-service huddle sheet** for the team to read together
before doors open. It pulls a single service day's bookings, specials (with
their allergen flags), and staff training into one printable HTML page. No
revenue or money — this is an operational sheet, not a financial one.

Inputs:

- `opentable-bookings.csv` — `date,time,party_size,status,source`
- `specials.csv` — `date,dish,description_seed,allergens` (`;`-separated; specials carry their own allergens)
- `training-rota.csv` — `date,staff,topic`

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_daily_briefing.py
```

Writes `daily-briefing.html` in this folder.

## Test it

```bash
python3 -m unittest test_daily_briefing
```

The tests independently recount the day's seated bookings and covers from the
CSV, confirm the bookings list is time-ordered, check a known special shows its
declared allergens, and guard against the committed HTML drifting from the
renderer.

Run the tests and the build script from **inside this directory**
(`demo/daily-briefing/`) — all paths are relative to it.

## What the sheet shows

- **Bookings** — the seated booking count and total covers booked, plus the
  full time-ordered booking list (time, party, status, source).
- **Today's specials** — each special with its allergen flags shown clearly.
  Allergens come from the specials export's own `allergens` field.
- **Training today** — the staff and topics scheduled, or "None scheduled".

The briefing date is set in `config.json`. Rows with a missing time, an
unreadable seated party size, a missing dish, or a missing staff name are
skipped and counted in the page's data-quality footer rather than crashing.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`opentable-bookings.csv`, `specials.csv`, `training-rota.csv`,
   same columns).
2. Edit `config.json` — set `site_name` and `briefing_date` (the service day
   to brief on).
3. Run `python3 build_daily_briefing.py`.

**Never change the deterministic numeric path** (the filtering, counting, and
ordering logic in `build_daily_briefing.py` and the vendored
`benjamins_common.py`). The same input must always produce the same output;
the tests depend on it.
