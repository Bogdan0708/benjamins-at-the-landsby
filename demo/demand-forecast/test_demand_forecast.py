import csv
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

import benjamins_common as bc
import build_demand_forecast as fc

CFG = json.loads(Path("config.json").read_text())
CUBIGO = "sample-data/cubigo-sales.csv"
BOOKINGS = "sample-data/opentable-bookings.csv"
DAYPARTS = ["Lunch", "Afternoon", "Evening"]


def independent_covers_by_date_daypart(cubigo_path):
    """Recompute historical GUEST-covers per (date, daypart) straight from the CSV.

    A cover is a GUEST: each unique (date, check_id) contributes its guest count
    int(float(covers)) (first value seen for the check); the check's daypart
    comes from its time. Rows whose date is unparseable, whose time is malformed,
    or whose covers is non-numeric are dropped (skipped exactly as the tool
    does)."""
    # map (date, check_id) -> (time, guest_covers) from the first row seen
    check_info = {}
    for path in [cubigo_path]:
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (r["date"], r["check_id"])
                if key in check_info:
                    continue
                try:
                    cv = int(float(r["covers"]))
                except (ValueError, TypeError):
                    continue
                check_info[key] = (r["time"], cv)
    covers = {}
    for (d, _cid), (t, cv) in check_info.items():
        try:
            day = bc.parse_date(d)
        except bc.BenjaminsError:
            continue
        try:
            band = bc.daypart(t)
        except bc.BenjaminsError:
            continue
        covers[(day, band)] = covers.get((day, band), 0) + cv
    return covers


class TestDemandForecast(unittest.TestCase):
    def setUp(self):
        self.m = fc.compute(CUBIGO, BOOKINGS, CFG)

    def test_config_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(CFG["weights"]), 1.0, places=9)

    def test_effective_weights_for_full_cell_sum_to_one(self):
        # every full (3-point) cell uses weights that renormalise to 1.0
        self.assertAlmostEqual(sum(self.m["weights"]), 1.0, places=9)

    def test_target_week_is_seven_days_after_last_history(self):
        covers = independent_covers_by_date_daypart(CUBIGO)
        last = max(d for (d, _b) in covers)
        expected = [(last + timedelta(days=i)).isoformat() for i in range(1, 8)]
        got = sorted({rec["target_date"] for rec in self.m["forecast"]})
        self.assertEqual(got, expected)

    def test_independent_recompute_one_cell(self):
        """Pick one (weekday, daypart) with >=3 historical occurrences and
        independently reproduce the weighted moving average."""
        covers = independent_covers_by_date_daypart(CUBIGO)
        weights = CFG["weights"]

        # find a (weekday, daypart) cell with at least 3 historical dates
        target_cell = None
        for daypart in DAYPARTS:
            for weekday in range(7):
                dates = sorted(
                    [d for (d, b) in covers if b == daypart and d.weekday() == weekday],
                    reverse=True,
                )
                if len(dates) >= 3:
                    target_cell = (weekday, daypart, dates[:3])
                    break
            if target_cell:
                break
        self.assertIsNotNone(target_cell, "need a full 3-point cell to test")
        weekday, daypart, recent3 = target_cell

        vals = [covers[(d, daypart)] for d in recent3]  # most-recent first
        expected = sum(w * v for w, v in zip(weights, vals))

        # the tool's forecast for the target-week date that is this weekday/daypart
        match = [r for r in self.m["forecast"]
                 if r["weekday"] == weekday and r["daypart"] == daypart]
        self.assertTrue(match, "weekday/daypart not present in target week")
        self.assertAlmostEqual(match[0]["base_covers"], expected, places=6)
        # with no event adjustment this cell's forecast equals its base
        self.assertAlmostEqual(match[0]["forecast_covers"], expected, places=6)

    def test_partial_cell_renormalises(self):
        # build a tiny dataset where one weekday/daypart has only 2 occurrences
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cub = Path(d) / "cubigo.csv"
            bk = Path(d) / "bookings.csv"
            # two Mondays at lunch: 2026-06-01 (10 covers) and 2026-05-25 (20 covers)
            lines = ["date,time,check_id,item,category,covers,net,guest_type"]
            for i in range(10):
                lines.append(f"2026-06-01,12:00,A{i},X,Main,1,10.00,resident")
            for i in range(20):
                lines.append(f"2026-05-25,12:00,B{i},X,Main,1,10.00,resident")
            cub.write_text("\n".join(lines) + "\n", encoding="utf-8")
            bk.write_text("date,time,party_size,status,source\n", encoding="utf-8")
            res = fc.compute(str(cub), str(bk), CFG)
            # last history = 2026-06-01 (Mon) -> target week Tue..Mon; the Monday is 2026-06-08
            mon_lunch = [r for r in res["forecast"]
                         if r["weekday"] == 0 and r["daypart"] == "Lunch"]
            self.assertTrue(mon_lunch)
            # 2 points, weights renormalised: 0.5/0.8 * 10 + 0.3/0.8 * 20
            w = CFG["weights"][:2]
            tot = sum(w)
            expected = (w[0] / tot) * 10 + (w[1] / tot) * 20
            self.assertAlmostEqual(mon_lunch[0]["base_covers"], expected, places=6)

    def test_event_override_doubles_and_flags(self):
        covers = independent_covers_by_date_daypart(CUBIGO)
        last = max(d for (d, _b) in covers)
        target = (last + timedelta(days=1)).isoformat()  # first target-week date
        cfg = dict(CFG)
        cfg["event_adjustments"] = [{"date": target, "multiplier": 2.0}]

        base = fc.compute(CUBIGO, BOOKINGS, CFG)
        adj = fc.compute(CUBIGO, BOOKINGS, cfg)

        base_by = {(r["target_date"], r["daypart"]): r for r in base["forecast"]}
        for r in adj["forecast"]:
            if r["target_date"] == target:
                self.assertTrue(r["event_flag"])
                b = base_by[(r["target_date"], r["daypart"])]
                self.assertAlmostEqual(r["forecast_covers"],
                                       b["forecast_covers"] * 2.0, places=6)
            else:
                self.assertFalse(r["event_flag"])

    def test_committed_html_matches_renderer(self):
        fresh = fc.render(fc.compute(CUBIGO, BOOKINGS, CFG))
        self.assertEqual(
            fresh,
            Path("demand-forecast.html").read_text(),
            "Committed HTML drifted - re-run build_demand_forecast.py",
        )


if __name__ == "__main__":
    unittest.main()
