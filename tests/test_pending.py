"""pending.py is the only writer of a track's pending.md: the questions a
stage handed up under `## Pending questions`, the round's whole report, and
the answers so far. It writes strictly (refuse and write nothing) and the
status reader forgives, so these tests hold the writer to the first half.
"""
import os
import subprocess
import sys

import pytest

import pending

SCRIPT = os.path.join(os.path.dirname(pending.__file__), "pending.py")

REPORT = (
    "## Report\n"
    "- what was built: nothing yet\n"
    "\n"
    "## Pending questions\n"
    "1. Commit per unit?\n"
    "   Background: workflow.md says never commit (stage-build.md:196)\n"
    "   Options: (a) yes (recommended) - costs 4 commits; (b) no\n"
    "   Blocks: the commit after unit 1\n"
    "   Why asked: gate - committing is the person's call every time\n"
    "2. Parallel lane?\n"
    "   Background: units depend linearly\n"
    "   Options: (a) no (recommended); (b) yes\n"
    "   Blocks: nothing\n"
    "   Why asked: outward - a lane touches the shared branch\n"
)


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "feat"
    d.mkdir()
    return d


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return str(p)


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, encoding="utf-8")


def _start(track, tmp_path, report=REPORT, stage="build", rnd=1):
    return _run("start", "--track-dir", str(track), "--stage", stage,
                "--round", str(rnd), "--report-file",
                _write(tmp_path, "report.md", report))


def _only_pending(track):
    """Anything in the track dir that is not pending.md is a leaked temp file."""
    return sorted(os.listdir(track))


def test_start_writes_the_documented_file_verbatim(track, tmp_path):
    done = _start(track, tmp_path)
    assert done.returncode == 0, done.stderr
    text = (track / "pending.md").read_text(encoding="utf-8")
    q1 = ("1. Commit per unit?\n"
          "   Background: workflow.md says never commit (stage-build.md:196)\n"
          "   Options: (a) yes (recommended) - costs 4 commits; (b) no\n"
          "   Blocks: the commit after unit 1\n"
          "   Why asked: gate - committing is the person's call every time")
    assert text.startswith("# pending questions\nformat: 1\nstage: build\n"
                           "round: 1\nquestions: 2\n\n"
                           "## question 1 [open] (5 lines)\n" + q1 + "\n\n"
                           "## question 2 [open] (5 lines)\n2. Parallel lane?\n")
    assert text.endswith("\n## report (%d lines)\n%s" % (
        len(REPORT.rstrip("\n").split("\n")), REPORT))
    assert _only_pending(track) == ["pending.md"]


def test_load_round_trips_questions_report_and_chinese_text(track, tmp_path):
    report = ("## Pending questions\n1. 要不要 commit？\n   Background: 見 a.py:1\n"
              "   Options: (a) 是\n   Blocks: 單元 1\n   Why asked: gate - 要問\n")
    assert _start(track, tmp_path, report).returncode == 0
    data = pending.load(str(track / "pending.md"))
    assert (data["format"], data["stage"], data["round"]) == (1, "build", 1)
    assert [q["status"] for q in data["questions"]] == ["open"]
    assert data["questions"][0]["text"].splitlines()[0] == "1. 要不要 commit？"
    assert data["report"] == report.rstrip("\n")


def test_load_reads_a_file_saved_with_windows_line_endings(track, tmp_path):
    assert _start(track, tmp_path).returncode == 0
    path = track / "pending.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert len(pending.load(str(path))["questions"]) == 2


@pytest.mark.parametrize("key", ["format", "round", "questions"])
def test_load_refuses_a_non_ascii_digit_header_with_pending_error(track, tmp_path, key):
    """`str.isdigit()` is true for a superscript two, and int() then raises
    ValueError -- load() promises PendingError and nothing else."""
    assert _start(track, tmp_path).returncode == 0
    path = track / "pending.md"
    text = path.read_text(encoding="utf-8")
    path.write_bytes(text.replace("%s: " % key, "%s: ²" % key, 1)
                     .replace("²" + {"format": "1", "round": "1",
                                          "questions": "2"}[key], "²", 1)
                     .encode("utf-8"))
    with pytest.raises(pending.PendingError):
        pending.load(str(path))


def test_crlf_input_is_stored_with_lf(track, tmp_path):
    assert _start(track, tmp_path, REPORT.replace("\n", "\r\n")).returncode == 0
    assert b"\r" not in (track / "pending.md").read_bytes()


@pytest.mark.parametrize("report, why", [
    ("## Report\nno section here\n", "no `## Pending questions`"),
    ("## Pending questions\n", "no numbered question"),
    ("## Pending questions\nprose first\n1. q\n   Background: b\n"
     "   Options: o\n   Blocks: x\n   Why asked: gate - r\n", "text before question 1"),
    ("## Pending questions\n1. q\n   Background: b\n   Options: o\n"
     "   Why asked: gate - r\n", "no Blocks"),
    ("## Pending questions\n1. q\n   Options: o\n   Blocks: x\n"
     "   Why asked: gate - r\n", "no Background"),
    ("## Pending questions\n1. q\n   Background: b\n   Options: o\n   Blocks: x\n",
     "no Why asked"),
    ("## Pending questions\n1. q\n   Background: b\n   Options: o\n   Blocks: x\n"
     "   Why asked: because\n", "bad Why asked value"),
    ("## Pending questions\n2. q\n   Background: b\n   Options: o\n"
     "   Blocks: x\n   Why asked: gate - r\n", "starts at 2"),
    ("## Pending questions\n1. q\n   Background: b\n   Options: o\n"
     "   Blocks: x\n   Why asked: gate - r\n3. r\n   Background: b\n   Options: o\n"
     "   Blocks: x\n   Why asked: gate - r\n", "gap"),
    ("", "empty report"),
])
def test_unusable_report_is_refused_and_nothing_is_written(track, tmp_path, report, why):
    done = _start(track, tmp_path, report)
    assert done.returncode == 2, why
    assert done.stderr.strip(), why
    assert _only_pending(track) == [], why


@pytest.mark.parametrize("args", [
    {"rnd": 0}, {"rnd": 4}, {"stage": "deploy"},
])
def test_bad_round_or_stage_is_refused_and_nothing_is_written(track, tmp_path, args):
    assert _start(track, tmp_path, **args).returncode == 2
    assert _only_pending(track) == []


def test_missing_report_file_or_track_dir_is_refused(track, tmp_path):
    done = _run("start", "--track-dir", str(track), "--stage", "build",
                "--round", "1", "--report-file", str(tmp_path / "nope.md"))
    assert done.returncode == 2 and _only_pending(track) == []
    done = _run("start", "--track-dir", str(tmp_path / "gone"), "--stage", "build",
                "--round", "1", "--report-file", _write(tmp_path, "r.md", REPORT))
    assert done.returncode == 2


def test_start_for_the_same_stage_replaces_the_round(track, tmp_path):
    assert _start(track, tmp_path).returncode == 0
    assert _start(track, tmp_path, rnd=2).returncode == 0
    assert pending.load(str(track / "pending.md"))["round"] == 2


def test_start_refuses_while_another_stage_is_pending(track, tmp_path):
    assert _start(track, tmp_path).returncode == 0
    before = (track / "pending.md").read_bytes()
    done = _start(track, tmp_path, stage="design")
    assert done.returncode == 2 and "build" in done.stderr
    assert (track / "pending.md").read_bytes() == before


def _state(track, **statuses):
    rows = "".join("| %s | %s | — | |\n" % kv for kv in statuses.items())
    (track / "state.md").write_text(
        "# fixture\n\n| stage | status | artifact | note |\n|---|---|---|---|\n" + rows,
        encoding="utf-8")


@pytest.mark.parametrize("finished", ["done", "skipped"])
def test_start_replaces_a_file_left_by_a_finished_stage(track, tmp_path, finished):
    # status prints such a file as "stale, ignored"; the writer must agree, or
    # one session that ended before `clear` costs every later stage its round.
    assert _start(track, tmp_path, stage="design").returncode == 0
    _state(track, design=finished, build="in-progress")
    done = _start(track, tmp_path, stage="build")
    assert done.returncode == 0, done.stderr
    assert pending.load(str(track / "pending.md"))["stage"] == "build"
    assert _only_pending(track) == ["pending.md", "state.md"]


@pytest.mark.parametrize("unfinished", ["in-progress", "blocked", ""])
def test_start_still_refuses_another_stage_that_has_not_finished(track, tmp_path, unfinished):
    assert _start(track, tmp_path, stage="design").returncode == 0
    _state(track, design=unfinished, build="in-progress")
    before = (track / "pending.md").read_bytes()
    done = _start(track, tmp_path, stage="build")
    assert done.returncode == 2 and "design" in done.stderr
    assert (track / "pending.md").read_bytes() == before


def test_round_three_is_accepted(track, tmp_path):
    assert _start(track, tmp_path, rnd=3).returncode == 0
    assert pending.load(str(track / "pending.md"))["round"] == 3


# A prescribed stop (#374) is a hand-up the procedure itself calls for. It
# spends no round, so --stop takes the rounds already spent, zero included.
def _stop(track, tmp_path, rnd):
    return _run("start", "--track-dir", str(track), "--stage", "build",
                "--round", str(rnd), "--stop", "--report-file",
                _write(tmp_path, "report.md", REPORT))


def test_a_prescribed_stop_is_accepted_before_any_round_is_spent(track, tmp_path):
    done = _stop(track, tmp_path, 0)
    assert done.returncode == 0, done.stderr
    assert pending.load(str(track / "pending.md"))["round"] == 0


def test_a_prescribed_stop_keeps_the_rounds_already_spent(track, tmp_path):
    assert _start(track, tmp_path, rnd=2).returncode == 0
    assert _stop(track, tmp_path, 2).returncode == 0
    assert pending.load(str(track / "pending.md"))["round"] == 2


def test_stop_does_not_lift_the_cap(track, tmp_path):
    assert _stop(track, tmp_path, 4).returncode == 2
    assert _only_pending(track) == []


def test_an_answer_to_the_first_of_two_questions_reads_back(track, tmp_path):
    _start(track, tmp_path)
    for n, expect in ((1, ["answered", "open"]), (2, ["answered", "answered"])):
        done = _run("answer", "--track-dir", str(track), "--question", str(n),
                    "--answer-file", _write(tmp_path, "a%d.md" % n, "yes %d" % n))
        assert done.returncode == 0, done.stderr
        data = pending.load(str(track / "pending.md"))
        assert [q["status"] for q in data["questions"]] == expect
    assert [q["answer"] for q in data["questions"]] == ["yes 1", "yes 2"]


def test_text_that_looks_like_section_headers_survives_verbatim(track, tmp_path):
    tricky = "## report (2 lines)\n## answer 1 (1 lines)\n\n## question 9 [open] (1 lines)"
    report = REPORT + "\n## Report\nsee below\n" + tricky + "\n"
    assert _start(track, tmp_path, report).returncode == 0
    done = _run("answer", "--track-dir", str(track), "--question", "1",
                "--answer-file", _write(tmp_path, "a.md", tricky))
    assert done.returncode == 0, done.stderr
    data = pending.load(str(track / "pending.md"))
    assert data["questions"][0]["answer"] == tricky
    assert data["report"].endswith(tricky)
    assert len(data["questions"]) == 2


def test_a_truncated_file_is_refused_never_half_read(track, tmp_path):
    _start(track, tmp_path)
    path = track / "pending.md"
    lines = path.read_bytes().split(b"\n")
    # The last two cuts are exempt: dropping exactly the final line leaves the
    # file's trailing blank line to stand in for it, which the format cannot
    # tell apart. Writes are atomic, so only a hand edit gets there.
    for keep in range(1, len(lines) - 2):
        path.write_bytes(b"\n".join(lines[:keep]) + b"\n")
        with pytest.raises(pending.PendingError):
            pending.load(str(path))


def test_answer_marks_answered_and_stores_the_answer_verbatim(track, tmp_path):
    _start(track, tmp_path)
    answer = "A 是，每單元 commit (推薦)\nsecond line"
    done = _run("answer", "--track-dir", str(track), "--question", "2",
                "--answer-file", _write(tmp_path, "a.md", answer + "\n"))
    assert done.returncode == 0, done.stderr
    data = pending.load(str(track / "pending.md"))
    assert [q["status"] for q in data["questions"]] == ["open", "answered"]
    assert data["questions"][1]["answer"] == answer
    assert data["questions"][0].get("answer") is None
    assert _only_pending(track) == ["pending.md"]


def test_answer_refusals_leave_the_file_byte_identical(track, tmp_path):
    _start(track, tmp_path)
    ok = _write(tmp_path, "a.md", "yes")
    assert _run("answer", "--track-dir", str(track), "--question", "1",
                "--answer-file", ok).returncode == 0
    before = (track / "pending.md").read_bytes()
    for q, f in [("1", ok),                                  # already answered
                 ("3", ok), ("0", ok), ("x", ok),            # no such question
                 ("2", _write(tmp_path, "blank.md", " \n")),  # empty answer
                 ("2", str(tmp_path / "nope.md"))]:           # unreadable
        done = _run("answer", "--track-dir", str(track), "--question", q,
                    "--answer-file", f)
        assert done.returncode != 0, (q, f)
        assert (track / "pending.md").read_bytes() == before, (q, f)


def test_answer_without_a_pending_file_is_refused(track, tmp_path):
    done = _run("answer", "--track-dir", str(track), "--question", "1",
                "--answer-file", _write(tmp_path, "a.md", "yes"))
    assert done.returncode == 2 and _only_pending(track) == []


def test_answer_on_an_unknown_format_number_is_refused(track, tmp_path):
    (track / "pending.md").write_text("# pending questions\nformat: 9\n", encoding="utf-8")
    done = _run("answer", "--track-dir", str(track), "--question", "1",
                "--answer-file", _write(tmp_path, "a.md", "yes"))
    assert done.returncode == 2 and "format 9" in done.stderr
    assert (track / "pending.md").read_text(encoding="utf-8") == \
        "# pending questions\nformat: 9\n"


def test_clear_removes_the_file_for_that_stage_only(track, tmp_path):
    _start(track, tmp_path)
    other = _run("clear", "--track-dir", str(track), "--stage", "design")
    assert other.returncode == 0 and (track / "pending.md").exists()
    done = _run("clear", "--track-dir", str(track), "--stage", "build")
    assert done.returncode == 0 and not (track / "pending.md").exists()


def test_clear_with_no_file_is_a_no_op_that_succeeds(track):
    assert _run("clear", "--track-dir", str(track), "--stage", "build").returncode == 0


def test_clear_refuses_a_file_it_cannot_read(track):
    (track / "pending.md").write_text("garbage\n", encoding="utf-8")
    done = _run("clear", "--track-dir", str(track), "--stage", "build")
    assert done.returncode == 2 and (track / "pending.md").exists()


def test_a_failed_replace_exits_non_zero_and_leaves_nothing(track, tmp_path, monkeypatch, capsys):
    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(pending.os, "replace", boom)
    code = pending.main(["start", "--track-dir", str(track), "--stage", "build",
                         "--round", "1", "--report-file",
                         _write(tmp_path, "r.md", REPORT)])
    assert code != 0
    assert "disk full" in capsys.readouterr().err
    assert _only_pending(track) == []


def test_usage_error_exits_1():
    assert _run("start").returncode == 1


def _run_stdin(text, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], input=text.encode("utf-8"),
                          capture_output=True)


def test_report_and_answer_read_from_stdin_match_the_file_path_form(tmp_path):
    # #345: `-` lets a POSIX shell pipe the text in, so there is no scratch
    # file to write, nor one Codex would stop to approve deleting.
    by_file, by_stdin = tmp_path / "file" / "track", tmp_path / "stdin" / "track"
    for t in (by_file, by_stdin):
        t.mkdir(parents=True)
    report = REPORT.replace("\n", "\r\n")  # line endings and a BOM are normalised the same way
    answer = "﻿選 B，因為「它」不改 API。\r\n"
    assert _run("start", "--track-dir", str(by_file), "--stage", "build", "--round", "1",
                "--report-file", _write(tmp_path, "r.md", report)).returncode == 0
    assert _run("answer", "--track-dir", str(by_file), "--question", "1",
                "--answer-file", _write(tmp_path, "a.txt", answer)).returncode == 0
    start = _run_stdin(report, "start", "--track-dir", str(by_stdin), "--stage", "build",
                       "--round", "1", "--report-file", "-")
    assert start.returncode == 0, start.stderr
    reply = _run_stdin(answer, "answer", "--track-dir", str(by_stdin), "--question", "1",
                       "--answer-file", "-")
    assert reply.returncode == 0, reply.stderr
    assert (by_stdin / "pending.md").read_bytes() == (by_file / "pending.md").read_bytes()
    assert _only_pending(by_stdin) == ["pending.md"]


SPLIT = ("## Pending questions\n1. Which db?\n   Background: b\n   Options: o\n"
         "   Blocks: x\n   Why asked: evidence-split - both fit the repo\n")


@pytest.fixture
def proj_track(tmp_path):
    """<project>/.cai/track/<feature>, the layout answer() derives the project from."""
    d = tmp_path / "proj" / ".cai" / "track" / "feat"
    d.mkdir(parents=True)
    return d


def _answer(track, tmp_path, n=1, text="Postgres"):
    return _run("answer", "--track-dir", str(track), "--question", str(n),
                "--answer-file", _write(tmp_path, "a%d.md" % n, text))


def test_an_evidence_split_answer_is_appended_to_answers_md(proj_track, tmp_path):
    assert _start(proj_track, tmp_path, SPLIT).returncode == 0
    done = _answer(proj_track, tmp_path)
    assert done.returncode == 0, done.stderr
    target = tmp_path / "proj" / ".cai" / "answers.md"
    assert "answers: appended to %s" % target in done.stdout.splitlines()
    row = target.read_text(encoding="utf-8").splitlines()[-1]
    assert row.endswith("| feat | 1. Which db? | Postgres |"), row
    assert pending.load(str(proj_track / "pending.md"))["questions"][0]["answer"] == "Postgres"


def test_a_gate_answer_is_saved_but_not_recorded(proj_track, tmp_path):
    assert _start(proj_track, tmp_path).returncode == 0   # q1 is `gate`
    done = _answer(proj_track, tmp_path, 1, "yes")
    assert done.returncode == 0, done.stderr
    assert "answers: not recorded (Why asked: gate - committing is the person's call "\
        "every time)" in done.stdout.splitlines()
    assert not (tmp_path / "proj" / ".cai" / "answers.md").exists()
    assert pending.load(str(proj_track / "pending.md"))["questions"][0]["answer"] == "yes"


def test_an_old_file_without_why_asked_still_loads_and_answers(proj_track, tmp_path):
    old = ("## Pending questions\n1. Old?\n   Background: b\n   Options: o\n   Blocks: x\n")
    questions = [{"text": "1. Old?\n   Background: b\n   Options: o\n   Blocks: x",
                  "answer": None}]
    (proj_track / "pending.md").write_text(
        pending.render("build", 1, questions, old), encoding="utf-8")
    assert len(pending.load(str(proj_track / "pending.md"))["questions"]) == 1
    done = _answer(proj_track, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "answers: not recorded (no Why asked line)" in done.stdout.splitlines()
    assert not (tmp_path / "proj" / ".cai" / "answers.md").exists()


def test_a_failed_append_is_reported_and_the_answer_stays_saved(proj_track, tmp_path,
                                                                monkeypatch, capsys):
    import answers

    def boom(*args):
        raise OSError("disk full")
    monkeypatch.setattr(answers, "append", boom)
    assert _start(proj_track, tmp_path, SPLIT).returncode == 0
    code = pending.main(["answer", "--track-dir", str(proj_track), "--question", "1",
                         "--answer-file", _write(tmp_path, "a.md", "Postgres")])
    assert code == 0
    assert "answers: not appended (disk full)" in capsys.readouterr().out.splitlines()
    assert pending.load(str(proj_track / "pending.md"))["questions"][0]["status"] == "answered"


def test_empty_stdin_is_refused_like_an_empty_file(track):
    result = _run_stdin("", "start", "--track-dir", str(track), "--stage", "build",
                        "--round", "1", "--report-file", "-")
    assert result.returncode == 2
    assert not (track / "pending.md").exists()
