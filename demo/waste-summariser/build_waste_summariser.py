import html
import json
import sys
from collections import defaultdict
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
WASTE_COLS = ["date", "item", "qty", "reason"]
APICBASE_COLS = ["item", "category", "unit_cost", "allergens"]

NOTE = ("Every binned plate, spilt jug, and over-prepped tray, costed at Apicbase "
        "unit cost and totalled by week. Waste you can see is waste you can cut — "
        "without ever shorting a resident's plate.")


def _validate_waste(fn, row):
    try:
        qty = float(row["qty"])  # non-numeric/empty qty -> skip+count this row
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable qty {row['qty']!r}")
    if qty <= 0:
        raise bc.BenjaminsError(f"non-positive qty '{row['qty']}'")


def _validate_apicbase(fn, row):
    try:
        float(row["unit_cost"])
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable unit_cost {row['unit_cost']!r}")


def compute(waste_path, apicbase_path):
    waste_rows, skipped = bc.read_csv_rows(waste_path, WASTE_COLS, _validate_waste)
    apicbase_rows, api_skipped = bc.read_csv_rows(apicbase_path, APICBASE_COLS, _validate_apicbase)
    skipped = skipped + api_skipped

    costs = {r["item"]: float(r["unit_cost"]) for r in apicbase_rows}

    cost_by_week = defaultdict(float)
    cost_by_item = defaultdict(float)
    qty_by_item = defaultdict(float)
    cost_by_reason = defaultdict(float)
    total = 0.0

    for r in waste_rows:
        item = r["item"]
        if item not in costs:
            # referential integrity: a wasted item with no Apicbase cost is a
            # data-quality failure — abort rather than silently miscost waste.
            raise bc.BenjaminsError(f"waste item '{item}' has no Apicbase cost")
        qty = float(r["qty"])
        unit_cost = costs[item]
        cost = qty * unit_cost
        week = bc.week_ending(bc.parse_date(r["date"]))
        cost_by_week[week.isoformat()] += cost
        cost_by_item[item] += cost
        qty_by_item[item] += qty
        cost_by_reason[r["reason"]] += cost
        total += cost

    # per-week costs in chronological order (week label is the ISO week-ending date)
    weeks = sorted((wk, round(c, 2)) for wk, c in cost_by_week.items())

    # top wasted items by cost desc, tie-stable on item name
    top_items = sorted(
        ({"item": it, "qty": qty_by_item[it], "cost": round(c, 2)}
         for it, c in cost_by_item.items()),
        key=lambda d: (-d["cost"], d["item"]),
    )

    reasons = sorted(
        ((reason, round(c, 2)) for reason, c in cost_by_reason.items()),
        key=lambda kv: (-kv[1], kv[0]),
    )

    return {
        "cost_by_week": weeks,
        "top_items": top_items,
        "reasons": reasons,
        "total_cost_of_waste": round(total, 2),
        "skipped": skipped,
    }


def render(metrics):
    cur = CONFIG["currency"]
    esc = html.escape

    # bar chart: cost of waste by week. Label each bar by week-ending day/month.
    pairs = []
    for wk, cost in metrics["cost_by_week"]:
        d = bc.parse_date(wk)
        pairs.append((f"{d.day} {d.strftime('%b')}", cost))

    body = ("<style>"
            ".explain { font: 13px sans-serif; color: #555; }"
            ".total { font-size: 17px; }"
            "</style>")
    body += f'<h2>Cost of waste &mdash; {len(metrics["cost_by_week"])} week(s)</h2>'
    body += f'<p class="explain">{esc(NOTE)}</p>'
    body += (f'<p class="total">Total cost of waste: '
             f'<strong>{bc.fmt_money(metrics["total_cost_of_waste"], cur)}</strong></p>')

    body += "<h2>Cost of waste by week</h2>"
    body += bc.bar_chart(pairs, prefix=cur)

    body += "<h2>Top wasted items</h2>"
    body += ("<table><tr>"
             "<td><strong>Item</strong></td>"
             "<td><strong>Qty</strong></td>"
             "<td><strong>Cost</strong></td></tr>")
    for it in metrics["top_items"]:
        body += (f"<tr><td>{esc(it['item'])}</td>"
                 f"<td>{it['qty']:g}</td>"
                 f"<td>{bc.fmt_money(it['cost'], cur)}</td></tr>")
    body += "</table>"

    if metrics["reasons"]:
        body += "<h2>By reason</h2>"
        body += ("<table><tr>"
                 "<td><strong>Reason</strong></td>"
                 "<td><strong>Cost</strong></td></tr>")
        for reason, cost in metrics["reasons"]:
            body += (f"<tr><td>{esc(reason)}</td>"
                     f"<td>{bc.fmt_money(cost, cur)}</td></tr>")
        body += "</table>"

    return bc.page("Waste summary", CONFIG["site_name"], body,
                   metrics["skipped"], "weekly cost of waste")


def main():
    try:
        metrics = compute("sample-data/waste-log.csv",
                          "sample-data/apicbase-costings.csv")
    except bc.BenjaminsError as e:
        print(f"Could not build the waste summary: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("waste-summariser.html").write_text(render(metrics))
    print("Wrote waste-summariser.html")


if __name__ == "__main__":
    main()
