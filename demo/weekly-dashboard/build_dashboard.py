#!/usr/bin/env python3
"""Benjamin's at The Landsby - weekly one-page dashboard.

Reads CSV/JSON exports from sample-data/ and writes dashboard.html.
Python standard library only. Same input always produces the same output.
"""
import csv
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "sample-data"
OUTPUT = BASE / "dashboard.html"

EXPECTED_COLUMNS = {
    "cubigo-sales.csv": ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"],
    "opentable-bookings.csv": ["date", "time", "party_size", "status", "source"],
    "square-settlements.csv": ["date", "gross", "fees", "net"],
    "flash-survey.csv": ["date", "food", "service", "value", "comment"],
}

EXPORT_SCREENS = {
    "cubigo-sales.csv": "Cubigo > Reports > Sales detail (CSV export)",
    "opentable-bookings.csv": "OpenTable > Reports > Reservations (CSV export)",
    "square-settlements.csv": "Square Dashboard > Balance > Settlements (CSV export)",
    "flash-survey.csv": "the QR flash-survey form responses (CSV export)",
}

NUMERIC_FIELDS = {
    "cubigo-sales.csv": ["covers", "net"],
    "opentable-bookings.csv": ["party_size"],
    "square-settlements.csv": ["gross", "fees", "net"],
    "flash-survey.csv": ["food", "service", "value"],
}

NOT_YET_TRACKED = [
    "Resident dining frequency (visits/apartment/month)",
    "Events & private dining revenue",
    "Food cost % (needs the purchasing/Apicbase export)",
    "Repeat-booking rate (needs booking history with guest identity)",
    "Club/society pipeline (contacted → visited → booked)",
]


class DashboardError(Exception):
    """A problem explained in plain English; main() prints it without a traceback."""


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def week_ending(d):
    """The Sunday on or after d (weeks end on Sunday)."""
    return d + timedelta(days=(6 - d.weekday()) % 7)


def validate_row(filename, row):
    # DictReader marks truncated rows with None values and over-wide rows
    # with a None key; both would crash downstream code if let through.
    if None in row or None in row.values():
        return False, "wrong number of fields"
    try:
        parse_date(row["date"])
    except (ValueError, TypeError, KeyError):
        return False, f"unreadable date {row.get('date')!r}"
    if filename in ("cubigo-sales.csv", "opentable-bookings.csv"):
        try:
            datetime.strptime(row["time"], "%H:%M")
        except (ValueError, TypeError, KeyError):
            return False, f"unreadable time {row.get('time')!r}"
    for field in NUMERIC_FIELDS[filename]:
        try:
            float(row[field])
        except (ValueError, TypeError, KeyError):
            return False, f"unreadable {field} {row.get(field)!r}"
    return True, ""


def read_csv_rows(filename):
    """Return (rows, skipped): valid rows as dicts, and human-readable skip reasons."""
    path = DATA_DIR / filename
    if not path.exists():
        raise DashboardError(
            f"Cannot find '{filename}' in {DATA_DIR}.\n"
            f"Export it from: {EXPORT_SCREENS.get(filename, 'the relevant system')}\n"
            f"then save it in the sample-data folder and run this script again."
        )
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            found = reader.fieldnames or []
            expected = EXPECTED_COLUMNS[filename]
            if found != expected:
                raise DashboardError(
                    f"'{filename}' does not look like the expected export - "
                    f"the export format may have changed.\n"
                    f"  Expected columns: {', '.join(expected)}\n"
                    f"  Found columns:    {', '.join(found)}"
                )
            rows, skipped = [], []
            for n, row in enumerate(reader, start=2):
                ok, reason = validate_row(filename, row)
                if ok:
                    rows.append(row)
                else:
                    skipped.append(f"{filename} line {n}: {reason}")
            return rows, skipped
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise DashboardError(
            f"Cannot read '{filename}': {e}\n"
            f"Re-export it from: {EXPORT_SCREENS.get(filename, 'the relevant system')}"
        )


def load_json_file(path, what):
    if not path.exists():
        raise DashboardError(f"Cannot find '{path.name}' ({what}). Expected at: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DashboardError(f"'{path.name}' ({what}) is not valid JSON (line {e.lineno}): {e.msg}")
    except (OSError, UnicodeDecodeError) as e:
        raise DashboardError(f"Cannot read '{path.name}' ({what}): {e}")


def daypart(time_str):
    h, m = (int(x) for x in time_str.split(":")[:2])
    mins = h * 60 + m
    if mins < 15 * 60:
        return "Lunch"
    if mins < 17 * 60 + 30:
        return "Afternoon"
    return "Evening"


def compute_metrics(sales_rows, booking_rows, settlement_rows, survey_rows, manual_kpis):
    """Pure computation: validated rows in, metrics dict out. No file or HTML concerns."""
    if not sales_rows:
        raise DashboardError("No readable sales rows found - cannot build a dashboard from empty data.")

    # Keyed by (date, check_id): real POS check numbers can reset daily,
    # so check_id alone is not unique across days.
    checks = {}
    revenue_by_week = defaultdict(float)
    sales_days_by_week = defaultdict(set)
    for row in sales_rows:
        d = parse_date(row["date"])
        wk = week_ending(d)
        revenue_by_week[wk] += float(row["net"])
        sales_days_by_week[wk].add(d)
        key = (row["date"], row["check_id"])
        if key not in checks:
            checks[key] = {
                "covers": int(float(row["covers"])),
                "guest_type": row["guest_type"],
                "daypart": daypart(row["time"]),
                "week": wk,
            }

    weeks = sorted(revenue_by_week)
    latest = weeks[-1]

    covers_by_week = defaultdict(int)
    for c in checks.values():
        covers_by_week[c["week"]] += c["covers"]

    latest_checks = [c for c in checks.values() if c["week"] == latest]
    covers_latest = sum(c["covers"] for c in latest_checks)
    revenue_latest = revenue_by_week[latest]
    external = sum(c["covers"] for c in latest_checks
                   if c["guest_type"].strip().lower() == "external")

    daypart_covers = defaultdict(int)
    for c in latest_checks:
        daypart_covers[c["daypart"]] += c["covers"]

    surveys_latest = [r for r in survey_rows if week_ending(parse_date(r["date"])) == latest]

    def avg(field):
        vals = [float(r[field]) for r in surveys_latest]
        return sum(vals) / len(vals) if vals else None

    bookings_latest = [r for r in booking_rows if week_ending(parse_date(r["date"])) == latest]
    no_shows = sum(1 for r in bookings_latest if r["status"].strip().lower() == "no-show")

    # None means "no settlement rows for the week"; a true £0.00 stays 0.0.
    settlements_latest = [r for r in settlement_rows
                          if week_ending(parse_date(r["date"])) == latest]
    settlement_net = (sum(float(r["net"]) for r in settlements_latest)
                      if settlements_latest else None)

    # Mon-Sat are trading days (closed Sundays); flag open days with no sales rows.
    expected_days = {latest - timedelta(days=i) for i in range(7)}
    expected_days = {d for d in expected_days if d.weekday() != 6}
    missing_days = sorted(expected_days - sales_days_by_week[latest])

    manual = manual_kpis.get(latest.isoformat(), {})

    def manual_number(key):
        value = manual.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise DashboardError(
                f"manual-kpis.json: '{key}' for week {latest.isoformat()} "
                f"should be a number, got {value!r}")

    labour_cost = manual_number("labour_cost")
    labour_pct = (labour_cost / revenue_latest
                  if labour_cost is not None and revenue_latest else None)
    reviews = manual.get("reviews") or {}
    try:
        review_total = sum(int(v) for v in reviews.values()) if reviews else None
    except (TypeError, ValueError):
        raise DashboardError(
            f"manual-kpis.json: review counts for week {latest.isoformat()} "
            f"should be whole numbers, got {reviews!r}")

    return {
        "latest_week": latest,
        "covers": covers_latest,
        "revenue": revenue_latest,
        "spend_per_head": revenue_latest / covers_latest if covers_latest else None,
        "external_share": external / covers_latest if covers_latest else None,
        "daypart_covers": dict(daypart_covers),
        "revenue_trend": [(wk, revenue_by_week[wk]) for wk in weeks],
        "covers_trend": [(wk, covers_by_week[wk]) for wk in weeks],
        "survey": {"food": avg("food"), "service": avg("service"), "value": avg("value"),
                   "responses": len(surveys_latest)},
        "bookings": len(bookings_latest),
        "no_show_rate": (no_shows / len(bookings_latest)) if bookings_latest else None,
        "settlement_net": settlement_net,
        "labour_pct": labour_pct,
        "review_total": review_total,
        "manual": manual,
        "missing_days": missing_days,
    }


def fmt_money(v, cur):
    return f"{cur}{v:,.0f}" if v is not None else "—"


def fmt_pct(v):
    return f"{v:.0%}" if v is not None else "—"


def fmt_score(v):
    return f"{v:.1f}" if v is not None else "—"


def fmt_day(d):
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def bar_chart(pairs, width=460, height=140, prefix=""):
    """Inline SVG bar chart from (label, value) pairs. No dependencies."""
    if not pairs:
        return "<p>No data.</p>"
    max_v = max(v for _, v in pairs) or 1
    bar_w = width // len(pairs)
    # 18px headroom above y=0: the tallest bar's value label sits at y = -5.
    parts = [f'<svg viewBox="0 -18 {width} {height + 54}" class="chart" role="img">']
    for i, (label, value) in enumerate(pairs):
        h = round(value / max_v * height)
        x = i * bar_w
        parts.append(
            f'<rect x="{x + 6}" y="{height - h}" width="{bar_w - 12}" height="{h}" rx="2"/>'
            f'<text x="{x + bar_w // 2}" y="{height + 16}" text-anchor="middle" class="lbl">{html.escape(str(label))}</text>'
            f'<text x="{x + bar_w // 2}" y="{height - h - 5}" text-anchor="middle" class="val">{prefix}{value:,.0f}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_html(metrics, config, skipped):
    m = metrics
    cur = config.get("currency", "£")
    cap = config.get("targets", {}).get("external_share_cap")
    esc = html.escape
    manual = m["manual"]

    spend = f"{cur}{m['spend_per_head']:.2f}" if m["spend_per_head"] is not None else "—"
    ext = fmt_pct(m["external_share"]) + (f" <span class=\"sub\">cap {fmt_pct(cap)}</span>" if cap else "")
    kpis = [
        ("Covers (week)", f"{m['covers']:,}"),
        ("Revenue (week)", fmt_money(m["revenue"], cur)),
        ("Spend per head", spend),
        ("External share", ext),
        ("Labour %", fmt_pct(m["labour_pct"])),
        ("Survey food/service/value",
         f"{fmt_score(m['survey']['food'])} / {fmt_score(m['survey']['service'])} / {fmt_score(m['survey']['value'])}"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-label">{esc(label)}</div><div class="kpi-value">{value}</div></div>'
        for label, value in kpis)

    daypart_pairs = [(dp, m["daypart_covers"].get(dp, 0)) for dp in ("Lunch", "Afternoon", "Evening")]
    trend_pairs = [(wk.strftime("%d %b"), rev) for wk, rev in m["revenue_trend"]]

    leading = [
        ("Google Business Profile views", manual.get("gbp_views")),
        ("Google Business Profile clicks", manual.get("gbp_clicks")),
        ("Online bookings (week)", m["bookings"]),
        ("No-show rate", fmt_pct(m["no_show_rate"]) if m["no_show_rate"] is not None else None),
        ("Flash-survey responses", m["survey"]["responses"]),
        ("Online reviews (all platforms, total)", m["review_total"]),
        ("Private dining / event enquiries", manual.get("enquiries")),
    ]
    leading_html = "".join(
        f"<tr><td>{esc(label)}</td><td>{esc(str(value)) if value is not None else '—'}</td></tr>"
        for label, value in leading)
    nyt_html = "".join(f"<li>{esc(item)}</li>" for item in NOT_YET_TRACKED)

    footer_bits = []
    if m["settlement_net"] is not None:
        footer_bits.append(
            f"Square settlements (week, net of fees): {fmt_money(m['settlement_net'], cur)} "
            f"vs POS revenue {fmt_money(m['revenue'], cur)} — differences are card fees, "
            f"cash sales and any missing export days.")
    if m["missing_days"]:
        days = ", ".join(fmt_day(d) for d in m["missing_days"])
        footer_bits.append(f"No sales data for: {days} (open day(s) with no rows in the export).")
    if skipped:
        items = "".join(f"<li>{esc(s)}</li>" for s in skipped)
        footer_bits.append(f"{len(skipped)} row(s) skipped as unreadable:<ul>{items}</ul>")
    if not (m["missing_days"] or skipped):
        footer_bits.append("All rows read; no missing open days detected.")
    footer_html = "".join(f"<div class=\"note\">{b}</div>" for b in footer_bits)

    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>{esc(config.get('site_name', ''))} — weekly dashboard</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #222; margin: 24px auto; max-width: 960px; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline;
            border-bottom: 3px double #1f3a2d; padding-bottom: 8px; }}
  h1 {{ font-size: 22px; margin: 0; color: #1f3a2d; }}
  .watermark {{ background: #fff3cd; border: 1px solid #b8860b; color: #7a5800;
                padding: 3px 10px; font: 12px sans-serif; border-radius: 3px; }}
  .week {{ font: 13px sans-serif; color: #555; }}
  .kpis {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin: 16px 0; }}
  .kpi {{ border: 1px solid #ccc; border-radius: 4px; padding: 8px; }}
  .kpi-label {{ font: 11px sans-serif; color: #555; text-transform: uppercase; }}
  .kpi-value {{ font-size: 19px; margin-top: 4px; }}
  .sub {{ font: 11px sans-serif; color: #777; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  h2 {{ font-size: 14px; color: #1f3a2d; border-bottom: 1px solid #ddd; padding-bottom: 3px; }}
  .chart rect {{ fill: #1f3a2d; }}
  .chart .lbl, .chart .val {{ font: 10px sans-serif; fill: #444; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td {{ padding: 3px 6px; border-bottom: 1px solid #eee; }}
  td:last-child {{ text-align: right; }}
  ul {{ margin: 4px 0 4px 18px; padding: 0; font-size: 12px; }}
  footer {{ margin-top: 18px; border-top: 1px solid #ccc; font: 12px sans-serif; color: #555; }}
  .note {{ margin-top: 6px; }}
  @media print {{ body {{ margin: 0; }} @page {{ size: A4; margin: 12mm; }} }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{esc(config.get('site_name', ''))} — weekly dashboard</h1>
    <div class="week">Week ending {fmt_day(m['latest_week'])} {m['latest_week'].year}</div>
  </div>
  <div class="watermark">SAMPLE DATA — synthetic, for demonstration</div>
</header>
<div class="kpis">{kpi_html}</div>
<div class="cols">
  <section><h2>Covers by daypart (this week)</h2>{bar_chart(daypart_pairs)}</section>
  <section><h2>Revenue by week</h2>{bar_chart(trend_pairs, prefix=cur)}</section>
</div>
<div class="cols">
  <section><h2>Leading indicators (this week)</h2><table>{leading_html}</table></section>
  <section><h2>Not yet tracked</h2>
    <p class="sub">Shown honestly rather than estimated; each gains a source as systems data becomes available.</p>
    <ul>{nyt_html}</ul>
  </section>
</div>
<footer><strong>Data quality</strong>{footer_html}</footer>
</body>
</html>"""


def main():
    try:
        config = load_json_file(BASE / "config.json", "site configuration")
        manual = load_json_file(DATA_DIR / "manual-kpis.json", "hand-entered weekly KPIs")
        sales, sk1 = read_csv_rows("cubigo-sales.csv")
        bookings, sk2 = read_csv_rows("opentable-bookings.csv")
        settlements, sk3 = read_csv_rows("square-settlements.csv")
        surveys, sk4 = read_csv_rows("flash-survey.csv")
        skipped = sk1 + sk2 + sk3 + sk4
        metrics = compute_metrics(sales, bookings, settlements, surveys, manual)
        OUTPUT.write_text(render_html(metrics, config, skipped), encoding="utf-8")
        print(f"Wrote {OUTPUT}")
        if skipped:
            print(f"Note: {len(skipped)} row(s) skipped - details in the page footer.")
    except DashboardError as e:
        print(f"\nProblem: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
