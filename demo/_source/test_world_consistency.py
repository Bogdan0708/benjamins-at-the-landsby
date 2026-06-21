import csv
import json
import unittest
from pathlib import Path

SRC = Path(__file__).parent
DEMO = SRC.parent
CANON_COMMON = (SRC / "benjamins_common.py").read_bytes()

TOOL_FOLDERS = [
    "daily-sales-flash", "cubigo-square-recon", "menu-engineering",
    "demand-forecast", "allergen-matrix", "daily-briefing",
    "pilot-gate-tracker", "waste-summariser", "feedback-theming",
    "review-response-drafts", "menu-copy-drafts", "resident-newsletter",
]


class TestVendoredCommonIdentical(unittest.TestCase):
    def test_each_vendored_copy_is_byte_identical(self):
        for folder in TOOL_FOLDERS:
            p = DEMO / folder / "benjamins_common.py"
            if p.exists():  # tool may not be built yet
                self.assertEqual(p.read_bytes(), CANON_COMMON,
                                 f"{folder}/benjamins_common.py drifted from _source")


class TestDailySalesFlashReconciles(unittest.TestCase):
    """The daily-sales-flash tool's sample CSV must reconcile, for its
    report_date, with the world manifest's authoritative cover count.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_covers_match_manifest(self):
        tool = DEMO / "daily-sales-flash"
        csv_path = tool / "sample-data" / "cubigo-sales.csv"
        config_path = tool / "config.json"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (csv_path.exists() and config_path.exists() and manifest_path.exists()):
            self.skipTest("daily-sales-flash tool not built yet")

        report_date = json.loads(config_path.read_text())["report_date"]
        manifest = json.loads(manifest_path.read_text())
        expected = manifest["days"][report_date]["covers"]

        # A cover is a GUEST: sum one int(float(covers)) per (date, check_id),
        # taking the first numeric covers per check (a check whose covers is
        # never numeric is malformed and excluded, mirroring the tool).
        check_covers = {}
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("date") != report_date:
                    continue
                if not r.get("check_id"):
                    continue
                key = (r["date"], r["check_id"])
                if key in check_covers:
                    continue
                try:
                    check_covers[key] = int(float(r["covers"]))
                except (ValueError, TypeError):
                    pass
        guest_covers = sum(check_covers.values())
        self.assertEqual(guest_covers, expected,
                         f"daily-sales-flash covers for {report_date} "
                         f"({guest_covers}) disagree with manifest ({expected})")


class TestCubigoSquareReconReconciles(unittest.TestCase):
    """The cubigo-square-recon tool's sample cubigo export must agree with the
    world manifest: till_net for a trading day (sum of cubigo net) equals the
    manifest's per-day net_revenue, since both are the same sum.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_till_net_matches_manifest_net_revenue(self):
        tool = DEMO / "cubigo-square-recon"
        csv_path = tool / "sample-data" / "cubigo-sales.csv"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (csv_path.exists() and manifest_path.exists()):
            self.skipTest("cubigo-square-recon tool not built yet")

        day = "2026-06-01"  # a normal trading day present in both sources
        manifest = json.loads(manifest_path.read_text())
        expected = manifest["days"][day]["net_revenue"]

        till_net = 0.0
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("date") != day:
                    continue
                try:
                    till_net += float(r["net"])
                except (ValueError, TypeError):
                    pass
        self.assertEqual(round(till_net, 2), expected,
                         f"cubigo-square-recon till_net for {day} "
                         f"({round(till_net, 2)}) disagrees with manifest ({expected})")


class TestMenuEngineeringReconciles(unittest.TestCase):
    """The menu-engineering tool sums every line-item's net into per-item
    revenue. The SUM of all per-item revenue must therefore equal the world
    manifest's totals.net_revenue (the sum of every valid-float cubigo net;
    the one malformed empty-net row contributes 0).

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_item_revenue_sum_matches_manifest_total(self):
        tool = DEMO / "menu-engineering"
        cubigo_path = tool / "sample-data" / "cubigo-sales.csv"
        apicbase_path = tool / "sample-data" / "apicbase-costings.csv"
        build = tool / "build_menu_engineering.py"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (cubigo_path.exists() and apicbase_path.exists()
                and build.exists() and manifest_path.exists()):
            self.skipTest("menu-engineering tool not built yet")

        import importlib.util
        spec = importlib.util.spec_from_file_location("build_menu_engineering", build)
        mod = importlib.util.module_from_spec(spec)
        import sys
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            metrics = mod.compute(str(cubigo_path), str(apicbase_path))
        finally:
            sys.path.remove(str(tool))

        rev_sum = round(sum(r["revenue"] for r in metrics["items"]), 2)
        expected = json.loads(manifest_path.read_text())["totals"]["net_revenue"]
        self.assertAlmostEqual(rev_sum, expected, delta=0.05,
                               msg=f"menu-engineering item-revenue sum ({rev_sum}) "
                                   f"disagrees with manifest net_revenue ({expected})")


class TestDemandForecastReconciles(unittest.TestCase):
    """The demand-forecast tool's historical base is the sum of covers per
    (date, daypart) over parseable dates. That total must tie to the world
    manifest's authoritative per-week cover count (the sum of
    weeks[*]['covers']): the forecast's input base is the same canon trading
    history. Checks with a malformed time would be skipped, but the canon has
    clean times, so the totals match the manifest weeks-covers sum exactly.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_history_covers_match_manifest_weeks_sum(self):
        tool = DEMO / "demand-forecast"
        cubigo_path = tool / "sample-data" / "cubigo-sales.csv"
        bookings_path = tool / "sample-data" / "opentable-bookings.csv"
        build = tool / "build_demand_forecast.py"
        config_path = tool / "config.json"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (cubigo_path.exists() and bookings_path.exists()
                and build.exists() and config_path.exists()
                and manifest_path.exists()):
            self.skipTest("demand-forecast tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("build_demand_forecast", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            config = json.loads(config_path.read_text())
            metrics = mod.compute(str(cubigo_path), str(bookings_path), config)
        finally:
            sys.path.remove(str(tool))

        history_covers = metrics["totals"]["history_covers"]
        manifest = json.loads(manifest_path.read_text())
        weeks_sum = sum(w["covers"] for w in manifest["weeks"].values())
        self.assertEqual(history_covers, weeks_sum,
                         f"demand-forecast history covers ({history_covers}) "
                         f"disagree with manifest weeks-covers sum ({weeks_sum})")


class TestAllergenMatrixReconciles(unittest.TestCase):
    """The allergen-matrix tool's sample apicbase CSV must contain the same
    dish set as the world's canonical apicbase-costings.csv.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_dish_set_matches_world_apicbase(self):
        tool = DEMO / "allergen-matrix"
        tool_csv = tool / "sample-data" / "apicbase-costings.csv"
        world_csv = SRC / "world" / "apicbase-costings.csv"
        if not (tool_csv.exists() and world_csv.exists()):
            self.skipTest("allergen-matrix tool not built yet")

        def _items(path):
            items = set()
            with path.open(newline="", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    item = (r.get("item") or "").strip()
                    if item:
                        items.add(item)
            return items

        tool_items = _items(tool_csv)
        world_items = _items(world_csv)
        self.assertEqual(
            tool_items, world_items,
            f"allergen-matrix dish set disagrees with world apicbase.\n"
            f"  Only in tool: {tool_items - world_items}\n"
            f"  Only in world: {world_items - tool_items}"
        )


class TestDailyBriefingReconciles(unittest.TestCase):
    """The daily-briefing tool's seated booking count for its briefing_date,
    as produced by compute(), must equal an independent recount of seated
    bookings for that date from the world's canonical opentable-bookings.csv.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_seated_booking_count_matches_world(self):
        tool = DEMO / "daily-briefing"
        bookings_path = tool / "sample-data" / "opentable-bookings.csv"
        specials_path = tool / "sample-data" / "specials.csv"
        training_path = tool / "sample-data" / "training-rota.csv"
        build = tool / "build_daily_briefing.py"
        config_path = tool / "config.json"
        world_csv = SRC / "world" / "opentable-bookings.csv"
        if not (bookings_path.exists() and specials_path.exists()
                and training_path.exists() and build.exists()
                and config_path.exists() and world_csv.exists()):
            self.skipTest("daily-briefing tool not built yet")

        briefing_date = json.loads(config_path.read_text())["briefing_date"]

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("build_daily_briefing", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            metrics = mod.compute(str(bookings_path), str(specials_path),
                                  str(training_path), briefing_date)
        finally:
            sys.path.remove(str(tool))

        expected = 0
        with world_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("date") == briefing_date and r.get("status") == "seated":
                    expected += 1
        self.assertEqual(metrics["booking_count"], expected,
                         f"daily-briefing seated booking count for {briefing_date} "
                         f"({metrics['booking_count']}) disagrees with world recount "
                         f"({expected})")


class TestPilotGateReconciles(unittest.TestCase):
    """The pilot-gate-tracker evaluates the latest week-ending key in its
    manual-kpis sample. Its compute()'d covers and spend_per_head for that week
    must agree with the world manifest's authoritative figures for the same week.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_latest_week_covers_and_spend_match_manifest(self):
        tool = DEMO / "pilot-gate-tracker"
        cubigo_path = tool / "sample-data" / "cubigo-sales.csv"
        survey_path = tool / "sample-data" / "flash-survey.csv"
        kpis_path = tool / "sample-data" / "manual-kpis.json"
        config_path = tool / "config.json"
        build = tool / "build_pilot_gate_tracker.py"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (cubigo_path.exists() and survey_path.exists() and kpis_path.exists()
                and config_path.exists() and build.exists() and manifest_path.exists()):
            self.skipTest("pilot-gate-tracker tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("build_pilot_gate_tracker", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            config = json.loads(config_path.read_text())
            metrics = mod.compute(str(cubigo_path), str(survey_path),
                                  str(kpis_path), config)
        finally:
            sys.path.remove(str(tool))

        week = metrics["week_ending"]
        manifest = json.loads(manifest_path.read_text())
        self.assertIn(week, manifest["weeks"],
                      f"pilot-gate-tracker latest week {week} not in manifest weeks")
        expected = manifest["weeks"][week]

        self.assertEqual(metrics["gates"]["covers"]["value"], expected["covers"],
                         f"pilot-gate-tracker covers for {week} "
                         f"({metrics['gates']['covers']['value']}) disagree with "
                         f"manifest ({expected['covers']})")
        self.assertAlmostEqual(
            metrics["gates"]["spend_per_head"]["value"], expected["spend_per_head"],
            delta=0.01,
            msg=f"pilot-gate-tracker spend_per_head for {week} "
                f"({metrics['gates']['spend_per_head']['value']}) disagrees with "
                f"manifest ({expected['spend_per_head']})")


class TestWasteSummariserReconciles(unittest.TestCase):
    """The waste-summariser costs each waste-log row at its Apicbase unit cost,
    keyed by item. Referential integrity at the world level: every distinct item
    in the world's canonical waste-log.csv must have a matching costing in the
    world's canonical apicbase-costings.csv, or the tool would (correctly) abort.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_every_waste_item_has_world_apicbase_cost(self):
        tool = DEMO / "waste-summariser"
        waste_csv = SRC / "world" / "waste-log.csv"
        apicbase_csv = SRC / "world" / "apicbase-costings.csv"
        if not (tool.exists() and waste_csv.exists() and apicbase_csv.exists()):
            self.skipTest("waste-summariser tool not built yet")

        cost_items = set()
        with apicbase_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                item = (r.get("item") or "").strip()
                if item:
                    cost_items.add(item)

        waste_items = set()
        with waste_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                item = (r.get("item") or "").strip()
                if item:
                    waste_items.add(item)

        missing = waste_items - cost_items
        self.assertEqual(
            missing, set(),
            f"waste-log items with no apicbase costing (waste-summariser would "
            f"abort on these): {missing}")


class TestFeedbackThemingReconciles(unittest.TestCase):
    """The feedback-theming tool themes the survey's free-text comments. Its
    compute()'d total_comments must equal an independent count of non-empty
    comment rows in the world's canonical flash-survey.csv — the tool themes
    exactly the comments that exist in the canon, no more, no fewer.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_total_comments_matches_world_recount(self):
        tool = DEMO / "feedback-theming"
        survey_path = tool / "sample-data" / "flash-survey.csv"
        config_path = tool / "config.json"
        build = tool / "build_feedback_theming.py"
        world_csv = SRC / "world" / "flash-survey.csv"
        if not (survey_path.exists() and config_path.exists()
                and build.exists() and world_csv.exists()):
            self.skipTest("feedback-theming tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("build_feedback_theming", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            themes = json.loads(config_path.read_text())["themes"]
            metrics = mod.compute(str(survey_path), themes)
        finally:
            sys.path.remove(str(tool))

        expected = 0
        with world_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("comment") or "").strip():
                    expected += 1
        self.assertEqual(metrics["total_comments"], expected,
                         f"feedback-theming total_comments "
                         f"({metrics['total_comments']}) disagrees with world "
                         f"comment recount ({expected})")


class TestReviewResponseReconciles(unittest.TestCase):
    """The review-response-drafts tool drafts a reply for every well-formed
    review. Its compute()'d total_reviews must equal an independent count of
    well-formed rows (platform present, rating an integer 1-5) in the world's
    canonical reviews.csv — the tool queues exactly the reviews that exist in the
    canon, no more, no fewer.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_total_reviews_matches_world_recount(self):
        tool = DEMO / "review-response-drafts"
        reviews_path = tool / "sample-data" / "reviews.csv"
        build = tool / "build_review_response_drafts.py"
        world_csv = SRC / "world" / "reviews.csv"
        if not (reviews_path.exists() and build.exists() and world_csv.exists()):
            self.skipTest("review-response-drafts tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "build_review_response_drafts", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            metrics = mod.compute(str(reviews_path))
        finally:
            sys.path.remove(str(tool))

        expected = 0
        with world_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if not (r.get("platform") or "").strip():
                    continue
                try:
                    rating = int(r["rating"])
                except (ValueError, TypeError):
                    continue
                if 1 <= rating <= 5:
                    expected += 1
        self.assertEqual(metrics["total_reviews"], expected,
                         f"review-response-drafts total_reviews "
                         f"({metrics['total_reviews']}) disagrees with world "
                         f"review recount ({expected})")


class TestMenuCopyReconciles(unittest.TestCase):
    """The menu-copy-drafts tool drafts copy for every standing menu dish. Its
    compute()'d standing-menu dish set must equal the apicbase item set in the
    world's canonical apicbase-costings.csv — the tool drafts copy for exactly
    the standing dishes that exist in the canon, no more, no fewer.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_standing_dish_set_matches_world_apicbase(self):
        tool = DEMO / "menu-copy-drafts"
        apic_path = tool / "sample-data" / "apicbase-costings.csv"
        specials_path = tool / "sample-data" / "specials.csv"
        build = tool / "build_menu_copy_drafts.py"
        world_csv = SRC / "world" / "apicbase-costings.csv"
        if not (apic_path.exists() and specials_path.exists()
                and build.exists() and world_csv.exists()):
            self.skipTest("menu-copy-drafts tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "build_menu_copy_drafts", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            metrics = mod.compute(str(apic_path), str(specials_path))
        finally:
            sys.path.remove(str(tool))

        tool_items = {d["name"] for d in metrics["standing"]}

        world_items = set()
        with world_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                item = (r.get("item") or "").strip()
                if item:
                    world_items.add(item)

        self.assertEqual(
            tool_items, world_items,
            f"menu-copy-drafts standing dish set disagrees with world apicbase.\n"
            f"  Only in tool: {tool_items - world_items}\n"
            f"  Only in world: {world_items - tool_items}")


class TestResidentNewsletterReconciles(unittest.TestCase):
    """The resident-newsletter tool drafts a "You said / We did" section from
    the survey's free-text comments. Its compute()'d total_comments must equal
    an independent count of non-empty comment rows in the world's canonical
    flash-survey.csv — the tool draws on exactly the comments that exist in the
    canon, no more, no fewer.

    Guarded by existence checks so it is skipped until the tool is built."""

    def test_total_comments_matches_world_recount(self):
        tool = DEMO / "resident-newsletter"
        survey_path = tool / "sample-data" / "flash-survey.csv"
        specials_path = tool / "sample-data" / "specials.csv"
        config_path = tool / "config.json"
        build = tool / "build_resident_newsletter.py"
        world_csv = SRC / "world" / "flash-survey.csv"
        if not (survey_path.exists() and specials_path.exists()
                and config_path.exists() and build.exists()
                and world_csv.exists()):
            self.skipTest("resident-newsletter tool not built yet")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "build_resident_newsletter", build)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(tool))
        try:
            spec.loader.exec_module(mod)
            themes = json.loads(config_path.read_text())["themes"]
            metrics = mod.compute(str(survey_path), str(specials_path), themes)
        finally:
            sys.path.remove(str(tool))

        expected = 0
        with world_csv.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("comment") or "").strip():
                    expected += 1
        self.assertEqual(metrics["total_comments"], expected,
                         f"resident-newsletter total_comments "
                         f"({metrics['total_comments']}) disagrees with world "
                         f"comment recount ({expected})")


class TestManifestMatchesDashboard(unittest.TestCase):
    """Permanent manifest <-> dashboard covers tie.

    The weekly dashboard (demo/weekly-dashboard/build_dashboard.py) is the
    canonical reference for what a "cover" is: it validates each cubigo row
    against NUMERIC_FIELDS = ["covers", "net"] and drops the row if EITHER is
    non-numeric, then counts one int(float(covers)) per unique (date, check_id)
    that has a surviving row. The world manifest MUST count covers the same way.

    This imports the REAL dashboard module by file path and runs its own pure
    metric function (compute_metrics) on its own sample-data — which is
    byte-identical to demo/_source/world/ (asserted by
    TestMakeWorld.test_canon_copied_verbatim). It then asserts the dashboard's
    per-week covers (covers_trend / covers_by_week) AND its latest-week covers
    equal the manifest's weeks[*].covers for the matching weeks. The dashboard
    is read-only and is NEVER modified or written to by this test.

    Guarded so it skips gracefully if the dashboard file is absent.
    """

    def test_dashboard_covers_match_manifest_weeks(self):
        import importlib.util
        import sys

        dash_file = DEMO / "weekly-dashboard" / "build_dashboard.py"
        manifest_path = SRC / "world" / "expected-metrics.json"
        if not (dash_file.exists() and manifest_path.exists()):
            self.skipTest("weekly-dashboard or manifest not present")

        spec = importlib.util.spec_from_file_location("build_dashboard", dash_file)
        dash = importlib.util.module_from_spec(spec)
        # The dashboard module is __main__-guarded, so executing it only defines
        # functions; main() does not run on import.
        sys.modules["build_dashboard"] = dash
        try:
            spec.loader.exec_module(dash)

            # Run the dashboard's OWN readers + pure compute on its OWN
            # sample-data (byte-identical to the world canon).
            sales, _ = dash.read_csv_rows("cubigo-sales.csv")
            bookings, _ = dash.read_csv_rows("opentable-bookings.csv")
            settlements, _ = dash.read_csv_rows("square-settlements.csv")
            surveys, _ = dash.read_csv_rows("flash-survey.csv")
            manual = dash.load_json_file(
                dash.DATA_DIR / "manual-kpis.json", "manual KPIs")
            metrics = dash.compute_metrics(
                sales, bookings, settlements, surveys, manual)
        finally:
            sys.modules.pop("build_dashboard", None)

        # covers_trend is [(week_ending_date, covers), ...] == covers_by_week.
        dash_covers_by_week = {wk.isoformat(): cov
                               for wk, cov in metrics["covers_trend"]}

        manifest = json.loads(manifest_path.read_text())
        man_weeks = manifest["weeks"]

        # Every week the dashboard counts must match the manifest's covers.
        for wk, dash_cov in dash_covers_by_week.items():
            self.assertIn(wk, man_weeks,
                          f"dashboard week {wk} absent from manifest weeks")
            self.assertEqual(
                man_weeks[wk]["covers"], dash_cov,
                f"manifest covers for week {wk} ({man_weeks[wk]['covers']}) "
                f"disagree with dashboard ({dash_cov})")

        # And the latest week the dashboard reports must match too (covers).
        latest_iso = metrics["latest_week"].isoformat()
        self.assertIn(latest_iso, man_weeks,
                      f"dashboard latest week {latest_iso} absent from manifest")
        self.assertEqual(
            man_weeks[latest_iso]["covers"], metrics["covers"],
            f"manifest latest-week covers for {latest_iso} "
            f"({man_weeks[latest_iso]['covers']}) disagree with dashboard "
            f"latest-week covers ({metrics['covers']})")


if __name__ == "__main__":
    unittest.main()
