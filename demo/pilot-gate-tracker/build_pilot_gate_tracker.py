import html
import json
import sys
from collections import defaultdict
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
CUBIGO_COLS = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]
SURVEY_COLS = ["date", "food", "service", "value", "comment"]

# Direction of merit per metric. "higher" = bigger is better (covers, spend,
# satisfaction); "lower" = smaller is better (labour cost as a share of net).
# repeat_bookings has no source in the data, so it is shown as not-yet-tracked.
DIRECTION = {
    "covers": "higher",
    "spend_per_head": "higher",
    "labour_pct": "lower",
    "satisfaction": "higher",
}

LABELS = {
    "covers": "Covers (guests)",
    "spend_per_head": "Spend per head",
    "labour_pct": "Labour as % of net",
    "satisfaction": "Guest satisfaction (1-5)",
    "repeat_bookings": "Repeat bookings",
}

NOTE = ("This is the mechanism for the plan's Sunday-lunch pilot. Each gate, its "
        "green and amber thresholds, and its direction of merit are pre-agreed in "
        "config.json before a pilot week runs. When the pilot is live, that week's "
        "figures plug straight in and the panel turns green, amber or red against the "
        "same gates. Shown here is the latest trading week as a worked example. A gate "
        "with no data source is shown as not-yet-tracked, never estimated.")


def _validate_cubigo(fn, row):
    if not row["check_id"]:
        raise bc.BenjaminsError("row missing check_id")
    try:
        float(row["net"])  # non-numeric net -> skip+count
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable net {row['net']!r}")
    try:
        float(row["covers"])  # a cover is a guest; non-numeric covers -> skip+count
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable covers {row['covers']!r}")


def _validate_survey(fn, row):
    for field in ("food", "service", "value"):
        try:
            float(row[field])
        except (ValueError, TypeError):
            raise bc.BenjaminsError(f"unreadable {field} {row[field]!r}")


def _status(value, green, amber, direction):
    if direction == "higher":
        if value >= green:
            return "green"
        if value >= amber:
            return "amber"
        return "red"
    # lower is better
    if value <= green:
        return "green"
    if value <= amber:
        return "amber"
    return "red"


def _gate(value, name, gates):
    g = gates[name]
    direction = DIRECTION[name]
    return {
        "value": value,
        "status": _status(value, g["green"], g["amber"], direction),
        "green": g["green"],
        "amber": g["amber"],
        "direction": direction,
    }


def compute(cubigo_path, survey_path, kpis_path, config):
    gates_cfg = config["gates"]
    kpis = bc.load_json_file(kpis_path, "weekly manual KPIs")
    if not kpis:
        raise bc.BenjaminsError("manual-kpis.json has no weeks — cannot evaluate gates.")
    week_iso = max(kpis.keys())          # latest week-ending Sunday
    week = bc.parse_date(week_iso)

    cubigo_rows, skipped = bc.read_csv_rows(cubigo_path, CUBIGO_COLS, _validate_cubigo)

    # covers (a COVER is a GUEST): one guest count int(float(covers)) per unique
    # (date, check_id) in the latest week, taking the first row of each check,
    # then summed. net sums the same surviving rows for the week.
    check_covers, net = {}, 0.0
    for r in cubigo_rows:
        try:
            d = bc.parse_date(r["date"])
        except bc.BenjaminsError:
            continue
        if bc.week_ending(d) != week:
            continue
        key = (r["date"], r["check_id"])
        check_covers.setdefault(key, int(float(r["covers"])))
        net += float(r["net"])
    covers = sum(check_covers.values())
    net = round(net, 2)

    if covers == 0:
        raise bc.BenjaminsError(
            f"No covers for week ending {week_iso} in the Cubigo export.")

    if not net:
        raise bc.BenjaminsError(
            f"week {week_iso} has zero net revenue — cannot compute spend/head or labour %")

    if "labour_cost" not in kpis[week_iso]:
        raise bc.BenjaminsError(
            f"manual-kpis is missing labour_cost for week {week_iso}")

    spend_per_head = net / covers
    labour_pct = kpis[week_iso]["labour_cost"] / net

    # satisfaction: mean over the week's flash-survey rows of (food+service+value)/3.
    survey_rows, s_skipped = bc.read_csv_rows(survey_path, SURVEY_COLS, _validate_survey)
    skipped = skipped + s_skipped
    scores = []
    for r in survey_rows:
        try:
            d = bc.parse_date(r["date"])
        except bc.BenjaminsError:
            continue
        if bc.week_ending(d) != week:
            continue
        scores.append((float(r["food"]) + float(r["service"]) + float(r["value"])) / 3)
    satisfaction = sum(scores) / len(scores) if scores else None

    gates = {
        "covers": _gate(covers, "covers", gates_cfg),
        "spend_per_head": _gate(spend_per_head, "spend_per_head", gates_cfg),
        "labour_pct": _gate(labour_pct, "labour_pct", gates_cfg),
    }
    if satisfaction is not None:
        gates["satisfaction"] = _gate(satisfaction, "satisfaction", gates_cfg)
    else:
        # no survey rows for the week -> treat as not-yet-tracked rather than
        # inventing a score.
        g = gates_cfg["satisfaction"]
        gates["satisfaction"] = {"value": None, "status": "untracked",
                                 "green": g["green"], "amber": g["amber"],
                                 "direction": DIRECTION["satisfaction"]}
        skipped = skipped + [f"No flash-survey rows for week ending {week_iso} — satisfaction not tracked"]

    # repeat_bookings: NOT AVAILABLE in the data — shown as not-yet-tracked, no
    # number invented (mirrors the dashboard's zero-vs-None policy).
    gates["repeat_bookings"] = {"value": None, "status": "untracked",
                                "green": None, "amber": None, "direction": None}

    return {
        "week_ending": week_iso,
        "net_revenue": net,
        "gates": gates,
        "skipped": skipped,
    }


_EXTRA_CSS = """
<style>
  .framing { font: 13px sans-serif; color: #555; margin: 6px 0 14px; }
  .gates { display: grid; grid-template-columns: 1fr; gap: 8px; margin: 12px 0; }
  .gate { display: grid; grid-template-columns: 1.4fr 1fr 90px 1.3fr;
          align-items: center; gap: 12px; border: 1px solid #ddd;
          border-left-width: 6px; border-radius: 4px; padding: 8px 12px; }
  .gate .metric { font-size: 14px; }
  .gate .value { font-size: 18px; font-weight: bold; }
  .gate .chip { font: 11px sans-serif; text-transform: uppercase; letter-spacing: 0.5px;
                text-align: center; padding: 3px 0; border-radius: 3px; color: #fff; }
  .gate .thresholds { font: 11px sans-serif; color: #666; text-align: right; }
  .gate.green { border-left-color: #1f7a3d; }
  .gate.green .chip { background: #1f7a3d; }
  .gate.amber { border-left-color: #b8860b; }
  .gate.amber .chip { background: #b8860b; }
  .gate.red { border-left-color: #a3261c; }
  .gate.red .chip { background: #a3261c; }
  .gate.untracked { border-left-color: #999; background: #f6f6f6; }
  .gate.untracked .metric, .gate.untracked .thresholds { color: #777; }
  .gate.untracked .value { color: #999; font-weight: normal; font-size: 14px; }
  .gate.untracked .chip { background: #888; }
</style>
"""

_STATUS_TEXT = {"green": "On gate", "amber": "Watch", "red": "Off gate",
                "untracked": "Not yet tracked"}


def _fmt_value(name, gate):
    v = gate["value"]
    if v is None:
        return "—"
    if name == "covers":
        return f"{v:.0f}"
    if name == "spend_per_head":
        return f"£{v:.2f}"
    if name == "labour_pct":
        return f"{v:.1%}"
    if name == "satisfaction":
        return f"{v:.2f}"
    return f"{v}"


def _fmt_threshold(name, val):
    if val is None:
        return ""
    if name == "spend_per_head":
        return f"£{val:g}"
    if name == "labour_pct":
        return f"{val:.0%}"
    return f"{val:g}"


def _thresholds_text(name, gate):
    if gate["green"] is None:
        return "no source"
    arrow = "≥" if gate["direction"] == "higher" else "≤"
    green = _fmt_threshold(name, gate["green"])
    amber = _fmt_threshold(name, gate["amber"])
    return f"green {arrow} {html.escape(green)} · amber {arrow} {html.escape(amber)}"


def render(metrics):
    esc = html.escape
    gates = metrics["gates"]
    week = bc.fmt_day(bc.parse_date(metrics["week_ending"]))

    body = _EXTRA_CSS
    body += f"<h2>Pilot gate tracker — RAG against pre-agreed gates</h2>"
    body += f'<p class="framing">{esc(NOTE)}</p>'
    body += (f"<p>Latest trading week: <strong>week ending {esc(week)}</strong>. "
             f"Net revenue this week: <strong>£{metrics['net_revenue']:,.2f}</strong>.</p>")

    order = ["covers", "spend_per_head", "labour_pct", "satisfaction", "repeat_bookings"]
    body += '<div class="gates">'
    for name in order:
        g = gates[name]
        status = g["status"]
        body += (
            f'<div class="gate {esc(status)}">'
            f'<div class="metric">{esc(LABELS[name])}</div>'
            f'<div class="value">{esc(_fmt_value(name, g))}</div>'
            f'<div class="chip">{esc(_STATUS_TEXT[status])}</div>'
            f'<div class="thresholds">{_thresholds_text(name, g)}</div>'
            f'</div>'
        )
    body += '</div>'

    return bc.page("Pilot gate tracker", CONFIG["site_name"], body,
                   metrics["skipped"], f"week ending {week}")


def main():
    try:
        metrics = compute("sample-data/cubigo-sales.csv",
                          "sample-data/flash-survey.csv",
                          "sample-data/manual-kpis.json", CONFIG)
    except bc.BenjaminsError as e:
        print(f"Could not build the pilot gate tracker: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("pilot-gate-tracker.html").write_text(render(metrics))
    print("Wrote pilot-gate-tracker.html")


if __name__ == "__main__":
    main()
