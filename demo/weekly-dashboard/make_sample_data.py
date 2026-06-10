#!/usr/bin/env python3
"""Generate synthetic sample data for the weekly-dashboard demo.

Deterministic: fixed seed, fixed date range. Re-running always produces
identical files. Volumes are consistent with the plan's stated planning
assumptions (~300-400 weekly covers, ~GBP 20-24 spend per head, external
share in low single digits).
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "sample-data"
rng = random.Random(42)

START = date(2026, 4, 13)            # Monday; 8 weeks ending Sunday 7 June 2026
DAYS = 8 * 7
MISSING_DAY = date(2026, 6, 2)       # Tuesday in the latest week: sales export "lost"

# weekday() -> target covers (Mon lunch-only; closed Sundays)
COVER_TARGETS = {0: 30, 1: 52, 2: 55, 3: 58, 4: 72, 5: 78}

STARTERS = [("Matzo ball soup", 8.95), ("Soup of the day", 7.95)]
MAINS = [("Roast chicken", 14.50), ("Fish pie", 13.95), ("Paneer & spinach curry", 12.50),
         ("Shepherd's pie", 12.95), ("Vegetable biryani", 11.95), ("Grilled salmon", 15.00)]
DESSERTS = [("Sticky toffee pudding", 6.50), ("Fruit crumble", 6.25)]
DRINKS = [("Glass of house wine", 5.50), ("Pot of tea", 3.25), ("Coffee", 3.00)]

COMMENTS = ["Lovely lunch as always.", "Service was warm and unhurried.", "",
            "Soup a little salty today.", "", "Wonderful staff, felt very looked after.", ""]


def trading_minutes(d):
    """(open, last-seating) in minutes since midnight, or None if closed."""
    if d.weekday() == 6:
        return None
    if d.weekday() == 0:
        return (12 * 60, 14 * 60 + 30)
    return (12 * 60, 19 * 60)


def make_day_checks(d, seq_start):
    """Return (check_rows, day_net, checks_meta) for one trading day."""
    hours = trading_minutes(d)
    rows, checks_meta = [], []
    day_net = 0.0
    target = round(COVER_TARGETS[d.weekday()] * rng.uniform(0.9, 1.1))
    covers_done, seq = 0, seq_start
    while covers_done < target:
        party = rng.choices([1, 2, 3, 4], [0.2, 0.5, 0.2, 0.1])[0]
        mins = rng.randint(hours[0], hours[1])
        t = f"{mins // 60:02d}:{mins % 60:02d}"
        cid = f"{d:%Y%m%d}-{seq:03d}"
        guest = "external" if rng.random() < 0.05 else "resident"
        items = []
        for _ in range(party):
            items.append(rng.choice(MAINS))
            if rng.random() < 0.45:
                items.append(rng.choice(STARTERS))
            if rng.random() < 0.35:
                items.append(rng.choice(DESSERTS))
            if rng.random() < 0.90:
                items.append(rng.choices(DRINKS, [0.3, 0.35, 0.35])[0])
        for name, price in items:
            cat = ("Starter" if (name, price) in STARTERS else
                   "Main" if (name, price) in MAINS else
                   "Dessert" if (name, price) in DESSERTS else "Drinks")
            rows.append({"date": d.isoformat(), "time": t, "check_id": cid, "item": name,
                         "category": cat, "covers": str(party), "net": f"{price:.2f}",
                         "guest_type": guest})
            day_net += price
        checks_meta.append({"date": d, "time": t, "party": party})
        covers_done += party
        seq += 1
    return rows, round(day_net, 2), checks_meta


def main():
    OUT.mkdir(exist_ok=True)
    sales, bookings, settlements, surveys = [], [], [], []
    for i in range(DAYS):
        d = START + timedelta(days=i)
        if trading_minutes(d) is None:
            continue
        # Check numbers restart at 1 each day, as real POS check numbers do.
        rows, day_net, checks_meta = make_day_checks(d, 1)
        # The missing day traded (settlement exists) but its sales export rows were lost.
        if d != MISSING_DAY:
            sales.extend(rows)
        # Card settlements cover only the card-paid share; the rest is cash to the till.
        gross = round(day_net * rng.uniform(0.82, 0.94), 2)
        fees = round(gross * 0.0175, 2)
        settlements.append({"date": d.isoformat(), "gross": f"{gross:.2f}",
                            "fees": f"{fees:.2f}", "net": f"{gross - fees:.2f}"})
        for c in rng.sample(checks_meta, k=max(1, len(checks_meta) * 2 // 5)):
            bookings.append({"date": d.isoformat(), "time": c["time"],
                             "party_size": str(c["party"]), "status": "seated",
                             "source": rng.choices(["online", "phone"], [0.7, 0.3])[0]})
        if rng.random() < 0.30:
            bookings.append({"date": d.isoformat(), "time": "13:00", "party_size": str(rng.randint(2, 4)),
                             "status": "no-show", "source": "online"})
        for _ in range(rng.randint(1, 3)):
            surveys.append({"date": d.isoformat(),
                            "food": str(rng.choices([3, 4, 5], [0.1, 0.35, 0.55])[0]),
                            "service": str(rng.choices([3, 4, 5], [0.05, 0.3, 0.65])[0]),
                            "value": str(rng.choices([3, 4, 5], [0.15, 0.45, 0.4])[0]),
                            "comment": rng.choice(COMMENTS)})

    # Three deliberately malformed rows (unreadable date / net / covers).
    bad = {"time": "13:00", "check_id": "BAD-001", "item": "Roast chicken",
           "category": "Main", "covers": "2", "net": "14.50", "guest_type": "resident"}
    sales.append({**bad, "date": "2026-13-01"})
    sales.append({**bad, "date": "2026-05-06", "check_id": "BAD-002", "net": ""})
    sales.append({**bad, "date": "2026-05-20", "check_id": "BAD-003", "covers": "two"})

    def write_csv(name, fieldnames, rows):
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    write_csv("cubigo-sales.csv",
              ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"], sales)
    write_csv("opentable-bookings.csv",
              ["date", "time", "party_size", "status", "source"], bookings)
    write_csv("square-settlements.csv", ["date", "gross", "fees", "net"], settlements)
    write_csv("flash-survey.csv", ["date", "food", "service", "value", "comment"], surveys)

    manual = {}
    for w in range(8):
        week_end = START + timedelta(days=6 + 7 * w)
        views = 110 + 35 * w + rng.randint(-15, 15)
        manual[week_end.isoformat()] = {
            "labour_cost": round(2850 - w * 20 + rng.uniform(-40, 40), 2),
            "labour_hours": 225 - w + rng.randint(-5, 5),
            "reviews": {"google": 3 + w // 2, "tripadvisor": 4 + (1 if w >= 5 else 0),
                        "opentable": 11 + w // 3},
            "gbp_views": views,
            "gbp_clicks": int(views * 0.08),
            "enquiries": rng.randint(0, 2),
        }
    (OUT / "manual-kpis.json").write_text(json.dumps(manual, indent=2), encoding="utf-8")
    print(f"Wrote sample data to {OUT}")


if __name__ == "__main__":
    main()
