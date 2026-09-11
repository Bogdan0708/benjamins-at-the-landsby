import shutil
import subprocess
import sys
import unittest, csv, json
from pathlib import Path
import build_daily_briefing as briefing

CFG = json.loads(Path("config.json").read_text())
BRIEFING_DATE = CFG["briefing_date"]

BOOKINGS = "sample-data/opentable-bookings.csv"
SPECIALS = "sample-data/specials.csv"
TRAINING = "sample-data/training-rota.csv"


def independent_booking_totals(path, day):
    """Independently count seated bookings and sum their party sizes for a date."""
    count, covers = 0, 0
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["date"] != day:
                continue
            if r["status"] == "seated":
                count += 1
                covers += int(r["party_size"])
    return count, covers


class TestDailyBriefing(unittest.TestCase):
    def setUp(self):
        self.m = briefing.compute(BOOKINGS, SPECIALS, TRAINING, BRIEFING_DATE)

    def test_booking_count_matches_independent_recount(self):
        count, _ = independent_booking_totals(BOOKINGS, BRIEFING_DATE)
        self.assertEqual(self.m["booking_count"], count)

    def test_covers_booked_matches_independent_recount(self):
        _, covers = independent_booking_totals(BOOKINGS, BRIEFING_DATE)
        self.assertEqual(self.m["covers_booked"], covers)

    def test_bookings_sorted_by_time(self):
        times = [time for time, _, _, _ in self.m["bookings"]]
        self.assertEqual(times, sorted(times))

    def test_specials_present(self):
        self.assertTrue(self.m["specials"], "expected at least one special on the briefing date")

    def test_special_with_known_allergen_shows_allergen(self):
        # Confit duck leg on 2026-04-16 carries crustaceans;mustard;soya.
        found = {dish: allergens for dish, _desc, allergens in self.m["specials"]}
        self.assertIn("Confit duck leg", found)
        self.assertIn("crustaceans", found["Confit duck leg"])
        self.assertIn("mustard", found["Confit duck leg"])
        self.assertIn("soya", found["Confit duck leg"])

    def test_committed_html_matches_renderer(self):
        fresh = briefing.render(
            briefing.compute(BOOKINGS, SPECIALS, TRAINING, BRIEFING_DATE)
        )
        self.assertEqual(
            fresh, Path("daily-briefing.html").read_text(),
            "Committed HTML drifted - re-run build_daily_briefing.py")


class TestSampleFlag(unittest.TestCase):
    """`--sample` must work from any cwd and must not touch the committed
    HTML — it writes into out/ instead."""

    def tearDown(self):
        shutil.rmtree(Path(__file__).parent / "out", ignore_errors=True)

    def test_sample_flag_writes_to_out_dir(self):
        out_dir = Path(__file__).parent / "out"
        shutil.rmtree(out_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "build_daily_briefing.py", "--sample"],
            check=True,
        )
        self.assertTrue((out_dir / "daily-briefing.html").exists())


if __name__ == "__main__":
    unittest.main()
