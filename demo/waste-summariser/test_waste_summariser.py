import csv
import json
import tempfile
import unittest
from pathlib import Path

import benjamins_common as bc
import build_waste_summariser as ws

CFG = json.loads(Path("config.json").read_text())
WASTE = "sample-data/waste-log.csv"
APICBASE = "sample-data/apicbase-costings.csv"


def independent_total_cost(waste_path, apicbase_path):
    """Recompute total cost of waste straight from the raw join: read both CSVs
    separately, join waste rows to unit_cost by item, sum qty*unit_cost. Rows
    with a non-numeric qty are skipped (the tool skips+counts them)."""
    costs = {}
    with open(apicbase_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            costs[r["item"]] = float(r["unit_cost"])
    total = 0.0
    with open(waste_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                qty = float(r["qty"])
            except (ValueError, TypeError):
                continue  # malformed qty row is skipped, not costed
            total += qty * costs[r["item"]]
    return total


class TestWasteSummariser(unittest.TestCase):
    def setUp(self):
        self.m = ws.compute(WASTE, APICBASE)

    def test_total_matches_independent_recompute(self):
        exp = independent_total_cost(WASTE, APICBASE)
        self.assertAlmostEqual(self.m["total_cost_of_waste"], exp, places=2)

    def test_cost_by_week_sums_to_total(self):
        week_sum = round(sum(c for _, c in self.m["cost_by_week"]), 2)
        self.assertAlmostEqual(week_sum, self.m["total_cost_of_waste"], places=2)

    def test_top_items_sum_to_total(self):
        # every wasted item appears in the top-items list (no truncation here);
        # their costs must also sum to the total.
        item_sum = round(sum(it["cost"] for it in self.m["top_items"]), 2)
        self.assertAlmostEqual(item_sum, self.m["total_cost_of_waste"], places=2)

    def test_top_items_sorted_desc_tie_stable(self):
        items = self.m["top_items"]
        keys = [(-it["cost"], it["item"]) for it in items]
        self.assertEqual(keys, sorted(keys),
                         "top_items must be cost desc, then item name asc (tie-stable)")

    def test_weeks_sorted(self):
        labels = [w for w, _ in self.m["cost_by_week"]]
        self.assertEqual(labels, sorted(labels), "weeks must be in chronological order")

    def test_referential_integrity_raises(self):
        # a waste item absent from apicbase -> BenjaminsError (data-quality abort)
        with tempfile.TemporaryDirectory() as d:
            waste = Path(d) / "waste.csv"
            api = Path(d) / "apicbase.csv"
            waste.write_text(
                "date,item,qty,reason\n"
                "2026-04-14,Widget,2,expired\n",
                encoding="utf-8",
            )
            api.write_text(
                "item,category,unit_cost,allergens\n"
                "Gadget,Main,3.00,\n",  # Widget intentionally missing
                encoding="utf-8",
            )
            with self.assertRaises(bc.BenjaminsError):
                ws.compute(str(waste), str(api))

    def test_non_numeric_qty_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            waste = Path(d) / "waste.csv"
            api = Path(d) / "apicbase.csv"
            waste.write_text(
                "date,item,qty,reason\n"
                "2026-04-14,Widget,2,expired\n"
                "2026-04-15,Widget,oops,expired\n",  # non-numeric qty -> skipped
                encoding="utf-8",
            )
            api.write_text(
                "item,category,unit_cost,allergens\n"
                "Widget,Main,3.00,\n",
                encoding="utf-8",
            )
            m = ws.compute(str(waste), str(api))
            self.assertAlmostEqual(m["total_cost_of_waste"], 6.00, places=2)
            self.assertEqual(len(m["skipped"]), 1)

    def test_negative_qty_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            waste = Path(d) / "waste.csv"
            api = Path(d) / "apicbase.csv"
            waste.write_text(
                "date,item,qty,reason\n"
                "2026-04-14,Widget,2,expired\n"
                "2026-04-15,Widget,-1,expired\n",  # negative qty -> skipped
                encoding="utf-8",
            )
            api.write_text(
                "item,category,unit_cost,allergens\n"
                "Widget,Main,3.00,\n",
                encoding="utf-8",
            )
            m = ws.compute(str(waste), str(api))
            self.assertFalse(
                m["total_cost_of_waste"] < 0,
                "negative-qty row must not drag total below zero",
            )
            self.assertAlmostEqual(m["total_cost_of_waste"], 6.00, places=2,
                                   msg="only the valid row (2 * 3.00) should be costed")
            self.assertGreaterEqual(len(m["skipped"]), 1,
                                    "negative-qty row must appear in skipped")

    def test_committed_html_matches_renderer(self):
        fresh = ws.render(ws.compute(WASTE, APICBASE))
        self.assertEqual(
            fresh,
            Path("waste-summariser.html").read_text(),
            "Committed HTML drifted - re-run build_waste_summariser.py",
        )


if __name__ == "__main__":
    unittest.main()
