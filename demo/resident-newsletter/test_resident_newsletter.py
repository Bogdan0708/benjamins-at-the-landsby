import unittest, csv, json, html
from pathlib import Path
import build_resident_newsletter as rn

CFG = json.loads(Path("config.json").read_text())
THEMES = CFG["themes"]
SURVEY = "sample-data/flash-survey.csv"
SPECIALS = "sample-data/specials.csv"


def independent_present_themes(path, themes):
    """Recompute, from scratch, which themes have at least one matching comment."""
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
    present = {t for t, c in counts.items() if c > 0}
    return present, total


def independent_specials(path):
    """Recompute, from scratch, the distinct special dish names (sorted)."""
    dishes = set()
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            dish = (r.get("dish") or "").strip()
            if dish:
                dishes.add(dish)
    return sorted(dishes)


class TestResidentNewsletter(unittest.TestCase):
    def setUp(self):
        self.res = rn.compute(SURVEY, SPECIALS, THEMES)

    def test_you_said_themes_deterministic(self):
        # The present-themes set equals an independent keyword recompute.
        present, _ = independent_present_themes(SURVEY, THEMES)
        self.assertEqual(set(self.res["you_said_themes"]), present)
        # Every reported present theme genuinely matched at least one comment.
        for t in self.res["you_said_themes"]:
            self.assertIn(t, THEMES)

    def test_draft_fn_cannot_change_themes_or_facts(self):
        a = rn.compute(SURVEY, SPECIALS, THEMES, draft_fn=lambda ctx: "AAA")
        z = rn.compute(SURVEY, SPECIALS, THEMES, draft_fn=lambda ctx: "ZZZ")
        # The deterministic you_said_themes and we_did_facts (the dated facts)
        # are identical regardless of draft_fn.
        self.assertEqual(a["you_said_themes"], z["you_said_themes"])
        self.assertEqual(a["you_said_themes"], self.res["you_said_themes"])
        self.assertEqual(a["we_did_facts"], z["we_did_facts"])
        self.assertEqual(a["we_did_facts"], self.res["we_did_facts"])
        # The draft DOES change (proves draft_fn was actually consulted).
        self.assertEqual(a["draft"], "AAA")
        self.assertNotEqual(a["draft"], z["draft"])

    def test_draft_fn_receives_no_numbers(self):
        seen = []

        def spy(ctx):
            seen.append(ctx)
            return "spied"

        rn.compute(SURVEY, SPECIALS, THEMES, draft_fn=spy)
        self.assertTrue(seen, "draft_fn was never called")
        for ctx in seen:
            # No count keys leak into the context.
            self.assertNotIn("counts", ctx)
            self.assertNotIn("count", ctx)
            self.assertNotIn("total_comments", ctx)
            self.assertEqual(set(ctx.keys()),
                             {"you_said_themes", "sample_phrases", "we_did"})
            # No top-level value is a number.
            self.assertFalse(any(isinstance(v, (int, float, bool))
                                 for v in ctx.values()),
                             f"numeric value in context: {ctx}")
            # you_said_themes is a list of strings.
            for t in ctx["you_said_themes"]:
                self.assertIsInstance(t, str)
            # we_did is a list of dish-name strings.
            for item in ctx["we_did"]:
                self.assertIsInstance(item, str)
            # sample_phrases maps theme -> list of string snippets.
            self.assertIsInstance(ctx["sample_phrases"], dict)
            for theme, phrases in ctx["sample_phrases"].items():
                self.assertIsInstance(theme, str)
                for p in phrases:
                    self.assertIsInstance(p, str)

    def test_draft_fn_context_has_no_dates(self):
        # Stronger guarantee than "no numeric values": NO string anywhere in the
        # draft_fn context may contain a digit. This proves no date (e.g. an ISO
        # "first offered 2026-04-21") and no number can reach draft_fn. The
        # we_did entries are dish NAMES only; the dated facts are rendered
        # deterministically outside the draft. (The canon resident comments in
        # sample_phrases carry no digits either, so the check covers the whole
        # context recursively — keys and values alike.)
        seen = []

        def spy(ctx):
            seen.append(ctx)
            return "spied"

        rn.compute(SURVEY, SPECIALS, THEMES, draft_fn=spy)
        self.assertTrue(seen, "draft_fn was never called")

        def assert_no_digits(node, path="context"):
            if isinstance(node, str):
                self.assertFalse(
                    any(ch.isdigit() for ch in node),
                    f"digit found in draft_fn context at {path}: {node!r}")
            elif isinstance(node, dict):
                for k, v in node.items():
                    assert_no_digits(k, f"{path}.<key>")
                    assert_no_digits(v, f"{path}[{k!r}]")
            elif isinstance(node, (list, tuple)):
                for i, v in enumerate(node):
                    assert_no_digits(v, f"{path}[{i}]")
            else:
                # Non-string scalars (other than the booleans/ints already
                # excluded above) would themselves be a leak; fail loudly.
                self.assertIsNone(
                    node, f"unexpected non-string scalar at {path}: {node!r}")

        for ctx in seen:
            assert_no_digits(ctx)

    def test_we_did_is_deterministic(self):
        # The we_did_facts are the distinct specials, sorted by dish name, each
        # carrying its first-offered date as factual text produced by code.
        dishes = independent_specials(SPECIALS)
        self.assertTrue(dishes, "no specials read")
        fact_dishes = [f["dish"] for f in self.res["we_did_facts"]]
        self.assertEqual(fact_dishes, dishes)
        # Every dated fact renders into the deterministic page section.
        html_out = rn.render(self.res)
        for fact in self.res["we_did_facts"]:
            self.assertIn(html.escape(fact["dish"]), html_out,
                          f"special {fact['dish']!r} missing from page")
            if fact["first_offered"]:
                self.assertIn(
                    f"first offered {html.escape(fact['first_offered'])}",
                    html_out,
                    f"date for {fact['dish']!r} missing from page")

    def test_total_comments_matches_independent(self):
        _, total = independent_present_themes(SURVEY, THEMES)
        self.assertEqual(self.res["total_comments"], total)

    def test_default_draft_prose_has_no_dates(self):
        # The drafted prose weaves dish names only; no date/number reaches it,
        # so the draft text must contain no digit.
        draft = self.res["draft"]
        self.assertFalse(any(ch.isdigit() for ch in draft),
                         f"digit found in drafted prose: {draft!r}")

    def test_approval_marker_present(self):
        html_out = rn.render(self.res)
        self.assertIn("DRAFT", html_out)
        self.assertIn("for GM approval before the newsletter goes out", html_out)

    def test_committed_html_matches_renderer(self):
        fresh = rn.render(rn.compute(SURVEY, SPECIALS, THEMES))
        self.assertEqual(
            fresh, Path("resident-newsletter.html").read_text(),
            "Committed HTML drifted - re-run build_resident_newsletter.py")


if __name__ == "__main__":
    unittest.main()
