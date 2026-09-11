import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import benjamins_common as bc

TOOL_DIR = Path(__file__).parent
CONFIG = json.loads((TOOL_DIR / "config.json").read_text())
CUBIGO_COLS = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]
BOOKINGS_COLS = ["date", "time", "party_size", "status", "source"]
DAYPARTS = ["Lunch", "Afternoon", "Evening"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

NOTE = ("This is a transparent weighted moving average, not a machine-learning "
        "forecast. Each cell is the weighted mean of the three most recent past "
        "occurrences of that weekday and daypart, most-recent first. The weights "
        "and any event adjustments are the only knobs — both are shown below so a "
        "manager can interrogate every number by hand.")


def _validate_cubigo(fn, row):
    # a check's daypart comes from its time; an unreadable time means we cannot
    # place the cover, so skip+count the row.
    bc.daypart(row["time"])  # raises BenjaminsError on malformed time
    # Mirror the weekly dashboard exactly: a cubigo row counts only if BOTH
    # covers AND net parse (the dashboard validates NUMERIC_FIELDS =
    # ["covers", "net"] and drops the row if either is non-numeric). Requiring
    # net here keeps this tool's covers identical to the world manifest.
    try:
        float(row["net"])  # non-numeric/empty net -> skip+count this row
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable net {row['net']!r}")
    try:
        float(row["covers"])  # a cover is a guest; non-numeric covers -> skip+count
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable covers {row['covers']!r}")


def _weighted_average(values, weights):
    """Weighted mean of values (most-recent first) against weights, using as
    many weights as there are values and renormalising them to sum to 1."""
    w = weights[:len(values)]
    total = sum(w)
    if not w or total == 0:
        return 0.0
    return sum((wi / total) * v for wi, v in zip(w, values))


def compute(cubigo_path, bookings_path, config):
    weights = config.get("weights", [0.5, 0.3, 0.2])
    events = {e["date"]: float(e["multiplier"]) for e in config.get("event_adjustments", [])}

    cubigo_rows, skipped = bc.read_csv_rows(cubigo_path, CUBIGO_COLS, _validate_cubigo)

    # historical covers per (date, daypart): a COVER is a GUEST, so each unique
    # (date, check_id) contributes its guest count int(float(covers)) (constant
    # within a check; take the first row seen). Rows with non-numeric covers OR
    # non-numeric net were already skipped+counted by _validate_cubigo, matching
    # the dashboard's drop rule.
    seen_checks = set()
    covers = defaultdict(int)        # (date_obj, daypart) -> guest covers
    bad_dates = set()
    for r in cubigo_rows:
        try:
            day = bc.parse_date(r["date"])
        except bc.BenjaminsError:
            bad_dates.add(r["date"])
            continue
        key = (r["date"], r["check_id"])
        if key in seen_checks:
            continue
        seen_checks.add(key)
        band = bc.daypart(r["time"])  # rows with bad times were already skipped
        covers[(day, band)] += int(float(r["covers"]))

    if bad_dates:
        skipped.append(
            f"{len(bad_dates)} unparseable date value(s) excluded from history: "
            + ", ".join(sorted(bad_dates)))

    if not covers:
        raise bc.BenjaminsError(
            "No datable covers in the Cubigo export — cannot build a forecast.")

    # bookings on the books per (date, daypart), for context alongside the forecast.
    booked = defaultdict(int)
    b_rows, b_skipped = bc.read_csv_rows(bookings_path, BOOKINGS_COLS)
    skipped = skipped + b_skipped
    for r in b_rows:
        try:
            day = bc.parse_date(r["date"])
            band = bc.daypart(r["time"])
            party = int(r["party_size"])
        except (bc.BenjaminsError, ValueError, TypeError):
            continue
        booked[(day, band)] += party

    # historical base value per (weekday, daypart): weighted avg of the 3 most
    # recent past occurrences of that weekday for that daypart.
    base = {}
    for daypart in DAYPARTS:
        for weekday in range(7):
            dates = sorted(
                (d for (d, b) in covers if b == daypart and d.weekday() == weekday),
                reverse=True,
            )[:3]
            vals = [covers[(d, daypart)] for d in dates]
            base[(weekday, daypart)] = {
                "value": _weighted_average(vals, weights),
                "recent_dates": [d.isoformat() for d in dates],
                "recent_values": vals,
            }

    # target week = the 7 days immediately after the last historical date.
    last = max(d for (d, _b) in covers)
    forecast = []
    for i in range(1, 8):
        td = last + timedelta(days=i)
        iso = td.isoformat()
        mult = events.get(iso)
        for daypart in DAYPARTS:
            b = base[(td.weekday(), daypart)]
            base_covers = b["value"]
            fc_covers = base_covers * mult if mult is not None else base_covers
            forecast.append({
                "target_date": iso,
                "weekday": td.weekday(),
                "weekday_name": WEEKDAYS[td.weekday()],
                "daypart": daypart,
                "base_covers": base_covers,
                "forecast_covers": fc_covers,
                "event_flag": mult is not None,
                "event_multiplier": mult,
                "recent_dates": b["recent_dates"],
                "recent_values": b["recent_values"],
                "booked": booked.get((td, daypart), 0),
            })

    total_history = sum(covers.values())
    total_forecast = sum(r["forecast_covers"] for r in forecast)

    return {
        "forecast": forecast,
        "weights": list(weights),
        "base": {f"{wd}|{dp}": v for (wd, dp), v in base.items()},
        "totals": {"history_covers": total_history,
                   "forecast_covers": total_forecast},
        "last_history": last.isoformat(),
        "skipped": skipped,
    }


_EXTRA_CSS = """
<style>
  .explain { font: 13px sans-serif; color: #555; }
  .dfchart { width: 100%; height: auto; margin: 8px 0 4px; }
  .dfchart rect.lunch { fill: #1f3a2d; }
  .dfchart rect.afternoon { fill: #7a5800; }
  .dfchart rect.evening { fill: #3a5a7a; }
  .dfchart .dlbl { font: 10px sans-serif; fill: #444; }
  .dfchart .vlbl { font: 9px sans-serif; fill: #444; }
  .legend { font: 11px sans-serif; color: #555; margin: 2px 0 8px; }
  .legend span { margin-right: 14px; }
  .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
        margin-right: 4px; vertical-align: middle; }
  td.num { text-align: right; }
  td.ev { color: #7a5800; font: 11px sans-serif; }
  .basis { font: 11px sans-serif; color: #777; }
</style>
"""

_SWATCH = {"Lunch": "#1f3a2d", "Afternoon": "#7a5800", "Evening": "#3a5a7a"}


def _chart(forecast):
    """Grouped bar chart: one cluster per target day, one bar per daypart."""
    days = sorted({r["target_date"] for r in forecast})
    if not days:
        return "<p>No data.</p>"
    by_day = defaultdict(dict)
    name_of = {}
    for r in forecast:
        by_day[r["target_date"]][r["daypart"]] = r["forecast_covers"]
        name_of[r["target_date"]] = r["weekday_name"]

    pad_l, pad_t = 8, 18
    plot_h = 150
    group_w = 86
    gap = 8
    bar_w = (group_w - gap) // len(DAYPARTS)
    width = pad_l * 2 + group_w * len(days)
    height = pad_t + plot_h + 34

    max_v = max((v for d in by_day.values() for v in d.values()), default=0) or 1

    parts = [f'<svg viewBox="0 0 {width} {height}" class="dfchart" role="img" '
             f'aria-label="Forecast covers by day and daypart">']
    base_y = pad_t + plot_h
    parts.append(f'<line x1="{pad_l}" y1="{base_y}" x2="{width - pad_l}" '
                 f'y2="{base_y}" stroke="#999" stroke-width="1"/>')
    for gi, day in enumerate(days):
        gx = pad_l + gi * group_w
        for bi, daypart in enumerate(DAYPARTS):
            v = by_day[day].get(daypart, 0.0)
            h = round(v / max_v * plot_h)
            x = gx + bi * bar_w + gap // 2
            cls = daypart.lower()
            parts.append(
                f'<rect class="{cls}" x="{x}" y="{base_y - h}" '
                f'width="{bar_w - 2}" height="{h}" rx="1"/>'
                f'<text class="vlbl" x="{x + (bar_w - 2) / 2:.1f}" '
                f'y="{base_y - h - 3}" text-anchor="middle">{v:.0f}</text>')
        parts.append(
            f'<text class="dlbl" x="{gx + group_w / 2:.1f}" y="{base_y + 14}" '
            f'text-anchor="middle">{html.escape(name_of[day][:3])}</text>'
            f'<text class="dlbl" x="{gx + group_w / 2:.1f}" y="{base_y + 26}" '
            f'text-anchor="middle">{html.escape(day[5:])}</text>')
    parts.append("</svg>")

    legend = '<div class="legend">' + "".join(
        f'<span><span class="sw" style="background:{_SWATCH[dp]}"></span>{dp}</span>'
        for dp in DAYPARTS) + "</div>"
    return "".join(parts) + legend


def render(metrics):
    esc = html.escape
    forecast = metrics["forecast"]
    weights = metrics["weights"]
    wtxt = ", ".join(f"{w:g}" for w in weights)

    body = _EXTRA_CSS
    body += "<h2>Demand forecast — next week, covers by day and daypart</h2>"
    body += f'<p class="explain">{esc(NOTE)}</p>'
    body += (f'<p>Weights (most-recent first): <strong>{esc(wtxt)}</strong>. '
             f'Built from history up to {esc(bc.fmt_day(bc.parse_date(metrics["last_history"])))}. '
             f'Forecast total for the week: '
             f'<strong>{metrics["totals"]["forecast_covers"]:.0f}</strong> covers '
             f'across {len(forecast) // len(DAYPARTS)} days.</p>')

    body += _chart(forecast)

    body += ("<table><tr>"
             "<td><strong>Date</strong></td>"
             "<td><strong>Day</strong></td>"
             "<td><strong>Daypart</strong></td>"
             "<td><strong>Forecast covers</strong></td>"
             "<td><strong>On the books</strong></td>"
             "<td><strong>Basis (recent covers)</strong></td>"
             "<td><strong>Event</strong></td></tr>")
    for r in forecast:
        basis = " / ".join(str(v) for v in r["recent_values"]) or "—"
        ev = (f"x{r['event_multiplier']:g}" if r["event_flag"] else "")
        body += (f"<tr><td>{esc(r['target_date'])}</td>"
                 f"<td>{esc(r['weekday_name'])}</td>"
                 f"<td>{esc(r['daypart'])}</td>"
                 f"<td class=\"num\">{r['forecast_covers']:.0f}</td>"
                 f"<td class=\"num\">{r['booked']}</td>"
                 f"<td class=\"basis\">{esc(basis)}</td>"
                 f"<td class=\"ev\">{esc(ev)}</td></tr>")
    body += "</table>"
    body += ('<p class="basis">"On the books" is current OpenTable party-size sum '
             "for that service, shown for cross-check; it is not part of the average. "
             '"Basis" lists the covers from the three source dates, most-recent first.</p>')

    return bc.page("Demand forecast", CONFIG["site_name"], body,
                   metrics["skipped"], "next week — weighted moving average")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample", action="store_true",
        help="Build from this tool's bundled sample-data/, regardless of the "
             "current directory, and write output to out/ instead of "
             "overwriting the committed HTML.")
    # parse_known_args: main() is also called directly (with no args) by the
    # test suite, so unrelated argv (e.g. a pytest invocation's own flags)
    # must not be treated as an error here.
    args, _unknown = parser.parse_known_args()

    if args.sample:
        cubigo_path = TOOL_DIR / "sample-data" / "cubigo-sales.csv"
        bookings_path = TOOL_DIR / "sample-data" / "opentable-bookings.csv"
        out_dir = TOOL_DIR / "out"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / "demand-forecast.html"
    else:
        cubigo_path = "sample-data/cubigo-sales.csv"
        bookings_path = "sample-data/opentable-bookings.csv"
        out_path = Path("demand-forecast.html")

    try:
        metrics = compute(cubigo_path, bookings_path, CONFIG)
    except bc.BenjaminsError as e:
        print(f"Could not build the demand forecast: {e}", file=sys.stderr)
        raise SystemExit(1)
    out_path.write_text(render(metrics))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
