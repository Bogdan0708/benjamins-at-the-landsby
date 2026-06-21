import html
import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
EXPECTED = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]


def _validate(fn, row):
    if not row["check_id"]:
        raise bc.BenjaminsError("row missing check_id")
    try:
        float(row["net"])  # non-numeric/empty net -> skip+count this row
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable net {row['net']!r}")
    try:
        float(row["covers"])  # non-numeric covers -> skip+count (a cover is a guest)
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable covers {row['covers']!r}")


def compute(csv_path, report_date):
    rows, skipped = bc.read_csv_rows(csv_path, EXPECTED, _validate)
    prior_date = report_date - timedelta(days=7)

    def day(d):
        # a COVER is a GUEST: one guest count per (date, check_id), taken from
        # the first row of that check (covers is constant within a check), then
        # summed. Rows with non-numeric covers were already skipped by _validate.
        check_covers, net = {}, 0.0
        items = defaultdict(float)
        for r in rows:
            if r["date"] != d.isoformat():
                continue
            key = (r["date"], r["check_id"])
            if key not in check_covers:
                check_covers[key] = int(float(r["covers"]))
            net += float(r["net"])
            items[r["item"]] += float(r["net"])
        return {"date": d.isoformat(), "covers": sum(check_covers.values()),
                "net": round(net, 2), "items": items}

    today, prior = day(report_date), day(prior_date)
    ranked = sorted(today["items"].items(), key=lambda kv: (-kv[1], kv[0]))
    # top/bottom are kept disjoint so no item appears in both lists on a quiet day.
    half = min(5, len(ranked) // 2)
    top_sellers = ranked[:half]
    bottom_sellers = ranked[len(ranked) - half:][::-1] if half else []
    return {"today": today, "prior": prior,
            "top_sellers": top_sellers, "bottom_sellers": bottom_sellers,
            "skipped": skipped}


def render(metrics):
    cur = CONFIG["currency"]
    body = f"<h2>Sales flash &mdash; {bc.fmt_day(bc.parse_date(metrics['today']['date']))}</h2>"
    body += (f"<p>Covers {metrics['today']['covers']} "
             f"(vs {metrics['prior']['covers']} same day last week). "
             f"Net {bc.fmt_money(metrics['today']['net'], cur)} "
             f"(vs {bc.fmt_money(metrics['prior']['net'], cur)}).</p>")
    body += "<h3>Top sellers</h3><ol>" + "".join(
        f"<li>{html.escape(i)} &mdash; {bc.fmt_money(v, cur)}</li>" for i, v in metrics["top_sellers"]) + "</ol>"
    body += "<h3>Slowest movers</h3><ol>" + "".join(
        f"<li>{html.escape(i)} &mdash; {bc.fmt_money(v, cur)}</li>" for i, v in metrics["bottom_sellers"]) + "</ol>"
    return bc.page("Daily Sales Flash", CONFIG["site_name"], body,
                   metrics["skipped"], bc.fmt_day(bc.parse_date(metrics["today"]["date"])))


def main():
    from datetime import date
    rd = date.fromisoformat(CONFIG["report_date"])
    try:
        html_out = render(compute("sample-data/cubigo-sales.csv", rd))
    except bc.BenjaminsError as e:
        print(f"Could not build the sales flash: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("daily-sales-flash.html").write_text(html_out)
    print("Wrote daily-sales-flash.html")


if __name__ == "__main__":
    main()
