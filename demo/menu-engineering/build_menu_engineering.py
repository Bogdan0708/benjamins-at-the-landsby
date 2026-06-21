import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
CUBIGO_COLS = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]
APICBASE_COLS = ["item", "category", "unit_cost", "allergens"]

NOTE = ("Each item is placed by sales volume (popularity) against gross margin. "
        "The crosshair is the menu median for each axis. Stars earn their place; "
        "plowhorses sell but thin; puzzles are profitable but overlooked; dogs do neither. "
        "A decision aid for the manager and head chef — never a reason to drop a resident favourite.")


def _validate_cubigo(fn, row):
    try:
        float(row["net"])  # non-numeric/empty net -> skip+count this row
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable net {row['net']!r}")


def _validate_apicbase(fn, row):
    try:
        float(row["unit_cost"])
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable unit_cost {row['unit_cost']!r}")


def _quadrant(hi_units, hi_margin):
    if hi_units and hi_margin:
        return "Star"
    if hi_units and not hi_margin:
        return "Plowhorse"
    if not hi_units and hi_margin:
        return "Puzzle"
    return "Dog"


def compute(cubigo_path, apicbase_path):
    cubigo_rows, skipped = bc.read_csv_rows(cubigo_path, CUBIGO_COLS, _validate_cubigo)
    apicbase_rows, api_skipped = bc.read_csv_rows(apicbase_path, APICBASE_COLS, _validate_apicbase)
    skipped = skipped + api_skipped

    costs = {r["item"]: float(r["unit_cost"]) for r in apicbase_rows}

    units = defaultdict(int)
    revenue = defaultdict(float)
    for r in cubigo_rows:
        units[r["item"]] += 1
        revenue[r["item"]] += float(r["net"])

    records = []
    for item in units:
        if item not in costs:
            raise bc.BenjaminsError(
                f"menu item {item!r} sold in Cubigo has no Apicbase costing — "
                f"costings and product mix are out of sync.")
        u = units[item]
        rev = round(revenue[item], 2)
        unit_price = revenue[item] / u
        unit_cost = costs[item]
        margin = unit_price - unit_cost
        margin_pct = margin / unit_price if unit_price else None
        records.append({
            "item": item,
            "units": u,
            "revenue": rev,
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "margin": margin,
            "margin_pct": margin_pct,
        })

    median_units = median(r["units"] for r in records)
    median_margin = median(r["margin"] for r in records)

    for r in records:
        r["quadrant"] = _quadrant(r["units"] >= median_units, r["margin"] >= median_margin)

    # deterministic order: by units desc, then margin desc, then item name.
    records.sort(key=lambda r: (-r["units"], -r["margin"], r["item"]))

    totals = {
        "units": sum(r["units"] for r in records),
        "revenue": round(sum(r["revenue"] for r in records), 2),
    }
    return {
        "items": records,
        "median_units": median_units,
        "median_margin": median_margin,
        "totals": totals,
        "skipped": skipped,
    }


_QFILL = {"Star": "#1f3a2d", "Plowhorse": "#7a5800", "Puzzle": "#3a5a7a", "Dog": "#8a3a3a"}


def _scatter(items, median_units, median_margin):
    """Inline SVG popularity (x=units) x margin (y) scatter with median crosshair."""
    if not items:
        return "<p>No data.</p>"
    pad_l, pad_r, pad_t, pad_b = 48, 16, 18, 36
    plot_w, plot_h = 460, 300
    width = pad_l + plot_w + pad_r
    height = pad_t + plot_h + pad_b

    max_u = max(r["units"] for r in items)
    max_m = max(r["margin"] for r in items)
    min_m = min(r["margin"] for r in items)
    # keep margin axis from 0 (or below) up to a little headroom.
    lo_m = min(0.0, min_m)
    hi_m = max_m * 1.08 or 1.0
    span_m = (hi_m - lo_m) or 1.0
    span_u = max_u * 1.08 or 1.0

    def px(u):
        return pad_l + (u / span_u) * plot_w

    def py(m):
        return pad_t + plot_h - ((m - lo_m) / span_m) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" class="scatter" role="img" '
             f'aria-label="Popularity by margin scatter">']
    # axes
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" class="axis"/>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" class="axis"/>')
    # median crosshair
    cx, cy = px(median_units), py(median_margin)
    parts.append(f'<line x1="{cx:.1f}" y1="{pad_t}" x2="{cx:.1f}" y2="{pad_t + plot_h}" class="median"/>')
    parts.append(f'<line x1="{pad_l}" y1="{cy:.1f}" x2="{pad_l + plot_w}" y2="{cy:.1f}" class="median"/>')
    # quadrant labels (corners of the plot area)
    parts.append(f'<text x="{pad_l + plot_w - 4}" y="{pad_t + 12}" text-anchor="end" class="qlbl">Stars</text>')
    parts.append(f'<text x="{pad_l + 4}" y="{pad_t + 12}" text-anchor="start" class="qlbl">Puzzles</text>')
    parts.append(f'<text x="{pad_l + plot_w - 4}" y="{pad_t + plot_h - 6}" text-anchor="end" class="qlbl">Plowhorses</text>')
    parts.append(f'<text x="{pad_l + 4}" y="{pad_t + plot_h - 6}" text-anchor="start" class="qlbl">Dogs</text>')
    # axis titles
    parts.append(f'<text x="{pad_l + plot_w / 2}" y="{height - 6}" text-anchor="middle" class="axt">Units sold &rarr;</text>')
    parts.append(f'<text x="12" y="{pad_t + plot_h / 2}" text-anchor="middle" class="axt" '
                 f'transform="rotate(-90 12 {pad_t + plot_h / 2:.1f})">Margin per unit &rarr;</text>')
    # points
    for r in items:
        x, y = px(r["units"]), py(r["margin"])
        fill = _QFILL[r["quadrant"]]
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}"/>')
        parts.append(f'<text x="{x:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="plbl">'
                     f'{html.escape(r["item"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


_EXTRA_CSS = """
<style>
  .scatter { width: 100%; height: auto; margin: 8px 0 4px; }
  .scatter .axis { stroke: #999; stroke-width: 1; }
  .scatter .median { stroke: #b8860b; stroke-width: 1; stroke-dasharray: 4 3; }
  .scatter .qlbl { font: 10px sans-serif; fill: #999; text-transform: uppercase; letter-spacing: .5px; }
  .scatter .axt { font: 11px sans-serif; fill: #555; }
  .scatter .plbl { font: 9px sans-serif; fill: #333; }
  .explain { font: 13px sans-serif; color: #555; }
  td.q { font: 11px sans-serif; }
</style>
"""


def render(metrics):
    cur = CONFIG["currency"]
    esc = html.escape
    items = metrics["items"]
    counts = defaultdict(int)
    for r in items:
        counts[r["quadrant"]] += 1

    body = _EXTRA_CSS
    body += "<h2>Menu engineering — popularity x margin</h2>"
    body += f'<p class="explain">{esc(NOTE)}</p>'
    body += (f'<p>{len(items)} menu items. Median units '
             f'{metrics["median_units"]:g}, median margin '
             f'{bc.fmt_money(metrics["median_margin"], cur)}. '
             f'{counts["Star"]} stars, {counts["Plowhorse"]} plowhorses, '
             f'{counts["Puzzle"]} puzzles, {counts["Dog"]} dogs.</p>')
    body += _scatter(items, metrics["median_units"], metrics["median_margin"])

    body += ("<table><tr>"
             "<td><strong>Item</strong></td>"
             "<td><strong>Units</strong></td>"
             "<td><strong>Unit price</strong></td>"
             "<td><strong>Margin</strong></td>"
             "<td><strong>Margin %</strong></td>"
             "<td><strong>Quadrant</strong></td></tr>")
    for r in items:
        body += (f"<tr><td>{esc(r['item'])}</td>"
                 f"<td>{r['units']}</td>"
                 f"<td>{bc.fmt_money(r['unit_price'], cur)}</td>"
                 f"<td>{bc.fmt_money(r['margin'], cur)}</td>"
                 f"<td>{bc.fmt_pct(r['margin_pct'])}</td>"
                 f"<td class=\"q\">{esc(r['quadrant'])}</td></tr>")
    body += "</table>"

    return bc.page("Menu engineering matrix", CONFIG["site_name"],
                   body, metrics["skipped"], "product mix x unit margin")


def main():
    try:
        metrics = compute("sample-data/cubigo-sales.csv",
                          "sample-data/apicbase-costings.csv")
    except bc.BenjaminsError as e:
        print(f"Could not build the menu-engineering matrix: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("menu-engineering.html").write_text(render(metrics))
    print("Wrote menu-engineering.html")


if __name__ == "__main__":
    main()
