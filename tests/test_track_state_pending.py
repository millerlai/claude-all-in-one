"""`track_state.py status` and a stage's saved pending questions.

With no pending.md the output must be exactly what it was before pending.md
existed, and git must not be asked anything. With one, status adds a
`pending:` section after `next:`, reading the branch and HEAD live because the
file does not store them. A file it cannot use costs one line, never the exit
code, and a file for a stage that already finished is ignored.
"""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import pending
import preflight
import track_state

SCRIPT = os.path.join(os.path.dirname(track_state.__file__), "track_state.py")

ROWS = [("intake", "done", "—", ""), ("discover", "skipped", "—", "not needed"),
        ("design", "done", "—", ""), ("build", "in-progress", "—", "unit 2 of 4"),
        ("verify", "", "", ""), ("ship", "", "", "")]
OTHER_ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
              ("design", "", "", ""), ("build", "", "", ""),
              ("verify", "", "", ""), ("ship", "", "", "")]

# Captured from track_state.py on main before any of this change existed.
BASELINE = (
    "current: billing\n"
    "intake     done\n"
    "discover   skipped  (reason: not needed)\n"
    "design     done\n"
    "build      in-progress\n"
    "verify     \n"
    "ship       \n"
    "\n"
    "next: build\n"
    "skipped:\n"
    "  discover: not needed\n"
    "other active tracks: other\n"
    "  other  stopped at: design (not started)\n")

REPORT = (
    "## Pending questions\n"
    "1. Commit per unit?\n"
    "   Background: a\n   Options: b\n   Blocks: c\n"
    "2. Parallel lane?\n"
    "   Background: a\n   Options: b\n   Blocks: c\n")


def _state(rows):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "track"
    for name, rows in (("billing", ROWS), ("other", OTHER_ROWS)):
        (r / name).mkdir(parents=True)
        (r / name / "state.md").write_bytes(_state(rows).encode("utf-8"))
    (r / "current").write_text("billing", encoding="utf-8")
    return str(r)


def _pending_file(root, stage="build", rnd=1, answered=()):
    track_dir = os.path.join(root, "billing")
    report = os.path.join(os.path.dirname(root), "report.md")
    with open(report, "wb") as fh:
        fh.write(REPORT.encode("utf-8"))
    pending.start(track_dir, stage, rnd, report)
    for n in answered:
        ans = os.path.join(os.path.dirname(root), "a%d.md" % n)
        with open(ans, "wb") as fh:
            fh.write(b"yes")
        pending.answer(track_dir, n, ans)
    return os.path.join(track_dir, "pending.md")


def _git_answers(monkeypatch, branch="track/x", sha="abc1234", calls=None):
    def fake(cwd, *args, **kw):
        if calls is not None:
            calls.append(args)
        out = {"--abbrev-ref": branch, "--short": sha}[args[1]]
        return SimpleNamespace(returncode=0, stdout=out + "\n", stderr="")
    monkeypatch.setattr(preflight, "git", fake)


def _status(root, capsys):
    code = track_state.status(root)
    out = capsys.readouterr()
    return code, out.out, out.err


def _after_next(extra):
    return BASELINE.replace("skipped:\n", extra + "skipped:\n", 1)


def test_no_pending_file_output_is_the_old_output_byte_for_byte(root):
    done = subprocess.run([sys.executable, SCRIPT, "status", "--track-root", root],
                          capture_output=True, text=True, encoding="utf-8")
    assert (done.returncode, done.stdout, done.stderr) == (0, BASELINE, "")


def test_no_pending_file_asks_git_nothing(root, capsys, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a subprocess was started with no pending.md")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(preflight, "git", boom)
    assert _status(root, capsys) == (0, BASELINE, "")


def test_pending_section_follows_next_and_reads_the_live_branch(root, capsys, monkeypatch):
    path = _pending_file(root)
    calls = []
    _git_answers(monkeypatch, calls=calls)
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    assert out == _after_next(
        "pending: build, round 1, 0 of 2 answered\n"
        "  file: %s\n"
        "  1. [open] Commit per unit?\n"
        "  2. [open] Parallel lane?\n"
        "  on: track/x at abc1234\n"
        "  resume: /cai:track\n" % path)
    assert len(calls) == 2


def test_answered_questions_are_counted_and_marked(root, capsys, monkeypatch):
    _pending_file(root, rnd=2, answered=(2,))
    _git_answers(monkeypatch)
    _, out, _ = _status(root, capsys)
    assert "pending: build, round 2, 1 of 2 answered\n" in out
    assert "  1. [open] Commit per unit?\n  2. [answered] Parallel lane?\n" in out


@pytest.mark.parametrize("fake, line", [
    (lambda cwd, *a, **k: None, "  on: unknown (git did not answer)\n"),
    (lambda cwd, *a, **k: SimpleNamespace(returncode=128, stdout="", stderr="fatal"),
     "  on: unknown (not a git repository)\n"),
])
def test_git_not_answering_is_said_and_the_exit_code_is_unchanged(
        root, capsys, monkeypatch, fake, line):
    _pending_file(root)
    monkeypatch.setattr(preflight, "git", fake)
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    assert line + "  resume: /cai:track\n" in out


def test_a_detached_head_is_named_as_one(root, capsys, monkeypatch):
    _pending_file(root)
    _git_answers(monkeypatch, branch="HEAD")
    assert "  on: (detached HEAD) at abc1234\n" in _status(root, capsys)[1]


def test_unknown_format_number_costs_one_line_only(root, capsys, monkeypatch):
    path = os.path.join(root, "billing", "pending.md")
    with open(path, "wb") as fh:
        fh.write(b"# pending questions\nformat: 7\nstage: build\n")
    monkeypatch.setattr(preflight, "git", lambda *a, **k: pytest.fail("git was asked"))
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    assert out == _after_next(
        "pending: pending.md has format 7, which this version does not read; ignored\n")


def test_a_non_ascii_digit_in_the_header_costs_one_line_not_a_traceback(root, capsys, monkeypatch):
    path = _pending_file(root)
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8")
    with open(path, "wb") as fh:
        fh.write(text.replace("round: 1", "round: ²", 1).encode("utf-8"))
    monkeypatch.setattr(preflight, "git", lambda *a, **k: pytest.fail("git was asked"))
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    extra = [ln for ln in out.splitlines(keepends=True)
             if ln not in BASELINE.splitlines(keepends=True)]
    assert len(extra) == 1 and extra[0].startswith("pending: ") and "ignored" in extra[0]
    assert out.replace(extra[0], "") == BASELINE


def test_a_malformed_file_costs_one_line_only(root, capsys, monkeypatch):
    path = os.path.join(root, "billing", "pending.md")
    with open(path, "wb") as fh:
        fh.write(b"not what pending.py writes\n")
    monkeypatch.setattr(preflight, "git", lambda *a, **k: pytest.fail("git was asked"))
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    lines = out.splitlines(keepends=True)
    extra = [ln for ln in lines if ln not in BASELINE.splitlines(keepends=True)]
    assert len(extra) == 1 and extra[0].startswith("pending: ") and "ignored" in extra[0]
    assert out.replace(extra[0], "") == BASELINE


@pytest.mark.parametrize("stage, status", [("design", "done"), ("discover", "skipped")])
def test_a_file_for_a_finished_stage_is_stale_and_ignored(root, capsys, monkeypatch, stage, status):
    _pending_file(root, stage=stage)
    monkeypatch.setattr(preflight, "git", lambda *a, **k: pytest.fail("git was asked"))
    code, out, err = _status(root, capsys)
    assert (code, err) == (0, "")
    assert out == _after_next(
        "pending: pending.md is for %s, which is already %s; stale, ignored\n"
        % (stage, status))
    assert "Commit per unit" not in out
