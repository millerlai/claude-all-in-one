"""The harness itself: prove a test can import the plugin's scripts.

Every later test starts with `import ledger` or `import preflight`. When
conftest.py's path wiring breaks, all of them fail with the same ImportError
and none of them says why -- this one does.
"""
import os

import track_state
import usage_collector


def test_plugin_scripts_are_importable():
    # stage_ids() reads stages.json relative to the script's own location, so
    # a passing call proves both halves: the module imported, and it found the
    # data file beside it rather than beside the test.
    assert track_state.stage_ids() == [
        "intake", "discover", "design", "build", "verify", "ship"]


# --- Major-5: the suite must never write to the developer's real central
# ledger. conftest.py's `_isolated_central_ledger` fixture is what keeps it
# off `~/.claude/cai/usage.jsonl` -- this asserts the env var it sets,
# rather than only relying on tests happening not to collide with a real
# file (which is how the fixture's absence went unnoticed before: 99 green,
# 4 red, but the 4 were cross-test contamination, not a guard on this). ----

def test_central_ledger_env_is_isolated_under_this_tests_tmp_path(tmp_path):
    isolated = os.environ["CAI_USAGE_LEDGER"]
    assert isolated == str(tmp_path / "isolated-usage.jsonl")

    real_path = os.path.join(os.path.expanduser("~/.claude"), "cai", "usage.jsonl")
    assert os.path.abspath(isolated) != os.path.abspath(real_path)
    assert usage_collector.central_ledger_path() == isolated
