"""open_items.py's record core and `add`: the one writer of a track's
open-items.md. Findings that build and verify leave unfixed become one item
each (AC1), the record reads back intact in a new process (AC2), a retried
`add` changes nothing (D1), and nothing public-bound carries what AC6
excludes (D11). `add` writes strictly: an entry it cannot use refuses with
exit 2 and writes nothing.
"""
import json
import os
import subprocess
import sys

import pytest

import open_items
import preflight

SCRIPT = os.path.join(os.path.dirname(open_items.__file__), "open_items.py")


@pytest.fixture(autouse=True)
def _branch(monkeypatch):
    # In-process tests must not depend on whatever git repository the temp
    # directory happens to sit in; subprocess tests use a real repo instead.
    monkeypatch.setattr(preflight, "current_branch", lambda cwd: "track/x")


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "feat"
    d.mkdir()
    return d


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=p, check=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/track/x"], cwd=p,
                   check=True)
    return p


def _state(track, *rows):
    lines = ["# fixture", "", "branch: track/x", "", "| stage | status | artifact | note |",
             "|---|---|---|---|"]
    lines += ["| %s | done | — | %s |" % r for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ledger(track, *records):
    (track / "ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _report(*entries):
    return "## Report\n- built\n\n## Open items\n" + "\n".join(entries) + "\n"


def _entry(n, kind, what="Minor A", where="src/a.py:3", why="left unfixed",
           quoted=None):
    out = ["%d. new %s" % (n, kind), "   What: %s" % what, "   Where: %s" % where,
           "   Why left: %s" % why, "   Severity: major"]
    if quoted:
        out.append("   Quoted: " + quoted.replace("\n", "\n     "))
    return "\n".join(out)


def _run(*args, stdin=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, encoding="utf-8", input=stdin)


def _add(track, project, stage, report, tmp_path):
    f = tmp_path / ("report-%s.md" % stage)
    f.write_bytes(report.encode("utf-8"))
    return _run("add", "--track-dir", str(track), "--project-dir", str(project),
                "--stage", stage, "--report-file", str(f))


def _files(track):
    return sorted(os.listdir(track))


def _text(track):
    return (track / "open-items.md").read_text(encoding="utf-8")


# ---- AC1, R1 (record half) -------------------------------------------------

def test_two_build_and_three_verify_entries_become_five_items(track, project, tmp_path):
    build = _report(_entry(1, "deviation", "Used a dict", "src/a.py:3", "plan said list"),
                    _entry(2, "out-of-scope", "Old helper is dead", "src/old.py", "not ours"))
    verify = _report(_entry(1, "unfixed-minor", "Minor A", "src/b.py:9", "Minor"),
                     _entry(2, "parked-proposal", "Pin the sha", "tests/t.py", "Parked"),
                     _entry(3, "unfixed-minor", "Minor C", "none", "Minor"))
    done = _add(track, project, "build", build, tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["added open-1", "added open-2"]
    done = _add(track, project, "verify", verify, tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["added open-3", "added open-4", "added open-5"]

    rec = open_items.load(str(track))
    assert [(i["id"], i["stage"], i["kind"], i["state"]) for i in rec["items"]] == [
        ("open-1", "build", "deviation", "undecided"),
        ("open-2", "build", "out-of-scope", "undecided"),
        ("open-3", "verify", "unfixed-minor", "undecided"),
        ("open-4", "verify", "parked-proposal", "undecided"),
        ("open-5", "verify", "unfixed-minor", "undecided")]
    assert rec["items"][4]["where"] is None
    assert rec["items"][0]["where"] == "src/a.py:3"
    assert rec["branch"] == "track/x"
    assert len(rec["applied"]) == 2


def test_file_is_written_in_the_documented_layout(track, project, tmp_path):
    report = _report(_entry(1, "unfixed-minor", "Minor A", "src/b.py:9", "Minor",
                            quoted="first line\n  indented\nlast"))
    assert _add(track, project, "verify", report, tmp_path).returncode == 0
    text = _text(track)
    head, _, body = text.partition("\n\n")
    lines = head.split("\n")
    assert lines[:4] == ["# open items", "format: 3", "branch: track/x", "items: 1"]
    assert lines[4].startswith("applied: ") and len(lines[4]) == len("applied: ") + 12
    assert body == (
        "## open-1\nstate: undecided\nstage: verify\nkind: unfixed-minor\n"
        "severity: major\nfixable: yes\nwhere: src/b.py:9\nwhat: Minor A\nwhy: Minor\npicked: none\nurl: none\n"
        "target: none\nsource: report\nquoted: 3 lines\n  first line\n"
        "    indented\n  last\n")
    assert _files(track) == ["open-items.md"]


# ---- AC2, R2 ---------------------------------------------------------------

def test_a_fresh_process_reads_every_field_back_byte_for_byte(track, project, tmp_path):
    what = "Ünïcode 中文 — what"
    why = "reason with trailing space "
    report = _report(_entry(1, "deviation", what, "src/a.py:3", why.strip(),
                            quoted="verbatim 中文\n  nested\n\ntail"))
    assert _add(track, project, "build", report, tmp_path).returncode == 0

    code = ("import json, sys; sys.path.insert(0, %r); import open_items; "
            "print(json.dumps(open_items.load(%r)))" % (os.path.dirname(SCRIPT), str(track)))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8")
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)["items"][0]
    assert got == {
        "id": "open-1", "state": "undecided", "stage": "build", "kind": "deviation",
        "severity": "major", "fixable": True, "where": "src/a.py:3", "what": what, "why": why.strip(), "picked": None,
        "url": None, "target": None, "source": "report",
        "quoted": "verbatim 中文\n  nested\n\ntail"}


def test_load_returns_none_with_no_record(track):
    assert open_items.load(str(track)) is None


def test_load_reads_a_decided_item(track):
    (track / "open-items.md").write_text(
        "# open items\nformat: 1\nbranch: none\nitems: 1\napplied: none\n\n"
        "## open-1\nstate: filed\nstage: verify\nkind: unfixed-minor\nwhere: a.py:1\n"
        "what: w\nwhy: y\npicked: 2026-10-13 file at stop\n"
        "url: https://github.com/o/r/issues/3\ntarget: issue\nsource: report\n"
        "quoted: 0 lines\n", encoding="utf-8")
    rec = open_items.load(str(track))
    assert rec["branch"] is None and rec["applied"] == []
    item = rec["items"][0]
    assert item["picked"] == {"date": "2026-10-13", "pick": "file", "at": "stop"}
    assert item["url"] == "https://github.com/o/r/issues/3"
    assert item["target"] == "issue" and item["quoted"] is None


@pytest.mark.parametrize("text, exc", [
    ("# open items\nformat: 4\nbranch: x\nitems: 0\napplied: none\n",
     open_items.UnknownFormat),
    ("# open items\nformat: \u00b2\nbranch: x\nitems: 0\napplied: none\n",
     open_items.OpenItemsError),
    ("# something else\n", open_items.OpenItemsError),
    ("", open_items.OpenItemsError),
    ("# open items\nformat: 1\nbranch: x\nitems: 1\napplied: none\n",
     open_items.OpenItemsError),
    ("# open items\nformat: 1\nbranch: x\nitems: 1\napplied: none\n\n## open-2\n",
     open_items.OpenItemsError),
    ("# open items\nformat: 1\nbranch: x\nitems: 1\napplied: none\n\n## open-1\n"
     "state: bogus\n", open_items.OpenItemsError),
])
def test_load_raises_only_the_documented_errors(track, text, exc):
    (track / "open-items.md").write_bytes(text.encode("utf-8"))
    with pytest.raises(exc):
        open_items.load(str(track))
    assert issubclass(open_items.UnknownFormat, open_items.OpenItemsError)


def test_load_names_an_undecodable_file_as_an_error(track):
    (track / "open-items.md").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(open_items.OpenItemsError):
        open_items.load(str(track))


def test_load_reads_crlf(track, project, tmp_path):
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    p = track / "open-items.md"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert open_items.load(str(track))["items"][0]["what"] == "Minor A"


# ---- D1, add twice ----------------------------------------------------------

def test_still_open_of_an_unknown_id_refuses_and_writes_nothing(track, project, tmp_path):
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    before = (track / "open-items.md").read_bytes()
    done = _add(track, project, "verify", _report("1. still open-9"), tmp_path)
    assert done.returncode == 2
    assert "open-9" in done.stderr
    assert (track / "open-items.md").read_bytes() == before
    assert _files(track) == ["open-items.md"]


def test_still_open_of_an_unknown_id_with_no_record_creates_nothing(track, project,
                                                                    tmp_path):
    done = _add(track, project, "verify", _report("1. still open-9"), tmp_path)
    assert done.returncode == 2
    assert _files(track) == []


def test_still_and_fixed_name_existing_items(track, project, tmp_path):
    assert _add(track, project, "build",
                _report(_entry(1, "deviation"), _entry(2, "out-of-scope")),
                tmp_path).returncode == 0
    done = _add(track, project, "verify",
                _report("1. still open-1", "2. fixed open-2"), tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["open-2 fixed"]
    states = {i["id"]: i["state"] for i in open_items.load(str(track))["items"]}
    assert states == {"open-1": "undecided", "open-2": "fixed"}


def test_fixed_on_a_settled_item_changes_nothing_and_says_so(track, project, tmp_path):
    (track / "open-items.md").write_text(
        "# open items\nformat: 1\nbranch: none\nitems: 1\napplied: none\n\n"
        "## open-1\nstate: accepted\nstage: build\nkind: deviation\nwhere: none\n"
        "what: w\nwhy: y\npicked: 2026-10-13 accept at stop\nurl: none\ntarget: none\n"
        "source: report\nquoted: 0 lines\n", encoding="utf-8")
    done = _add(track, project, "verify", _report("1. fixed open-1"), tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["open-1 already accepted; left as it is"]
    assert open_items.load(str(track))["items"][0]["state"] == "accepted"


def test_fixed_on_a_fix_pending_item_marks_it_fixed(track, project, tmp_path):
    (track / "open-items.md").write_text(
        "# open items\nformat: 1\nbranch: none\nitems: 1\napplied: none\n\n"
        "## open-1\nstate: fix-pending\nstage: build\nkind: deviation\nwhere: none\n"
        "what: w\nwhy: y\npicked: 2026-10-13 fix-now at stop\nurl: none\ntarget: none\n"
        "source: report\nquoted: 0 lines\n", encoding="utf-8")
    done = _add(track, project, "verify", _report("1. fixed open-1"), tmp_path)
    assert done.stdout.splitlines() == ["open-1 fixed"]
    assert open_items.load(str(track))["items"][0]["state"] == "fixed"


def test_add_twice_leaves_one_copy_and_says_already_applied(track, project, tmp_path):
    report = _report(_entry(1, "deviation"), _entry(2, "out-of-scope", "Other"))
    first = _add(track, project, "build", report, tmp_path)
    assert first.returncode == 0
    once = (track / "open-items.md").read_bytes()
    second = _add(track, project, "build", report, tmp_path)
    assert second.returncode == 0
    assert second.stdout.splitlines() == ["already applied; record unchanged"]
    assert (track / "open-items.md").read_bytes() == once
    assert len(open_items.load(str(track))["items"]) == 2


def test_report_without_the_section_creates_the_record_and_adds_nothing(
        track, project, tmp_path):
    done = _add(track, project, "build", "## Report\n- built\n", tmp_path)
    assert done.returncode == 0
    assert done.stdout.splitlines() == ["no ## Open items section; record unchanged"]
    assert open_items.load(str(track))["items"] == []


def test_the_section_ends_before_pending_questions_and_the_last_one_wins(
        track, project, tmp_path):
    report = ("## Open items\n" + _entry(1, "deviation", "Early") + "\n\n"
              "## Report\nx\n\n"
              "## Open items\n" + _entry(1, "deviation", "Late") + "\n\n"
              "## Pending questions\n1. Q?\n   Background: b\n   Options: o\n"
              "   Blocks: n\n")
    done = _add(track, project, "build", report, tmp_path)
    assert done.returncode == 0, done.stderr
    items = open_items.load(str(track))["items"]
    assert [i["what"] for i in items] == ["Late"]


def test_a_heading_line_inside_quoted_text_does_not_drop_later_entries_silently(
        track, project, tmp_path):
    # An unindented `## Summary` in a quoted review comment ends the section
    # early; entry 2 after it must make `add` refuse, not vanish.
    report = ("## Open items\n"
              "1. new unfixed-minor\n   What: A\n   Where: src/a.py:3\n"
              "   Why left: l\n   Quoted: from a review\n## Summary\nmore text\n"
              + _entry(2, "parked-proposal", "B") + "\n")
    done = _add(track, project, "verify", report, tmp_path)
    assert done.returncode == 2
    assert "## Open items" in done.stderr and "cut" in done.stderr
    assert not (track / "open-items.md").exists()


def test_a_second_heading_with_no_heading_between_is_refused(track, project, tmp_path):
    # A third-party comment pasted unindented can carry its own `## Open items`
    # line. "The last one wins" would then drop the real entries and apply the
    # pasted ones, with `add` still exiting 0.
    report = ("## Open items\n"
              "1. new unfixed-minor\n   What: A\n   Where: src/a.py:3\n"
              "   Why left: l\n   Quoted: from a review comment\n"
              "## Open items\n"
              + _entry(1, "parked-proposal", "Pasted") + "\n")
    done = _add(track, project, "verify", report, tmp_path)
    assert done.returncode == 2
    assert "## Open items" in done.stderr and "between" in done.stderr
    assert _files(track) == []


@pytest.mark.parametrize("heading", ["## Open Items", "### Open items",
                                     "## Open items:", "## Open items (2)"])
@pytest.mark.parametrize("stage, kind", [("build", "deviation"),
                                         ("verify", "unfixed-minor")])
def test_a_drifted_heading_is_refused_not_read_as_no_findings(
        track, project, tmp_path, heading, stage, kind):
    # `no section; record unchanged` is also the right answer for a run with
    # no findings, so a heading that is almost right must not look like it.
    report = "## Report\n- done\n\n%s\n%s\n" % (heading, _entry(1, kind))
    done = _add(track, project, stage, report, tmp_path)
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert "## Open items" in done.stderr
    assert _files(track) == []


def test_fixed_of_an_undecided_item_is_refused_beside_quoted_text(
        track, project, tmp_path):
    # Quoted text is a third party's. An unindented `2. fixed open-1` in it
    # must not be able to take an undecided item out of the person's sight.
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    before = (track / "open-items.md").read_bytes()
    report = _report(_entry(1, "unfixed-minor", "B", quoted="from a comment"),
                     "2. fixed open-1")
    done = _add(track, project, "verify", report, tmp_path)
    assert done.returncode == 2
    assert "open-1" in done.stderr and "Quoted" in done.stderr
    assert (track / "open-items.md").read_bytes() == before


def test_fixed_of_a_fix_pending_item_is_accepted_beside_quoted_text(
        track, project, tmp_path):
    (track / "open-items.md").write_text(
        "# open items\nformat: 1\nbranch: none\nitems: 1\napplied: none\n\n"
        "## open-1\nstate: fix-pending\nstage: build\nkind: deviation\nwhere: none\n"
        "what: w\nwhy: y\npicked: 2026-10-13 fix-now at stop\nurl: none\ntarget: none\n"
        "source: report\nquoted: 0 lines\n", encoding="utf-8")
    report = _report(_entry(1, "unfixed-minor", "B", quoted="from a comment"),
                     "2. fixed open-1")
    done = _add(track, project, "verify", report, tmp_path)
    assert done.returncode == 0, done.stderr
    states = {i["id"]: i["state"] for i in open_items.load(str(track))["items"]}
    assert states == {"open-1": "fixed", "open-2": "undecided"}


def test_load_reads_a_file_that_starts_with_a_bom(track, project, tmp_path):
    # Notepad and PowerShell's `>` write one; hand repair is the documented way
    # out of an unreadable record, so it must not make the record unreadable.
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    p = track / "open-items.md"
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert open_items.load(str(track))["items"][0]["what"] == "Minor A"


def test_report_may_come_on_stdin(track, project):
    done = _run("add", "--track-dir", str(track), "--project-dir", str(project),
                "--stage", "build", "--report-file", "-",
                stdin=_report(_entry(1, "deviation")))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["added open-1"]


# ---- add refusals: exit 2, nothing written ---------------------------------

def _bad(entry):
    return _report(entry)


REFUSED = [
    ("kind of the other stage", "build", _bad(_entry(1, "unfixed-minor")), "open-1|entry 1"),
    ("unknown kind", "verify", _bad(_entry(1, "bogus")), "bogus"),
    ("stage with no kinds", "intake", _bad(_entry(1, "deviation")), "intake"),
    ("ship stage", "ship", _bad(_entry(1, "deviation")), "ship"),
    ("missing What", "build", _bad("1. new deviation\n   Where: a.py\n   Why left: y"),
     "What"),
    ("missing Where", "build", _bad("1. new deviation\n   What: w\n   Why left: y"),
     "Where"),
    ("missing Why left", "build", _bad("1. new deviation\n   What: w\n   Where: a.py"),
     "Why left"),
    ("What over 200 characters", "build", _bad(_entry(1, "deviation", what="x" * 201)),
     "What"),
    ("absolute Where", "build", _bad(_entry(1, "deviation", where="/etc/passwd")), "Where"),
    ("drive Where", "build", _bad(_entry(1, "deviation", where="C:/x/y.py")), "Where"),
    ("parent Where", "build", _bad(_entry(1, "deviation", where="../x.py")), "Where"),
    ("Where with spaces", "build", _bad(_entry(1, "deviation", where="a b.py")), "Where"),
    ("credential in What", "build",
     _bad(_entry(1, "deviation", what="token GITHUB_TOKEN=abcd1234efgh")), "credential"),
    ("local path in Why left", "build",
     _bad(_entry(1, "deviation", why="see /home/me/x")), "local-path"),
    ("credential in Where", "build",
     _bad(_entry(1, "deviation", where="AKIAABCDEFGHIJKLMNOP.txt")), "credential"),
    ("fixed from build", "build", _bad("1. fixed open-1"), "fixed"),
    ("numbering out of order", "build",
     _report(_entry(2, "deviation")), "1"),
    ("second entry numbered 3", "build",
     _report(_entry(1, "deviation"), _entry(3, "deviation")), "3"),
    ("entry that is not new, still or fixed", "build", _bad("1. maybe open-1"), "entry 1"),
    ("text before entry 1", "build", "## Open items\nsome prose\n1. new deviation\n", "entry"),
]


@pytest.mark.parametrize("label, stage, report, mention", REFUSED,
                         ids=[r[0] for r in REFUSED])
def test_add_refuses_with_exit_2_and_writes_nothing(track, project, tmp_path,
                                                    label, stage, report, mention):
    _state(track, ("build", "x"))
    done = _add(track, project, stage, report, tmp_path)
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert any(word in done.stderr for word in mention.split("|")), done.stderr
    assert done.stderr.strip() and len(done.stderr.strip().splitlines()) == 1
    assert _files(track) == ["state.md"]


def test_a_refusal_after_a_good_entry_writes_nothing_of_either(track, project, tmp_path):
    report = _report(_entry(1, "deviation"),
                     _entry(2, "deviation", what="x" * 201))
    done = _add(track, project, "build", report, tmp_path)
    assert done.returncode == 2
    assert _files(track) == []


def test_a_refusal_on_an_existing_record_leaves_its_bytes(track, project, tmp_path):
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    before = (track / "open-items.md").read_bytes()
    done = _add(track, project, "build",
                _report(_entry(1, "deviation", why="see /home/me/x")), tmp_path)
    assert done.returncode == 2
    assert (track / "open-items.md").read_bytes() == before


def test_an_unknown_format_record_makes_add_refuse(track, project, tmp_path):
    p = track / "open-items.md"
    p.write_text("# open items\nformat: 9\nbranch: x\nitems: 0\napplied: none\n",
                 encoding="utf-8")
    before = p.read_bytes()
    done = _add(track, project, "build", _report(_entry(1, "deviation")), tmp_path)
    assert done.returncode == 2
    assert "format" in done.stderr
    assert p.read_bytes() == before


def test_every_kind_is_accepted_by_its_own_stage(track, project, tmp_path):
    assert open_items.KINDS == {"build": ("deviation", "out-of-scope"),
                                "verify": ("unfixed-minor", "parked-proposal")}
    for stage, kinds in open_items.KINDS.items():
        for kind in kinds:
            d = track / ("%s-%s" % (stage, kind))
            d.mkdir()
            done = _add(d, project, stage, _report(_entry(1, kind)), tmp_path)
            assert done.returncode == 0, (stage, kind, done.stderr)


def test_usage_errors_exit_1(track):
    assert _run("add", "--track-dir", str(track)).returncode == 1
    assert _run("nonsense").returncode == 1


# ---- branch rules, import, reminders ---------------------------------------

@pytest.mark.parametrize("seen, stored", [
    ("main", None), ("master", None), (None, None),
    (preflight.UNKNOWN_BRANCH, None), ("track/x", "track/x")])
def test_branch_stored_at_creation(track, monkeypatch, seen, stored):
    monkeypatch.setattr(preflight, "current_branch", lambda cwd: seen)
    open_items.ensure_record(str(track), str(track))
    assert open_items.load(str(track))["branch"] == stored
    if stored is None:
        assert "branch: none\n" in _text(track)


def test_ensure_record_imports_left_open_lines_as_undecided_items(track):
    long_text = "x" * 250
    _state(track, ("build", "Ready. Left open: run X by hand; %s" % long_text),
           ("verify", "Left open: see /home/me/x"))
    rec = open_items.ensure_record(str(track), str(track))
    assert [(i["id"], i["stage"], i["what"]) for i in rec["items"]] == [
        ("open-1", "build", "run X by hand"), ("open-2", "build", long_text),
        ("open-3", "verify", "see /home/me/x")]
    first = rec["items"][0]
    assert first["state"] == "undecided" and first["kind"] == "imported"
    assert first["source"] == "state.md" and first["where"] is None
    assert first["why"] == "recorded before this version of cai kept open items"
    assert rec["applied"] == []
    assert open_items.load(str(track))["items"] == rec["items"]


def test_ensure_record_does_not_rewrite_an_existing_record(track):
    _state(track, ("build", "Left open: a"))
    open_items.ensure_record(str(track), str(track))
    before = (track / "open-items.md").read_bytes()
    _state(track, ("build", "Left open: a; b"))
    open_items.ensure_record(str(track), str(track))
    assert (track / "open-items.md").read_bytes() == before
    assert _files(track) == ["open-items.md", "state.md"]


def test_ensure_record_without_state_md_makes_an_empty_record(track):
    assert open_items.ensure_record(str(track), str(track))["items"] == []
    assert open_items.load(str(track))["items"] == []


def test_items_for_without_a_record_numbers_left_open_lines(track):
    _state(track, ("build", "Left open: a; b"), ("verify", "Left open: c"))
    items = open_items.items_for(str(track), (track / "state.md").read_text("utf-8"))
    assert [(i["id"], i["stage"], i["what"], i["state"], i["kind"], i["where"])
            for i in items] == [
        ("open-1", "build", "a", "undecided", "imported", None),
        ("open-2", "build", "b", "undecided", "imported", None),
        ("open-3", "verify", "c", "undecided", "imported", None)]
    assert open_items.reminders(str(track), (track / "state.md").read_text("utf-8")) == []
    assert not (track / "open-items.md").exists()


def test_add_imports_first_and_numbers_new_items_after(track, project, tmp_path):
    _state(track, ("build", "Left open: a; b"))
    done = _add(track, project, "build", _report(_entry(1, "deviation")), tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["added open-3"]
    items = open_items.load(str(track))["items"]
    assert [i["id"] for i in items] == ["open-1", "open-2", "open-3"]
    assert [i["source"] for i in items] == ["state.md", "state.md", "report"]


def test_reminders_drop_what_an_import_came_from_and_keep_the_rest(track):
    _state(track, ("build", "Left open: a; b"))
    open_items.ensure_record(str(track), str(track))
    _state(track, ("build", "Left open: a; b"), ("verify", "Left open: manual check"))
    text = (track / "state.md").read_text("utf-8")
    assert open_items.reminders(str(track), text) == [("verify", "manual check")]
    # An identical text in another stage is not the import's.
    _state(track, ("build", "Left open: a"), ("verify", "Left open: a"))
    text = (track / "state.md").read_text("utf-8")
    assert open_items.reminders(str(track), text) == [("verify", "a")]


def test_items_for_with_a_record_returns_the_records_items(track, project, tmp_path):
    _state(track, ("verify", "Left open: manual check"))
    assert _add(track, project, "build", _report(_entry(1, "deviation")),
                tmp_path).returncode == 0
    items = open_items.items_for(str(track), (track / "state.md").read_text("utf-8"))
    assert [i["id"] for i in items] == ["open-1", "open-2"]
    assert items[0]["kind"] == "imported" and items[1]["kind"] == "deviation"


# ---- state words ------------------------------------------------------------

@pytest.mark.parametrize("state, url, word", [
    ("filed", "https://github.com/o/r/issues/3", "filed https://github.com/o/r/issues/3"),
    ("noted", "https://github.com/o/r/pull/4#issuecomment-1",
     "noted https://github.com/o/r/pull/4#issuecomment-1"),
    ("accepted", None, "accepted"), ("fixed", None, "fixed"),
    ("fix-pending", None, "fix pending"),
    ("queued-issue", None, "queued: issue once the PR is open"),
    ("queued-note", None, "queued: note once the PR is open"),
    ("filing", None, "filing: result unknown, check GitHub"),
    ("undecided", None, "undecided")])
def test_state_word(state, url, word):
    assert open_items.state_word({"state": state, "url": url}) == word


def test_every_state_has_a_word_and_holds_ship_is_a_subset():
    for s in open_items.STATES:
        assert open_items.state_word({"state": s, "url": "u"})
    assert set(open_items.HOLDS_SHIP) == {"undecided", "fix-pending", "filing"}
    assert set(open_items.HOLDS_SHIP) <= set(open_items.STATES)


# ---- recorded_pr ------------------------------------------------------------

def test_recorded_pr_with_no_ledger_or_no_ship_passed(track):
    assert open_items.recorded_pr(str(track)) is None
    _ledger(track, {"stage": "build", "outcome": "passed", "note": "PR #7"},
            {"stage": "ship", "outcome": "blocked", "note": "PR #8"})
    assert open_items.recorded_pr(str(track)) is None


def test_recorded_pr_reads_the_first_ship_passed_note(track):
    _ledger(track, {"stage": "ship", "outcome": "passed",
                    "note": "Left open: merge not confirmed (PR #42)"},
            {"stage": "ship", "outcome": "passed", "note": "PR #43"})
    assert open_items.recorded_pr(str(track)) == 42


def test_recorded_pr_is_unknown_when_the_note_names_none(track):
    _ledger(track, {"stage": "ship", "outcome": "passed", "note": "cut by _fit"})
    assert open_items.recorded_pr(str(track)) is open_items.PR_UNKNOWN
    _ledger(track, {"stage": "ship", "outcome": "passed"})
    assert open_items.recorded_pr(str(track)) is open_items.PR_UNKNOWN


def test_recorded_pr_ignores_a_malformed_line(track):
    (track / "ledger.jsonl").write_text(
        "not json\n" + json.dumps({"stage": "ship", "outcome": "passed",
                                   "note": "PR #5"}) + "\n", encoding="utf-8")
    assert open_items.recorded_pr(str(track)) == 5


# ---- branch_on_remote -------------------------------------------------------

class _Done:
    def __init__(self, rc):
        self.returncode = rc


@pytest.mark.parametrize("answer, expected", [
    (_Done(0), True), (_Done(2), False), (_Done(1), False), (None, False)])
def test_branch_on_remote_only_exit_0_counts(monkeypatch, answer, expected):
    calls = []

    def fake(cwd, *args, **kw):
        calls.append((cwd, args))
        return answer
    monkeypatch.setattr(preflight, "git", fake)
    assert open_items.branch_on_remote("P", "track/x") is expected
    assert calls == [("P", ("ls-remote", "--exit-code", "origin", "refs/heads/track/x"))]


@pytest.mark.parametrize("branch", [None, preflight.UNKNOWN_BRANCH])
def test_branch_on_remote_without_a_branch_does_not_ask_git(monkeypatch, branch):
    monkeypatch.setattr(preflight, "git",
                        lambda *a, **k: pytest.fail("git must not be asked"))
    assert open_items.branch_on_remote("P", branch) is False


# ---- D11: forbidden() -------------------------------------------------------

SAMPLES = [
    ("credential", "ghp_" + "a1B2" * 5),
    ("credential", "gho_" + "x" * 20),
    ("credential", "github_pat_" + "A_b1" * 6),
    ("credential", "-----BEGIN RSA PRIVATE KEY-----"),
    ("credential", "-----BEGIN PRIVATE KEY-----"),
    ("credential", "clone https://user:s3cret@example.com/r.git"),
    ("credential", "Authorization: Basic abc"),
    ("credential", "sent authorization : x"),
    ("credential", "header Bearer abcdefgh12345"),
    ("credential", "password: hunter2hunter2"),
    ("credential", "api_key=0123456789"),
    ("credential", "GITHUB_TOKEN=abcd1234efgh"),
    ("credential", "DB_PASSWORD=abcd1234efgh"),
    ("credential", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("credential", "ASIA" + "ABCDEFGHIJKLMNOP"),
    ("local-path", "C:\\Users\\me\\x"),
    ("local-path", "see C:/work/x"),
    ("local-path", "/home/me/x"),
    ("local-path", "at /Users/me/f"),
    ("local-path", "in /root/.ssh"),
    ("local-path", "\\\\server\\share\\f"),
    ("local-path", "file:///home/x"),
    # CJK text has no spaces, and a CJK ideograph is a word character, so a
    # Unicode-aware `\b` finds no boundary before a path or key written
    # straight after it.
    ("local-path", "\u672c\u6a5f\u8def\u5f91D:\\project\\foo.py \u6e2c\u8a66\u5931\u6557"),
    ("credential", "\u91d1\u9470AKIA" + "ABCDEFGHIJKLMNOP" + "\u5df2\u5916\u6d29"),
    ("credential", "\u4ee4\u724cghp_" + "a1B2" * 5),
    ("raw-output", "Traceback (most recent call last):"),
    ("raw-output", "error: pathspec 'x' did not match"),
    ("raw-output", "text\nfatal: not a git repository"),
    ("raw-output", "backend gh issue create -> unreachable"),
    ("raw-output", "backend gh -> ok"),
    ("argument-vector", "uses --alpha --beta --gamma here"),
    ("argument-vector", "git status -z"),
    ("argument-vector", "gh issue create --title x"),
    ("argument-vector", "python -m pytest"),
]


@pytest.mark.parametrize("rule, text", SAMPLES)
def test_forbidden_names_the_rule_of_every_pattern(rule, text):
    assert open_items.forbidden(text) == rule
    assert open_items.forbidden(text, field=True) == rule


ORDINARY = [
    "app/home/page.tsx:12",
    "src/a.py:3",
    "https://github.com/o/r/issues/3",
    "https://example.com/home/x",
    "uses --force and --quiet here",
    "needs the --flag",
    "the token is checked before use",
    "a token of appreciation",
    "the backend maps 403 -> unclassified",
    "Minor: the sha-line wording reads as two rules",
    "password hashing is described in the doc",
    "see the Authorization header section",
    "Bearer of the news",
    "gits are not gh",
    "",
]


@pytest.mark.parametrize("text", ORDINARY)
def test_forbidden_lets_ordinary_item_text_through(text):
    assert open_items.forbidden(text) is None
    assert open_items.forbidden(text, field=False) is None


@pytest.mark.parametrize("text", [
    "error: pathspec",
    "backend gh issue create -> unreachable",
    "git status -z",
    "gh issue create --title x",
    "python -m pytest",
    "uses --alpha --beta --gamma here",
])
def test_field_false_skips_the_four_field_only_patterns(text):
    assert open_items.forbidden(text, field=True) is not None
    assert open_items.forbidden(text, field=False) is None


@pytest.mark.parametrize("rule, text", [
    ("credential", "GITHUB_TOKEN=abcd1234efgh"),
    ("local-path", "file:///home/x"),
    ("raw-output", "Traceback (most recent call last):"),
])
def test_field_false_still_runs_the_other_patterns(rule, text):
    assert open_items.forbidden(text, field=False) == rule


def test_forbidden_tries_credential_first():
    assert open_items.forbidden("/home/me/x GITHUB_TOKEN=abcd1234efgh") == "credential"
