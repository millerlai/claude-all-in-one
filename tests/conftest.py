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

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "plugins", "cai", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
