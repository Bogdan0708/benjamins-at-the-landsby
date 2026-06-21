"""Tests for build_allergen_matrix.py — run from inside demo/allergen-matrix/."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

import build_allergen_matrix as am

APICBASE = "sample-data/apicbase-costings.csv"
COMMITTED_HTML = Path("allergen-matrix.html")


def _raw_allergen_sets(csv_path):
    """Independently parse the CSV and return {item: frozenset(allergens)} ."""
    result = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = row["item"]
            raw = row.get("allergens", "") or ""
            tokens = frozenset(t.strip() for t in raw.split(";") if t.strip())
            result[item] = tokens
    return result


class TestComputeMatrix(unittest.TestCase):
    def setUp(self):
        self.dishes, self.allergens, self.matrix, self.counts, self.skipped = \
            am.compute(APICBASE)

    def test_returns_exactly_14_allergens(self):
        self.assertEqual(len(self.allergens), 14)

    def test_allergen_list_matches_canonical(self):
        self.assertEqual(self.allergens, am.ALLERGENS_14)

    def test_matrix_ticks_match_csv(self):
        """For every dish, the set of allergens with True must equal the raw CSV tokens."""
        raw = _raw_allergen_sets(APICBASE)
        for dish in self.dishes:
            expected_allergens = raw[dish]
            actual_allergens = frozenset(
                a for a in self.allergens if self.matrix[dish][a]
            )
            self.assertEqual(
                actual_allergens, expected_allergens,
                f"Allergen mismatch for dish '{dish}': "
                f"expected {expected_allergens}, got {actual_allergens}"
            )

    def test_all_14_columns_always_present_in_matrix(self):
        """Every dish row must have a key for every canonical allergen."""
        for dish in self.dishes:
            for allergen in am.ALLERGENS_14:
                self.assertIn(allergen, self.matrix[dish],
                              f"Allergen column '{allergen}' missing for dish '{dish}'")

    def test_per_allergen_counts_correct(self):
        """counts[allergen] == number of dishes containing that allergen."""
        for allergen in self.allergens:
            expected = sum(1 for dish in self.dishes if self.matrix[dish][allergen])
            self.assertEqual(self.counts[allergen], expected,
                             f"Count wrong for allergen '{allergen}'")

    def test_dishes_in_stable_order(self):
        """Dishes must be sorted (deterministic output)."""
        self.assertEqual(self.dishes, sorted(self.dishes))

    def test_no_skipped_rows_for_clean_data(self):
        self.assertEqual(self.skipped, [])


class TestUnknownAllergenGuard(unittest.TestCase):
    def test_bogus_allergen_raises_benjamins_error(self):
        """A CSV with an unknown allergen token must raise BenjaminsError."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        try:
            tmp.write("item,category,unit_cost,allergens\n")
            tmp.write("Magic Dish,Mains,5.00,kryptonite\n")
            tmp.flush()
            tmp.close()
            with self.assertRaises(am.bc.BenjaminsError) as ctx:
                am.compute(tmp.name)
            self.assertIn("kryptonite", str(ctx.exception))
        finally:
            os.unlink(tmp.name)

    def test_good_allergen_does_not_raise(self):
        """A CSV with only valid allergen tokens must not raise."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        try:
            tmp.write("item,category,unit_cost,allergens\n")
            tmp.write("Safe Dish,Mains,5.00,milk;eggs\n")
            tmp.flush()
            tmp.close()
            dishes, allergens, matrix, counts, skipped = am.compute(tmp.name)
            self.assertIn("Safe Dish", dishes)
        finally:
            os.unlink(tmp.name)


class TestCaseInsensitiveMatching(unittest.TestCase):
    def test_allergen_matching_is_case_insensitive(self):
        """Mixed-case and padded allergen tokens must not raise and must map to canonical names."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        try:
            tmp.write("item,category,unit_cost,allergens\n")
            # "Milk" and "GLUTEN (CEREALS)" with extra padding — real Apicbase export style.
            tmp.write("Mixed Case Dish,Mains,6.00, Milk ; GLUTEN (CEREALS) \n")
            tmp.flush()
            tmp.close()
            # Must not raise despite mixed case and whitespace padding.
            dishes, allergens, matrix, counts, skipped = am.compute(tmp.name)
            self.assertIn("Mixed Case Dish", dishes)
            # Matrix must record the CANONICAL (lower-case) allergen names.
            self.assertTrue(matrix["Mixed Case Dish"]["milk"],
                            "Expected canonical 'milk' to be True")
            self.assertTrue(matrix["Mixed Case Dish"]["gluten (cereals)"],
                            "Expected canonical 'gluten (cereals)' to be True")
            # All other allergens must be False.
            other_allergens = {a for a in am.ALLERGENS_14 if a not in {"milk", "gluten (cereals)"}}
            for allergen in other_allergens:
                self.assertFalse(matrix["Mixed Case Dish"][allergen],
                                 f"Expected '{allergen}' to be False but was True")
        finally:
            os.unlink(tmp.name)


class TestRenderAllColumns(unittest.TestCase):
    def setUp(self):
        self.html = am.render(am.compute(APICBASE))

    def test_all_14_allergen_names_in_html(self):
        """Every one of the 14 canonical allergen names must appear in the rendered HTML."""
        for allergen in am.ALLERGENS_14:
            self.assertIn(allergen, self.html,
                          f"Allergen column '{allergen}' missing from rendered HTML")

    def test_all_dishes_in_html(self):
        """Every dish name must appear in the rendered HTML (html-escaped form)."""
        import html as html_module
        dishes, *_ = am.compute(APICBASE)
        for dish in dishes:
            escaped = html_module.escape(dish)
            self.assertIn(escaped, self.html,
                          f"Dish '{dish}' (escaped: '{escaped}') missing from rendered HTML")

    def test_watermark_present(self):
        self.assertIn("SAMPLE DATA", self.html)

    def test_html_has_table(self):
        self.assertIn("<table", self.html)


class TestDriftGuard(unittest.TestCase):
    def test_committed_html_matches_renderer(self):
        """The committed allergen-matrix.html must equal a fresh render."""
        if not COMMITTED_HTML.exists():
            self.skipTest("allergen-matrix.html not yet generated; run build first")
        fresh = am.render(am.compute(APICBASE))
        self.assertEqual(
            fresh, COMMITTED_HTML.read_text(encoding="utf-8"),
            "Committed allergen-matrix.html drifted — re-run build_allergen_matrix.py"
        )
