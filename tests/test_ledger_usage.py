"""ledger.py's usage fields: the record's five new keys (orchestration,
agents, usage_problems, window_end, session_id) and _fit()'s new `limit`
parameter and fourth step.

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
`ledger.append`/`_fit` sections; this is unit 2 of the work breakdown. Each
test names the Verification-table row it stands for.

Usage is never passed to append() (D2) -- it is fetched from
usage_collector internally, so these tests monkeypatch
`ledger.usage_collector.collect` to control what "the transcript said"
without needing a real one on disk.
"""
import os

import ledger
import usage_collector

# The longest real model identifier observed (Budgets: 25 chars), so a
# 7-model worst case lands near the 2060-byte figure the design measured.
LONG_MODEL = "claude-haiku-4-5-2025100%d"
MAX_TOKENS = {key: 999999 for key in usage_collector.TOKEN_KEYS}


def _worst_case_models(n):
    """`n` distinct model ids, each at the maximum five-key token count."""
    return {(LONG_MODEL % i) + ("x" * 16): dict(MAX_TOKENS) for i in range(n)}


# --- today's shape is not rejected (Major-2 regression guard) --------------

def test_seven_models_and_a_long_note_still_write_note_truncated(tmp_path, monkeypatch):
    track = str(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-today")

    orchestration = _worst_case_models(4)
    agents = _worst_case_models(3)

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        return dict(orchestration), dict(agents), []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    note = "n" * 3800
    record = ledger.append(track, "build", "failed", note=note)

    # Note truncation is the step that fired -- nothing else was touched.
    assert record["note"].endswith(ledger.TRUNCATED)
    assert record["note"] != ledger.TRUNCATED  # some text survived, not just the marker
    assert "usage_collapsed" not in record
    assert record["orchestration"] == orchestration
    assert record["agents"] == agents

    line = ledger.records(track)[0]
    assert line["outcome"] == "failed"


# --- _fit's fourth step: collapse when the model count grows ---------------

def test_twenty_models_trigger_the_collapse_step(tmp_path, monkeypatch):
    track = str(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-many-models")

    # 20 distinct models per column, well past the 12-model threshold the
    # design measured for the (smaller) 3840-byte central-candidate target,
    # so this clears append()'s 4096-byte default regardless of key names.
    orchestration = _worst_case_models(20)
    agents = _worst_case_models(20)

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        return dict(orchestration), dict(agents), []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    record = ledger.append(track, "build", "passed", note="short note")

    assert record.get("usage_collapsed") is True
    # Per-model detail is gone; what's left is the five-key total.
    assert set(record["orchestration"].keys()) == set(usage_collector.TOKEN_KEYS)
    assert set(record["agents"].keys()) == set(usage_collector.TOKEN_KEYS)

    for key in usage_collector.TOKEN_KEYS:
        expected_orch = sum(m[key] for m in orchestration.values())
        expected_agents = sum(m[key] for m in agents.values())
        assert record["orchestration"][key] == expected_orch
        assert record["agents"][key] == expected_agents

    # attempts() must still be able to read this record -- collapsing usage
    # must not corrupt the mechanical fields the retry cap depends on.
    assert ledger.attempts(track, "build") == 0  # a "passed" resets the streak


# --- adjacent windows do not overlap (D4) -----------------------------------

def test_adjacent_windows_do_not_overlap(tmp_path, monkeypatch):
    track = str(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-window")

    calls = []

    def fake_collect(session_id, cwd, since, until, projects_root=None):
        calls.append((since, until))
        return {}, {}, []

    monkeypatch.setattr(ledger.usage_collector, "collect", fake_collect)

    record1 = ledger.append(track, "build", "passed", note="first")
    record2 = ledger.append(track, "verify", "passed", note="second")

    assert len(calls) == 2
    # First attempt in this session: no prior window, so the lower bound is
    # "since the start of this session" (collector's None).
    assert calls[0][0] is None
    assert calls[0][1] == record1["window_end"]

    # Second attempt's lower bound is exactly the first attempt's window_end
    # -- the boundary millisecond belongs to window 1 only (collector's
    # window is left-open, right-closed), so it is counted exactly once.
    assert calls[1][0] == record1["window_end"]
    assert calls[1][0] == calls[0][1]
    assert calls[1][1] == record2["window_end"]


# --- no session id: record still written, with the reason on file ----------

def test_missing_session_id_writes_empty_dicts_with_a_reason(tmp_path, monkeypatch):
    track = str(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    called = []
    monkeypatch.setattr(ledger.usage_collector, "collect",
                        lambda *a, **k: called.append(1) or ({}, {}, []))

    record = ledger.append(track, "build", "failed", note="no session")

    assert record["session_id"] is None
    assert record["orchestration"] == {}
    assert record["agents"] == {}
    assert record["usage_problems"] != []
    assert called == []  # collect() is never invoked without a session id
    assert "window_end" in record


# --- _fit's new `limit` parameter defaults to MAX_RECORD (unchanged) -------

def test_fit_without_limit_behaves_as_before():
    record = {"ts": "2026-08-30T00:00:00Z", "stage": "build", "outcome": "failed",
              "artifact": None, "sha256": None, "gate": "auto", "note": "x",
              "orchestration": {}, "agents": {}, "usage_problems": [],
              "window_end": "2026-08-30T00:00:00.000Z", "session_id": None}
    line, why = ledger._fit(record)
    assert why == ""
    assert len(line) <= ledger.MAX_RECORD


def test_fit_honours_a_smaller_limit():
    record = {"ts": "2026-08-30T00:00:00Z", "stage": "build", "outcome": "failed",
              "artifact": None, "sha256": None, "gate": "auto", "note": "n" * 200,
              "orchestration": _worst_case_models(20), "agents": {},
              "usage_problems": [], "window_end": "2026-08-30T00:00:00.000Z",
              "session_id": "sess-x"}
    # 500 fit the old 4-key collapsed total; the 5-key total needs a little
    # more room (measured: 548 bytes), so the limit moves with the schema.
    line, why = ledger._fit(record, limit=600)
    assert line is not None
    assert len(line) <= 600
    assert "usage_collapsed" in why or record.get("usage_collapsed")


# --- _fit's second step: artifact reduced to its basename (Major-4 guard) --

def test_fit_step_two_reduces_artifact_to_basename_when_note_alone_is_not_enough():
    long_artifact = "C:\\" + "\\".join(["deep-directory-segment"] * 10) + "\\artifact.txt"
    # A note short enough (<= len(TRUNCATED)) that step 1 always empties it
    # outright, regardless of how tight `limit` is -- so which step actually
    # shrank the record to fit is unambiguous.
    record = {"ts": "2026-08-30T00:00:00Z", "stage": "build", "outcome": "failed",
              "artifact": long_artifact, "sha256": "a" * 64, "gate": "auto",
              "note": "n" * 5,
              "orchestration": {}, "agents": {}, "usage_problems": [],
              "window_end": "2026-08-30T00:00:00.000Z", "session_id": "sess-x"}

    note_emptied = dict(record, note="")
    size_after_step_one = len(ledger._encode(note_emptied))
    basename_too = dict(note_emptied, artifact=os.path.basename(long_artifact))
    size_after_step_two = len(ledger._encode(basename_too))

    # A limit only the artifact-basename step (step 2) can reach: too small
    # for step 1 (emptied note, full path) alone, big enough once the path
    # is shortened too.
    limit = size_after_step_two + 5
    assert limit < size_after_step_one

    line, why = ledger._fit(record, limit=limit)

    assert line is not None
    assert record["artifact"] == os.path.basename(long_artifact)
    assert "usage_collapsed" not in record
    assert "basename" in why
