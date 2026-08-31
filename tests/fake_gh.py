"""A reusable fake ticket CLI, run as a subprocess via CAI_TICKET_CLI.

Unit 1's own tests (test_ticket_backend.py) wrote a fresh throwaway script
per test case; this is the shared version other units reach for instead --
in particular, a `gh` that always fails, for proving code elsewhere never
calls it (AC23) rather than merely surviving when it does.

Configured entirely through the environment, not arguments: a subprocess
only inherits `os.environ`, never a pytest monkeypatch of this module
(tests/conftest.py:56, matching ticket_backend.py:26-30's own reasoning for
why CAI_TICKET_CLI itself is an environment variable).

FAKE_GH_MODE:
  "ok"   (default) -- exits 0; stdout is FAKE_GH_STDOUT (default "").
  "fail"           -- exits FAKE_GH_EXIT (default 1); stderr is
                      FAKE_GH_STDERR (default "boom").
"""
import json
import os
import sys


def main():
    mode = os.environ.get("FAKE_GH_MODE", "ok")
    if mode == "fail":
        sys.stderr.write(os.environ.get("FAKE_GH_STDERR", "boom"))
        return int(os.environ.get("FAKE_GH_EXIT", "1"))
    sys.stdout.write(os.environ.get("FAKE_GH_STDOUT", ""))
    return 0


def cli_argv():
    """The CAI_TICKET_CLI value that runs this file under the current
    interpreter -- the JSON argv array form ticket_backend.py:26-30 expects."""
    return json.dumps([sys.executable, os.path.abspath(__file__)])


if __name__ == "__main__":
    sys.exit(main())
