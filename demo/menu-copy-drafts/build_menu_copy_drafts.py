"""Benjamin's at The Landsby — menu copy drafts (Tier 2: AI-assisted).

Reads the Apicbase costings (the standing menu) and the specials log, and
produces a one-page COPY-REVIEW queue: for every dish — standing or special —
it shows an appetising menu/listing copy DRAFT awaiting a person's approval.
It follows the reference Tier 2 division of labour exactly (see
demo/feedback-theming):

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

  * EVERY NUMBER is computed by deterministic code below. The standing dishes'
    unit_cost is read straight from the Apicbase file and shown clearly as the
    FOOD COST (not a menu price). No number ever passes through draft_fn.
  * draft_fn is a pluggable function that DRAFTS PROSE ONLY — the menu copy for
    each dish. In this demo it is a deterministic template (default_draft); in
    production a real model can swap in behind the SAME interface. It receives
    only qualitative context (name, category, allergens, optional seed phrase)
    and CANNOT see or alter any cost or price.
  * Nothing is auto-published. render() produces a review queue: each draft is
    badged "DRAFT — pending approval". A person edits, approves and publishes.

draft_fn signature (shared with the reference tool):
    draft_fn(context: dict) -> str
where context = {"name": str, "category": str, "allergens": list[str],
                 "seed": str | None}  -- NO unit_cost, NO price, NO numbers.

Python standard library only. Same input always produces the same output.
"""
import html
import json
import sys
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())

APIC_EXPECTED = ["item", "category", "unit_cost", "allergens"]
SPECIALS_EXPECTED = ["date", "dish", "description_seed", "allergens"]


def _split_allergens(raw):
    """Deterministic allergen list from a 'a;b;c' cell (may be empty).

    Allergens are returned sorted alphabetically so the order is independent
    of CSV cell order.
    """
    return sorted(a.strip() for a in (raw or "").split(";") if a.strip())


def _validate_apic(fn, row):
    # A standing dish needs a name and a numeric unit_cost; either missing means
    # the row cannot be costed or labelled, so it is skipped and counted in the
    # data-quality footer. (No filename prefix: read_csv_rows prepends it.)
    if not (row["item"] or "").strip():
        raise bc.BenjaminsError("row missing item name")
    raw = (row["unit_cost"] or "").strip()
    try:
        float(raw)
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unit_cost is not a number: {row['unit_cost']!r}")


def _validate_special(fn, row):
    # A special needs a dish name to be copy-drafted; without one it is skipped
    # and counted.
    if not (row["dish"] or "").strip():
        raise bc.BenjaminsError("row missing special dish name")


def _join(items):
    """Deterministic 'a, b and c' join for a small list of strings."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# Map category labels to a grammatically natural singular noun for use inside
# "A {noun} from our kitchen."  Any category not listed falls through to a
# lower-cased version of its label, which works for "starter", "dessert" etc.
_CATEGORY_NOUN = {
    "drinks": "drink",
    "mains":  "main",
    "sides":  "side",
}


def _category_noun(category):
    """Return a grammatically natural singular noun for a category label."""
    key = (category or "").strip().lower()
    return _CATEGORY_NOUN.get(key, key)


def default_draft(context):
    """Deterministic, pure draft_fn used for the demo.

    Turns the dish's qualitative context into appetising menu/listing prose. A
    production model can replace this behind the same interface; it must never
    receive or return a cost or price.

    Note on description_seed: seed values should be qualitative words only
    (e.g. "rich classic redcurrant indulgent"), free of figures or quantities.
    A production draft_fn (a model) could otherwise weave a number into the
    copy — the deterministic-numbers guarantee covers computed fields, not text
    a model is handed.
    """
    name = context["name"]
    category = context["category"]
    allergens = context.get("allergens") or []
    seed = context.get("seed")

    if seed:
        # Specials carry a description seed: weave it into a flowing sentence.
        phrases = [p for p in seed.split() if p]
        flavour = f"{_join(phrases)}" if phrases else "a seasonal highlight"
        copy = f"{name} — {flavour}, prepared fresh for this period."
    elif category and category.lower() != "special":
        noun = _category_noun(category)
        copy = (f"{name} — a {noun} from the Benjamin's kitchen, "
                f"served with care.")
    else:
        copy = f"{name} — prepared in the Benjamin's kitchen, served with care."

    if allergens:
        copy += f" Contains: {_join(allergens)}."
    else:
        copy += " No declared allergens; please ask if you have any concern."
    return copy


def compute(apicbase_path, specials_path, draft_fn=default_draft):
    apic_rows, apic_skipped = bc.read_csv_rows(
        apicbase_path, APIC_EXPECTED, _validate_apic)
    spec_rows, spec_skipped = bc.read_csv_rows(
        specials_path, SPECIALS_EXPECTED, _validate_special)

    # Standing menu: one entry per apicbase row, sorted by name. unit_cost is
    # read straight from the file — DETERMINISTIC, never via draft_fn.
    standing = []
    for r in apic_rows:
        standing.append({
            "name": r["item"].strip(),
            "category": (r["category"] or "").strip(),
            "unit_cost": float(r["unit_cost"]),
            "allergens": _split_allergens(r["allergens"]),
        })
    standing.sort(key=lambda d: d["name"])

    # Specials: the DISTINCT dishes (a special recurs on many dates). First-seen
    # row wins for seed/allergens; then sorted by name for deterministic order.
    seen = {}
    for r in spec_rows:
        dish = r["dish"].strip()
        if dish in seen:
            continue
        seen[dish] = {
            "name": dish,
            "description_seed": (r["description_seed"] or "").strip(),
            "allergens": _split_allergens(r["allergens"]),
        }
    specials = sorted(seen.values(), key=lambda d: d["name"])

    # For each dish, build a context with NO numbers, then call draft_fn. A
    # draft_fn — template or model — physically cannot move a cost or price.
    drafts = {}
    for d in standing:
        context = {
            "name": d["name"],
            "category": d["category"] or "special",
            "allergens": list(d["allergens"]),
            "seed": None,
        }
        drafts[d["name"]] = draft_fn(context)
    for d in specials:
        context = {
            "name": d["name"],
            "category": "special",
            "allergens": list(d["allergens"]),
            "seed": d["description_seed"] or None,
        }
        drafts[d["name"]] = draft_fn(context)

    return {
        "standing": standing,
        "specials": specials,
        "drafts": drafts,
        "total_dishes": len(standing) + len(specials),
        "skipped": apic_skipped + spec_skipped,
    }


def render(metrics):
    esc = html.escape
    body = (
        "<h2>Menu copy drafts &mdash; approval queue</h2>"
        "<p class=\"explain\">Each dish below carries an <strong>AI-drafted piece "
        "of menu copy</strong>, written from the dish name, category, allergens "
        "and (for specials) a short description seed only &mdash; the AI never "
        "sees or changes a cost or price. Any number on this page is the "
        "<strong>food cost, computed by code</strong> from the Apicbase export, "
        "shown for reference &mdash; it is <strong>not a menu price</strong>. "
        "<strong>Nothing is published automatically:</strong> a person edits, "
        "approves and publishes each piece of copy.</p>"
        f"<p class=\"explain\">{metrics['total_dishes']} dishes in the queue "
        f"({len(metrics['standing'])} standing, {len(metrics['specials'])} "
        f"specials).</p>"
    )

    # Standing menu section.
    body += "<h2 class=\"sec\">Standing menu</h2>"
    body += "<div class=\"queue\">"
    for d in metrics["standing"]:
        draft = metrics["drafts"][d["name"]]
        allergens = _join(d["allergens"]) or "none declared"
        body += (
            "<section class=\"card\">"
            "<div class=\"meta\">"
            f"<span class=\"name\">{esc(d['name'])}</span>"
            f"<span class=\"cat\">{esc(d['category'])}</span>"
            f"<span class=\"cost\" title=\"food cost computed by code\">"
            f"food cost &pound;{d['unit_cost']:.2f} "
            f"<span class=\"tag\">cost, not a menu price</span></span>"
            "</div>"
            "<div class=\"draftwrap\">"
            "<div class=\"badge\">DRAFT &mdash; pending approval</div>"
            f"<div class=\"draft\">{esc(draft)}</div>"
            "</div>"
            f"<div class=\"allergens\">Allergens: {esc(allergens)}</div>"
            "</section>"
        )
    body += "</div>"

    # This period's specials section.
    body += "<h2 class=\"sec\">This period&rsquo;s specials</h2>"
    body += "<div class=\"queue\">"
    for d in metrics["specials"]:
        draft = metrics["drafts"][d["name"]]
        allergens = _join(d["allergens"]) or "none declared"
        body += (
            "<section class=\"card special\">"
            "<div class=\"meta\">"
            f"<span class=\"name\">{esc(d['name'])}</span>"
            "<span class=\"cat\">special</span>"
            "</div>"
            "<div class=\"draftwrap\">"
            "<div class=\"badge\">DRAFT &mdash; pending approval</div>"
            f"<div class=\"draft\">{esc(draft)}</div>"
            "</div>"
            f"<div class=\"allergens\">Allergens: {esc(allergens)}</div>"
            "</section>"
        )
    body += "</div>"

    body += (
        "<style>"
        ".explain{font:13px sans-serif;color:#444;}"
        ".sec{margin-top:18px;}"
        ".queue{display:grid;gap:12px;margin-top:8px;}"
        ".card{border:1px solid #ccc;border-radius:5px;padding:12px;"
        "border-left:4px solid #1f3a2d;}"
        ".card.special{border-left:4px solid #b8860b;}"
        ".meta{display:flex;gap:12px;align-items:baseline;font:12px sans-serif;color:#555;}"
        ".name{font-weight:bold;color:#1f3a2d;font-size:15px;}"
        ".cat{text-transform:capitalize;}"
        ".cost{margin-left:auto;font:12px sans-serif;color:#555;}"
        ".tag{font:10px sans-serif;color:#555;background:#eef3ef;border-radius:3px;padding:1px 5px;}"
        ".draftwrap{background:#f7f9f7;border:1px dashed #b8860b;border-radius:4px;"
        "padding:8px;margin-top:8px;}"
        ".badge{font:10px sans-serif;text-transform:uppercase;letter-spacing:.04em;"
        "background:#fff3cd;border:1px solid #b8860b;color:#7a5800;border-radius:3px;"
        "padding:2px 6px;display:inline-block;}"
        ".draft{font:13px/1.5 Georgia,serif;color:#222;margin-top:6px;}"
        ".allergens{font:11px sans-serif;color:#777;margin-top:6px;}"
        "</style>"
    )

    return bc.page("Menu Copy Drafts", CONFIG["site_name"], body,
                   metrics["skipped"], "menu & specials copy queue")


def main():
    try:
        html_out = render(compute("sample-data/apicbase-costings.csv",
                                  "sample-data/specials.csv"))
    except bc.BenjaminsError as e:
        print(f"Could not build the menu-copy-drafts page: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("menu-copy-drafts.html").write_text(html_out)
    print("Wrote menu-copy-drafts.html")


if __name__ == "__main__":
    main()
