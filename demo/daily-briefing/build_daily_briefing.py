"""build_daily_briefing.py — Pre-service huddle sheet for Benjamin's at The Landsby.

Reads three exports for a single service day and writes daily-briefing.html:
a one-page sheet the team reads together before doors open.

  opentable-bookings.csv  date,time,party_size,status,source
  specials.csv            date,dish,description_seed,allergens (";"-separated)
  training-rota.csv       date,staff,topic

No revenue or money — this is an operational sheet, not a financial one.

Run from inside demo/daily-briefing/:
    python3 build_daily_briefing.py

Python standard library only. Same input always produces the same output.
"""
import html
import json
import sys
from pathlib import Path

import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())

BOOKINGS_COLUMNS = ["date", "time", "party_size", "status", "source"]
SPECIALS_COLUMNS = ["date", "dish", "description_seed", "allergens"]
TRAINING_COLUMNS = ["date", "staff", "topic"]


def _validate_booking(fn, row):
    if not row["time"]:
        raise bc.BenjaminsError("booking missing time")
    if row["status"] == "seated":
        try:
            int(row["party_size"])  # seated covers must be countable
        except (ValueError, TypeError):
            raise bc.BenjaminsError(f"unreadable party_size {row['party_size']!r}")


def _validate_special(fn, row):
    if not row["dish"].strip():
        raise bc.BenjaminsError("special missing dish name")


def _validate_training(fn, row):
    if not row["staff"].strip():
        raise bc.BenjaminsError("training row missing staff name")


def compute(bookings_path, specials_path, training_path, briefing_date):
    """Filter all three inputs to briefing_date and summarise for the huddle.

    Returns a dict with:
        briefing_date  the ISO date string
        bookings       sorted [(time, party_size, status, source)]
        booking_count  number of seated bookings
        covers_booked  sum of party_size over seated bookings
        specials       [(dish, description_seed, [allergen, ...])]
        training       [(staff, topic)]
        skipped        data-quality notes from all three files
    """
    book_rows, skipped = bc.read_csv_rows(bookings_path, BOOKINGS_COLUMNS, _validate_booking)
    spec_rows, spec_skipped = bc.read_csv_rows(specials_path, SPECIALS_COLUMNS, _validate_special)
    train_rows, train_skipped = bc.read_csv_rows(training_path, TRAINING_COLUMNS, _validate_training)
    skipped = skipped + spec_skipped + train_skipped

    bookings = []
    booking_count = 0
    covers_booked = 0
    for r in book_rows:
        if r["date"] != briefing_date:
            continue
        status = r["status"]
        party = int(r["party_size"]) if status == "seated" else r["party_size"]
        bookings.append((r["time"], r["party_size"], status, r["source"]))
        if status == "seated":
            booking_count += 1
            covers_booked += party
    # Stable order: by time, then the rest, so the committed HTML never drifts.
    bookings.sort(key=lambda b: (b[0], b[1], b[2], b[3]))

    specials = []
    for r in spec_rows:
        if r["date"] != briefing_date:
            continue
        raw = r.get("allergens", "") or ""
        allergens = [t.strip() for t in raw.split(";") if t.strip()]
        specials.append((r["dish"].strip(), r["description_seed"].strip(), allergens))
    specials.sort(key=lambda s: s[0])

    training = []
    for r in train_rows:
        if r["date"] != briefing_date:
            continue
        training.append((r["staff"].strip(), r["topic"].strip()))
    training.sort(key=lambda t: (t[0], t[1]))

    return {
        "briefing_date": briefing_date,
        "bookings": bookings,
        "booking_count": booking_count,
        "covers_booked": covers_booked,
        "specials": specials,
        "training": training,
        "skipped": skipped,
    }


def render(metrics):
    """Build the huddle sheet HTML. No business logic here."""
    esc = html.escape
    day_label = bc.fmt_day(bc.parse_date(metrics["briefing_date"]))

    # --- Bookings ---
    if metrics["bookings"]:
        rows = "".join(
            f"<tr><td>{esc(time)}</td><td>{esc(str(party))}</td>"
            f"<td>{esc(status)}</td><td>{esc(source)}</td></tr>"
            for time, party, status, source in metrics["bookings"]
        )
        bookings_table = (
            "<table><thead><tr><th>Time</th><th>Party</th>"
            "<th>Status</th><th>Source</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        bookings_table = "<p>No bookings on the system for today.</p>"

    bookings_html = (
        "<h2>Bookings</h2>"
        f'<p class="summary">{metrics["booking_count"]} seated booking(s) — '
        f'{metrics["covers_booked"]} covers booked.</p>'
        f"{bookings_table}"
    )

    # --- Specials ---
    if metrics["specials"]:
        items = []
        for dish, desc, allergens in metrics["specials"]:
            if allergens:
                flags = " ".join(
                    f'<span class="allergen">{esc(a)}</span>' for a in allergens
                )
                allergen_html = f'<div class="allergens"><strong>Allergens:</strong> {flags}</div>'
            else:
                allergen_html = '<div class="allergens no-allergens">No declared allergens — confirm with kitchen.</div>'
            desc_html = f'<div class="desc">{esc(desc)}</div>' if desc else ""
            items.append(
                f'<li><div class="dish">{esc(dish)}</div>{desc_html}{allergen_html}</li>'
            )
        specials_html = "<h2>Today's specials</h2><ul class=\"specials\">" + "".join(items) + "</ul>"
    else:
        specials_html = "<h2>Today's specials</h2><p>No specials listed for today.</p>"

    # --- Training ---
    if metrics["training"]:
        rows = "".join(
            f"<tr><td>{esc(staff)}</td><td>{esc(topic)}</td></tr>"
            for staff, topic in metrics["training"]
        )
        training_html = (
            "<h2>Training today</h2>"
            "<table><thead><tr><th>Staff</th><th>Topic</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        training_html = "<h2>Training today</h2><p>None scheduled.</p>"

    body_html = f"""
<p class="caption">Pre-service huddle sheet — read together before doors open.</p>
{bookings_html}
{specials_html}
{training_html}
<style>
  .caption {{ font-size: 12px; color: #444; margin-bottom: 12px; }}
  .summary {{ font-size: 14px; }}
  table {{ margin: 6px 0 14px; }}
  th {{ text-align: left; font: 11px sans-serif; color: #555; text-transform: uppercase;
        border-bottom: 1px solid #ccc; padding: 3px 6px; }}
  td:last-child {{ text-align: left; }}
  ul.specials {{ list-style: none; margin: 6px 0 14px; padding: 0; font-size: 13px; }}
  ul.specials li {{ border: 1px solid #ddd; border-radius: 4px; padding: 8px 10px; margin-bottom: 8px; }}
  .dish {{ font-weight: bold; color: #1f3a2d; }}
  .desc {{ font-size: 12px; color: #555; font-style: italic; margin: 2px 0; }}
  .allergens {{ font-size: 12px; margin-top: 4px; }}
  .allergen {{ display: inline-block; background: #fdecea; color: #b30000; border: 1px solid #e6b3ad;
               border-radius: 3px; padding: 1px 6px; margin: 1px 2px; font: 11px sans-serif; }}
  .no-allergens {{ color: #777; }}
</style>
"""

    return bc.page(
        "Daily Briefing",
        CONFIG["site_name"],
        body_html,
        metrics["skipped"],
        day_label,
    )


def main():
    try:
        metrics = compute(
            "sample-data/opentable-bookings.csv",
            "sample-data/specials.csv",
            "sample-data/training-rota.csv",
            CONFIG["briefing_date"],
        )
        html_out = render(metrics)
    except bc.BenjaminsError as e:
        print(f"Could not build the daily briefing: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("daily-briefing.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote daily-briefing.html "
          f"({metrics['booking_count']} bookings, {len(metrics['specials'])} specials, "
          f"{len(metrics['training'])} training)")


if __name__ == "__main__":
    main()
