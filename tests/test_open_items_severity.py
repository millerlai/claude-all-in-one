"""#443: open items carry a severity, and the stop before ship asks one menu
for all of them instead of one menu per item.

Thirteen items meant thirteen menus in a row. Build and verify now mark each
`new` entry `Severity: major|minor`; `options --at stop` lists the items under
`Major:` and `Minor:` and prints one `menu:` line; `decide-all` records that one
pick for every item still asked. "Fix major" fixes the majors and queues the
minors as a note on the PR (maintainer decision, 2026-10-14). `done` keeps
asking item by item.
"""
import os
import subprocess
import sys

import pytest

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
    lines += ["| %s | done | — |  |" % s for s in ("intake", "design", "build", "verify")]
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


def test_render_writes_format_2_with_a_severity_line(track):
    _record(track, _item(1, "minor"))
    text = (track / "open-items.md").read_text(encoding="utf-8")
    assert text.startswith("# open items\nformat: 2\n")
    assert "\nkind: unfixed-minor\nseverity: minor\nwhere: " in text


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


def test_done_still_asks_item_by_item(track, project):
    _record(track, _item(1, "major"), _item(2, "minor"))
    lines = open_items.options(str(track), str(project), "done")
    assert "Major:" not in lines
    assert [ln for ln in lines if " menu: " in ln][0].startswith("open-1 menu: ")


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


def test_decide_all_refuses_done(track, project):
    _record(track, _item(1, "major"))
    done = _run("decide-all", "--track-dir", str(track), "--project-dir", str(project),
                "--pick", "accept", "--at", "done")
    assert done.returncode == 1
    assert _states(track) == {"open-1": "undecided"}
