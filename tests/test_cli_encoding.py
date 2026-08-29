"""Every one of these CLIs prints prose a person wrote, so every one has to
print UTF-8.

On Windows a piped stdout defaults to the ANSI codepage, and the caller --
the track skill, reading the output back -- gets bytes it cannot decode. The
note column of state.md, a ledger note and preflight's quoting of that note
all carry whatever alphabet the author uses, so all three entry points
reconfigure their streams. This asserts on raw bytes rather than letting the
subprocess decode, because a decode with the right encoding would pass
whatever the script actually wrote.
"""
import os
import subprocess
import sys

import ledger

SCRIPTS = os.path.dirname(ledger.__file__)
REASON = "三個未知都在別的 repo"

ROWS = [("intake", "done", "—", ""), ("discover", "", "", ""),
        ("design", "", "", ""), ("build", "", "", ""),
        ("verify", "", "", ""), ("ship", "", "", "")]


def make_track(tmp_path, rows=ROWS):
    root = tmp_path / "track"
    (root / "billing").mkdir(parents=True)
    (root / "current").write_text("billing", encoding="utf-8")
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (root / "billing" / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(root), str(root / "billing")


def run(script, *args):
    """Raw bytes, deliberately: decoding here would hide what was written."""
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True)


def test_track_state_status_prints_utf8(tmp_path):
    rows = list(ROWS)
    rows[1] = ("discover", "skipped", "—", REASON)
    root, _ = make_track(tmp_path, rows)

    done = run("track_state.py", "status", "--track-root", root)
    assert done.returncode == 0, done.stderr
    assert REASON in done.stdout.decode("utf-8")


def test_ledger_show_prints_utf8(tmp_path):
    _, track = make_track(tmp_path)
    ledger.append(track, "discover", "failed", note=REASON)

    done = run("ledger.py", "show", "--track-dir", track)
    assert done.returncode == 0, done.stderr
    text = done.stdout.decode("utf-8")
    assert REASON in text
    # `—` is the no-artifact sentinel and was the first thing to break here.
    assert "—" in text


def test_preflight_quotes_the_notes_in_utf8(tmp_path):
    _, track = make_track(tmp_path)
    for _ in range(5):
        ledger.append(track, "discover", "failed", note=REASON)

    done = run("preflight.py", "discover", "--track-dir", track)
    assert done.returncode == 2
    assert REASON in done.stdout.decode("utf-8")
