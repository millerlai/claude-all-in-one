"""validate.py builds preflight fixtures with `ledger.append()`, and that call
writes a copy of every record to the cross-project central ledger
unconditionally (ledger.py's D6). conftest.py's `_isolated_central_ledger`
keeps pytest off the developer's real `~/.claude/cai/usage.jsonl`, but
validate.py is not run by pytest -- it runs by hand, in CI, and from the
PostToolUse hook on every edit under plugins/cai/. Unisolated, each of those
runs appended a fake `design passed human` record for a track named `track`
to the file `/cai:usage` and the #85 metrics read a person's real history
from.

The subprocess is given a throwaway CLAUDE_CONFIG_DIR and no
CAI_USAGE_LEDGER, so the default central path resolves under tmp_path: if
validate.py writes there, it would have written to the real one.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")


def test_validate_writes_nothing_to_the_default_central_ledger(tmp_path):
    env = dict(os.environ)
    env.pop("CAI_USAGE_LEDGER", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = str(tmp_path)

    subprocess.run([sys.executable, VALIDATE], cwd=REPO_ROOT, env=env,
                   capture_output=True, text=True, encoding="utf-8")

    central = tmp_path / "cai" / "usage.jsonl"
    assert not central.exists(), central.read_text(encoding="utf-8")
