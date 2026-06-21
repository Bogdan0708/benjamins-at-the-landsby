import csv
import json
import tempfile
import unittest
from pathlib import Path

import benjamins_common as bc
import build_menu_engineering as me

CFG = json.loads(Path("config.json").read_text())
CUBIGO = "sample-data/cubigo-sales.csv"
APICBASE = "sample-data/apicbase-costings.csv"
QUADRANTS = {"Star", "Plowhorse", "Puzzle", "Dog"}


def independent_item_stats(cubigo_path, apicbase_path, target):
    """Recompute one item's stats straight from the raw CSVs."""
    units, revenue = 0, 0.0
    with open(cubigo_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["item"] != target:
                continue
            try:
                net = float(r["net"])
            except (ValueError, TypeError):
                continue  # malformed net row is skipped, not counted as a unit
            units += 1
            revenue += net
    unit_cost = None
    with open(apicbase_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["item"] == target:
                unit_cost = float(r["unit_cost"])
    unit_price = revenue / units
    margin = unit_price - unit_cost
    return {
        "units": units,
        "revenue": round(revenue, 2),
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "margin": margin,
        "margin_pct": margin / unit_price,
    }


class TestMenuEngineering(unittest.TestCase):
    def setUp(self):
        self.m = me.compute(CUBIGO, APICBASE)
        self.by_item = {r["item"]: r for r in self.m["items"]}

    def test_independent_recompute_one_item(self):
        target = "Fish pie"
        exp = independent_item_stats(CUBIGO, APICBASE, target)
        got = self.by_item[target]
        self.assertEqual(got["units"], exp["units"])
        self.assertAlmostEqual(got["revenue"], exp["revenue"], places=2)
        self.assertAlmostEqual(got["unit_price"], exp["unit_price"], places=6)
        self.assertAlmostEqual(got["unit_cost"], exp["unit_cost"], places=6)
        self.assertAlmostEqual(got["margin"], exp["margin"], places=6)
        self.assertAlmostEqual(got["margin_pct"], exp["margin_pct"], places=6)

    def test_every_item_classified_into_one_quadrant(self):
        distinct = set()
        with open(CUBIGO, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                try:
                    float(r["net"])
                except (ValueError, TypeError):
                    continue
                distinct.add(r["item"])
        classified = {r["item"] for r in self.m["items"]}
        self.assertEqual(classified, distinct)
        for r in self.m["items"]:
            self.assertIn(r["quadrant"], QUADRANTS)

    def test_quadrant_rule_matches_medians(self):
        mu, mm = self.m["median_units"], self.m["median_margin"]
        for r in self.m["items"]:
            hi_u = r["units"] >= mu
            hi_m = r["margin"] >= mm
            expected = {
                (True, True): "Star",
                (True, False): "Plowhorse",
                (False, True): "Puzzle",
                (False, False): "Dog",
            }[(hi_u, hi_m)]
            self.assertEqual(r["quadrant"], expected)

    def test_referential_integrity_raises(self):
        # apicbase missing an item that cubigo sells -> BenjaminsError
        with tempfile.TemporaryDirectory() as d:
            cub = Path(d) / "cubigo.csv"
            api = Path(d) / "apicbase.csv"
            cub.write_text(
                "date,time,check_id,item,category,covers,net,guest_type\n"
                "2026-04-13,13:00,C1,Widget,Main,1,10.00,resident\n"
                "2026-04-13,13:05,C2,Gadget,Main,1,12.00,resident\n",
                encoding="utf-8",
            )
            api.write_text(
                "item,category,unit_cost,allergens\n"
                "Widget,Main,3.00,\n",  # Gadget intentionally missing
                encoding="utf-8",
            )
            with self.assertRaises(bc.BenjaminsError):
                me.compute(str(cub), str(api))

    def test_zero_price_item_no_crash(self):
        # An item whose every net row is 0.00 produces unit_price=0 -> margin_pct must be None
        with tempfile.TemporaryDirectory() as d:
            cub = Path(d) / "cubigo.csv"
            api = Path(d) / "apicbase.csv"
            cub.write_text(
                "date,time,check_id,item,category,covers,net,guest_type\n"
                "2026-04-13,13:00,C1,ZeroItem,Main,1,0.00,resident\n"
                "2026-04-13,13:05,C2,ZeroItem,Main,1,0.00,resident\n"
                "2026-04-13,13:10,C3,NormalItem,Main,1,12.00,resident\n",
                encoding="utf-8",
            )
            api.write_text(
                "item,category,unit_cost,allergens\n"
                "ZeroItem,Main,0.00,\n"
                "NormalItem,Main,4.00,\n",
                encoding="utf-8",
            )
            result = me.compute(str(cub), str(api))  # must not raise
            by_item = {r["item"]: r for r in result["items"]}
            self.assertIsNone(by_item["ZeroItem"]["margin_pct"])
            self.assertIsNotNone(by_item["NormalItem"]["margin_pct"])

    def test_committed_html_matches_renderer(self):
        fresh = me.render(me.compute(CUBIGO, APICBASE))
        self.assertEqual(
            fresh,
            Path("menu-engineering.html").read_text(),
            "Committed HTML drifted - re-run build_menu_engineering.py",
        )


if __name__ == "__main__":
    unittest.main()
