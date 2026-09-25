"""viewer.py's ### cai_mapper component (find_track()).

Fixtures are entirely synthetic: made-up track names, session ids, state.md
content -- built to match preflight.data_rows()'s and ledger.records()'s real
formats, confirmed by reading plugins/cai/scripts/preflight.py and
plugins/cai/scripts/ledger.py, not guessed.
"""
import json
import os

import viewer

STAGE_IDS = ["intake", "discover", "design", "build", "verify", "ship"]


def _state_md(statuses):
    """A GFM table matching preflight.data_rows()'s expected shape: a header
    row and a `---` separator row, both skipped by data_rows(), then one row
    per stage id with (status, artifact, note) from `statuses`."""
    lines = ["| stage | status | artifact | note |", "|---|---|---|---|"]
    for sid in STAGE_IDS:
        status, artifact, note = statuses.get(sid, ("", "—", ""))
        lines.append("| %s | %s | %s | %s |" % (sid, status, artifact, note))
    return "\n".join(lines) + "\n"


def _write_track(track_root, name, statuses, ledger_records=None):
    track_dir = track_root / name
    track_dir.mkdir(parents=True)
    (track_dir / "state.md").write_text(_state_md(statuses), encoding="utf-8")
    if ledger_records:
        with open(track_dir / "ledger.jsonl", "w", encoding="utf-8") as fh:
            for record in ledger_records:
                fh.write(json.dumps(record) + "\n")
    return track_dir


def _ledger_record(stage, session_id, outcome="passed"):
    # Minimal shape ledger.records() understands -- read back verbatim by
    # json.loads, "line" added by records() itself, not written here.
    return {"ts": "2026-09-25T00:00:00Z", "stage": stage, "outcome": outcome,
            "artifact": None, "sha256": None, "gate": "auto", "note": "",
            "orchestration": {}, "agents": {}, "usage_problems": [],
            "window_end": "2026-09-25T00:00:00.000Z", "session_id": session_id}


def _setup_project(tmp_path):
    project_root = tmp_path / "project"
    track_root = project_root / ".claude" / "track"
    track_root.mkdir(parents=True)
    return project_root, track_root


# ============================================================ session_id ====

def test_session_id_match_gives_confirmed_track(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    statuses = {"intake": ("done", "—", ""), "discover": ("done", "—", ""),
                "design": ("done", "x-decisions.md", ""), "build": ("", "—", ""),
                "verify": ("", "—", ""), "ship": ("", "—", "")}
    _write_track(track_root, "feat-a", statuses,
                 ledger_records=[_ledger_record("design", "sess-123")])
    _write_track(track_root, "feat-b", {})

    result = viewer.find_track(str(project_root), "sess-123")

    assert result["name"] == "feat-a"
    assert result["certainty"] == "confirmed"
    assert result["stages"] == [
        {"id": "intake", "status": "done"}, {"id": "discover", "status": "done"},
        {"id": "design", "status": "done"}, {"id": "build", "status": ""},
        {"id": "verify", "status": ""}, {"id": "ship", "status": ""}]
    assert result["current"] == "build"
    assert result["gateWaiting"] == "build"


# ============================================================= fallback ====

def test_no_session_match_falls_back_to_current_feature(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    _write_track(track_root, "feat-a", {})
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), "sess-does-not-exist")

    assert result["name"] == "feat-a"
    assert result["certainty"] == "inferred"


def test_session_id_none_falls_back_to_current_feature(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    _write_track(track_root, "feat-a", {})
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), None)

    assert result["name"] == "feat-a"
    assert result["certainty"] == "inferred"


def test_neither_session_nor_current_resolves_returns_none(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    _write_track(track_root, "feat-a", {})
    # No "current" file written.

    result = viewer.find_track(str(project_root), "sess-does-not-exist")

    assert result is None


def test_current_names_a_missing_track_returns_none(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    (track_root / "current").write_text("ghost\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), None)

    assert result is None


# ============================================================ gateWaiting ===

def test_gate_waiting_ship_when_current_is_ship(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    statuses = {sid: ("done", "—", "") for sid in STAGE_IDS}
    statuses["ship"] = ("", "—", "")
    _write_track(track_root, "feat-a", statuses)
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), None)

    assert result["current"] == "ship"
    assert result["gateWaiting"] == "ship"


def test_gate_waiting_none_when_neither_condition_holds(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    statuses = {sid: ("done", "—", "") for sid in STAGE_IDS}
    statuses["design"] = ("", "—", "")
    _write_track(track_root, "feat-a", statuses)
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), None)

    assert result["current"] == "design"
    assert result["gateWaiting"] is None


def test_gate_waiting_none_when_every_stage_done(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    statuses = {sid: ("done", "—", "") for sid in STAGE_IDS}
    _write_track(track_root, "feat-a", statuses)
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    result = viewer.find_track(str(project_root), None)

    assert result["current"] is None
    assert result["gateWaiting"] is None


# ==================================================== format_status guard ===

def test_format_status_is_never_called(tmp_path, monkeypatch):
    project_root, track_root = _setup_project(tmp_path)
    _write_track(track_root, "feat-a", {})
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("track_state.format_status must not be called")

    monkeypatch.setattr(viewer.track_state, "format_status", boom)

    result = viewer.find_track(str(project_root), None)

    assert result["name"] == "feat-a"


# ==================================================== walking up / limits ===

def test_walks_up_from_a_nested_cwd(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    _write_track(track_root, "feat-a", {})
    (track_root / "current").write_text("feat-a\n", encoding="utf-8")

    nested = project_root / "src" / "pkg" / "sub"
    nested.mkdir(parents=True)

    result = viewer.find_track(str(nested), None)

    assert result["name"] == "feat-a"


def test_no_track_dir_within_reach_returns_none(tmp_path):
    lone = tmp_path / "no_track_here"
    lone.mkdir()
    assert viewer.find_track(str(lone), None) is None


def test_no_track_dir_anywhere_up_to_root_returns_none(tmp_path):
    # A deep chain with no .claude/track anywhere in it.
    deep = tmp_path
    for i in range(25):
        deep = deep / ("d%d" % i)
    deep.mkdir(parents=True)
    assert viewer.find_track(str(deep), None) is None


# =========================================================== done/skip ====

def test_done_directory_is_skipped_as_a_track_candidate(tmp_path):
    project_root, track_root = _setup_project(tmp_path)
    done_dir = track_root / "done"
    done_dir.mkdir()
    (done_dir / "state.md").write_text(_state_md({}), encoding="utf-8")
    with open(done_dir / "ledger.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_ledger_record("design", "sess-in-done")) + "\n")

    result = viewer.find_track(str(project_root), "sess-in-done")

    assert result is None
