import unittest
from pathlib import Path
import sync_demo

DASH = (Path(__file__).parent.parent / "weekly-dashboard").resolve()


class TestSyncGuards(unittest.TestCase):
    def test_no_tool_targets_the_dashboard(self):
        for folder, _inputs, _script in sync_demo.TOOLS:
            self.assertNotEqual(folder, "weekly-dashboard")

    def test_write_guard_rejects_dashboard_paths(self):
        with self.assertRaises(sync_demo.SyncError):
            sync_demo.assert_writable(DASH / "sample-data" / "x.csv")

    def test_write_guard_allows_tool_paths(self):
        ok = (Path(__file__).parent.parent / "daily-sales-flash" / "x.csv").resolve()
        sync_demo.assert_writable(ok)  # must not raise

    def test_write_guard_rejects_relative_path_resolving_to_dashboard(self):
        # A plain string path that resolves under the dashboard must be rejected.
        with self.assertRaises(sync_demo.SyncError):
            sync_demo.assert_writable(str(DASH / "x.csv"))

    def test_tools_build_script_names_match_folders(self):
        for folder, _inputs, script in sync_demo.TOOLS:
            expected = "build_" + folder.replace("-", "_") + ".py"
            self.assertEqual(script, expected)


if __name__ == "__main__":
    unittest.main()
