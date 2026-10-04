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
  "script"         -- a different answer per call. FAKE_GH_SCRIPT is a JSON
                      file: [{"match": "<substring of the argv joined by
                      spaces>", "responses": [{"stdout": "", "stderr": "",
                      "exit": 0, "sleep": 0}, ...]}]. The first entry whose
                      `match` occurs in this call is used; it answers with
                      response k, k being how many earlier calls in
                      FAKE_GH_LOG matched it too (the last response repeats
                      once they run out). FAKE_GH_LOG gets one
                      json.dumps(argv) line appended per call, matched or not.
                      No entry matches -> exit 1, "fake gh: no scripted
                      response".
"""
import json
import os
import sys
import time


def _scripted():
    argv = sys.argv[1:]
    joined = " ".join(argv)
    log = os.environ.get("FAKE_GH_LOG", "")
    try:
        with open(os.environ["FAKE_GH_SCRIPT"], encoding="utf-8") as fh:
            entries = json.load(fh)
        entry = next((e for e in entries if e["match"] in joined), None)
        earlier = 0
        if entry is not None and log and os.path.exists(log):
            with open(log, encoding="utf-8") as fh:
                earlier = sum(1 for line in fh if line.strip()
                              and entry["match"] in " ".join(json.loads(line)))
    except (KeyError, OSError, ValueError, TypeError):
        sys.stderr.write("fake gh: cannot read FAKE_GH_SCRIPT")
        return 1
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(argv) + "\n")
    if entry is None:
        sys.stderr.write("fake gh: no scripted response")
        return 1
    responses = entry["responses"]
    response = responses[min(earlier, len(responses) - 1)]
    time.sleep(response.get("sleep", 0))
    sys.stderr.write(response.get("stderr", ""))
    sys.stdout.write(response.get("stdout", ""))
    return int(response.get("exit", 0))


def main():
    mode = os.environ.get("FAKE_GH_MODE", "ok")
    if mode == "script":
        return _scripted()
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
