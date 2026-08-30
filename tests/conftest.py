"""Puts the plugin's scripts on sys.path so the tests can import them.

The scripts are not a package -- they are standalone files the model runs
through `python <path>`, and `plugins/cai/scripts/` has no `__init__.py` by
design. So a test that wants `import ledger` needs the directory itself on
the path, which is what this does.

`tests/` lives at the repo root rather than under `plugins/cai/` on purpose:
`.claude-plugin/marketplace.json:11` ships `./plugins/cai` and nothing else,
so neither these tests nor pytest can reach an installed copy.
"""
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "plugins", "cai", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


@pytest.fixture(autouse=True)
def _no_live_session(monkeypatch):
    """Keeps the suite off the developer's real transcripts.

    `ledger.append()` reads `CLAUDE_CODE_SESSION_ID` and, when it resolves,
    scans that session's transcripts under `~/.claude/projects/`. That
    variable is set inside Claude Code and unset in CI, so without this the
    same test exercises a different branch on each -- and a green run here
    would say nothing about the run that matters. It also charged the suite
    60% wall-clock (10.4s vs 6.5s, measured 2026-08-30) reading a file that
    only grows.

    A test that wants the collecting branch monkeypatches
    `usage_collector.collect` itself, which is deterministic; this fixture
    only removes the ambient one.
    """
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


@pytest.fixture(autouse=True)
def _isolated_central_ledger(tmp_path, monkeypatch):
    """Keeps the suite off the developer's real central ledger.

    Unlike `_no_live_session` above, which only gates the collecting branch,
    `ledger.append()` writes a copy of every record to the cross-project
    ledger at `usage_collector.central_ledger_path()` unconditionally --
    passing or failing session id makes no difference. Without this,
    `python -m pytest` would create and append to
    `~/.claude/cai/usage.jsonl` on whatever machine runs the suite, mixing
    fake test records into the file this feature exists to let a person
    query their own real spend from.

    Set through the environment, not a direct monkeypatch of
    `usage_collector.central_ledger_path()`: the concurrency test spawns
    subprocesses that never see a monkeypatch, only what they inherit in
    `os.environ` -- which is exactly why `CAI_USAGE_LEDGER` exists (D14). A
    test that wants a specific central-ledger path overrides this value
    itself; it is only the ambient default this removes.
    """
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(tmp_path / "isolated-usage.jsonl"))
