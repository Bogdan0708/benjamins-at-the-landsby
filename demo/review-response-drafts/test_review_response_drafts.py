import unittest, csv, json
from pathlib import Path
import build_review_response_drafts as rr

CFG = json.loads(Path("config.json").read_text())
SAMPLE = "sample-data/reviews.csv"


def independent_buckets(path):
    """Recount, from scratch, how many reviews fall in each rating bucket."""
    counts = {"negative": 0, "neutral": 0, "positive": 0}
    total = 0
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not (r.get("platform") or "").strip():
                continue
            try:
                rating = int(r["rating"])
            except (ValueError, TypeError):
                continue
            if rating < 1 or rating > 5:
                continue
            total += 1
            if rating in (1, 2):
                counts["negative"] += 1
            elif rating == 3:
                counts["neutral"] += 1
            else:
                counts["positive"] += 1
    return counts, total


class TestReviewResponseDrafts(unittest.TestCase):
    def setUp(self):
        self.res = rr.compute(SAMPLE)

    def test_buckets_are_rating_deterministic(self):
        indep, total = independent_buckets(SAMPLE)
        self.assertEqual(self.res["bucket_counts"], indep)
        self.assertEqual(self.res["total_reviews"], total)

    def test_draft_fn_cannot_change_buckets_or_ratings(self):
        a = rr.compute(SAMPLE, draft_fn=lambda ctx: "AAA")
        z = rr.compute(SAMPLE, draft_fn=lambda ctx: "ZZZ")
        # Bucket counts are identical regardless of draft_fn.
        self.assertEqual(a["bucket_counts"], z["bucket_counts"])
        self.assertEqual(a["bucket_counts"], self.res["bucket_counts"])
        # Per-review rating values are identical regardless of draft_fn.
        a_ratings = [rec["rating"] for rec in a["reviews"]]
        z_ratings = [rec["rating"] for rec in z["reviews"]]
        self.assertEqual(a_ratings, z_ratings)
        # The drafts DO change (proves draft_fn was actually consulted).
        self.assertNotEqual([r["draft"] for r in a["reviews"]],
                            [r["draft"] for r in z["reviews"]])
        self.assertEqual({r["draft"] for r in a["reviews"]}, {"AAA"})

    def test_draft_fn_receives_no_numbers(self):
        seen = []

        def spy(ctx):
            seen.append(ctx)
            return "spied"

        rr.compute(SAMPLE, draft_fn=spy)
        self.assertTrue(seen, "draft_fn was never called")
        for ctx in seen:
            # No rating/count keys leak into the context.
            self.assertNotIn("rating", ctx)
            self.assertNotIn("count", ctx)
            self.assertNotIn("bucket_counts", ctx)
            # No top-level value is a number.
            self.assertFalse(any(isinstance(v, (int, float, bool))
                                 for v in ctx.values()))
            # themes, if present, must be strings — not numbers.
            for t in ctx.get("themes", []):
                self.assertIsInstance(t, str)
            # bucket and platform are strings.
            self.assertIsInstance(ctx["bucket"], str)
            self.assertIsInstance(ctx["platform"], str)

    def test_one_star_routes_to_negative(self):
        # Synthesise a one-star review and confirm it buckets negative and the
        # default_draft emits the negative-template marker.
        ctx_neg = {"platform": "google", "bucket": "negative", "themes": []}
        draft = rr.default_draft(ctx_neg)
        self.assertIn(rr.NEGATIVE_MARKER, draft)
        # End-to-end: a rating-1 row routes to the negative bucket.
        tmp = Path("sample-data/_one_star_test.csv")
        tmp.write_text("date,platform,rating,text\n"
                       "2026-06-10,google,1,Very disappointing visit.\n")
        try:
            res = rr.compute(str(tmp))
            self.assertEqual(res["bucket_counts"]["negative"], 1)
            self.assertEqual(len(res["reviews"]), 1)
            self.assertEqual(res["reviews"][0]["bucket"], "negative")
            self.assertIn(rr.NEGATIVE_MARKER, res["reviews"][0]["draft"])
        finally:
            tmp.unlink()

    def test_bad_rows_skipped_and_counted(self):
        tmp = Path("sample-data/_bad_rows_test.csv")
        tmp.write_text(
            "date,platform,rating,text\n"
            "2026-06-10,google,5,Lovely.\n"        # good
            "2026-06-10,google,7,Out of range.\n"  # rating > 5 -> skip
            "2026-06-10,google,x,Not an int.\n"    # non-int -> skip
            "2026-06-10,,4,No platform.\n"         # missing platform -> skip
        )
        try:
            res = rr.compute(str(tmp))
            self.assertEqual(res["total_reviews"], 1)
            self.assertEqual(len(res["skipped"]), 3)
        finally:
            tmp.unlink()

    def test_committed_html_matches_renderer(self):
        fresh = rr.render(rr.compute(SAMPLE))
        self.assertEqual(
            fresh, Path("review-response-drafts.html").read_text(),
            "Committed HTML drifted - re-run build_review_response_drafts.py")


if __name__ == "__main__":
    unittest.main()
