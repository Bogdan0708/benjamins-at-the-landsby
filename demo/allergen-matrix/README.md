# Allergen Matrix

Reads an Apicbase costings export and produces a printable **dish × 14-allergen compliance grid** for front-of-house and kitchen use. Staff can answer "does X contain Y?" instantly from the single-page output.

All 14 UK statutory allergens (Natasha's Law / FSA list) are always rendered as columns — even if none of the current dishes contains a given allergen — so the layout is consistent and no column can go missing.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## Run it

```bash
python3 build_allergen_matrix.py
```

Run from inside this directory (`demo/allergen-matrix/`). Writes `allergen-matrix.html`.

## Test it

```bash
python3 -m unittest test_allergen_matrix
```

Run from inside this directory. Tests cover:

- Matrix ticks match the raw CSV allergen field for every dish (independent parse).
- All 14 allergen columns always present in both `compute()` output and rendered HTML.
- Per-allergen counts are correct.
- Dishes sorted (stable/deterministic output).
- Unknown allergen tokens abort with a plain-English error (data-quality guard).
- Committed `allergen-matrix.html` matches a fresh render (drift guard).

## The 14 allergens

celery, gluten (cereals), crustaceans, eggs, fish, lupin, milk, molluscs, mustard, tree nuts, peanuts, sesame, soya, sulphur dioxide.

## Production adoption

1. Replace `sample-data/apicbase-costings.csv` with a real Apicbase export (columns: `item`, `category`, `unit_cost`, `allergens`; `allergens` is a `;`-separated list of the 14 statutory allergen names). Allergen names are matched case-insensitively (canonical names are lower-case), so "Milk" and "GLUTEN (CEREALS)" are accepted — but a genuinely unrecognised token still aborts the run.
2. Edit `config.json` — set `site_name` if needed.
3. Run `python3 build_allergen_matrix.py`.
4. Print or share `allergen-matrix.html` with your team.

**Never change the deterministic numeric path** (the matrix-building logic in `build_allergen_matrix.py` and the vendored `benjamins_common.py`). The same input must always produce the same output; the drift guard test depends on it.
