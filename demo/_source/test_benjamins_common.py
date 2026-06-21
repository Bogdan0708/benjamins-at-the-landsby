import unittest
from datetime import date
import benjamins_common as bc


class TestParsing(unittest.TestCase):
    def test_parse_date(self):
        self.assertEqual(bc.parse_date("2026-04-13"), date(2026, 4, 13))

    def test_week_ending_is_sunday(self):
        # Mon 2026-04-13 belongs to week ending Sun 2026-04-19
        self.assertEqual(bc.week_ending(date(2026, 4, 13)), date(2026, 4, 19))
        self.assertEqual(bc.week_ending(date(2026, 4, 19)), date(2026, 4, 19))

    def test_parse_date_bad_raises_benjamins_error(self):
        with self.assertRaises(bc.BenjaminsError):
            bc.parse_date("13/04/2026")


class TestReadCsv(unittest.TestCase):
    def test_skips_and_counts_malformed_rows(self):
        import tempfile, os
        data = "a,b\n1,2\n,9\n3,4\n"  # middle row fails validator (empty a)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(data)
            path = f.name

        def validator(fn, row):
            if not row["a"]:
                raise bc.BenjaminsError(f"{fn}: empty 'a'")

        try:
            rows, skipped = bc.read_csv_rows(path, expected_columns=["a", "b"], validator=validator)
        finally:
            os.unlink(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(skipped), 1)

    def test_missing_expected_column_raises(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("a\n1\n")
            path = f.name
        try:
            with self.assertRaises(bc.BenjaminsError):
                bc.read_csv_rows(path, expected_columns=["a", "b"])
        finally:
            os.unlink(path)


class TestPage(unittest.TestCase):
    def test_page_includes_watermark_and_footer(self):
        html = bc.page("T", "Site", "<p>x</p>", skipped=["bad row 4"],
                       generated_label="week ending 7 June 2026")
        self.assertIn("synthetic", html.lower())
        self.assertIn("bad row 4", html)


class TestDaypart(unittest.TestCase):
    def test_lunch_time(self):
        # before 15:00 → "Lunch"
        self.assertEqual(bc.daypart("12:30"), "Lunch")

    def test_dinner_time(self):
        # 17:30 or later → "Evening"
        self.assertEqual(bc.daypart("19:45"), "Evening")

    def test_malformed_time_raises_benjamins_error(self):
        with self.assertRaises(bc.BenjaminsError):
            bc.daypart("not-a-time")


class TestLoadJsonFile(unittest.TestCase):
    def test_valid_json_returns_object(self):
        import tempfile, os, json
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"x": 1, "y": [2, 3]}, f)
            path = f.name
        try:
            obj = bc.load_json_file(path, "test data")
        finally:
            os.unlink(path)
        self.assertEqual(obj, {"x": 1, "y": [2, 3]})

    def test_missing_file_raises(self):
        with self.assertRaises(bc.BenjaminsError):
            bc.load_json_file("/no/such/path/missing.json", "test data")

    def test_malformed_json_raises(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            with self.assertRaises(bc.BenjaminsError):
                bc.load_json_file(path, "test data")
        finally:
            os.unlink(path)


class TestBarChart(unittest.TestCase):
    def test_normal_pairs_returns_svg(self):
        svg = bc.bar_chart([("Mon", 10), ("Tue", 20), ("Wed", 15)])
        self.assertIn("<svg", svg)

    def test_empty_list_does_not_crash(self):
        out = bc.bar_chart([])
        self.assertIsInstance(out, str)


class TestFormatters(unittest.TestCase):
    def test_fmt_money(self):
        self.assertEqual(bc.fmt_money(12.5, "£"), "£12")

    def test_fmt_pct(self):
        self.assertEqual(bc.fmt_pct(0.25), "25%")


if __name__ == "__main__":
    unittest.main()
