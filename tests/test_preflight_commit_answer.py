"""preflight's `commit_answer` line (#385): the commit answer a person gave at
Gate 1, read back from the ledger note of the newest matching Approve.

The line always passes. What matters is that anything but a strict
`commit: yes` / `commit: no` at the very start of the note reads as
"unreadable", which the track treats as no.
"""
import builtins
import json
import os
import subprocess
import sys

import ledger
import preflight
import pytest

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")

DOC = ("# x\n\n## Status\napproved 2026-10-12\n\n"
       "## Work breakdown\n\n| # | Unit |\n|---|---|\n| 1 | a |\n")

NO_APPROVE = ("commit_answer (unreadable: no Approve on the ledger matches the "
              "design row's document as it stands)")
NO_DOC = "commit_answer (unreadable: the design row names no document that exists)"


def make_track(tmp_path, artifact="d-detail.md"):
    track = tmp_path / "track"
    track.mkdir(exist_ok=True)
    rows = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
            ("design", "done", artifact, ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def write_doc(tmp_path, name="d-detail.md", text=DOC):
    doc = tmp_path / name
    doc.write_text(text, encoding="utf-8")
    return str(doc)


def answer(track, tmp_path):
    ok, label = preflight.commit_answer(track, str(tmp_path))
    assert ok is True
    return label


def test_yes_and_no_name_the_ledger_line(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human",
                  note="commit: yes; approved the design")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 1)"

    ledger.append(track, "design", "passed", artifact=doc, gate="human",
                  note="commit: no")
    assert answer(track, tmp_path) == "commit_answer (no, ledger line 2)"


def test_newest_matching_approve_wins(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: no")
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 2)"


@pytest.mark.parametrize("note", [
    "", "approved after review", "…[truncated]", "Commit: yes", " commit: yes",
    "commit: yesterday", "commit:yes", "commit: maybe",
])
def test_anything_but_a_strict_marker_is_unreadable(tmp_path, note):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note=note)
    assert answer(track, tmp_path) == (
        "commit_answer (unreadable: ledger line 1's note does not start with "
        "commit: yes or commit: no)")


def test_non_string_note_is_unreadable(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    path = os.path.join(track, "ledger.jsonl")
    with open(path, encoding="utf-8") as fh:
        record = json.loads(fh.read())
    record["note"] = 7
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    assert "unreadable: ledger line 1's note" in answer(track, tmp_path)


def test_an_approve_of_another_digest_does_not_count(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    write_doc(tmp_path, text=DOC + "\nedited after sign-off\n")
    assert answer(track, tmp_path) == NO_APPROVE


def test_auto_and_failed_rows_do_not_count(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="auto", note="commit: yes")
    ledger.append(track, "design", "failed", artifact=doc, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == NO_APPROVE


def test_no_ledger_is_no_approve(tmp_path):
    write_doc(tmp_path)
    track = make_track(tmp_path)
    assert answer(track, tmp_path) == NO_APPROVE


@pytest.mark.parametrize("artifact", ["", "—", "missing.md"])
def test_design_row_without_a_document(tmp_path, artifact):
    track = make_track(tmp_path, artifact)
    assert answer(track, tmp_path) == NO_DOC


def test_no_state_md_means_no_document(tmp_path):
    track = tmp_path / "track"
    track.mkdir()
    assert answer(str(track), tmp_path) == NO_DOC


def test_unreadable_document(tmp_path, monkeypatch):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    real_open = builtins.open
    target = os.path.normcase(os.path.abspath(doc))

    def fake_open(file, *args, **kwargs):
        if isinstance(file, str) and os.path.normcase(os.path.abspath(file)) == target:
            raise OSError("denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert answer(track, tmp_path) == (
        "commit_answer (unreadable: the design row's document cannot be read)")


def test_unreadable_state_md(tmp_path):
    track = make_track(tmp_path)
    with open(os.path.join(track, "state.md"), "wb") as fh:
        fh.write(b"| stage | status | artifact | note |\n\xff\xfe\xfa\n")
    assert answer(track, tmp_path) == (
        "commit_answer (unreadable: the track's state.md or ledger cannot be read)")


# --- through main(): where the line prints --------------------------------

def run(stage, track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, stage, "--track-dir", track,
         "--project-dir", project],
        capture_output=True, text=True, encoding="utf-8")


def test_build_prints_the_line_before_ledger_attempts(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human",
                  note="commit: yes; ok")
    done = run("build", track, str(tmp_path))

    assert done.returncode == 0, done.stdout
    lines = done.stdout.splitlines()
    assert "PASS commit_answer (yes, ledger line 1)" in lines
    mine = lines.index("PASS commit_answer (yes, ledger line 1)")
    assert lines[mine + 1].startswith("PASS ledger_attempts")


def test_build_without_an_approve_still_prints_the_line(tmp_path):
    write_doc(tmp_path)
    track = make_track(tmp_path)
    done = run("build", track, str(tmp_path))

    assert done.returncode == 2
    assert "PASS " + NO_APPROVE in done.stdout.splitlines()


def test_verify_prints_the_line_even_when_blocked(tmp_path):
    write_doc(tmp_path)
    track = make_track(tmp_path)
    done = run("verify", track, str(tmp_path))  # tmp_path is not a git repo

    assert done.returncode == 2
    assert any(l.startswith("PASS commit_answer (") for l in done.stdout.splitlines())


def test_other_stages_print_no_such_line(tmp_path):
    write_doc(tmp_path)
    track = make_track(tmp_path)
    done = run("ship", track, str(tmp_path))
    assert "commit_answer" not in done.stdout
