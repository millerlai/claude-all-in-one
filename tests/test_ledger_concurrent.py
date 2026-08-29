"""R6: two sessions on one track must not corrupt the ledger.

This is the only test here that checks a promise the platform makes rather
than one this repo makes, and the only one that can legitimately go red on a
machine where the code is fine. Read the failure message before the diff.
"""
import json
import os
import subprocess
import sys

import ledger

SCRIPTS = os.path.dirname(ledger.__file__)
WRITERS = 8
PER_WRITER = 50

WORKER = '''
import sys
sys.path.insert(0, %r)
import ledger

track, tag, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
for n in range(count):
    # Long enough that a torn write lands mid-record rather than between two
    # tiny ones, which is the failure this test exists to catch.
    ledger.append(track, "build", "failed", note="%%s-%%04d-%%s" %% (tag, n, "x" * 300))
''' % SCRIPTS

WHY_RED = """
%d writers x %d appends should leave %d intact lines; found %d line(s), %d
unparseable.

This does not mean ledger.py is wrong. It means os.O_APPEND is not atomic on
this filesystem, which is what design decision D11 anticipates: on Windows the
CRT's _O_APPEND seeks then writes as two steps, so two processes can take the
same offset. The fix is D11's msvcrt.locking() fallback in append(), not a
change to the record format.
"""


def test_concurrent_appends_neither_tear_nor_vanish(tmp_path):
    track = str(tmp_path)
    worker = tmp_path / "worker.py"
    worker.write_text(WORKER, encoding="utf-8")

    running = [subprocess.Popen(
        [sys.executable, str(worker), track, "w%d" % index, str(PER_WRITER)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for index in range(WRITERS)]
    for process in running:
        _, err = process.communicate()
        assert process.returncode == 0, err.decode("utf-8", "replace")

    with open(os.path.join(track, "ledger.jsonl"), "rb") as fh:
        lines = [line for line in fh.read().split(b"\n") if line]

    torn = 0
    for line in lines:
        try:
            json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            torn += 1

    expected = WRITERS * PER_WRITER
    assert (len(lines), torn) == (expected, 0), WHY_RED % (
        WRITERS, PER_WRITER, expected, len(lines), torn)

    # Every writer's every append is present -- a count alone would pass if one
    # process lost a line and another somehow gained one.
    notes = {r["note"].split("-")[0] + "-" + r["note"].split("-")[1]
             for r in ledger.records(track) if not r.get("malformed")}
    assert len(notes) == expected
    assert not ledger.malformed_lines(track)
