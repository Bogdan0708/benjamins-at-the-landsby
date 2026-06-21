import unittest, csv
from datetime import date, timedelta
from pathlib import Path
import build_daily_sales_flash as flash
import json

CFG = json.loads(Path("config.json").read_text())
REPORT = date.fromisoformat(CFG["report_date"])
PRIOR = REPORT - timedelta(days=7)


def independent_day_totals(path, day):
    # A cover is a GUEST: sum one int(float(covers)) per (date, check_id),
    # taking the first numeric covers per check. Rows that the tool skips
    # (missing check_id, non-numeric net, or non-numeric covers) contribute
    # nothing — including their net — so the recount stays aligned with the tool.
    check_covers, net = {}, 0.0
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["date"] != day.isoformat():
                continue
            if not r["check_id"]:
                continue
            try:
                cv = int(float(r["covers"]))
                n = float(r["net"])
            except (ValueError, TypeError):
                continue
            key = (r["date"], r["check_id"])
            check_covers.setdefault(key, cv)
            net += n
    return sum(check_covers.values()), round(net, 2)


class TestFlash(unittest.TestCase):
    def setUp(self):
        self.m = flash.compute("sample-data/cubigo-sales.csv", REPORT)

    def test_covers_match_independent_recount(self):
        c, n = independent_day_totals("sample-data/cubigo-sales.csv", REPORT)
        self.assertEqual(self.m["today"]["covers"], c)
        self.assertEqual(self.m["today"]["net"], n)

    def test_compares_same_weekday_last_week(self):
        self.assertEqual(self.m["prior"]["date"], PRIOR.isoformat())

    def test_top_and_bottom_sellers_present(self):
        self.assertTrue(self.m["top_sellers"])
        self.assertTrue(self.m["bottom_sellers"])

    def test_ranking_order(self):
        top = self.m["top_sellers"]
        if len(top) >= 2:
            nets = [v for _, v in top]
            self.assertTrue(all(a >= b for a, b in zip(nets, nets[1:])),
                            "top_sellers must be ordered best-first (non-increasing net)")
        bottom = self.m["bottom_sellers"]
        if len(bottom) >= 2:
            nets = [v for _, v in bottom]
            self.assertTrue(all(a <= b for a, b in zip(nets, nets[1:])),
                            "bottom_sellers must be ordered worst-first (non-decreasing net)")

    def test_committed_html_matches_renderer(self):
        from pathlib import Path
        fresh = flash.render(flash.compute("sample-data/cubigo-sales.csv", REPORT))
        self.assertEqual(fresh, Path("daily-sales-flash.html").read_text(),
                         "Committed HTML drifted - re-run build_daily_sales_flash.py")
