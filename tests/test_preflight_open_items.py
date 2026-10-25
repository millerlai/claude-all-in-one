"""ship's preflight holds the first draft while an open item is undecided.

`open_items_decided` asks open_items.py through a subprocess (preflight.py
cannot import it: open_items imports preflight). fix-pending and filing hold
ship like undecided; a `ship` `passed` record on the ledger means the PR is
already open, so nothing is held then.
"""
import os

import ledger
import open_items
import preflight

LABEL = "open_items_decided"
STAGES = ("design", "build", "verify", "ship")


def make_track(tmp_path, left_open=""):
    track = tmp_path / "track"
    track.mkdir()
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    for stage in STAGES:
        note = left_open if stage == "build" else ""
        lines.append("| %s | %s |  | %s |" % (stage, "done" if stage == "verify" else "", note))
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def item(n, state):
    return {"id": "open-%d" % n, "state": state, "stage": "build", "kind": "deviation",
            "severity": "major", "where": None, "what": "thing %d" % n, "why": "because", "picked": None,
            "url": None, "target": None, "source": "report", "quoted": None}


def write_record(track, *states):
    record = {"branch": "feat", "applied": [],
              "items": [item(n, s) for n, s in enumerate(states, 1)]}
    with open(os.path.join(track, open_items.FILE_NAME), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(open_items.render(record))


def decided(track):
    ok, detail = preflight.open_items_decided(track)
    assert detail.startswith(LABEL + " (") and detail.endswith(")"), detail
    return ok, detail


def test_an_undecided_item_blocks(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "accepted", "undecided")
    ok, detail = decided(track)
    assert ok is False
    assert detail == ("open_items_decided (1 undecided: open-2 -- run the open-items "
                      "stop in approval-gates.md)")


def test_a_fix_pending_item_blocks(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "fix-pending")
    ok, detail = decided(track)
    assert ok is False and "1 undecided: open-1" in detail


def test_a_filing_item_blocks(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "filed", "filing", "undecided")
    ok, detail = decided(track)
    assert ok is False and "2 undecided: open-2, open-3" in detail


def test_every_item_settled_passes(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "accepted", "filed", "noted", "fixed", "queued-issue", "queued-note")
    assert decided(track)[0] is True


def test_no_record_and_no_left_open_passes(tmp_path):
    assert decided(make_track(tmp_path))[0] is True


def test_no_record_with_a_left_open_line_blocks(tmp_path):
    track = make_track(tmp_path, left_open="Left open: a thing; another")
    ok, detail = decided(track)
    assert ok is False and "2 undecided: open-1, open-2" in detail


def test_a_ship_passed_row_passes_whatever_the_record_holds(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "undecided", "fix-pending", "filing")
    ledger.append(track, "ship", "passed", note="PR #7")
    assert preflight.open_items_decided(track) == (
        True, "open_items_decided (not held: the PR is open, fix rounds are not held)")


def test_an_unreadable_record_blocks_and_quotes_the_line(tmp_path):
    track = make_track(tmp_path)
    with open(os.path.join(track, open_items.FILE_NAME), "w", encoding="utf-8") as fh:
        fh.write("not a record\n")
    ok, detail = decided(track)
    assert ok is False
    assert "open-items.md does not start with `# open items`" in detail


def test_a_script_that_crashes_blocks(tmp_path, monkeypatch):
    script = tmp_path / "boom.py"
    script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(preflight, "OPEN_ITEMS", str(script))
    ok, detail = decided(make_track(tmp_path))
    assert ok is False and "exit 1" in detail


def test_an_answer_that_is_not_one_undecided_line_blocks(tmp_path, monkeypatch):
    track = make_track(tmp_path)
    for text in ("hello", "undecided 0\nundecided 0", ""):
        script = tmp_path / "odd.py"
        script.write_text("print(%r)\n" % text, encoding="utf-8")
        monkeypatch.setattr(preflight, "OPEN_ITEMS", str(script))
        ok, _ = decided(track)
        assert ok is False, text


def test_a_script_that_cannot_run_blocks(tmp_path, monkeypatch):
    def hung(*args, **kwargs):
        raise preflight.subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(preflight.subprocess, "run", hung)
    ok, detail = decided(make_track(tmp_path))
    assert ok is False and "cannot run open_items.py" in detail


def test_a_missing_state_md_blocks(tmp_path):
    track = tmp_path / "empty"
    track.mkdir()
    ok, detail = decided(str(track))
    assert ok is False and "state.md" in detail


def test_ship_lists_the_check_and_prints_it_as_a_line(tmp_path):
    track = make_track(tmp_path)
    write_record(track, "undecided")
    labels = [d for _, d in preflight.ship(track, str(tmp_path))]
    assert any(d.startswith(LABEL + " (") for d in labels)
