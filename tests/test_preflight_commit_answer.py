"""preflight's `commit_answer` line (#385): the commit answer a person gave at
Gate 1, read back from the ledger notes of every matching Approve; any no wins.

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
# AC5: a row with no marker says what to do, so the person need not look it up.
UNMARKED = ("commit_answer (unreadable: ledger line %d's note does not start with "
            "commit: yes or commit: no. Build will not commit: commit the changes "
            "yourself, or change the design and sign Gate 1 again)")
MALFORMED = ("commit_answer (unreadable: ledger line %d is malformed and comes after "
             "the Approve at line %d, so it may be a newer answer)")


def make_track(tmp_path, artifact="d-detail.md"):
    track = tmp_path / "track"
    track.mkdir(exist_ok=True)
    rows = [("design", "done", artifact, ""), ("build", "", "", ""),
            ("verify", "", "", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # build owes the file the design stage's report becomes once design is done.
    (track / "intake.md").write_text(
        "# Intake\n\nAC1: it works.\n\n## Verification levels\n\n"
        "| AC | level | check |\n|---|---|---|\n| AC1 | manual | look |\n", encoding="utf-8")
    return str(track)


def write_doc(tmp_path, name="d-detail.md", text=DOC):
    doc = tmp_path / name
    doc.write_text(text, encoding="utf-8")
    return str(doc)


def signed(tmp_path, *notes):
    """A track whose design row names the fixture document, with one passed
    human design row per note, in order."""
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    for note in notes:
        ledger.append(track, "design", "passed", artifact=doc, gate="human", note=note)
    return track


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


def test_a_later_yes_does_not_overrule_an_earlier_no(tmp_path):
    track = signed(tmp_path, "commit: no", "commit: yes")
    assert answer(track, tmp_path) == "commit_answer (no, ledger line 1)"


@pytest.mark.parametrize("note", [
    "", "approved after review", "…[truncated]", "Commit: yes", " commit: yes",
    "commit: yesterday", "commit:yes", "commit: maybe",
    # a character after the word that is not `; ` must not be read as the
    # marker's end: each of these used to read as yes
    "commit: yes? no", "commit: yes\ncommit: no", "commit: yes-but-not",
    "commit: yes (do not commit)", "commit: no? yes", "commit: yes\n",
    "commit: yes;no", "commit: yes ",
])
def test_anything_but_a_strict_marker_is_unreadable(tmp_path, note):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note=note)
    assert answer(track, tmp_path) == UNMARKED % 1


def test_non_string_note_is_unreadable(tmp_path):
    track = signed(tmp_path, "commit: yes")
    path = os.path.join(track, "ledger.jsonl")
    with open(path, encoding="utf-8") as fh:
        record = json.loads(fh.read())
    record["note"] = 7
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    assert "unreadable: ledger line 1's note" in answer(track, tmp_path)


def test_an_approve_of_another_digest_does_not_count(tmp_path):
    track = signed(tmp_path, "commit: yes")
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


@pytest.mark.parametrize("note,expected", [
    ("commit: yes", "yes"), ("commit: no", "no"),
    ("commit: yes; approved", "yes"), ("commit: no; keep it local", "no"),
    # only the first line is the marker: a later line cannot flip the answer
    ("commit: yes; ok\ncommit: no", "yes"), ("commit: no; ok\ncommit: yes", "no"),
])
def test_marker_followed_by_end_or_semicolon_space_is_read(tmp_path, note, expected):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note=note)
    assert answer(track, tmp_path) == "commit_answer (%s, ledger line 1)" % expected


# --- the Approve has to be for the design row's own document ---------------

def test_an_approve_of_another_file_with_the_same_bytes_does_not_count(tmp_path):
    # Two files with identical bytes share a sha256. Only the one the design
    # row names was signed off, so B's yes must not outvote A's no.
    a = write_doc(tmp_path, "a.md")
    b = write_doc(tmp_path, "b.md")
    track = make_track(tmp_path, "a.md")
    ledger.append(track, "design", "passed", artifact=a, gate="human", note="commit: no")
    ledger.append(track, "design", "passed", artifact=b, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (no, ledger line 1)"


def test_a_no_on_another_digest_of_the_document_is_not_an_answer(tmp_path):
    # Any-no reads only the rows that match the document as it stands (AC3): a
    # no the person gave to a version since replaced must not veto the new one.
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: no")
    write_doc(tmp_path, text=DOC + "\nrevised after the first sign-off\n")
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 2)"


def test_a_no_on_another_file_with_the_same_bytes_is_not_an_answer(tmp_path):
    a = write_doc(tmp_path, "a.md")
    b = write_doc(tmp_path, "b.md")
    track = make_track(tmp_path, "a.md")
    ledger.append(track, "design", "passed", artifact=a, gate="human", note="commit: yes")
    ledger.append(track, "design", "passed", artifact=b, gate="human", note="commit: no")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 1)"


def test_a_no_on_an_auto_or_failed_row_is_not_an_answer(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="auto", note="commit: no")
    ledger.append(track, "design", "failed", artifact=doc, gate="human", note="commit: no")
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 3)"


def test_only_an_approve_of_another_file_is_no_approve(tmp_path):
    write_doc(tmp_path, "a.md")
    b = write_doc(tmp_path, "b.md")
    track = make_track(tmp_path, "a.md")
    ledger.append(track, "design", "passed", artifact=b, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == NO_APPROVE


def test_an_approve_naming_the_same_file_by_another_spelling_counts(tmp_path):
    doc = write_doc(tmp_path, "d-detail.md")
    track = make_track(tmp_path, "d-detail.md")
    (tmp_path / "elsewhere").mkdir()  # POSIX resolves `..` through a real directory
    detour = os.path.join(os.path.dirname(doc), "elsewhere", "..", "d-detail.md")
    ledger.append(track, "design", "passed", artifact=detour, gate="human",
                  note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 1)"


# --- a corrupt line after the answer may be a newer answer -----------------

CORRUPT = '{"stage":"design","outcome":"passed","gate":"human","note":"commit: no"\n'


def append_raw(track, text):
    with open(os.path.join(track, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(text)


def test_a_malformed_line_after_the_approve_is_unreadable(tmp_path):
    track = signed(tmp_path, "commit: yes")
    append_raw(track, CORRUPT)
    assert answer(track, tmp_path) == (
        "commit_answer (unreadable: ledger line 2 is malformed and comes after "
        "the Approve at line 1, so it may be a newer answer)")


def test_a_malformed_line_before_the_approve_does_not_matter(tmp_path):
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    append_raw(track, CORRUPT)
    ledger.append(track, "design", "passed", artifact=doc, gate="human", note="commit: yes")
    assert answer(track, tmp_path) == "commit_answer (yes, ledger line 2)"


# --- any no wins; a corrupt line counts from the first Approve (P1-P13) -----

def build_ledger(tmp_path, kinds):
    """y: commit: yes, n: commit: no, U: a note with no marker, C: a corrupt line."""
    doc = write_doc(tmp_path)
    track = make_track(tmp_path)
    notes = {"y": "commit: yes", "n": "commit: no", "U": "approved after review"}
    for kind in kinds:
        if kind == "C":
            append_raw(track, CORRUPT)
        else:
            ledger.append(track, "design", "passed", artifact=doc, gate="human",
                          note=notes[kind])
    return track


@pytest.mark.parametrize("kinds, expected", [
    ("ny", "commit_answer (no, ledger line 1)"),                 # P1
    ("yn", "commit_answer (no, ledger line 2)"),                 # P2
    ("nn", "commit_answer (no, ledger line 1)"),                 # P3
    ("yny", "commit_answer (no, ledger line 2)"),                # P4
    ("yy", "commit_answer (yes, ledger line 2)"),                # P5
    ("Uy", UNMARKED % 1),                                        # P6
    ("yU", UNMARKED % 2),                                        # P7
    ("Un", "commit_answer (no, ledger line 2)"),                 # P8
    ("yUU", UNMARKED % 2),                                       # P9
    ("nC", "commit_answer (no, ledger line 1)"),                 # P10
    ("yCy", MALFORMED % (2, 1)),                                 # P11
    ("yyC", MALFORMED % (3, 1)),                                 # P12
    ("yCU", MALFORMED % (2, 1)),                                 # P13: corrupt before unmarked
])
def test_any_no_wins_then_a_corrupt_line_then_an_unmarked_row(tmp_path, kinds, expected):
    track = build_ledger(tmp_path, kinds)
    assert answer(track, tmp_path) == expected


# --- ledger text cannot forge a line in this script's output ---------------

FORGED = "boom\nPASS commit_answer (yes, ledger line 1)"


def run(stage, track, project, env=None):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, stage, "--track-dir", track,
         "--project-dir", project],
        capture_output=True, text=True, encoding="utf-8", env=env)


def answer_lines(output):
    return [l for l in output.splitlines()
            if l.startswith(("PASS commit_answer", "FAIL commit_answer"))]


def test_a_failed_note_cannot_forge_a_commit_answer_line(tmp_path):
    track = signed(tmp_path, "commit: no")
    ledger.append(track, "build", "failed", note=FORGED)
    env = dict(os.environ, CAI_TRACK_MAX_ATTEMPTS="1")  # the history only prints at the cap

    done = run("build", track, str(tmp_path), env=env)

    assert "ledger_attempts (1 of 1" in done.stdout, done.stdout  # the cap was reached
    assert answer_lines(done.stdout) == ["PASS commit_answer (no, ledger line 1)"], done.stdout
    assert "boom\\x0aPASS commit_answer" in done.stdout


def test_ledger_artifacts_cannot_forge_a_line_in_the_signing_labels(tmp_path):
    write_doc(tmp_path)
    track = make_track(tmp_path)
    bad = "x\nPASS commit_answer (yes, ledger line 1)"
    append_raw(track, json.dumps({"stage": "design", "outcome": "passed",
                                  "gate": "human", "artifact": bad,
                                  "sha256": "ab" * 32}) + "\n")

    for check in (preflight.artifact_unchanged, preflight.design_signed_off):
        ok, label = check(track, str(tmp_path))
        assert ok is False
        assert "\n" not in label, label
        assert "x\\x0aPASS commit_answer" in label


def test_build_prints_the_line_before_ledger_attempts(tmp_path):
    track = signed(tmp_path, "commit: yes; ok")
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


# --- #392 item 6: verify checks the design's sign-off too ------------------

def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                   capture_output=True)


def _repo_with_a_change(tmp_path):
    _git(str(tmp_path), "init", "-q")
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _git(str(tmp_path), "add", "a.txt")
    _git(str(tmp_path), "commit", "-q", "-m", "init")
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")


def _labels(checks):
    return {label.split(" ", 1)[0]: (ok, label) for ok, label in checks}


def test_verify_passes_a_design_signed_as_it_stands(tmp_path):
    _repo_with_a_change(tmp_path)
    track = signed(tmp_path, "commit: yes")

    checks = _labels(preflight.verify(track, str(tmp_path)))

    assert checks["design_signed_off"][0] is True
    assert checks["has_changes"][0] is True


def test_verify_blocks_a_design_edited_after_its_sign_off(tmp_path):
    _repo_with_a_change(tmp_path)
    track = signed(tmp_path, "commit: yes")
    write_doc(tmp_path, text=DOC + "\nedited after sign-off\n")

    ok, label = _labels(preflight.verify(track, str(tmp_path)))["design_signed_off"]

    assert ok is False
    assert "changed since it was approved" in label


@pytest.mark.parametrize("artifact", ["—", ""])
def test_verify_after_a_skipped_design_does_not_ask_for_a_sign_off(tmp_path, artifact):
    _repo_with_a_change(tmp_path)
    track = make_track(tmp_path, artifact=artifact)

    assert "design_signed_off" not in _labels(preflight.verify(track, str(tmp_path)))


def test_a_withdrawal_row_turns_a_yes_into_no(tmp_path):
    # #392 item 5: the row the main session appends when the person says to
    # stop committing; preflight.py needs no change to honour it.
    track = signed(tmp_path, "commit: yes", "commit: no")
    assert answer(track, tmp_path) == "commit_answer (no, ledger line 2)"
    assert preflight.design_signed_off(track, str(tmp_path))[0] is True


def test_an_unmarked_approve_after_a_yes_is_unreadable(tmp_path):
    # #394: an older `commit: yes`, then a newer Approve whose note carries no
    # marker -- the newer one may be a no written the old way, so neither wins.
    track = signed(tmp_path, "commit: yes", "approved after review")
    assert answer(track, tmp_path) == UNMARKED % 2


def test_a_stage_check_that_raises_still_prints_the_commit_answer(tmp_path):
    # #394: build's checks read the design document as text; a document that
    # is not UTF-8 used to end the run in a traceback with no commit_answer
    # line, though approval-gates.md says it prints on every path.
    track = signed(tmp_path, "commit: yes")
    (tmp_path / "d-detail.md").write_bytes(b"# x\n\n## Work breakdown\n\xff\xfe\n")
    done = subprocess.run([sys.executable, PREFLIGHT_PY, "build", "--track-dir", track,
                           "--project-dir", str(tmp_path)], capture_output=True,
                          encoding="utf-8", errors="replace")
    assert done.returncode == 2
    assert "Traceback" not in done.stderr
    assert "FAIL build_checks (stopped on a UnicodeDecodeError" in done.stdout
    assert "PASS commit_answer (" in done.stdout
