# Menu Copy Drafts (Tier 2: AI-assisted)

Reads the Apicbase costings (the **standing menu**) and the specials log, and
produces a one-page **approval queue**: for every dish — standing or special —
it shows an appetising piece of menu/listing copy **draft** that a person edits,
approves and publishes. Nothing is published automatically.

This tool follows the **Tier 2 (AI-assisted)** pattern set by the reference tool
`demo/feedback-theming`.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## The Tier 2 pattern — what the AI may and may not do

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

- **The numbers are deterministic.** Each standing dish's `unit_cost` is read
  straight from the Apicbase export by code in `build_menu_copy_drafts.py` and
  shown clearly as the **food cost — not a menu price**. The dish set (standing
  items + distinct specials) is read deterministically and sorted by name.
- **draft_fn drafts prose only.** It writes the menu copy for each dish. It is a
  pluggable function: a **deterministic template** here (`default_draft`), a
  **real model** in production — behind the *same interface*. Its signature
  (shared with the reference tool) is:

  ```python
  draft_fn(context: dict) -> str
  # context = {"name": str, "category": str, "allergens": list[str],
  #            "seed": str | None}                                   # NO numbers
  ```

  The context contains **no unit_cost, no price and no counts**, so a draft_fn —
  template or model — physically cannot move a cost or a price. A test passes two
  different draft_fns and proves the standing dishes' `unit_cost` values and the
  whole dish set are identical; a spy test proves the context handed to draft_fn
  carries no numbers.
- **Nothing is auto-published.** `render()` is a review queue: every piece of
  copy is badged *"DRAFT — pending approval"* beside the code-computed food cost.
  A person edits, approves and publishes each one.

## Run it

```bash
python3 build_menu_copy_drafts.py
```

Writes `menu-copy-drafts.html` in this folder.

## Test it

```bash
python3 -m unittest test_menu_copy_drafts
```

The tests confirm every standing dish and every distinct special gets a
non-empty draft, prove that swapping `draft_fn` cannot change any `unit_cost` or
the dish set, prove `draft_fn` receives no numbers, confirm the dish set matches
an independent read of the two CSVs in deterministic (sorted) order, and guard
against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/menu-copy-drafts/`) — all paths are relative to it.

## Production adoption

1. Replace `sample-data/apicbase-costings.csv` with your real Apicbase export
   (columns `item,category,unit_cost,allergens`) and `sample-data/specials.csv`
   with your real specials log (columns `date,dish,description_seed,allergens`).
2. Optionally tune the house voice by editing `default_draft` in
   `build_menu_copy_drafts.py`.
3. Optionally swap `draft_fn` for a real model behind the same
   `draft_fn(context) -> str` interface (context = name + category + allergens +
   optional seed, no numbers).
4. Run `python3 build_menu_copy_drafts.py` and work the queue: edit, approve and
   publish each piece of copy yourself.

**Never change the deterministic numeric path** (the `unit_cost` validation and
read, the dish-set construction and the sort order in
`build_menu_copy_drafts.py` and the vendored `benjamins_common.py`). The AI may
draft the words of menu copy; it must never touch a cost or a price. The same
input must always produce the same dish set and the same food-cost figures; the
tests depend on it.
