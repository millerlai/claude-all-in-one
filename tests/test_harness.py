"""The harness itself: prove a test can import the plugin's scripts.

Every later test starts with `import ledger` or `import preflight`. When
conftest.py's path wiring breaks, all of them fail with the same ImportError
and none of them says why -- this one does.
"""
import track_state


def test_plugin_scripts_are_importable():
    # stage_ids() reads stages.json relative to the script's own location, so
    # a passing call proves both halves: the module imported, and it found the
    # data file beside it rather than beside the test.
    assert track_state.stage_ids() == [
        "intake", "discover", "design", "build", "verify", "ship"]
