"""Tests for the weekly dashboard. Run: python3 -m unittest test_dashboard -v"""
import csv
import tempfile
import unittest
from pathlib import Path

import build_dashboard as bd


def sales_row(**kw):
    row = {"date": "2026-06-01", "time": "12:30", "check_id": "C1", "item": "Soup",
           "category": "Starter", "covers": "2", "net": "8.95", "guest_type": "resident"}
    row.update(kw)
    return row


class TempDataDir:
    """Point bd.DATA_DIR at a temp dir for the duration of a test."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)

    def __enter__(self):
        self._saved = bd.DATA_DIR
        bd.DATA_DIR = self.path
        return self.path

    def __exit__(self, *exc):
        bd.DATA_DIR = self._saved
        self._tmp.cleanup()


def write_sales_csv(dirpath, fieldnames, rows):
    with (dirpath / "cubigo-sales.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


class ReadingAndValidation(unittest.TestCase):
    FIELDS = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]

    def test_missing_file_is_plain_english(self):
        with TempDataDir():
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.read_csv_rows("cubigo-sales.csv")
        msg = str(ctx.exception)
        self.assertIn("cubigo-sales.csv", msg)
        self.assertIn("Cubigo", msg)          # names the export screen
        self.assertNotIn("Traceback", msg)

    def test_unexpected_columns_reported(self):
        with TempDataDir() as d:
            write_sales_csv(d, ["date", "total"], [{"date": "2026-06-01", "total": "5"}])
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.read_csv_rows("cubigo-sales.csv")
        msg = str(ctx.exception)
        self.assertIn("export format may have changed", msg)
        self.assertIn("check_id", msg)        # lists expected columns
        self.assertIn("total", msg)           # lists found columns

    def test_malformed_rows_skipped_and_counted(self):
        rows = [sales_row(),
                sales_row(check_id="C2", date="2026-13-01"),   # impossible month
                sales_row(check_id="C3", net=""),              # missing net
                sales_row(check_id="C4", covers="two")]        # non-numeric covers
        with TempDataDir() as d:
            write_sales_csv(d, self.FIELDS, rows)
            good, skipped = bd.read_csv_rows("cubigo-sales.csv")
        self.assertEqual(len(good), 1)
        self.assertEqual(len(skipped), 3)
        self.assertTrue(all("cubigo-sales.csv line" in s for s in skipped))

    def test_truncated_row_skipped_not_crash(self):
        with TempDataDir() as d:
            (d / "cubigo-sales.csv").write_text(
                "date,time,check_id,item,category,covers,net,guest_type\n"
                "2026-06-01,12:30,C1\n", encoding="utf-8")
            good, skipped = bd.read_csv_rows("cubigo-sales.csv")
        self.assertEqual(good, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("wrong number of fields", skipped[0])

    def test_unparseable_time_skipped(self):
        with TempDataDir() as d:
            write_sales_csv(d, self.FIELDS, [sales_row(time="noon")])
            good, skipped = bd.read_csv_rows("cubigo-sales.csv")
        self.assertEqual(good, [])
        self.assertIn("unreadable time", skipped[0])

    def test_empty_file_is_plain_english(self):
        with TempDataDir() as d:
            (d / "cubigo-sales.csv").write_text("", encoding="utf-8")
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.read_csv_rows("cubigo-sales.csv")
        self.assertIn("export format may have changed", str(ctx.exception))

    def test_header_only_file_returns_no_rows(self):
        with TempDataDir() as d:
            write_sales_csv(d, self.FIELDS, [])
            good, skipped = bd.read_csv_rows("cubigo-sales.csv")
        self.assertEqual((good, skipped), ([], []))

    def test_invalid_json_is_plain_english(self):
        with TempDataDir() as d:
            p = d / "manual-kpis.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.load_json_file(p, "hand-entered weekly KPIs")
        msg = str(ctx.exception)
        self.assertIn("manual-kpis.json", msg)
        self.assertIn("not valid JSON", msg)

    def test_unreadable_csv_is_plain_english(self):
        # The path exists but cannot be read (here: it is a directory).
        with TempDataDir() as d:
            (d / "cubigo-sales.csv").mkdir()
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.read_csv_rows("cubigo-sales.csv")
        msg = str(ctx.exception)
        self.assertIn("cubigo-sales.csv", msg)
        self.assertIn("Cubigo", msg)
        self.assertNotIn("Traceback", msg)

    def test_unreadable_json_is_plain_english(self):
        with TempDataDir() as d:
            p = d / "manual-kpis.json"
            p.mkdir()
            with self.assertRaises(bd.DashboardError) as ctx:
                bd.load_json_file(p, "hand-entered weekly KPIs")
        self.assertIn("manual-kpis.json", str(ctx.exception))


class Metrics(unittest.TestCase):
    def test_covers_counted_once_per_check(self):
        # C1 has two line items but covers=2 must count once. C2 adds 3. Total 5, not 7.
        rows = [sales_row(),
                sales_row(item="Roast chicken", category="Main", net="14.50"),
                sales_row(check_id="C2", covers="3", net="12.00")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertEqual(m["covers"], 5)

    def test_revenue_and_spend_per_head(self):
        rows = [sales_row(net="10.00"), sales_row(item="Pie", net="10.00"),
                sales_row(check_id="C2", covers="3", net="30.00")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertAlmostEqual(m["revenue"], 50.00)
        self.assertAlmostEqual(m["spend_per_head"], 10.00)

    def test_same_check_id_on_different_dates_counts_separately(self):
        # Real POS check numbers can reset daily: C1 on Mon and C1 on Tue are
        # different checks (same week ending 7 June). 2 + 2 = 4, not 2.
        rows = [sales_row(), sales_row(date="2026-06-02")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertEqual(m["covers"], 4)

    def test_external_share(self):
        rows = [sales_row(covers="3"), sales_row(check_id="C2", guest_type="external", covers="1")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertAlmostEqual(m["external_share"], 0.25)

    def test_weekly_grouping_uses_latest_week(self):
        # 2026-05-25 (Mon, week ending 31 May) vs 2026-06-01 (Mon, week ending 7 Jun)
        rows = [sales_row(date="2026-05-25", check_id="OLD", covers="4", net="99.00"),
                sales_row(date="2026-06-01", check_id="NEW", covers="2", net="20.00")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertEqual(m["latest_week"].isoformat(), "2026-06-07")
        self.assertEqual(m["covers"], 2)
        self.assertEqual(len(m["revenue_trend"]), 2)

    def test_labour_pct_from_manual_kpis(self):
        rows = [sales_row(covers="2", net="100.00")]
        manual = {"2026-06-07": {"labour_cost": 35.0, "reviews": {"google": 3, "tripadvisor": 4}}}
        m = bd.compute_metrics(rows, [], [], [], manual)
        self.assertAlmostEqual(m["labour_pct"], 0.35)
        self.assertEqual(m["review_total"], 7)

    def test_missing_manual_kpis_yield_none_not_crash(self):
        m = bd.compute_metrics([sales_row()], [], [], [], {})
        self.assertIsNone(m["labour_pct"])
        self.assertIsNone(m["review_total"])

    def test_missing_open_day_detected(self):
        # Latest week = w/e 2026-06-07; only Monday 1 June has sales.
        # Tue-Sat (2-6 June) must be flagged missing; Sunday must not (closed).
        m = bd.compute_metrics([sales_row(date="2026-06-01")], [], [], [], {})
        missing = [d.isoformat() for d in m["missing_days"]]
        self.assertIn("2026-06-02", missing)
        self.assertNotIn("2026-06-07", missing)

    def test_no_show_rate(self):
        bookings = [{"date": "2026-06-01", "time": "13:00", "party_size": "2", "status": "seated", "source": "online"},
                    {"date": "2026-06-01", "time": "13:00", "party_size": "2", "status": "no-show", "source": "online"}]
        m = bd.compute_metrics([sales_row()], bookings, [], [], {})
        self.assertAlmostEqual(m["no_show_rate"], 0.5)
        self.assertEqual(m["bookings"], 2)

    def test_empty_sales_is_plain_english_error(self):
        with self.assertRaises(bd.DashboardError):
            bd.compute_metrics([], [], [], [], {})

    def test_daypart_boundaries(self):
        self.assertEqual(bd.daypart("14:59"), "Lunch")
        self.assertEqual(bd.daypart("15:00"), "Afternoon")
        self.assertEqual(bd.daypart("17:29"), "Afternoon")
        self.assertEqual(bd.daypart("17:30"), "Evening")

    def test_daypart_covers_aggregation(self):
        rows = [sales_row(time="12:15", covers="2"),
                sales_row(check_id="C2", time="18:00", covers="3")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertEqual(m["daypart_covers"], {"Lunch": 2, "Evening": 3})

    def test_settlement_zero_distinct_from_absent(self):
        settle = [{"date": "2026-06-01", "gross": "0.00", "fees": "0.00", "net": "0.00"}]
        m = bd.compute_metrics([sales_row()], [], settle, [], {})
        self.assertEqual(m["settlement_net"], 0.0)
        m2 = bd.compute_metrics([sales_row()], [], [], [], {})
        self.assertIsNone(m2["settlement_net"])

    def test_guest_type_case_insensitive(self):
        rows = [sales_row(covers="3"), sales_row(check_id="C2", guest_type=" External ", covers="1")]
        m = bd.compute_metrics(rows, [], [], [], {})
        self.assertAlmostEqual(m["external_share"], 0.25)

    def test_non_numeric_manual_kpi_is_plain_english(self):
        manual = {"2026-06-07": {"labour_cost": "about 2700"}}
        with self.assertRaises(bd.DashboardError):
            bd.compute_metrics([sales_row()], [], [], [], manual)

    def test_week_ending_boundaries(self):
        from datetime import date
        self.assertEqual(bd.week_ending(date(2026, 6, 1)), date(2026, 6, 7))   # Monday
        self.assertEqual(bd.week_ending(date(2026, 6, 6)), date(2026, 6, 7))   # Saturday
        self.assertEqual(bd.week_ending(date(2026, 6, 7)), date(2026, 6, 7))   # Sunday maps to itself


class Rendering(unittest.TestCase):
    CONFIG = {"site_name": "Benjamin's at The Landsby", "currency": "£",
              "targets": {"external_share_cap": 0.25}}

    def _metrics(self):
        rows = [sales_row(covers="2", net="48.00")]
        return bd.compute_metrics(rows, [], [], [], {})

    def test_page_has_watermark_and_site_name(self):
        page = bd.render_html(self._metrics(), self.CONFIG, [])
        # Exact watermark text from the spec, em dash included.
        self.assertIn("SAMPLE DATA — synthetic, for demonstration", page)
        self.assertIn("Benjamin&#x27;s at The Landsby", page)

    def test_not_yet_tracked_indicators_shown(self):
        page = bd.render_html(self._metrics(), self.CONFIG, [])
        self.assertIn("not yet tracked", page.lower())
        self.assertIn("Resident dining frequency", page)

    def test_footer_discloses_skipped_rows_and_missing_days(self):
        page = bd.render_html(self._metrics(), self.CONFIG,
                              ["cubigo-sales.csv line 7: unreadable date '2026-13-01'"])
        self.assertIn("1 row(s) skipped", page)
        self.assertIn("2026-13-01", page)
        self.assertIn("no sales data", page.lower())   # missing-days note (Tue-Sat absent)

    def test_unavailable_figures_show_dash_not_zero(self):
        page = bd.render_html(self._metrics(), self.CONFIG, [])
        self.assertIn("—", page)                       # labour % has no manual entry

    def test_bar_chart_svg(self):
        svg = bd.bar_chart([("Lunch", 30), ("Evening", 10)])
        self.assertIn("<svg", svg)
        self.assertEqual(svg.count("<rect"), 2)
        self.assertIn("Lunch", svg)

    def test_bar_chart_value_labels_inside_viewbox(self):
        import re
        svg = bd.bar_chart([("Lunch", 100), ("Evening", 10)])
        y0 = float(re.search(r'viewBox="0 (-?\d+)', svg).group(1))
        text_ys = [float(y) for y in re.findall(r'<text[^>]* y="(-?\d+(?:\.\d+)?)"', svg)]
        self.assertTrue(text_ys, "no text labels found")
        self.assertTrue(all(y >= y0 for y in text_ys),
                        f"label clipped: min y {min(text_ys)} < viewBox top {y0}")


class SampleDataIntegration(unittest.TestCase):
    """Independent recomputation from the raw CSVs - a separate code path from
    compute_metrics - asserting the dashboard's headline figures match."""

    @classmethod
    def setUpClass(cls):
        cls.sales, cls.skipped = bd.read_csv_rows("cubigo-sales.csv")
        cls.metrics = bd.compute_metrics(
            cls.sales,
            bd.read_csv_rows("opentable-bookings.csv")[0],
            bd.read_csv_rows("square-settlements.csv")[0],
            bd.read_csv_rows("flash-survey.csv")[0],
            bd.load_json_file(bd.DATA_DIR / "manual-kpis.json", "manual KPIs"),
        )

    @staticmethod
    def independent_recount():
        covers_by_check, week_of_check = {}, {}
        revenue = {}
        with (bd.DATA_DIR / "cubigo-sales.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    d = bd.parse_date(row["date"])
                    net = float(row["net"])
                    cov = int(float(row["covers"]))
                except (ValueError, TypeError, KeyError):
                    continue
                wk = bd.week_ending(d)
                revenue[wk] = revenue.get(wk, 0.0) + net
                key = (row["date"], row["check_id"])   # check numbers may reset daily
                covers_by_check.setdefault(key, cov)
                week_of_check.setdefault(key, wk)
        latest = max(revenue)
        covers = sum(c for cid, c in covers_by_check.items() if week_of_check[cid] == latest)
        return latest, covers, revenue[latest]

    def test_headline_totals_match_independent_recount(self):
        latest, covers, revenue = self.independent_recount()
        self.assertEqual(self.metrics["latest_week"], latest)
        self.assertEqual(self.metrics["covers"], covers)
        self.assertAlmostEqual(self.metrics["revenue"], revenue, places=2)

    def test_sample_data_has_expected_imperfections(self):
        self.assertEqual(len(self.skipped), 3)
        missing = [d.isoformat() for d in self.metrics["missing_days"]]
        self.assertEqual(missing, ["2026-06-02"])

    def test_volumes_consistent_with_plan_assumptions(self):
        # Plan planning assumptions: ~300-400 weekly covers, ~GBP 20-24 spend/head.
        # Latest week is missing one trading day, so allow the lower bound to dip.
        self.assertGreaterEqual(self.metrics["covers"], 240)
        self.assertLessEqual(self.metrics["covers"], 400)
        self.assertGreaterEqual(self.metrics["spend_per_head"], 20.0)
        self.assertLessEqual(self.metrics["spend_per_head"], 25.0)
        self.assertLess(self.metrics["external_share"], 0.10)   # "low single digits"

    def test_full_page_builds_from_sample_data(self):
        config = bd.load_json_file(bd.BASE / "config.json", "site configuration")
        page = bd.render_html(self.metrics, config, self.skipped)
        self.assertIn("SAMPLE DATA — synthetic, for demonstration", page)
        self.assertIn("3 row(s) skipped", page)
        self.assertIn("Tuesday 2 June", page)

    def test_committed_dashboard_matches_renderer(self):
        config = bd.load_json_file(bd.BASE / "config.json", "site configuration")
        page = bd.render_html(self.metrics, config, self.skipped)
        committed = (bd.BASE / "dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(page, committed)


if __name__ == "__main__":
    unittest.main()
