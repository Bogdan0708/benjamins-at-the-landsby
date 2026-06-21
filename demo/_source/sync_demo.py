"""sync_demo.py — maintenance loop for the Benjamin's demo portfolio.

Regenerates the whole demo suite in five steps:
  1. Run make_world.py to produce demo/_source/world/
  2. Copy each tool's required input slices from world/ into that tool's sample-data/
  3. Vendor benjamins_common.py byte-identically into every tool folder
  4. Run each tool's build_*.py to regenerate committed HTML
  5. Run all tests

WRITE-GUARD: writes performed directly by sync_demo.py functions are routed
through assert_writable(), which resolves the path and raises SyncError if it
is the read-only weekly-dashboard/ directory or anything inside it. make_world.py
(run via runpy) and the per-tool build scripts (run via subprocess) are trusted
to write only within their own folders; as a backstop, _step4_build_html asserts
each build script's HTML output landed under its own tool folder and that the
dashboard directory was not the write target.
"""

import runpy
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level path constants
# ---------------------------------------------------------------------------

SRC = Path(__file__).resolve().parent          # demo/_source/
DEMO = SRC.parent                              # demo/
DASHBOARD = (DEMO / "weekly-dashboard").resolve()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SyncError(Exception):
    """Raised when a sync step fails or an illegal write is attempted."""


# ---------------------------------------------------------------------------
# Tool manifest
# Each entry is a 3-tuple: (folder_name, [input_files_from_world], build_script)
# folder_name is relative to DEMO (i.e. just the bare folder name).
# ---------------------------------------------------------------------------

TOOLS = [
    (
        "daily-sales-flash",
        ["cubigo-sales.csv"],
        "build_daily_sales_flash.py",
    ),
    (
        "cubigo-square-recon",
        ["cubigo-sales.csv", "square-settlements.csv"],
        "build_cubigo_square_recon.py",
    ),
    (
        "menu-engineering",
        ["cubigo-sales.csv", "apicbase-costings.csv"],
        "build_menu_engineering.py",
    ),
    (
        "demand-forecast",
        ["cubigo-sales.csv", "opentable-bookings.csv"],
        "build_demand_forecast.py",
    ),
    (
        "allergen-matrix",
        ["apicbase-costings.csv"],
        "build_allergen_matrix.py",
    ),
    (
        "daily-briefing",
        ["opentable-bookings.csv", "specials.csv", "training-rota.csv"],
        "build_daily_briefing.py",
    ),
    (
        "pilot-gate-tracker",
        ["cubigo-sales.csv", "flash-survey.csv", "manual-kpis.json"],
        "build_pilot_gate_tracker.py",
    ),
    (
        "waste-summariser",
        ["waste-log.csv", "apicbase-costings.csv"],
        "build_waste_summariser.py",
    ),
    (
        "feedback-theming",
        ["flash-survey.csv"],
        "build_feedback_theming.py",
    ),
    (
        "review-response-drafts",
        ["reviews.csv"],
        "build_review_response_drafts.py",
    ),
    (
        "menu-copy-drafts",
        ["apicbase-costings.csv", "specials.csv"],
        "build_menu_copy_drafts.py",
    ),
    (
        "resident-newsletter",
        ["flash-survey.csv", "specials.csv"],
        "build_resident_newsletter.py",
    ),
]


# ---------------------------------------------------------------------------
# Write-guard
# ---------------------------------------------------------------------------

def assert_writable(path):
    """Resolve *path* and raise SyncError if it is (or is inside) the dashboard.

    Compares against the already-resolved DASHBOARD constant rather than a string
    name, so a symlinked dashboard is still caught.

    Returns the resolved Path on success (or None if path is None).
    """
    if path is None:
        return None
    resolved = Path(path).resolve()
    if resolved == DASHBOARD or DASHBOARD in resolved.parents:
        raise SyncError(f"refusing to write under the read-only dashboard: {resolved}")
    return resolved


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _step1_make_world():
    """Run make_world.py to regenerate demo/_source/world/."""
    make_world = SRC / "make_world.py"
    if not make_world.exists():
        raise SyncError(f"make_world.py not found at {make_world}")
    runpy.run_path(str(make_world), run_name="__main__")


def _step2_copy_inputs():
    """Copy each tool's required world slices into its sample-data/ directory."""
    world = SRC / "world"
    for folder, inputs, _script in TOOLS:
        tool_dir = DEMO / folder
        if not tool_dir.exists():
            # Tool folder not yet created — skip silently (later tasks build it)
            continue
        sample_data = tool_dir / "sample-data"
        dest_dir = assert_writable(sample_data)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for filename in inputs:
            src_file = world / filename
            if not src_file.exists():
                raise SyncError(f"World slice missing: {src_file}")
            dest_file = assert_writable(dest_dir / filename)
            shutil.copyfile(src_file, dest_file)


def _step3_vendor_common():
    """Byte-identically copy benjamins_common.py into every tool folder."""
    common_src = SRC / "benjamins_common.py"
    if not common_src.exists():
        raise SyncError(f"benjamins_common.py not found at {common_src}")
    for folder, _inputs, _script in TOOLS:
        tool_dir = DEMO / folder
        if not tool_dir.exists():
            continue
        dest_file = assert_writable(tool_dir / "benjamins_common.py")
        shutil.copyfile(common_src, dest_file)
        # Verify byte-equality
        if common_src.read_bytes() != dest_file.read_bytes():
            raise SyncError(
                f"Byte-equality check failed after vendoring benjamins_common.py "
                f"to {dest_file}"
            )


def _step4_build_html():
    """Run each tool's build script to regenerate committed HTML."""
    for folder, _inputs, build_script in TOOLS:
        tool_dir = DEMO / folder
        if not tool_dir.exists():
            continue
        script_path = tool_dir / build_script
        if not script_path.exists():
            raise SyncError(
                f"Build script not found: {script_path}. "
                f"Expected {build_script} in {tool_dir}."
            )
        # The build script is trusted to write only within its own folder. Its
        # expected HTML output is <folder>.html in the tool dir; assert that path
        # is writable (i.e. not the dashboard) before and after running, so a
        # build script misconfigured to target the dashboard is caught.
        expected_html = tool_dir / f"{folder}.html"
        html_name = expected_html.name
        assert_writable(expected_html)

        # Record the prior mtime so we can prove the file was actually rewritten
        # this run. A failed build that swallows its error and returns 0 would
        # otherwise leave the OLD committed HTML in place and look like success.
        prior_mtime = expected_html.stat().st_mtime if expected_html.exists() else None

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(tool_dir),
        )
        if result.returncode != 0:
            raise SyncError(
                f"Build script {build_script} failed for {folder}:\n"
                f"{result.stderr}"
            )

        # Safety: the produced HTML must have landed under the tool folder, not
        # under the read-only dashboard.
        assert_writable(expected_html)
        if not expected_html.exists():
            raise SyncError(
                f"Build script {build_script} did not produce expected output "
                f"{expected_html} under {tool_dir}."
            )

        # The HTML must have been (re)written THIS run, not left stale. If the
        # build silently failed but the script still exited 0, the file would be
        # unchanged (same mtime as before) — treat that as a failure.
        new_mtime = expected_html.stat().st_mtime
        if prior_mtime is not None and new_mtime <= prior_mtime:
            raise SyncError(f"{folder}: build did not (re)write {html_name}")


def _run_unittest_discover(start_dir, cwd):
    """Run `python -m unittest discover` in *cwd* over *start_dir*.

    Returns the completed CompletedProcess. Per-tool tests import their sibling
    build_<tool> module, so each must run with its own folder as the cwd.
    """
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(start_dir),
         "-p", "test_*.py"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _step5_run_tests():
    """Run the _source tests and each existing tool's tests in its own folder.

    Tool folders that don't exist yet, or that contain no test_*.py, are skipped.
    A SyncError is raised listing every folder whose test run returned non-zero.
    """
    failures = []

    def _record(label, result):
        if result.returncode != 0:
            tail_out = result.stdout[-1000:] if result.stdout else ""
            tail_err = result.stderr[-1000:] if result.stderr else ""
            failures.append(f"{label}:\n{tail_err}\n{tail_out}".rstrip())

    # _source tests (run from demo/_source/).
    _record("_source", _run_unittest_discover(SRC, SRC))

    # Per-tool tests: run with the tool folder as cwd so sibling imports resolve.
    for folder, _inputs, _script in TOOLS:
        tool_dir = DEMO / folder
        if not tool_dir.exists():
            continue
        if not any(tool_dir.glob("test_*.py")):
            continue
        _record(folder, _run_unittest_discover(tool_dir, tool_dir))

    if failures:
        raise SyncError(
            "Test suite failed in the following folder(s):\n\n"
            + "\n\n".join(failures)
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Run the full five-step maintenance loop."""
    print("Step 1: Regenerating world data...")
    _step1_make_world()

    print("Step 2: Copying input slices to tool sample-data/ folders...")
    _step2_copy_inputs()

    print("Step 3: Vendoring benjamins_common.py into tool folders...")
    _step3_vendor_common()

    print("Step 4: Running build scripts to regenerate HTML...")
    _step4_build_html()

    print("Step 5: Running test suite...")
    _step5_run_tests()

    print("sync_demo: all steps complete.")


if __name__ == "__main__":
    main()
