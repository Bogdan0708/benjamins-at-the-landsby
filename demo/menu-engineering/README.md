# Menu Engineering

Reads a Cubigo product-mix export and an Apicbase costings export and produces
a one-page **popularity x margin** matrix — the classic four-quadrant menu
engineering grid — as an inline SVG scatter plus a per-item table. The output
is a single printable HTML page, a decision aid for the manager and head chef.

Each item is placed by **units sold** (popularity, x-axis) against **gross
margin per unit** (y-axis). The crosshair is the menu median on each axis,
splitting items into four quadrants:

- **Stars** — sell well *and* high margin (protect and feature)
- **Plowhorses** — sell well but thin margin (re-cost or re-price carefully)
- **Puzzles** — high margin but overlooked (reposition / promote)
- **Dogs** — neither popular nor profitable (review)

It is a conversation starter, never an instruction to drop a resident
favourite — resident protection always comes first.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_menu_engineering.py
```

Writes `menu-engineering.html` in this folder.

## Test it

```bash
python3 -m unittest test_menu_engineering
```

The tests independently recompute one item's units / revenue / unit price /
unit cost / margin straight from the raw CSVs, confirm every sold item is
classified into exactly one quadrant by the two medians, check that a Cubigo
item with no Apicbase costing raises a plain-English error (referential
integrity), and guard against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/menu-engineering/`) — all paths are relative to it.

## How an item is measured

- **units** = number of Cubigo line-item rows for that item (one row = one sale)
- **revenue** = sum of `net` over those rows
- **unit_price** = revenue / units
- **unit_cost** = the item's food cost from Apicbase (joined by item name)
- **margin** = unit_price − unit_cost; **margin %** = margin / unit_price

Rows with an unreadable `net` are skipped and counted in the page's
data-quality footer rather than crashing the report. If a sold item has **no**
Apicbase costing, the tool stops with a plain-English message — product mix and
costings must stay in sync.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`cubigo-sales.csv` and `apicbase-costings.csv`, same columns).
2. Edit `config.json` — set `site_name` and `currency`.
3. Run `python3 build_menu_engineering.py`.

**Never change the deterministic numeric path** (the units / revenue / margin /
median / quadrant logic in `build_menu_engineering.py` and the vendored
`benjamins_common.py`). The same input must always produce the same output;
the tests depend on it.
