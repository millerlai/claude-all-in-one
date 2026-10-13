"""open_items.py's menu commands: `undecided`, `options`, `decide`,
`record-url` and `brief`. They read the record and the ledger and print what
the main session asks the person at the stop and at `done` (AC3, AC5, AC8), and
they write only a pick or a URL the person gave. `options` computes each
item's menu from the recorded PR, the PR state, the fix rounds spent, the
commit answer and, with no PR, whether the branch is on `origin` (D3, D12).
"""
import os
import shutil
import subprocess
import sys

import pytest

import ledger
import open_items

SCRIPT = os.path.join(os.path.dirname(open_items.__file__), "open_items.py")

FIX = "Fix now"
FILE = "File a GitHub issue"
NOTE = "Note on the PR"
ACCEPT = "Accept as is"
STOP = "Stop: I will push the branch first"

NOTE_ROUNDS = "note: both fix rounds are spent, so Fix now is not offered"
NOTE_COMMIT = ("note: the commit answer is no, so the fix stays in the working "
               "tree and will not reach the PR")
NOTE_TREE = ("note: the working tree holds tracked changes; a fix round would "
             "stop on clean_tree and use a round")
NOTE_NO_PR = ("note: no PR number is on the ledger, and the branch was not "
              "found on origin (git ls-remote did not exit 0), so File is not "
              "offered")

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is absent")


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "feat"
    d.mkdir()
    return d


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    _git(p, "init", "-q")
    _git(p, "symbolic-ref", "HEAD", "refs/heads/track/x")
    return p


def _item(n, state="undecided", stage="verify", kind="unfixed-minor",
          where="src/a.py:3", what=None, why="left unfixed", picked=None,
          url=None, target=None, source="report", quoted=None):
    return {"id": "open-%d" % n, "state": state, "stage": stage, "kind": kind,
            "where": where, "what": what or "Minor %d" % n, "why": why,
            "picked": picked, "url": url, "target": target, "source": source,
            "quoted": quoted}


def _record(track, *items, branch="track/x"):
    open_items.write_atomic(
        str(track / "open-items.md"),
        open_items.render({"branch": branch, "applied": [], "items": list(items)}))


def _state(track, design_doc=None, left_open=()):
    """state.md with a design row naming the approved document, so the real
    preflight.commit_answer reads the ledger; `left_open` is (stage, text)."""
    rows = [("intake", "done", "—", ""), ("design", "done", design_doc or "—", ""),
            ("build", "done", "—", ""), ("verify", "done", "—", ""),
            ("ship", "", "", "")]
    def note(stage):
        texts = [t for s, t in left_open if s == stage]
        return "Left open: " + "; ".join(texts) if texts else ""
    rows = [r[:3] + (note(r[0]),) for r in rows]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _commit_answer(track, tmp_path, answer):
    doc = tmp_path / "d-detail.md"
    doc.write_text("# x\n\n## Status\napproved 2026-10-12\n", encoding="utf-8")
    _state(track, design_doc=str(doc))
    ledger.append(str(track), "design", "passed", artifact=str(doc), gate="human",
                  note="commit: " + answer)


def _shipped(track, note="PR #7", rounds=0):
    ledger.append(str(track), "ship", "passed", note=note)
    for _ in range(rounds):
        ledger.append(str(track), "verify", "passed")


def _opts(track, project, at="done", pr=None, pr_state=None):
    return open_items.options(str(track), str(project), at, pr=pr, pr_state=pr_state)


def _menus(lines):
    return [ln for ln in lines if " menu: " in ln]


def _run(*args, stdin=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, encoding="utf-8", input=stdin)


@pytest.fixture
def decided(track, tmp_path):
    """A track whose commit answer is yes and whose PR #7 is recorded, with
    one undecided item: the baseline every `options` row varies from."""
    _commit_answer(track, tmp_path, "yes")
    _shipped(track)
    _record(track, _item(1))
    return track


# ---- undecided --------------------------------------------------------------

def test_undecided_counts_the_three_holding_states(track):
    _state(track)
    _record(track, _item(1), _item(2, state="accepted"), _item(3, state="fix-pending"),
            _item(4, state="filed", url="https://github.com/o/r/issues/3"),
            _item(5, state="filing", target="issue"), _item(6, state="queued-issue"),
            _item(7, state="queued-note"), _item(8, state="noted"), _item(9, state="fixed"))
    done = _run("undecided", "--track-dir", str(track))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["undecided 3: open-1, open-3, open-5"]


def test_undecided_zero(track):
    _state(track)
    _record(track, _item(1, state="accepted"))
    done = _run("undecided", "--track-dir", str(track))
    assert (done.returncode, done.stdout.splitlines()) == (0, ["undecided 0"])


def test_undecided_with_no_record_counts_left_open_lines(track):
    _state(track, left_open=[("build", "run X by hand"), ("verify", "Minor A")])
    done = _run("undecided", "--track-dir", str(track))
    assert done.stdout.splitlines() == ["undecided 2: open-1, open-2"]
    assert not (track / "open-items.md").exists()


def test_undecided_exits_2_without_state_md(track):
    _record(track, _item(1))
    done = _run("undecided", "--track-dir", str(track))
    assert done.returncode == 2 and done.stderr.strip()


def test_undecided_exits_2_on_an_unreadable_record(track):
    _state(track)
    (track / "open-items.md").write_text("not a record\n", encoding="utf-8")
    done = _run("undecided", "--track-dir", str(track))
    assert done.returncode == 2 and done.stderr.strip() and not done.stdout


# ---- options: the stop ------------------------------------------------------

def test_options_block_and_menu_line_format(decided, project):
    lines = _opts(decided, project, "done", pr=7, pr_state="OPEN")
    assert lines == [
        "open-1 [verify] unfixed-minor",
        "  where: src/a.py:3",
        "  what: Minor 1",
        "  why: left unfixed",
        "open-1 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT)]


def test_options_at_stop_gives_all_four_and_prints_none_where_missing(track, project):
    _state(track)
    _record(track, _item(1, where=None), _item(2, state="fix-pending"),
            _item(3, state="accepted"))
    lines = _opts(track, project, "stop")
    assert "  where: none" in lines
    assert _menus(lines) == [
        "open-1 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT),
        "open-2 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT)]
    assert not [ln for ln in lines if ln.startswith("note:")]


def test_options_at_stop_ignores_the_pr(track, project):
    # Before ship there is no PR; the stop never reads the ledger or git.
    _state(track)
    _record(track, _item(1))
    assert _menus(_opts(track, project, "stop")) == [
        "open-1 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT)]


# ---- options: the done table ------------------------------------------------

def test_open_with_fewer_than_two_rounds_offers_fix_now(decided, project):
    ledger.append(str(decided), "verify", "passed")
    lines = _opts(decided, project, pr=7, pr_state="OPEN")
    assert _menus(lines) == ["open-1 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT)]
    assert NOTE_ROUNDS not in lines


def test_open_with_two_rounds_drops_fix_now_and_says_why(decided, project):
    ledger.append(str(decided), "verify", "passed")
    ledger.append(str(decided), "verify", "failed", note="a fix round failed")
    lines = _opts(decided, project, pr=7, pr_state="OPEN")
    assert _menus(lines) == ["open-1 menu: %s | %s | %s" % (FILE, NOTE, ACCEPT)]
    assert lines[-1] == NOTE_ROUNDS
    # Fix now is not offered, so the two notes about it have nothing to say.
    assert NOTE_COMMIT not in lines and NOTE_TREE not in lines


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_merged_or_closed_offers_file_and_accept(decided, project, state):
    lines = _opts(decided, project, pr=7, pr_state=state)
    assert _menus(lines) == ["open-1 menu: %s | %s" % (FILE, ACCEPT)]
    assert not [ln for ln in lines if ln.startswith("note:")]


def test_unknown_state_offers_file_and_accept(decided, project):
    lines = _opts(decided, project, pr=7, pr_state="unknown")
    assert _menus(lines) == ["open-1 menu: %s | %s" % (FILE, ACCEPT)]


def test_no_pr_line_reads_as_unknown(decided, project):
    assert _menus(_opts(decided, project)) == ["open-1 menu: %s | %s" % (FILE, ACCEPT)]


def test_a_pr_number_that_differs_from_the_ledger_reads_as_unknown(decided, project):
    lines = _opts(decided, project, pr=8, pr_state="OPEN")
    assert _menus(lines) == ["open-1 menu: %s | %s" % (FILE, ACCEPT)]


@needs_git
def test_no_recorded_pr_and_branch_on_origin_offers_file_and_accept(
        track, project, tmp_path):
    _commit_answer(track, tmp_path, "yes")
    _record(track, _item(1))
    _push_branch(project, tmp_path)
    lines = _opts(track, project, pr=7, pr_state="OPEN")
    assert _menus(lines) == ["open-1 menu: %s | %s" % (FILE, ACCEPT)]
    assert not [ln for ln in lines if ln.startswith("note:")]


@needs_git
def test_no_recorded_pr_and_branch_not_on_origin_offers_accept_and_stop(
        track, project, tmp_path):
    _commit_answer(track, tmp_path, "yes")
    _record(track, _item(1), _item(2))
    _bare_origin(project, tmp_path)
    lines = _opts(track, project)
    assert _menus(lines) == ["open-1 menu: %s | %s" % (ACCEPT, STOP),
                             "open-2 menu: %s | %s" % (ACCEPT, STOP)]
    assert lines.count(NOTE_NO_PR) == 1
    # The Stop label is a menu word only, never part of a note.
    assert not any(STOP in ln for ln in lines if ln.startswith("note:"))


@needs_git
def test_a_ship_note_without_a_pr_number_takes_the_branch_path(track, project, tmp_path):
    _commit_answer(track, tmp_path, "yes")
    _shipped(track, note="shipped, the note lost its number")
    _record(track, _item(1))
    _bare_origin(project, tmp_path)
    assert _menus(_opts(track, project, pr=7, pr_state="OPEN")) == [
        "open-1 menu: %s | %s" % (ACCEPT, STOP)]


def test_git_is_not_asked_unless_there_is_no_recorded_pr(decided, project, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ls-remote ran")
    monkeypatch.setattr(open_items, "branch_on_remote", boom)
    _opts(decided, project, pr=7, pr_state="OPEN")
    _opts(decided, project, "stop")


# ---- options: notes ---------------------------------------------------------

def test_commit_no_prints_its_note_once_at_done(track, project, tmp_path):
    _commit_answer(track, tmp_path, "no")
    _shipped(track)
    _record(track, _item(1), _item(2))
    lines = _opts(track, project, pr=7, pr_state="OPEN")
    assert lines.count(NOTE_COMMIT) == 1
    # After the items, not between them.
    assert lines.index(NOTE_COMMIT) > max(i for i, ln in enumerate(lines) if " menu: " in ln)


def test_commit_no_prints_no_note_at_stop(track, project, tmp_path):
    _commit_answer(track, tmp_path, "no")
    _record(track, _item(1))
    assert NOTE_COMMIT not in _opts(track, project, "stop")


def test_commit_yes_prints_no_note(decided, project):
    assert NOTE_COMMIT not in _opts(decided, project, pr=7, pr_state="OPEN")


def test_an_unreadable_commit_answer_counts_as_no(track, project):
    _state(track)  # no design document on the ledger
    _shipped(track)
    _record(track, _item(1))
    assert NOTE_COMMIT in _opts(track, project, pr=7, pr_state="OPEN")


def test_commit_no_note_needs_fix_now_on_the_menu(track, project, tmp_path):
    _commit_answer(track, tmp_path, "no")
    _shipped(track)
    _record(track, _item(1))
    assert NOTE_COMMIT not in _opts(track, project, pr=7, pr_state="MERGED")


# ---- options: answer 4, the clean_tree note ---------------------------------

@pytest.fixture
def tree(decided, project):
    (project / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(project, "add", "tracked.txt")
    _git(project, "commit", "-q", "-m", "init")
    return project


@needs_git
def test_tracked_change_prints_the_clean_tree_note_with_fix_now(decided, tree):
    (tree / "tracked.txt").write_text("two\n", encoding="utf-8")
    lines = _opts(decided, tree, pr=7, pr_state="OPEN")
    assert lines.count(NOTE_TREE) == 1
    assert lines[-1] == NOTE_TREE


@needs_git
def test_only_untracked_files_print_no_clean_tree_note(decided, tree):
    (tree / "new.txt").write_text("x\n", encoding="utf-8")
    assert NOTE_TREE not in _opts(decided, tree, pr=7, pr_state="OPEN")


@needs_git
def test_a_clean_tree_prints_no_clean_tree_note(decided, tree):
    assert NOTE_TREE not in _opts(decided, tree, pr=7, pr_state="OPEN")


@needs_git
def test_the_clean_tree_note_is_not_printed_at_stop(decided, tree):
    (tree / "tracked.txt").write_text("two\n", encoding="utf-8")
    assert NOTE_TREE not in _opts(decided, tree, "stop")


@needs_git
def test_the_clean_tree_note_needs_fix_now_on_the_menu(decided, tree):
    (tree / "tracked.txt").write_text("two\n", encoding="utf-8")
    assert NOTE_TREE not in _opts(decided, tree, pr=7, pr_state="MERGED")


def test_git_not_answering_prints_no_clean_tree_note(decided, project, monkeypatch):
    import preflight
    real = preflight.git

    def deaf(cwd, *args, **kw):
        return None if args[:1] == ("status",) else real(cwd, *args, **kw)
    monkeypatch.setattr(preflight, "git", deaf)
    assert NOTE_TREE not in _opts(decided, project, pr=7, pr_state="OPEN")


# ---- options: a filing item -------------------------------------------------

def test_a_filing_item_prints_check_github_then_its_menu(decided, project):
    _record(decided, _item(1, state="filing", target="issue",
                           picked={"date": "2026-10-13", "pick": "file", "at": "done"}))
    lines = _opts(decided, project, pr=7, pr_state="OPEN")
    assert lines[4:] == [
        "open-1 check-github",
        "open-1 menu: %s | %s | %s | %s" % (FIX, FILE, NOTE, ACCEPT)]


def test_a_filing_item_with_no_pr_state_gets_the_unknown_menu(decided, project):
    _record(decided, _item(1, state="filing", target="issue",
                           picked={"date": "2026-10-13", "pick": "file", "at": "done"}))
    lines = _opts(decided, project)
    assert lines[4:] == ["open-1 check-github", "open-1 menu: %s | %s" % (FILE, ACCEPT)]


# ---- options: errors --------------------------------------------------------

def test_pr_state_without_pr_at_done_is_a_usage_error(decided, project):
    done = _run("options", "--track-dir", str(decided), "--project-dir", str(project),
                "--at", "done", "--pr-state", "OPEN")
    assert done.returncode == 1 and not done.stdout


def test_options_exits_2_on_an_unreadable_record(track, project):
    _state(track)
    (track / "open-items.md").write_text("# open items\nformat: 9\n", encoding="utf-8")
    done = _run("options", "--track-dir", str(track), "--project-dir", str(project),
                "--at", "stop")
    assert done.returncode == 2 and done.stderr.strip() and not done.stdout


def test_options_cli_prints_the_lines(decided, project):
    done = _run("options", "--track-dir", str(decided), "--project-dir", str(project),
                "--at", "done", "--pr", "7", "--pr-state", "MERGED")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == "open-1 menu: %s | %s" % (FILE, ACCEPT)


def test_options_writes_nothing(decided, project):
    before = sorted(os.listdir(decided))
    text = (decided / "open-items.md").read_bytes()
    _opts(decided, project, pr=7, pr_state="OPEN")
    assert sorted(os.listdir(decided)) == before
    assert (decided / "open-items.md").read_bytes() == text


# ---- decide -----------------------------------------------------------------

def _decide(track, project, item, pick, at="stop"):
    return _run("decide", "--track-dir", str(track), "--project-dir", str(project),
                "--item", item, "--pick", pick, "--at", at)


@pytest.mark.parametrize("pick,state", [
    ("fix-now", "fix-pending"), ("file", "queued-issue"), ("note", "queued-note"),
    ("accept", "accepted")])
def test_decide_sets_the_pick_and_the_state(track, project, pick, state):
    _state(track)
    _record(track, _item(1), _item(2))
    done = _decide(track, project, "open-2", pick, "done")
    assert done.returncode == 0, done.stderr
    items = open_items.load(str(track))["items"]
    assert items[0]["state"] == "undecided" and items[0]["picked"] is None
    assert items[1]["state"] == state
    assert items[1]["picked"]["pick"] == pick and items[1]["picked"]["at"] == "done"
    assert len(items[1]["picked"]["date"]) == 10


def test_decide_without_a_record_imports_then_decides(track, project):
    # I8: ids printed for a track with no record are valid here.
    _state(track, left_open=[("build", "run X by hand"), ("verify", "Minor A")])
    assert not (track / "open-items.md").exists()
    done = _decide(track, project, "open-2", "accept")
    assert done.returncode == 0, done.stderr
    left = _run("undecided", "--track-dir", str(track))
    assert left.stdout.splitlines() == ["undecided 1: open-1"]
    rec = open_items.load(str(track))
    assert [i["what"] for i in rec["items"]] == ["run X by hand", "Minor A"]
    assert rec["items"][1]["state"] == "accepted"


def test_decide_accepts_fix_pending_and_filing(track, project):
    _state(track)
    _record(track, _item(1, state="fix-pending"),
            _item(2, state="filing", target="issue"))
    assert _decide(track, project, "open-1", "accept").returncode == 0
    assert _decide(track, project, "open-2", "note").returncode == 0
    states = [i["state"] for i in open_items.load(str(track))["items"]]
    assert states == ["accepted", "queued-note"]


def test_decide_again_with_the_same_pick_is_idempotent(track, project):
    _state(track)
    _record(track, _item(1, state="fix-pending"))
    assert _decide(track, project, "open-1", "fix-now").returncode == 0
    one = (track / "open-items.md").read_bytes()
    assert _decide(track, project, "open-1", "fix-now").returncode == 0
    assert (track / "open-items.md").read_bytes() == one


@pytest.mark.parametrize("state", ["queued-issue", "queued-note", "filed", "noted",
                                   "accepted", "fixed"])
def test_decide_refuses_any_other_state(track, project, state):
    _state(track)
    url = "https://github.com/o/r/issues/1" if state in ("filed", "noted") else None
    _record(track, _item(1, state=state, url=url))
    before = (track / "open-items.md").read_bytes()
    done = _decide(track, project, "open-1", "accept")
    assert done.returncode == 2 and done.stderr.strip()
    assert (track / "open-items.md").read_bytes() == before


def test_decide_refuses_an_unknown_id_and_writes_nothing(track, project):
    _state(track, left_open=[("build", "a")])
    done = _decide(track, project, "open-9", "accept")
    assert done.returncode == 2 and done.stderr.strip()
    assert not (track / "open-items.md").exists()


def test_decide_refuses_an_unknown_pick_as_a_usage_error(track, project):
    _state(track)
    _record(track, _item(1))
    assert _decide(track, project, "open-1", "stop").returncode == 1


# ---- record-url -------------------------------------------------------------

ISSUE = "https://github.com/o/r/issues/12"
COMMENT = "https://github.com/o/r/pull/7#issuecomment-99"


def _url(track, project, item, url):
    return _run("record-url", "--track-dir", str(track), "--project-dir", str(project),
                "--item", item, "--url", url)


def test_record_url_issue_target_files_the_item(track, project):
    _state(track)
    _record(track, _item(1, state="filing", target="issue"))
    done = _url(track, project, "open-1", ISSUE)
    assert done.returncode == 0, done.stderr
    item = open_items.load(str(track))["items"][0]
    assert (item["state"], item["url"]) == ("filed", ISSUE)


def test_record_url_issue_target_files_only_the_named_item(track, project):
    # One `gh issue create` call carries one item, so a URL the person found
    # for open-1 says nothing about open-2's unknown result.
    _state(track)
    _record(track,
            _item(1, state="filing", target="issue"),
            _item(2, state="filing", target="issue"))
    done = _url(track, project, "open-1", ISSUE)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["open-1 filed " + ISSUE]
    got = [(i["state"], i["url"]) for i in open_items.load(str(track))["items"]]
    assert got == [("filed", ISSUE), ("filing", None)]


def test_record_url_note_target_notes_every_filing_item_of_that_comment(track, project):
    _state(track)
    _record(track,
            _item(1, state="filing", target="note-1"),
            _item(2, state="filing", target="note-1"),
            _item(3, state="filing", target="note-2"),
            _item(4, state="noted", target="note-1", url=COMMENT.replace("99", "5")),
            _item(5, state="filing", target="issue"))
    done = _url(track, project, "open-1", COMMENT)
    assert done.returncode == 0, done.stderr
    got = [(i["state"], i["url"]) for i in open_items.load(str(track))["items"]]
    assert got == [("noted", COMMENT), ("noted", COMMENT), ("filing", None),
                   ("noted", COMMENT.replace("99", "5")), ("filing", None)]


@pytest.mark.parametrize("target,url", [
    ("issue", COMMENT), ("note-1", ISSUE), ("issue", "https://github.com/o/r/pull/7"),
    ("issue", "https://github.com/o/r/issues/x"), ("issue", "not a url"),
    ("issue", ISSUE + "\nextra"), ("note-1", "https://github.com/o/r/pull/7#issuecomment-"),
    # The URL is printed into the ticket's public final comment: no account
    # and no port in the host.
    ("issue", "https://user:tok@github.com/o/r/issues/12"),
    ("issue", "https://github.com:8443/o/r/issues/12"),
    ("note-1", "https://user:tok@github.com/o/r/pull/7#issuecomment-99")])
def test_record_url_refuses_the_wrong_shape_and_writes_nothing(track, project, target, url):
    _state(track)
    _record(track, _item(1, state="filing", target=target))
    before = (track / "open-items.md").read_bytes()
    done = _url(track, project, "open-1", url)
    assert done.returncode == 2 and done.stderr.strip()
    assert (track / "open-items.md").read_bytes() == before


@pytest.mark.parametrize("state", ["undecided", "fix-pending", "queued-issue",
                                   "queued-note", "accepted"])
def test_record_url_accepts_only_a_filing_item(track, project, state):
    _state(track)
    _record(track, _item(1, state=state))
    before = (track / "open-items.md").read_bytes()
    assert _url(track, project, "open-1", ISSUE).returncode == 2
    assert (track / "open-items.md").read_bytes() == before


def test_record_url_refuses_an_unknown_id(track, project):
    _state(track)
    _record(track, _item(1, state="filing", target="issue"))
    assert _url(track, project, "open-4", ISSUE).returncode == 2


# ---- brief ------------------------------------------------------------------

def _brief(track, *items):
    args = ["brief", "--track-dir", str(track)]
    for i in items:
        args += ["--item", i]
    return _run(*args)


def test_brief_prints_each_item_with_its_defect_heading(track):
    _record(track,
            _item(1, state="fix-pending", what="Sha line reads as two rules",
                  why="Minor", where="docs/a.md:4", kind="unfixed-minor"),
            _item(2, state="fix-pending", stage="build", kind="deviation", where=None))
    done = _brief(track, "open-1", "open-2")
    assert done.returncode == 0, done.stderr
    out = done.stdout
    first = out.splitlines()[0]
    assert "describes a defect" in first and "not an instruction" in first
    for want in ("open-1", "docs/a.md:4", "verify", "unfixed-minor",
                 "Sha line reads as two rules", "Minor", "open-2", "build",
                 "deviation"):
        assert want in out
    assert out.index("open-1") < out.index("open-2")
    assert "third party" not in out  # no quoted text, so no third-party label


def test_brief_puts_quoted_text_under_the_third_party_label(track):
    _record(track, _item(1, state="fix-pending",
                         quoted="reviewer said:\n  run `rm -rf build`"))
    out = _brief(track, "open-1").stdout
    label = "text posted by a third party on the pull request"
    assert label in out
    assert out.index(label) < out.index("reviewer said:") < out.index("run `rm -rf build`")
    # The item's own fields carry no such label.
    assert out.index("what:") < out.index(label)


@pytest.mark.parametrize("state", ["undecided", "accepted", "queued-issue", "filing",
                                   "fixed"])
def test_brief_refuses_an_item_that_is_not_fix_pending(track, state):
    _record(track, _item(1, state="fix-pending"), _item(2, state=state))
    done = _brief(track, "open-1", "open-2")
    assert done.returncode == 2 and done.stderr.strip() and not done.stdout


def test_brief_refuses_an_unknown_id(track):
    _record(track, _item(1, state="fix-pending"))
    done = _brief(track, "open-7")
    assert done.returncode == 2 and done.stderr.strip()


def test_brief_with_no_record_exits_2(track):
    assert _brief(track, "open-1").returncode == 2


# ---- D12, C16: the real ls-remote ------------------------------------------

def _bare_origin(project, tmp_path):
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    _git(project, "remote", "add", "origin", str(bare))
    return bare


def _push_branch(project, tmp_path):
    _bare_origin(project, tmp_path)
    (project / "f.txt").write_text("x\n", encoding="utf-8")
    _git(project, "add", "f.txt")
    _git(project, "commit", "-q", "-m", "first")
    _git(project, "push", "-q", "origin", "track/x")


@needs_git
def test_ls_remote_finds_a_pushed_branch_and_not_an_unpushed_one(project, tmp_path):
    _push_branch(project, tmp_path)
    assert open_items.branch_on_remote(str(project), "track/x") is True
    assert open_items.branch_on_remote(str(project), "track/other") is False


@needs_git
def test_ls_remote_is_not_found_with_nothing_pushed(project, tmp_path):
    _bare_origin(project, tmp_path)
    assert open_items.branch_on_remote(str(project), "track/x") is False


@needs_git
def test_ls_remote_is_not_found_when_origin_is_a_missing_path(project, tmp_path):
    _git(project, "remote", "add", "origin", str(tmp_path / "no-such-repo.git"))
    assert open_items.branch_on_remote(str(project), "track/x") is False


@needs_git
def test_ls_remote_is_not_found_with_no_origin(project):
    assert open_items.branch_on_remote(str(project), "track/x") is False
