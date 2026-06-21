"""build_allergen_matrix.py — Allergen compliance matrix for Benjamin's at The Landsby.

Reads apicbase-costings.csv and writes allergen-matrix.html: a printable
dish x 14-allergen grid for FOH and kitchen compliance lookup.

Run from inside demo/allergen-matrix/:
    python3 build_allergen_matrix.py

Python standard library only.
"""
import html
import json
import sys
from pathlib import Path

import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())

# The 14 UK statutory allergens (Natasha's Law / FSA list).
# Exact spelling/casing matches make_world.py ALLERGENS_14.
ALLERGENS_14 = [
    "celery", "gluten (cereals)", "crustaceans", "eggs", "fish", "lupin",
    "milk", "molluscs", "mustard", "tree nuts", "peanuts", "sesame",
    "soya", "sulphur dioxide",
]

_ALLERGEN_SET = frozenset(ALLERGENS_14)

EXPECTED_COLUMNS = ["item", "category", "unit_cost", "allergens"]


def _validate(fn, row):
    """Raise BenjaminsError for structurally bad rows (non-allergen checks only).

    Unknown allergen tokens are a data-quality error that should abort the whole
    run (not silently skip a row), so allergen validation is done in compute().
    """
    # Currently no additional row-level structural checks beyond column presence.
    # This hook is kept so bc.read_csv_rows can still skip rows with wrong field
    # counts (None key / None value checks are built into read_csv_rows).
    pass


def compute(apicbase_path):
    """Parse apicbase-costings.csv and build the allergen matrix.

    Returns:
        dishes    list[str]           — sorted dish names
        allergens list[str]           — ALLERGENS_14 (fixed order, always 14)
        matrix    dict[dish, dict[allergen, bool]]
        counts    dict[allergen, int] — how many dishes contain each allergen
        skipped   list[str]           — data-quality notes
    """
    rows, skipped = bc.read_csv_rows(apicbase_path, EXPECTED_COLUMNS, _validate)

    matrix = {}
    for row in rows:
        item = row["item"].strip()
        raw = row.get("allergens", "") or ""
        # Normalise each token: strip whitespace and lower-case before matching.
        # This tolerates real Apicbase exports that use "Milk" or "GLUTEN (CEREALS)".
        # The canonical ALLERGENS_14 strings are already lowercase, so normalised
        # tokens match them directly.  We record the CANONICAL string in the matrix,
        # not the raw token, so spelling/casing in the output is always consistent.
        raw_tokens = [t.strip() for t in raw.split(";") if t.strip()]
        canonical_tokens = set()
        for raw_token in raw_tokens:
            normalised = raw_token.lower()
            if normalised not in _ALLERGEN_SET:
                # Data-quality guard: unknown allergen tokens abort the run.
                raise bc.BenjaminsError(
                    f"unknown allergen '{raw_token}' for dish '{item}'"
                )
            canonical_tokens.add(normalised)
        matrix[item] = {a: (a in canonical_tokens) for a in ALLERGENS_14}

    dishes = sorted(matrix.keys())
    counts = {a: sum(1 for d in dishes if matrix[d][a]) for a in ALLERGENS_14}

    return dishes, ALLERGENS_14, matrix, counts, skipped


def render(result):
    """Build the compliance matrix HTML page. No business logic here."""
    dishes, allergens, matrix, counts, skipped = result

    # --- table header ---
    th_cells = "".join(
        f'<th class="allergen-col">{html.escape(a)}</th>' for a in allergens
    )
    header_row = f'<tr><th class="dish-col">Dish</th>{th_cells}</tr>'

    # --- table body rows ---
    body_rows = []
    for dish in dishes:
        tds = "".join(
            f'<td class="tick">{"&#10003;" if matrix[dish][a] else ""}</td>'
            for a in allergens
        )
        body_rows.append(
            f'<tr><td class="dish-name">{html.escape(dish)}</td>{tds}</tr>'
        )

    # --- per-allergen count footer row ---
    count_cells = "".join(
        f'<td class="count">{counts[a]}</td>' for a in allergens
    )
    count_row = f'<tr class="count-row"><td class="dish-col"><em>Dishes affected</em></td>{count_cells}</tr>'

    body_html = f"""
<h2>Allergen Compliance Matrix</h2>
<p class="caption">Generated from Apicbase costings. Compliance lookup for front-of-house and kitchen staff.
All 14 UK statutory allergens are shown; a tick (&#10003;) indicates the dish contains that allergen.
Verify against the current Apicbase recipe record before advising a guest.</p>
<div class="matrix-wrap">
<table class="allergen-table">
<caption>Benjamin's Allergen Matrix &mdash; {len(dishes)} dishes &times; 14 allergens</caption>
<thead>{header_row}</thead>
<tbody>{"".join(body_rows)}</tbody>
<tfoot>{count_row}</tfoot>
</table>
</div>
<style>
  .matrix-wrap {{ overflow-x: auto; }}
  .allergen-table {{ border-collapse: collapse; font-size: 11px; width: 100%; }}
  .allergen-table th, .allergen-table td {{ border: 1px solid #ccc; padding: 4px 6px; }}
  .allergen-table thead th {{ background: #1f3a2d; color: #fff; text-align: center; vertical-align: bottom; }}
  .dish-col {{ text-align: left; min-width: 160px; font-weight: bold; }}
  .allergen-col {{ writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap;
                   height: 110px; min-width: 28px; text-align: left; }}
  .dish-name {{ white-space: nowrap; }}
  .tick {{ text-align: center; font-size: 14px; color: #b30000; font-weight: bold; }}
  .count-row td {{ background: #f0f4f2; font-weight: bold; text-align: center; }}
  .count-row .dish-col {{ text-align: left; }}
  .caption {{ font-size: 12px; color: #444; margin-bottom: 10px; }}
  @media print {{
    .allergen-table {{ font-size: 9px; }}
    .allergen-col {{ height: 80px; }}
  }}
</style>
"""

    return bc.page(
        "Allergen Matrix",
        CONFIG["site_name"],
        body_html,
        skipped,
        f"{len(dishes)} dishes x 14 allergens",
    )


def main():
    try:
        result = compute("sample-data/apicbase-costings.csv")
        html_out = render(result)
    except bc.BenjaminsError as e:
        print(f"Could not build the allergen matrix: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("allergen-matrix.html").write_text(html_out, encoding="utf-8")
    dishes, allergens, matrix, counts, skipped = result
    print(f"Wrote allergen-matrix.html ({len(dishes)} dishes, 14 allergens)")
    if skipped:
        print(f"  Skipped {len(skipped)} rows (see HTML footer for details)")


if __name__ == "__main__":
    main()
