"""#443: open items carry a severity, and the stop before ship asks one menu
for all of them instead of one menu per item.

Thirteen items meant thirteen menus in a row. Build and verify now mark each
`new` entry `Severity: major|minor`; `options --at stop` lists the items under
`Major:` and `Minor:` and prints one `menu:` line; `decide-all` records that one
pick for every item still asked. "Fix major" fixes the majors and queues the
minors as a note on the PR (maintainer decision, 2026-10-14). `done` asks
the same one menu, its labels cut to what the PR's state allows; only a
`filing` item is still asked on its own (maintainer decision, 2026-10-14).
"""
import os
import subprocess
import sys

import pytest

import ledger
import open_items

SCRIPT = os.path.join(os.path.dirname(open_items.__file__), "open_items.py")

FIX_MAJOR = "Fix major"
FIX_ALL = "Fix major + minor"
FIX_MINOR = "Fix minor"
NOTE = "Note on the PR"
ACCEPT = "Accept as is"
PER_ITEM = "Fix now | File a GitHub issue | Note on the PR | Accept as is"


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.fixture
def track(tmp_path):
    d = tmp_path / "feat"
    d.mkdir()
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| %s | done | — |  |" % s for s in ("design", "build", "verify")]
    lines += ["| ship |  |  |  |"]
    (d / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    _git(p, "init", "-q")
    _git(p, "symbolic-ref", "HEAD", "refs/heads/track/x")
    return p


def _item(n, severity, state="undecided"):
    return {"id": "open-%d" % n, "state": state, "stage": "verify",
            "kind": "unfixed-minor", "severity": severity, "where": "src/a.py:%d" % n,
            "what": "Item %d" % n, "why": "left", "picked": None, "url": None,
            "target": None, "source": "report", "quoted": None}


def _record(track, *items):
    open_items.write_atomic(
        str(track / "open-items.md"),
        open_items.render({"branch": "track/x", "applied": [], "items": list(items)}))


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, encoding="utf-8")


def _report(severity_line):
    entry = ["1. new unfixed-minor", "   What: w", "   Where: src/a.py:3", "   Why left: y"]
    if severity_line is not None:
        entry.append("   " + severity_line)
    return "## Report\n- x\n\n## Open items\n" + "\n".join(entry) + "\n"


def _add(track, project, tmp_path, report):
    f = tmp_path / "report.md"
    f.write_text(report, encoding="utf-8")
    return _run("add", "--track-dir", str(track), "--project-dir", str(project),
                "--stage", "verify", "--report-file", str(f))


def test_unfixable_pending_items_offer_no_fix_action():
    items = [dict(_item(1, "major", "fix-pending"), fixable=False),
             dict(_item(2, "minor", "fix-pending"), fixable=False)]
    lines = open_items._grouped(items, [open_items.FIX, open_items.FILE_ISSUE,
                                      open_items.NOTE_PR, open_items.ACCEPT])
    assert "menu: Note on the PR | Accept as is" in lines
    assert not any("Fix " in line for line in lines if "menu:" in line)


def test_report_can_mark_a_new_item_unfixable(track, project, tmp_path):
    done = _add(track, project, tmp_path,
                _report("Severity: major") + "   Fixable: no\n")
    assert done.returncode == 0, done.stderr
    assert open_items.load(str(track))["items"][0]["fixable"] is False


def test_verify_can_mark_a_fix_pending_item_unfixable(track, project, tmp_path):
    _record(track, _item(1, "major", "fix-pending"))
    done = _add(track, project, tmp_path,
                "## Open items\n1. unfixable open-1\n"
                "   Why left: Requires a manual observation before merging\n")
    assert done.returncode == 0, done.stderr
    item = open_items.load(str(track))["items"][0]
    assert item["state"] == "fix-pending" and item["fixable"] is False
    assert item["why"] == "Requires a manual observation before merging"
    lines = open_items.options(str(track), str(project), "stop")
    assert "menu: Note on the PR | Accept as is" in lines


def test_mixed_batch_fixes_only_actionable_items(track, project):
    _record(track, _item(1, "minor"), dict(_item(2, "major"), fixable=False))
    lines = open_items.options(str(track), str(project), "stop")
    assert "menu: Fix minor | Note on the PR | Accept as is" in lines
    assert "open-2 menu: File a GitHub issue | Note on the PR | Accept as is" in lines
    open_items.decide_all(str(track), str(project), "fix-all", "stop")
    items = open_items.load(str(track))["items"]
    assert [i["state"] for i in items] == ["fix-pending", "queued-note"]


def test_unfixable_item_refuses_individual_fix_without_writes(track, project):
    _record(track, dict(_item(1, "major"), fixable=False))
    before = (track / "open-items.md").read_bytes()
    with pytest.raises(open_items.OpenItemsError, match="not fixable"):
        open_items.decide(str(track), str(project), "open-1", "fix-now", "stop")
    assert (track / "open-items.md").read_bytes() == before


@pytest.mark.parametrize("value", ["maybe", "", "true"])
def test_report_refuses_invalid_fixability(track, project, tmp_path, value):
    done = _add(track, project, tmp_path,
                _report("Severity: major") + "   Fixable: " + value + "\n")
    assert done.returncode == 2 and not (track / "open-items.md").exists()


# ---- the report and the record ------------------------------------------------

@pytest.mark.parametrize("value", ["major", "minor"])
def test_add_stores_the_reported_severity(track, project, tmp_path, value):
    done = _add(track, project, tmp_path, _report("Severity: %s" % value))
    assert done.returncode == 0, done.stderr
    assert open_items.load(str(track))["items"][0]["severity"] == value


def test_add_refuses_an_entry_without_severity(track, project, tmp_path):
    done = _add(track, project, tmp_path, _report(None))
    assert done.returncode == 2
    assert "Severity" in done.stderr
    assert not (track / "open-items.md").exists()


def test_add_refuses_a_severity_outside_major_and_minor(track, project, tmp_path):
    done = _add(track, project, tmp_path, _report("Severity: blocker"))
    assert done.returncode == 2
    assert "major or minor" in done.stderr


def test_render_writes_format_3_with_severity_and_fixability(track):
    _record(track, _item(1, "minor"))
    text = (track / "open-items.md").read_text(encoding="utf-8")
    assert text.startswith("# open items\nformat: 3\n")
    assert "\nkind: unfixed-minor\nseverity: minor\nfixable: yes\nwhere: " in text


def test_a_format_2_record_keeps_fix_choices(track, project):
    _record(track, _item(1, "minor"))
    path = track / "open-items.md"
    path.write_text(path.read_text(encoding="utf-8").replace("format: 3", "format: 2")
                    .replace("fixable: yes\n", ""), encoding="utf-8")
    assert open_items.load(str(track))["items"][0]["fixable"] is True
    assert "menu: Fix minor | Note on the PR | Accept as is" in open_items.options(
        str(track), str(project), "stop")


@pytest.mark.parametrize("pick", ["fix-major", "fix-all"])
def test_unfixable_batch_refuses_fix_without_writes(track, project, pick):
    _record(track, dict(_item(1, "major", "fix-pending"), fixable=False))
    before = (track / "open-items.md").read_bytes()
    with pytest.raises(open_items.OpenItemsError, match="no fixable item"):
        open_items.decide_all(str(track), str(project), pick, "stop")
    assert (track / "open-items.md").read_bytes() == before


@pytest.mark.parametrize("entry", ["1. unfixable open-1",
    "1. unfixable open-1\n   Why left: Requires a manual check\n   What: replacement"])
def test_unfixable_report_requires_one_reason_and_preserves_record(track, project, tmp_path, entry):
    _record(track, _item(1, "major", "fix-pending"))
    before = (track / "open-items.md").read_bytes()
    done = _add(track, project, tmp_path, "## Open items\n" + entry + "\n")
    assert done.returncode == 2
    assert (track / "open-items.md").read_bytes() == before


def test_an_undecided_item_cannot_be_marked_unfixable_as_a_fix_result(track, project, tmp_path):
    _record(track, _item(1, "major"))
    before = (track / "open-items.md").read_bytes()
    done = _add(track, project, tmp_path,
                "## Open items\n1. unfixable open-1\n   Why left: Manual check\n")
    assert done.returncode == 2
    assert (track / "open-items.md").read_bytes() == before


def test_done_menu_omits_fix_actions_and_fix_warnings_for_unfixable_items(track, project):
    ledger.append(str(track), "ship", "passed", note="PR #7")
    _record(track, dict(_item(1, "major", "fix-pending"), fixable=False))
    lines = open_items.options(str(track), str(project), "done", pr=7, pr_state="OPEN")
    assert "menu: Note on the PR | Accept as is" in lines
    assert not any("Fix " in line for line in lines if "menu:" in line)
    assert not any("commit answer" in line or "working tree" in line for line in lines)


def test_a_format_1_record_still_loads_with_every_item_major(track):
    (track / "open-items.md").write_text(
        "# open items\nformat: 1\nbranch: none\nitems: 1\napplied: none\n\n"
        "## open-1\nstate: undecided\nstage: build\nkind: deviation\nwhere: none\n"
        "what: w\nwhy: y\npicked: none\nurl: none\ntarget: none\nsource: report\n"
        "quoted: 0 lines\n", encoding="utf-8")
    assert open_items.load(str(track))["items"][0]["severity"] == "major"


def test_an_imported_left_open_line_is_major(track, project):
    (track / "state.md").write_text(
        (track / "state.md").read_text(encoding="utf-8").replace(
            "| verify | done | — |  |", "| verify | done | — | Left open: Minor A |"),
        encoding="utf-8")
    record = open_items.ensure_record(str(track), str(project))
    assert [i["severity"] for i in record["items"]] == ["major"]


# ---- options at the stop: one grouped menu ------------------------------------

def test_stop_groups_by_severity_and_prints_one_menu(track, project):
    _record(track, _item(1, "major"), _item(2, "minor"), _item(3, "major"),
            _item(4, "minor", state="accepted"))
    lines = open_items.options(str(track), str(project), "stop")
    assert lines[0] == "Major:"
    minor_at = lines.index("Minor:")
    assert [ln for ln in lines[:minor_at] if ln.startswith("open-")] == [
        "open-1 [verify] unfixed-minor", "open-3 [verify] unfixed-minor"]
    assert [ln for ln in lines[minor_at:] if ln.startswith("open-")] == [
        "open-2 [verify] unfixed-minor"]
    menus = [ln for ln in lines if "menu: " in ln]
    assert menus == ["menu: %s | %s | %s | %s" % (FIX_MAJOR, FIX_ALL, NOTE, ACCEPT),
                     "per-item menu: " + PER_ITEM]


@pytest.mark.parametrize("severities,first", [
    (["major", "major"], FIX_MAJOR),
    (["minor", "minor"], FIX_MINOR),
])
def test_stop_menu_with_one_severity_has_one_fix_option(track, project, severities, first):
    _record(track, *[_item(n, s) for n, s in enumerate(severities, 1)])
    lines = open_items.options(str(track), str(project), "stop")
    assert ("Major:" in lines) == ("major" in severities)
    assert ("Minor:" in lines) == ("minor" in severities)
    assert "menu: %s | %s | %s" % (first, NOTE, ACCEPT) in lines


# ---- options at done: the same one menu, cut by the PR's state ------------------

def _menus(lines):
    return [ln for ln in lines if "menu: " in ln]


def _shipped(track, rounds=0):
    ledger.append(str(track), "ship", "passed", note="PR #7")
    for _ in range(rounds):
        ledger.append(str(track), "verify", "passed")


def test_done_with_an_open_pr_groups_and_offers_the_fixes(track, project):
    _shipped(track)
    _record(track, _item(1, "major"), _item(2, "minor"))
    lines = open_items.options(str(track), str(project), "done", pr=7, pr_state="OPEN")
    assert lines[0] == "Major:" and "Minor:" in lines
    assert _menus(lines) == [
        "menu: %s | %s | %s | %s" % (FIX_MAJOR, FIX_ALL, NOTE, ACCEPT),
        "per-item menu: " + PER_ITEM]


def test_done_with_both_rounds_spent_offers_no_fix(track, project):
    _shipped(track, rounds=2)
    _record(track, _item(1, "major"))
    lines = open_items.options(str(track), str(project), "done", pr=7, pr_state="OPEN")
    assert _menus(lines) == [
        "menu: %s | %s" % (NOTE, ACCEPT),
        "per-item menu: File a GitHub issue | %s | %s" % (NOTE, ACCEPT)]


def test_done_with_a_merged_pr_batches_only_accept(track, project):
    # File writes one public issue per item, so it is never a batch pick.
    _shipped(track)
    _record(track, _item(1, "major"), _item(2, "minor"))
    lines = open_items.options(str(track), str(project), "done", pr=7, pr_state="MERGED")
    assert _menus(lines) == ["menu: " + ACCEPT,
                             "per-item menu: File a GitHub issue | " + ACCEPT]


def test_done_with_no_pr_and_no_branch_batches_accept_and_stop(track, project):
    _record(track, _item(1, "major"))
    lines = open_items.options(str(track), str(project), "done")
    stop = "Stop: I will push the branch first"
    assert _menus(lines) == ["menu: %s | %s" % (ACCEPT, stop),
                             "per-item menu: %s | %s" % (ACCEPT, stop)]


def test_done_asks_a_filing_item_on_its_own(track, project):
    _shipped(track)
    filing = dict(_item(2, "minor", state="filing"), target="issue")
    _record(track, _item(1, "major"), filing)
    lines = open_items.options(str(track), str(project), "done", pr=7, pr_state="MERGED")
    minor_or_end = lines.index("open-2 [verify] unfixed-minor")
    assert "Minor:" not in lines
    assert lines[minor_or_end + 4:minor_or_end + 6] == [
        "open-2 check-github", "open-2 menu: File a GitHub issue | " + ACCEPT]


# ---- decide-all ---------------------------------------------------------------

def _states(track):
    return {i["id"]: i["state"] for i in open_items.load(str(track))["items"]}


def _decide_all(track, project, pick):
    return _run("decide-all", "--track-dir", str(track), "--project-dir", str(project),
                "--pick", pick, "--at", "stop")


def test_fix_major_fixes_majors_and_notes_minors(track, project):
    _record(track, _item(1, "major"), _item(2, "minor"), _item(3, "minor", state="accepted"),
            _item(4, "major", state="fix-pending"))
    done = _decide_all(track, project, "fix-major")
    assert done.returncode == 0, done.stderr
    assert _states(track) == {"open-1": "fix-pending", "open-2": "queued-note",
                              "open-3": "accepted", "open-4": "fix-pending"}
    picked = {i["id"]: i["picked"] for i in open_items.load(str(track))["items"]}
    assert picked["open-1"]["pick"] == "fix-now" and picked["open-1"]["at"] == "stop"
    assert picked["open-2"]["pick"] == "note"
    assert picked["open-3"] is None


@pytest.mark.parametrize("pick,major,minor", [
    ("fix-all", "fix-pending", "fix-pending"),
    ("note", "queued-note", "queued-note"),
    ("accept", "accepted", "accepted"),
])
def test_the_other_batch_picks_apply_to_every_asked_item(track, project, pick, major, minor):
    _record(track, _item(1, "major"), _item(2, "minor"))
    assert _decide_all(track, project, pick).returncode == 0
    assert _states(track) == {"open-1": major, "open-2": minor}


def test_decide_all_leaves_a_filing_item_to_its_own_menu(track, project):
    item = dict(_item(2, "minor", state="filing"), target="issue")
    _record(track, _item(1, "major"), item)
    assert _decide_all(track, project, "accept").returncode == 0
    assert _states(track) == {"open-1": "accepted", "open-2": "filing"}


def test_decide_all_at_done_records_done(track, project):
    _record(track, _item(1, "major"), _item(2, "minor"))
    done = _run("decide-all", "--track-dir", str(track), "--project-dir", str(project),
                "--pick", "accept", "--at", "done")
    assert done.returncode == 0, done.stderr
    items = open_items.load(str(track))["items"]
    assert [(i["state"], i["picked"]["at"]) for i in items] == [
        ("accepted", "done"), ("accepted", "done")]
