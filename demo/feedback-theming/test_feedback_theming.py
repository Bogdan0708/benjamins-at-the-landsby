import unittest, csv, json
from pathlib import Path
import build_feedback_theming as ft

CFG = json.loads(Path("config.json").read_text())
THEMES = CFG["themes"]
SAMPLE = "sample-data/flash-survey.csv"


def independent_counts(path, themes):
    """Recount, from scratch, how many comments match each theme's keywords."""
    counts = {t: 0 for t in themes}
    total = 0
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            com = (r["comment"] or "").strip()
            if not com:
                continue
            total += 1
            low = com.lower()
            for t, kws in themes.items():
                if any(k in low for k in kws):
                    counts[t] += 1
    return counts, total


class TestFeedbackTheming(unittest.TestCase):
    def setUp(self):
        self.res = ft.compute(SAMPLE, THEMES)

    def test_counts_are_keyword_deterministic(self):
        # The tool's own counts must equal its independent second pass...
        self.assertEqual(self.res["counts"], self.res["_independent"])
        # ...and equal a fully independent recount written here.
        indep, _ = independent_counts(SAMPLE, THEMES)
        self.assertEqual(self.res["counts"], indep)

    def test_draft_fn_cannot_change_counts(self):
        a = ft.compute(SAMPLE, THEMES, draft_fn=lambda ctx: "AAA")
        z = ft.compute(SAMPLE, THEMES, draft_fn=lambda ctx: "ZZZ")
        self.assertEqual(a["counts"], z["counts"])
        self.assertEqual(a["counts"], self.res["counts"])
        # The labels DO change (proves draft_fn was actually consulted)...
        self.assertNotEqual(a["labels"], z["labels"])
        self.assertEqual(set(a["labels"].values()), {"AAA"})

    def test_draft_fn_receives_no_numbers(self):
        seen = []

        def spy(ctx):
            seen.append(ctx)
            return "spied"

        ft.compute(SAMPLE, THEMES, draft_fn=spy)
        self.assertTrue(seen, "draft_fn was never called")
        for ctx in seen:
            self.assertEqual(set(ctx.keys()), {"theme_key", "sample_phrases"})
            self.assertNotIn("counts", ctx)
            self.assertIsInstance(ctx["theme_key"], str)
            for p in ctx["sample_phrases"]:
                # Guard: each phrase in the list must be a string, not a number.
                # This is the check that catches numbers hidden inside the phrase
                # list — the top-level isinstance check below only sees str/list
                # values, so do NOT remove this per-phrase assertion if copying
                # this test to a sibling tool.
                self.assertIsInstance(p, str)
            # Top-level ctx values are str (theme_key) and list (sample_phrases).
            # Neither is itself a number, but numbers could still be inside the
            # list — that case is caught by the per-phrase assertIsInstance above.
            self.assertFalse(any(isinstance(v, (int, float)) for v in ctx.values()))

    def test_total_comments_matches_independent(self):
        _, total = independent_counts(SAMPLE, THEMES)
        self.assertEqual(self.res["total_comments"], total)

    def test_committed_html_matches_renderer(self):
        fresh = ft.render(ft.compute(SAMPLE, THEMES))
        self.assertEqual(
            fresh, Path("feedback-theming.html").read_text(),
            "Committed HTML drifted - re-run build_feedback_theming.py")


if __name__ == "__main__":
    unittest.main()
