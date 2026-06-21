import unittest, csv
from pathlib import Path
import build_menu_copy_drafts as mc

APIC = "sample-data/apicbase-costings.csv"
SPECIALS = "sample-data/specials.csv"


def world_standing_items(path):
    """Independent read: the apicbase item set."""
    items = set()
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            item = (r.get("item") or "").strip()
            if item:
                items.add(item)
    return items


def world_special_dishes(path):
    """Independent read: the DISTINCT special dish names."""
    dishes = set()
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            dish = (r.get("dish") or "").strip()
            if dish:
                dishes.add(dish)
    return dishes


class TestMenuCopyDrafts(unittest.TestCase):
    def setUp(self):
        self.res = mc.compute(APIC, SPECIALS)

    def test_every_dish_gets_a_draft(self):
        # Every standing dish AND every distinct special has a non-empty draft.
        standing_names = {d["name"] for d in self.res["standing"]}
        special_names = {d["name"] for d in self.res["specials"]}
        for name in standing_names | special_names:
            self.assertIn(name, self.res["drafts"])
            self.assertTrue(self.res["drafts"][name].strip(),
                            f"empty draft for {name!r}")
        # total_dishes accounts for both lists.
        self.assertEqual(self.res["total_dishes"],
                         len(standing_names) + len(special_names))

    def test_draft_fn_cannot_change_prices(self):
        a = mc.compute(APIC, SPECIALS, draft_fn=lambda ctx: "AAA")
        z = mc.compute(APIC, SPECIALS, draft_fn=lambda ctx: "ZZZ")
        # Standing dish set + unit_cost values are identical regardless of draft_fn.
        a_costs = {d["name"]: d["unit_cost"] for d in a["standing"]}
        z_costs = {d["name"]: d["unit_cost"] for d in z["standing"]}
        self.assertEqual(a_costs, z_costs)
        self_costs = {d["name"]: d["unit_cost"] for d in self.res["standing"]}
        self.assertEqual(a_costs, self_costs)
        # The dish set (standing + specials) is identical too.
        self.assertEqual({d["name"] for d in a["standing"]},
                         {d["name"] for d in z["standing"]})
        self.assertEqual({d["name"] for d in a["specials"]},
                         {d["name"] for d in z["specials"]})
        # The drafts DO change (proves draft_fn was actually consulted).
        self.assertEqual(set(a["drafts"].values()), {"AAA"})
        self.assertNotEqual(a["drafts"], z["drafts"])

    def test_draft_fn_receives_no_numbers(self):
        seen = []

        def spy(ctx):
            seen.append(ctx)
            return "spied"

        mc.compute(APIC, SPECIALS, draft_fn=spy)
        self.assertTrue(seen, "draft_fn was never called")
        for ctx in seen:
            # No price/cost keys leak into the context.
            self.assertNotIn("unit_cost", ctx)
            self.assertNotIn("price", ctx)
            self.assertNotIn("cost", ctx)
            # No top-level value is a number.
            self.assertFalse(any(isinstance(v, (int, float, bool))
                                 for v in ctx.values()),
                             f"numeric value in context: {ctx}")
            # allergens are strings.
            for al in ctx.get("allergens", []):
                self.assertIsInstance(al, str)
            self.assertIsInstance(ctx["name"], str)
            self.assertIsInstance(ctx["category"], str)
            # seed is a string or None.
            self.assertTrue(ctx["seed"] is None or isinstance(ctx["seed"], str))

    def test_dish_set_is_deterministic(self):
        # The dish set (standing + specials) equals an independent read of the
        # two CSVs (apicbase items + distinct specials dishes).
        standing_names = {d["name"] for d in self.res["standing"]}
        special_names = {d["name"] for d in self.res["specials"]}
        self.assertEqual(standing_names, world_standing_items(APIC))
        self.assertEqual(special_names, world_special_dishes(SPECIALS))
        # Deterministic ordering: both lists sorted by name.
        self.assertEqual([d["name"] for d in self.res["standing"]],
                         sorted(standing_names))
        self.assertEqual([d["name"] for d in self.res["specials"]],
                         sorted(special_names))

    def test_committed_html_matches_renderer(self):
        fresh = mc.render(mc.compute(APIC, SPECIALS))
        self.assertEqual(
            fresh, Path("menu-copy-drafts.html").read_text(),
            "Committed HTML drifted - re-run build_menu_copy_drafts.py")


if __name__ == "__main__":
    unittest.main()
