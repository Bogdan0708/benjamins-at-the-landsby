import shutil
import subprocess
import sys
import unittest, csv, json
from pathlib import Path
import build_cubigo_square_recon as recon

CFG = json.loads(Path("config.json").read_text())
BAND_LOW, BAND_HIGH = CFG["ratio_band"]
FEE_TOL = CFG["fee_tolerance"]
CUBIGO = "sample-data/cubigo-sales.csv"
SQUARE = "sample-data/square-settlements.csv"


def independent_till_net(path, day):
    """Sum cubigo net for one date, skipping malformed nets — mirrors the tool's
    valid-row rule but written separately so a logic change in the tool can't
    silently pass this test."""
    net = 0.0
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["date"] != day:
                continue
            try:
                net += float(r["net"])
            except (ValueError, TypeError):
                pass
    return round(net, 2)


def independent_square_row(path, day):
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["date"] == day:
                return {"gross": round(float(r["gross"]), 2),
                        "fees": round(float(r["fees"]), 2),
                        "net": round(float(r["net"]), 2)}
    return None


class TestRecon(unittest.TestCase):
    def setUp(self):
        self.m = recon.compute(CUBIGO, SQUARE, CFG)
        self.rows = {r["date"]: r for r in self.m["rows"]}

    def test_independent_ratio_recompute_for_in_band_day(self):
        # 2026-06-01 is present in both sources and is in-band (ratio ~0.84).
        day = "2026-06-01"
        till = independent_till_net(CUBIGO, day)
        sq = independent_square_row(SQUARE, day)
        self.assertIsNotNone(sq)
        ratio = round(sq["gross"] / till, 4)
        # confirm this fixture day really is in-band
        self.assertTrue(BAND_LOW <= ratio <= BAND_HIGH)
        row = self.rows[day]
        self.assertEqual(row["till_net"], till)
        self.assertEqual(row["sq_gross"], sq["gross"])
        self.assertEqual(row["ratio"], ratio)

    def test_coverage_gap_settlement_with_no_till_trading(self):
        # 2026-06-02 is absent from cubigo but present in square — a coverage gap.
        day = "2026-06-02"
        self.assertEqual(independent_till_net(CUBIGO, day), 0.0)  # no cubigo rows
        self.assertIsNotNone(independent_square_row(SQUARE, day))  # square has it
        row = self.rows[day]
        self.assertIsNone(row["till_net"])
        self.assertIsNone(row["ratio"])
        self.assertIn("settlement with no till trading", row["reasons"])
        self.assertIn(day, [r["date"] for r in self.m["exceptions"]])

    def test_fee_integrity_matches_independent_recompute(self):
        # For every square row, the tool must flag a fee-integrity exception
        # iff an independent recompute exceeds tolerance — no false pass/fail.
        with open(SQUARE, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                day = r["date"]
                gross, fees, net = (round(float(r[c]), 2) for c in ("gross", "fees", "net"))
                expected_flag = abs(gross - fees - net) > FEE_TOL
                row = self.rows[day]
                tool_flag = any(reason.startswith("square fee integrity")
                                for reason in row["reasons"])
                self.assertEqual(tool_flag, expected_flag,
                                 f"fee-integrity mismatch for {day}")

    def test_band_behaviour(self):
        # Every ratio-band exception truly has a ratio outside the band.
        for r in self.m["exceptions"]:
            ratio_flagged = any(reason.startswith("coverage ratio")
                                for reason in r["reasons"])
            if ratio_flagged:
                self.assertIsNotNone(r["ratio"])
                self.assertTrue(r["ratio"] < BAND_LOW or r["ratio"] > BAND_HIGH)
        # A known in-band day is NOT flagged at all.
        in_band = self.rows["2026-06-01"]
        self.assertEqual(in_band["reasons"], [])

    def test_skipped_malformed_cubigo_rows_counted(self):
        self.assertTrue(self.m["skipped"])

    def test_unparseable_date_is_skipped_not_a_trading_day(self):
        # 2026-13-01 is an unparseable calendar date (month 13). It is a
        # data-quality issue, not a trading day: it must be counted as skipped
        # and must NOT appear in the rows/exceptions or mismatches.csv.
        bad = "2026-13-01"
        self.assertNotIn(bad, self.rows)
        self.assertNotIn(bad, [r["date"] for r in self.m["exceptions"]])
        self.assertTrue(any(bad in note for note in self.m["skipped"]),
                        "bad date should be recorded as a skipped data-quality note")
        recon.main()
        with open("mismatches.csv", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertNotIn(bad, [r[0] for r in rows[1:]])
        # The genuine coverage gap 2026-06-02 (real date) is still an exception.
        self.assertIn("2026-06-02", [r[0] for r in rows[1:]])

    def test_mismatches_csv_row_count_equals_exception_count(self):
        recon.main()
        n_exc = len(recon.compute(CUBIGO, SQUARE, CFG)["exceptions"])
        with open("mismatches.csv", encoding="utf-8-sig") as f:
            all_rows = list(csv.reader(f))
        header, data_rows = all_rows[0], all_rows[1:]
        self.assertEqual(header, ["date", "till_net", "sq_gross", "sq_net", "ratio", "reason"])
        self.assertEqual(len(data_rows), n_exc)

    def test_committed_html_matches_renderer(self):
        fresh = recon.render(recon.compute(CUBIGO, SQUARE, CFG))
        self.assertEqual(
            fresh, Path("cubigo-square-recon.html").read_text(),
            "Committed HTML drifted - re-run build_cubigo_square_recon.py")


class TestSampleFlag(unittest.TestCase):
    """`--sample` must work from any cwd and must not touch the committed
    HTML/CSV — it writes into out/ instead."""

    def tearDown(self):
        shutil.rmtree(Path(__file__).parent / "out", ignore_errors=True)

    def test_sample_flag_writes_to_out_dir(self):
        out_dir = Path(__file__).parent / "out"
        shutil.rmtree(out_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "build_cubigo_square_recon.py", "--sample"],
            check=True,
        )
        self.assertTrue((out_dir / "cubigo-square-recon.html").exists())
        self.assertTrue((out_dir / "mismatches.csv").exists())


if __name__ == "__main__":
    unittest.main()
