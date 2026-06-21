#!/usr/bin/env python3
"""make_world.py — assemble the demo "world" from the dashboard's canon.

This script does NOT regenerate the weekly dashboard's data. The dashboard's
sample-data is grandfathered canon (read-only). What this does:

  (a) copies the five canonical files VERBATIM into demo/_source/world/;
  (b) deterministically generates new inputs that RECONCILE to that canon
      (referential integrity: every generated item/date traces back to the
      cubigo facts) — apicbase costings, waste log, specials, training rota,
      and reviews derived from the flash survey;
  (c) computes expected-metrics.json, the declared source of truth that
      downstream tools reconcile their own figures against.

Deterministic: every synthetic value comes from random.Random(20260413).
The global random module, time, and wall-clock are never touched.

Python standard library only. Run with cwd = demo/_source:
    python3 make_world.py
"""
import csv
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import benjamins_common as bc

SEED = 20260413

SRC = Path(__file__).parent
DASH = SRC.parent / "weekly-dashboard" / "sample-data"
WORLD = SRC / "world"

CANON_FILES = [
    "cubigo-sales.csv",
    "square-settlements.csv",
    "opentable-bookings.csv",
    "flash-survey.csv",
    "manual-kpis.json",
]

# The 14 UK statutory allergens (Natasha's Law / FSA list).
ALLERGENS_14 = [
    "celery", "gluten (cereals)", "crustaceans", "eggs", "fish", "lupin",
    "milk", "molluscs", "mustard", "tree nuts", "peanuts", "sesame",
    "soya", "sulphur dioxide",
]

WASTE_REASONS = ["spoilage", "over-prep", "returned", "trim", "expired"]

ROTA_STAFF = ["Aisha", "Bartek", "Carmen", "Devon", "Elaine", "Farid"]
ROTA_TOPICS = [
    "allergen handling", "wine service", "resident dietary needs",
    "till & Square close-down", "fire & evacuation", "food hygiene refresher",
    "complaint recovery",
]

SPECIAL_DISHES = [
    ("Pan-fried sea bream", "light citrus butter seasonal greens"),
    ("Slow-braised lamb shoulder", "rosemary root vegetables comfort"),
    ("Wild mushroom risotto", "creamy parmesan vegetarian warming"),
    ("Roast vegetable wellington", "festive vegetarian crisp pastry"),
    ("Poached pear & almond tart", "autumn dessert delicate sweet"),
    ("Smoked haddock chowder", "creamy hearty lunchtime starter"),
    ("Confit duck leg", "rich classic redcurrant indulgent"),
    ("Beetroot & goats cheese salad", "fresh light colourful starter"),
]


def _platform_for(rng):
    return rng.choice(["google", "tripadvisor", "opentable"])


def read_cubigo():
    """Return (rows, item_set, modal_price, category_of).

    rows         every DictReader row, verbatim order.
    item_set     every distinct non-empty item string a plain DictReader
                 yields (this MUST equal the test's cubigo item set).
    modal_price  item -> most-common parseable per-line net (for costings).
    category_of  item -> most-common category seen for that item.
    """
    path = WORLD / "cubigo-sales.csv"
    rows = []
    item_set = set()
    price_counts = defaultdict(Counter)
    cat_counts = defaultdict(Counter)
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            item = r.get("item")
            if item:  # exclude empty/None items
                item_set.add(item)
            # modal price / category from well-formed rows only
            try:
                net = float(r["net"])
            except (TypeError, ValueError, KeyError):
                continue
            if item:
                price_counts[item][net] += 1
                cat_counts[item][r.get("category") or ""] += 1
    modal_price = {it: c.most_common(1)[0][0] for it, c in price_counts.items()}
    category_of = {it: c.most_common(1)[0][0] for it, c in cat_counts.items()}
    return rows, item_set, modal_price, category_of


def trading_days(rows):
    """Sorted distinct trading dates whose date string parses (canon only)."""
    days = set()
    for r in rows:
        try:
            days.add(bc.parse_date(r["date"]))
        except bc.BenjaminsError:
            continue
    return sorted(days)


def write_apicbase(rng, item_set, modal_price, category_of):
    """One row per distinct cubigo item; food-cost lands in the 30-35% band."""
    path = WORLD / "apicbase-costings.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "category", "unit_cost", "allergens"])
        for item in sorted(item_set):
            net_price = modal_price.get(item, 0.0)
            unit_cost = round(net_price * rng.uniform(0.30, 0.35), 2)
            category = category_of.get(item, "")
            # deterministic per-item allergen subset, seeded off the item name
            arng = random.Random(f"{SEED}:{item}")
            k = arng.randint(0, 4)  # 0..4 allergens; 0 -> empty string
            allergens = ";".join(sorted(arng.sample(ALLERGENS_14, k)))
            w.writerow([item, category, f"{unit_cost:.2f}", allergens])


def write_waste(rng, days, item_set):
    """~2-4 entries per (canonical) week; dates & items drawn from canon."""
    path = WORLD / "waste-log.csv"
    items = sorted(item_set)
    by_week = defaultdict(list)
    for d in days:
        by_week[bc.week_ending(d)].append(d)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "item", "qty", "reason"])
        for we in sorted(by_week):
            n = rng.randint(2, 4)
            for _ in range(n):
                d = rng.choice(by_week[we])
                item = rng.choice(items)
                qty = rng.randint(1, 5)
                reason = rng.choice(WASTE_REASONS)
                w.writerow([d.isoformat(), item, qty, reason])


def _special_allergens(dish):
    """Stable per-dish allergen subset (0-3), seeded off the dish name.

    Uses a dedicated sub-RNG so it does NOT perturb the main rng stream — the
    same dish maps to the same allergens on every date and across runs. Specials
    are off-menu and disjoint from apicbase, so they carry their own tags.
    """
    arng = random.Random(f"specials:{dish}")
    k = arng.randint(0, 3)  # 0..3 allergens; 0 -> empty string
    return ";".join(sorted(arng.sample(ALLERGENS_14, k)))


def write_specials(rng, days):
    """One or two specials per service day across the window."""
    path = WORLD / "specials.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "dish", "description_seed", "allergens"])
        for d in days:
            n = rng.randint(1, 2)
            chosen = rng.sample(SPECIAL_DISHES, n)
            for dish, seed in chosen:
                w.writerow([d.isoformat(), dish, seed, _special_allergens(dish)])


def write_training(rng, days):
    """Training entries spread across the window."""
    path = WORLD / "training-rota.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "staff", "topic"])
        # roughly one or two sessions a week, on real trading days
        by_week = defaultdict(list)
        for d in days:
            by_week[bc.week_ending(d)].append(d)
        for we in sorted(by_week):
            n = rng.randint(1, 2)
            for _ in range(n):
                d = rng.choice(by_week[we])
                staff = rng.choice(ROTA_STAFF)
                topic = rng.choice(ROTA_TOPICS)
                w.writerow([d.isoformat(), staff, topic])


def write_reviews(rng, kpis):
    """Generate reviews from flash-survey sentiment.

    Each emitted review maps to a survey row: platform in {google, tripadvisor,
    opentable}, rating = round(mean(food,service,value)), text from the comment.
    The count per platform across the window broadly tracks the growing review
    trajectory in manual-kpis.json (we emit, per week, the week-on-week increase
    in each platform's cumulative count, plus a small baseline so every survey
    week contributes something).
    """
    path = WORLD / "reviews.csv"

    # survey rows grouped by week-ending
    survey_by_week = defaultdict(list)
    with (WORLD / "flash-survey.csv").open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                d = bc.parse_date(r["date"])
            except bc.BenjaminsError:
                continue
            try:
                food = int(r["food"])
                service = int(r["service"])
                value = int(r["value"])
            except (TypeError, ValueError):
                continue
            rating = round((food + service + value) / 3)
            comment = (r.get("comment") or "").strip()
            survey_by_week[bc.week_ending(d).isoformat()].append((d, rating, comment))

    # week-on-week increase in cumulative review counts per platform
    weeks = sorted(kpis)
    prev = {"google": 0, "tripadvisor": 0, "opentable": 0}
    quota = {}  # week -> {platform: how many reviews to emit}
    for wk in weeks:
        revs = kpis[wk].get("reviews", {})
        q = {}
        for plat in ("google", "tripadvisor", "opentable"):
            cur = int(revs.get(plat, prev[plat]))
            q[plat] = max(0, cur - prev[plat]) + 1  # +1 baseline per platform/week
            prev[plat] = cur
        quota[wk] = q

    rows_out = []
    for wk in weeks:
        survey = survey_by_week.get(wk, [])
        if not survey:
            continue
        for plat in ("google", "tripadvisor", "opentable"):
            for _ in range(quota[wk][plat]):
                d, rating, comment = rng.choice(survey)
                text = _review_text(rng, rating, comment)
                rows_out.append((d.isoformat(), plat, rating, text))

    rows_out.sort(key=lambda x: (x[0], x[1]))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "platform", "rating", "text"])
        for row in rows_out:
            w.writerow(row)


_POSITIVE = [
    "A really lovely meal, we'll be back.",
    "Warm welcome and attentive service throughout.",
    "Everything was beautifully presented and tasty.",
]
_NEUTRAL = [
    "Pleasant enough, a few small things to tidy up.",
    "Decent food and friendly staff, nothing to fault.",
]
_NEGATIVE = [
    "Bit of an off day for the kitchen, hope it improves.",
    "Service was kind but the food missed the mark.",
]


def _review_text(rng, rating, comment):
    """Derive review text from the survey comment, padded by sentiment."""
    if comment:
        return comment
    if rating >= 5:
        return rng.choice(_POSITIVE)
    if rating >= 4:
        return rng.choice(_NEUTRAL)
    return rng.choice(_NEGATIVE)


def compute_metrics(rows):
    """Compute expected-metrics.json from the canonical cubigo rows.

    Definitions (the declared source of truth — they mirror the weekly
    dashboard's covers logic exactly):
      - a COVER is a GUEST, not a check. The dashboard validates each cubigo
        row against NUMERIC_FIELDS = ["covers", "net"], so a row survives only
        if BOTH its covers AND its net parse as numbers. For each distinct
        (date, check_id) with a non-empty check_id that has at least one such
        surviving row, the check's guest count is int(float(covers)) taken from
        the FIRST surviving row (covers is constant within a check). Covers =
        the SUM of those guest counts. A check with no surviving row (covers
        non-numeric, OR net non-numeric) is excluded from covers entirely —
        exactly as the dashboard drops the row before counting it;
      - net_revenue = sum of net, skipping rows whose net is not a valid float
        (independent of covers — a check excluded for non-numeric covers still
        contributes its valid net, exactly as the menu line-items would);
      - external_share = external guest-covers / total guest-covers (guest_type
        resolved once per check);
      - spend_per_head = net_revenue / guest-covers;
      - labour_pct = labour_cost / net_revenue (per week, from manual-kpis).
    Per-week and per-day blocks include only checks whose date parses (canon).
    The totals block counts every well-formed (date, check_id) — including the
    deliberately malformed-DATE row — so it reconciles with an independent
    guest-cover recount.
    """
    kpis = bc.load_json_file(WORLD / "manual-kpis.json", "manual KPIs")

    week_keys = sorted(kpis)
    weeks = {
        wk: {"covers": 0, "ext_covers": 0, "net_revenue": 0.0}
        for wk in week_keys
    }
    days = defaultdict(lambda: {"covers": 0, "net_revenue": 0.0})

    # First pass: resolve each well-formed check's guest count and guest_type.
    # A check is well-formed iff at least one of its rows is dashboard-VALID,
    # i.e. has BOTH a numeric covers AND a numeric net (the dashboard validates
    # cubigo rows against NUMERIC_FIELDS = ["covers", "net"] and drops a row if
    # EITHER is non-numeric). The first such row's covers (constant within a
    # check) is its guest count. Checks with no dashboard-valid row are dropped.
    #
    # totals.covers = SUM of guest counts over all well-formed checks, regardless
    # of date validity, so it matches an independent guest-cover recount.
    #
    # Why totals.covers != sum(per-week covers). The canon carries three
    # deliberate BAD rows:
    #   - BAD-001 (date 2026-13-01, covers=2, net=14.50): the date does NOT
    #     parse, so this check is excluded from every per-week/per-day block, but
    #     its covers AND net are both numeric, so it IS dashboard-valid and is
    #     still counted in totals. It is the ONLY date-invalid (yet
    #     dashboard-valid) check, hence the exact identity
    #         totals.covers == sum(week covers) + (BAD-001 guest count = 2).
    #   - BAD-002 (date 2026-05-06, covers=2, EMPTY net): the date parses and
    #     covers is numeric, BUT net is empty, so the dashboard DROPS the row —
    #     the check has no dashboard-valid row and is excluded from covers
    #     everywhere (totals, week, day). The empty net contributes 0 to
    #     net_revenue (net summing is independent of covers), so net is unchanged.
    #   - BAD-003 (date 2026-05-20, covers="two", net=14.50): covers is
    #     NON-numeric, so the row is dropped and the check is excluded from
    #     covers everywhere — mirroring the dashboard. Its valid net is still
    #     summed into net_revenue (net summing is independent of covers).
    check_covers = {}  # (date, check_id) -> int guest count (first valid row seen)
    check_gtype = {}   # (date, check_id) -> guest_type (first non-empty seen)
    for r in rows:
        check_id = r.get("check_id")
        if not check_id:
            continue
        key = (r.get("date", ""), check_id)
        gtype = (r.get("guest_type") or "").strip()
        if gtype and key not in check_gtype:
            check_gtype[key] = gtype
        if key not in check_covers:
            # dashboard rule: a row counts only if BOTH covers and net parse.
            try:
                covers_val = int(float(r["covers"]))
                float(r["net"])
            except (TypeError, ValueError, KeyError):
                continue  # leave unresolved; a later valid row may resolve it
            check_covers[key] = covers_val

    total_net = 0.0

    # net sum (totals): every row with a valid float net (covers-independent)
    for r in rows:
        try:
            total_net += float(r["net"])
        except (TypeError, ValueError, KeyError):
            continue

    total_covers = 0
    total_ext = 0
    for key, covers in check_covers.items():
        total_covers += covers
        if check_gtype.get(key) == "external":
            total_ext += covers

    # per-day / per-week net needs a parseable date (skip invalid-float nets)
    for r in rows:
        try:
            d = bc.parse_date(r.get("date", ""))
        except bc.BenjaminsError:
            continue
        wk = bc.week_ending(d).isoformat()
        # Data-drift guard: a parseable trading day whose week-ending has no
        # manual-KPIs entry means the canon has drifted out from under us.
        # Fail loudly rather than silently counting it in days but not weeks.
        # (Never triggers on the current canon.)
        if wk not in weeks:
            raise bc.BenjaminsError(f"week {wk} has no manual-KPIs entry")
        try:
            net = float(r["net"])
        except (TypeError, ValueError, KeyError):
            net = None
        if net is not None:
            weeks[wk]["net_revenue"] += net
            days[d.isoformat()]["net_revenue"] += net
        else:
            # ensure the day key exists even if its only row has an empty net
            days[d.isoformat()]

    # per-week / per-day guest-covers: one entry per well-formed check whose
    # date parses, contributing its guest count.
    for (date_s, check_id), covers in check_covers.items():
        try:
            d = bc.parse_date(date_s)
        except bc.BenjaminsError:
            continue
        wk = bc.week_ending(d).isoformat()
        weeks[wk]["covers"] += covers
        if check_gtype.get((date_s, check_id)) == "external":
            weeks[wk]["ext_covers"] += covers
        days[d.isoformat()]["covers"] += covers

    weeks_out = {}
    for wk in week_keys:
        covers = weeks[wk]["covers"]
        ext = weeks[wk]["ext_covers"]
        net_rev = round(weeks[wk]["net_revenue"], 2)
        share = round(ext / covers, 4) if covers else 0.0
        sph = round(net_rev / covers, 2) if covers else 0.0
        labour_cost = float(kpis[wk].get("labour_cost", 0.0))
        labour_pct = round(labour_cost / net_rev, 4) if net_rev else 0.0
        weeks_out[wk] = {
            "covers": covers,
            "net_revenue": net_rev,
            "external_covers": ext,
            "external_share": share,
            "spend_per_head": sph,
            "labour_pct": labour_pct,
        }

    days_out = {}
    for day in sorted(days):
        days_out[day] = {
            "covers": days[day]["covers"],
            "net_revenue": round(days[day]["net_revenue"], 2),
        }

    # Derive the window from the data, not hardcoded strings:
    #   start = earliest parseable trading day (ISO);
    #   end   = latest week-ending key in manual-kpis (a Sunday) — this is the
    #           last WEEK-ENDING, not the last trading day (the final trading
    #           day falls earlier in that closing week).
    window_start = min(days_out) if days_out else None
    window_end = week_keys[-1] if week_keys else None

    return {
        "window": {"start": window_start, "end": window_end},
        "weeks": weeks_out,
        "totals": {
            "covers": total_covers,
            "net_revenue": round(total_net, 2),
            "external_share": round(total_ext / total_covers, 4) if total_covers else 0.0,
        },
        "days": days_out,
    }


def main():
    WORLD.mkdir(parents=True, exist_ok=True)

    # (a) copy the five canonical files verbatim
    for name in CANON_FILES:
        shutil.copyfile(DASH / name, WORLD / name)

    rng = random.Random(SEED)

    rows, item_set, modal_price, category_of = read_cubigo()
    days = trading_days(rows)
    kpis = bc.load_json_file(WORLD / "manual-kpis.json", "manual KPIs")

    # (b) generate new inputs that reconcile to canon
    write_apicbase(rng, item_set, modal_price, category_of)
    write_waste(rng, days, item_set)
    write_specials(rng, days)
    write_training(rng, days)
    write_reviews(rng, kpis)

    # (c) compute the declared source-of-truth manifest
    metrics = compute_metrics(rows)
    (WORLD / "expected-metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"world assembled in {WORLD}")
    print(f"  items costed: {len(item_set)}  trading days: {len(days)}")
    print(f"  total covers: {metrics['totals']['covers']}  "
          f"net revenue: {metrics['totals']['net_revenue']}")


if __name__ == "__main__":
    main()
