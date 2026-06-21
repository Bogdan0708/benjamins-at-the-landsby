import unittest, json, csv, subprocess, sys
from pathlib import Path

SRC = Path(__file__).parent
WORLD = SRC / "world"
DASH = SRC.parent / "weekly-dashboard" / "sample-data"


class TestMakeWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, "make_world.py"], cwd=SRC, check=True)

    def test_canon_copied_verbatim(self):
        for name in ["cubigo-sales.csv", "square-settlements.csv",
                     "opentable-bookings.csv", "flash-survey.csv", "manual-kpis.json"]:
            self.assertEqual((WORLD / name).read_bytes(), (DASH / name).read_bytes(),
                             f"{name} must be byte-identical to dashboard canon")

    def test_apicbase_covers_every_cubigo_item(self):
        with open(WORLD / "cubigo-sales.csv", encoding="utf-8-sig") as f:
            cubigo_items = {r["item"] for r in csv.DictReader(f) if r["item"]}
        with open(WORLD / "apicbase-costings.csv") as f:
            costed_items = {r["item"] for r in csv.DictReader(f)}
        self.assertEqual(cubigo_items, costed_items)

    def test_manifest_totals_match_independent_recount(self):
        # A cover is a GUEST, not a check. Independently sum guest-covers using
        # the DASHBOARD's exact rule: a cubigo row counts only if BOTH covers
        # AND net parse as numbers (the dashboard validates NUMERIC_FIELDS =
        # ["covers", "net"] and drops a row if either is non-numeric). Take one
        # int(float(covers)) per well-formed (date, check_id) from its first
        # dashboard-valid row. Excluded: the empty-net row (BAD-002) and the
        # covers="two" row (BAD-003) — exactly as the dashboard drops them.
        manifest = json.loads((WORLD / "expected-metrics.json").read_text())
        with open(WORLD / "cubigo-sales.csv", encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f)]
        check_covers = {}
        for r in rows:
            if not r["check_id"]:
                continue
            key = (r["date"], r["check_id"])
            if key in check_covers:
                continue
            try:
                covers = int(float(r["covers"]))
                float(r["net"])  # dashboard drops the row if net is non-numeric
            except (TypeError, ValueError):
                continue
            check_covers[key] = covers
        guest_covers = sum(check_covers.values())
        self.assertEqual(manifest["totals"]["covers"], guest_covers)

    def test_external_share_in_unit_range(self):
        manifest = json.loads((WORLD / "expected-metrics.json").read_text())
        self.assertGreaterEqual(manifest["totals"]["external_share"], 0.0)
        self.assertLessEqual(manifest["totals"]["external_share"], 1.0)
        for wk, block in manifest["weeks"].items():
            self.assertGreaterEqual(block["external_share"], 0.0, wk)
            self.assertLessEqual(block["external_share"], 1.0, wk)

    def test_week_covers_reconcile_to_totals(self):
        manifest = json.loads((WORLD / "expected-metrics.json").read_text())
        weeks = manifest["weeks"]
        totals = manifest["totals"]
        # Covers are now GUEST-covers (sum of per-check guest counts), counted
        # under the dashboard's rule (a row counts only if BOTH covers and net
        # parse). The only check counted in totals but in no week is BAD-001
        # (date 2026-13-01 does not parse, but its covers=2 and net=14.50 are
        # both numeric, so it is dashboard-valid), whose guest count is 2 — so
        # the totals/weeks gap is that check's 2 guests. BAD-002 (empty net) and
        # BAD-003 (covers="two") are dropped by the dashboard rule, so they
        # contribute to NEITHER totals nor weeks and do not affect this gap.
        self.assertEqual(sum(w["covers"] for w in weeks.values()),
                         totals["covers"] - 2)


if __name__ == "__main__":
    unittest.main()
