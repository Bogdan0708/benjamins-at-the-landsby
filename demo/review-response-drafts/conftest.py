"""Make `pytest -q` from the repo root behave like `cd` into this folder.

Every tool in demo/ is designed to be run and tested from inside its own
folder (see each tool's README: `cd demo/<tool> && python3 -m unittest`),
and its test file reads config.json / sample-data with plain relative
paths. This conftest changes the working directory to this tool's own
folder both at collection time (for module-level reads such as
`json.loads(Path("config.json").read_text())`) and for every individual
test (for reads inside setUp()/test bodies), so root-level `pytest -q`
in CI exercises the same behaviour without changing any tool or test
logic.
"""
import os
from pathlib import Path

import pytest

_TOOL_DIR = Path(__file__).parent

# Collection-time: module-level code in the test file runs with this
# directory as the working directory.
os.chdir(_TOOL_DIR)


@pytest.fixture(autouse=True)
def _tool_cwd(monkeypatch):
    # Run-time: every test in this directory gets the same working
    # directory as running it standalone from inside the folder.
    monkeypatch.chdir(_TOOL_DIR)
