import csv
import json
import unittest
from pathlib import Path

import benjamins_common as bc
import build_pilot_gate_tracker as pilot

CFG = json.loads(Path("config.json").read_text())
CUBIGO = "sample-data/cubigo-sales.csv"
SURVEY = "sample-data/flash-survey.csv"
KPIS = "sample-data/manual-kpis.json"


def latest_week():
    kpis = json.loads(Path(KPIS).read_text(encoding="utf-8"))
    return max(kpis.keys())


def independent_week(week_iso):
    """Recompute the latest week's guest-covers and net from the raw CSV.

    A cover is a GUEST: sum one int(float(covers)) per (date, check_id), taking
    the first numeric covers per check. A check whose covers is never numeric is
    malformed and excluded (mirrors the tool). Net sums the same surviving rows.
    """
    week = bc.parse_date(week_iso)
    check_covers, net = {}, 0.0
    with open(CUBIGO, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("check_id"):
                continue
            try:
                d = bc.parse_date(r["date"])
            except bc.BenjaminsError:
                continue
            if bc.week_ending(d) != week:
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


def independent_satisfaction(week_iso):
    week = bc.parse_date(week_iso)
    scores = []
    with open(SURVEY, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                d = bc.parse_date(r["date"])
                food, service, value = float(r["food"]), float(r["service"]), float(r["value"])
            except (ValueError, TypeError, bc.BenjaminsError):
                continue
            if bc.week_ending(d) != week:
                continue
            scores.append((food + service + value) / 3)
    return sum(scores) / len(scores) if scores else None


class TestPilotGate(unittest.TestCase):
    def setUp(self):
        self.m = pilot.compute(CUBIGO, SURVEY, KPIS, CFG)
        self.gates = self.m["gates"]

    def test_latest_week_selected(self):
        self.assertEqual(self.m["week_ending"], latest_week())

    def test_covers_match_independent_recount(self):
        covers, _net = independent_week(latest_week())
        self.assertEqual(self.gates["covers"]["value"], covers)

    def test_spend_per_head_matches_independent(self):
        covers, net = independent_week(latest_week())
        self.assertAlmostEqual(self.gates["spend_per_head"]["value"], net / covers, places=4)
        # the demo's worked example sits around £23/head
        self.assertTrue(22.0 <= self.gates["spend_per_head"]["value"] <= 24.0)

    def test_labour_pct_matches_independent(self):
        _covers, net = independent_week(latest_week())
        kpis = json.loads(Path(KPIS).read_text(encoding="utf-8"))
        labour_cost = kpis[latest_week()]["labour_cost"]
        self.assertAlmostEqual(self.gates["labour_pct"]["value"], labour_cost / net, places=4)

    def test_satisfaction_matches_independent(self):
        self.assertAlmostEqual(self.gates["satisfaction"]["value"],
                               independent_satisfaction(latest_week()), places=4)

    def test_labour_pct_is_lower_is_better(self):
        self.assertEqual(self.gates["labour_pct"]["direction"], "lower")

    def test_higher_is_better_directions(self):
        for name in ("covers", "spend_per_head", "satisfaction"):
            self.assertEqual(self.gates[name]["direction"], "higher")

    def test_rag_rule_higher_is_better(self):
        for name in ("covers", "spend_per_head", "satisfaction"):
            g = self.gates[name]
            v, green, amber = g["value"], g["green"], g["amber"]
            if v >= green:
                expected = "green"
            elif v >= amber:
                expected = "amber"
            else:
                expected = "red"
            self.assertEqual(g["status"], expected,
                             f"{name}: value {v} vs green {green}/amber {amber}")

    def test_rag_rule_lower_is_better(self):
        g = self.gates["labour_pct"]
        v, green, amber = g["value"], g["green"], g["amber"]
        if v <= green:
            expected = "green"
        elif v <= amber:
            expected = "amber"
        else:
            expected = "red"
        self.assertEqual(g["status"], expected,
                         f"labour_pct: value {v} vs green {green}/amber {amber}")

    def test_repeat_bookings_untracked(self):
        g = self.gates["repeat_bookings"]
        self.assertEqual(g["status"], "untracked")
        self.assertIsNone(g["value"])

    def test_rag_mix_is_honest(self):
        statuses = {g["status"] for k, g in self.gates.items() if k != "repeat_bookings"}
        self.assertFalse(statuses == {"green"}, "the worked example should not be all green")

    def test_committed_html_matches_renderer(self):
        fresh = pilot.render(pilot.compute(CUBIGO, SURVEY, KPIS, CFG))
        self.assertEqual(fresh, Path("pilot-gate-tracker.html").read_text(),
                         "Committed HTML drifted - re-run build_pilot_gate_tracker.py")


if __name__ == "__main__":
    unittest.main()
