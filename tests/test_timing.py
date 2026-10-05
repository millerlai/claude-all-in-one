"""Explicit ownership and durable timing events, independent of the viewer."""
import json
import os
import subprocess
import sys
import threading

import pytest

import timing
import timing_sources


def event(kind, event_id="event", **fields):
    candidate = dict(format=1, event_id=event_id, run_id="run", stage="build",
                     platform="codex", kind=kind)
    candidate.update(fields)
    return candidate


def track(tmp_path):
    path = tmp_path / ".claude" / "track" / "feature"
    timing.begin_run(str(path), "build", "run", "codex")
    timing.bind_actor(str(path), "run", "actor", "session", "source:v1", "dispatch-1")
    return path


def test_missing_journal_is_no_data(tmp_path):
    assert timing.read_events(str(tmp_path)) == ([], [])


def test_run_and_binding_are_durable_and_idempotent(tmp_path):
    path = track(tmp_path)
    original = (path / "timing.jsonl").read_bytes()
    timing.begin_run(str(path), "build", "run", "codex")
    timing.bind_actor(str(path), "run", "actor", "session", "source:v1", "dispatch-1")
    assert timing.read_events(str(path))[0][0]["kind"] == "run_begin"
    assert (path / "timing.jsonl").read_bytes() == original
    binding = timing.resolve_binding(str(tmp_path), "codex", "session", "actor", "dispatch-1")
    assert binding["track_dir"] == str(path)
    assert binding["run_id"] == "run"
    assert timing.resolve_binding(str(tmp_path), "claude", "session", "actor", "dispatch-1") is None
    assert timing.resolve_binding(str(tmp_path), "codex", "other", "actor", "dispatch-1") is None


@pytest.mark.parametrize("field,value", [
    ("format", True), ("format", 2), ("stage", "unknown"),
    ("platform", "other"), ("kind", "unknown"), ("event_id", ""),
    ("run_id", ""), ("extra", "raw content"),
])
def test_invalid_event_is_not_written(tmp_path, field, value):
    candidate = event("run_begin")
    candidate[field] = value
    with pytest.raises(ValueError):
        timing.append_event(str(tmp_path), candidate)
    assert not (tmp_path / "timing.jsonl").exists()


def test_unknown_source_cannot_write_work_or_coverage(tmp_path):
    path = track(tmp_path)
    for kind in ("work_begin", "work_end"):
        with pytest.raises(ValueError, match="source-unverified"):
            timing.append_event(str(path), event(kind, actor_id="actor",
                source_id="source:v1", activity_id="activity", at_ms=1))
    with pytest.raises(ValueError, match="source-unverified"):
        timing.append_event(str(path), event("source_coverage", source_id="source:v1",
            capture_id="capture", start_token="start", end_token="end",
            actor_ids=["actor"], coverage_scope=["model"]))
    assert timing_sources.source_admitted("source:v1", "codex") is False


def test_collect_unknown_source_records_gap_without_raw_payload(tmp_path):
    path = track(tmp_path)
    assert timing.collect_event(str(tmp_path), "codex", "session", "actor", "dispatch-1",
                                {"secret": "private text"}) == ["source-unverified"]
    events, problems = timing.read_events(str(path))
    assert not problems
    assert events[-1]["reason"] == "source-unverified"
    assert "private text" not in (path / "timing.jsonl").read_text()
    assert timing.collect_event(str(tmp_path), "codex", "missing", "actor", "dispatch-1", {}) == ["binding-missing"]


def test_ambiguous_binding_does_not_use_current_track(tmp_path):
    path = track(tmp_path)
    other = path.parent / "other"
    timing.begin_run(str(other), "build", "second", "codex")
    timing.bind_actor(str(other), "second", "actor", "session", "source:v1", "dispatch-1")
    (path.parent / "current").write_text("feature")
    assert timing.resolve_binding(str(tmp_path), "codex", "session", "actor", "dispatch-1") is None
    assert timing.collect_event(str(tmp_path), "codex", "session", "actor", "dispatch-1", {}) == ["binding-ambiguous"]


def test_end_preserves_binding_and_accepts_late_end(tmp_path, monkeypatch):
    path = track(tmp_path)
    monkeypatch.setattr(timing_sources, "source_admitted", lambda *args: True)
    timing.append_event(str(path), event("work_begin", "begin", actor_id="actor",
        source_id="source:v1", activity_id="activity", at_ms=20))
    timing.append_event(str(path), event("run_end", "end"))
    timing.append_event(str(path), event("work_end", "late", actor_id="actor",
        source_id="source:v1", activity_id="activity", at_ms=30))
    assert timing.resolve_binding(str(tmp_path), "codex", "session", "actor", "dispatch-1")
    assert not any(e.get("reason") == "open-activity" for e in timing.read_events(str(path))[0])
    with pytest.raises(ValueError):
        timing.bind_actor(str(path), "run", "new", "session", "source:v1", "dispatch-new")
    with pytest.raises(ValueError):
        timing.append_event(str(path), event("work_begin", "new", actor_id="actor",
            source_id="source:v1", activity_id="new", at_ms=40))


def test_out_of_order_end_and_invalid_time(tmp_path, monkeypatch):
    path = track(tmp_path)
    monkeypatch.setattr(timing_sources, "source_admitted", lambda *args: True)
    timing.append_event(str(path), event("work_end", "end", actor_id="actor",
        source_id="source:v1", activity_id="activity", at_ms=30))
    timing.append_event(str(path), event("work_begin", "begin", actor_id="actor",
        source_id="source:v1", activity_id="activity", at_ms=20))
    for value in (-1, True, 1.5):
        with pytest.raises(ValueError):
            timing.append_event(str(path), event("work_begin", "bad", actor_id="actor",
                source_id="source:v1", activity_id="bad", at_ms=value))


def test_reader_keeps_valid_rows_and_excludes_conflicting_ids(tmp_path):
    path = tmp_path / "timing.jsonl"
    first = event("run_begin")
    conflict = dict(first, stage="verify")
    good = event("run_begin", "other")
    path.write_text("\n".join([json.dumps(first), json.dumps(first),
        "invalid secret", json.dumps(conflict), json.dumps(good), '{"format":2}']), encoding="utf-8")
    events, problems = timing.read_events(str(tmp_path))
    assert events == [good]
    assert set(problems) == {"event-conflict", "journal-malformed", "unsupported-format"}
    assert "secret" not in str(problems)


def test_oversized_record_not_truncated(tmp_path):
    path = track(tmp_path)
    before = (path / "timing.jsonl").read_bytes()
    with pytest.raises(ValueError):
        timing.append_event(str(path), event("gap", actor_id="actor", reason="x" * 4096))
    assert (path / "timing.jsonl").read_bytes() == before


def test_unreadable_journal_is_a_gap(tmp_path, monkeypatch):
    path = track(tmp_path)
    def denied(*args, **kwargs):
        raise PermissionError("private filename")
    monkeypatch.setattr(timing, "_read_bytes", denied)
    assert timing.read_events(str(path)) == ([], ["journal-unreadable"])


def test_invalid_duplicate_also_invalidates_original_id(tmp_path):
    original = event("run_begin")
    invalid = dict(original, platform="unknown")
    (tmp_path / "timing.jsonl").write_text(
        json.dumps(original) + "\n" + json.dumps(invalid) + "\n", encoding="utf-8")
    events, problems = timing.read_events(str(tmp_path))
    assert events == []
    assert "event-conflict" in problems


def test_work_requires_binding_even_for_admitted_source(tmp_path, monkeypatch):
    timing.begin_run(str(tmp_path), "build", "run", "codex")
    monkeypatch.setattr(timing_sources, "source_admitted", lambda *args: True)
    with pytest.raises(ValueError, match="binding-missing"):
        timing.append_event(str(tmp_path), event("work_end", actor_id="actor",
            source_id="source:v1", activity_id="activity", at_ms=0))


def test_no_actor_hint_only_resolves_unique_session_binding(tmp_path):
    path = track(tmp_path)
    assert timing.resolve_binding(str(tmp_path), "codex", "session", None, "dispatch-1")["actor_id"] == "actor"
    timing.bind_actor(str(path), "run", "child", "session", "source:v1", "dispatch-1", parent_actor_id="actor")
    assert timing.resolve_binding(str(tmp_path), "codex", "session", None, "dispatch-1") is None


def test_source_run_id_routes_reused_session_to_exact_dispatch(tmp_path, monkeypatch):
    first = track(tmp_path)
    second = tmp_path / ".claude" / "track" / "second"
    timing.begin_run(str(second), "build", "second-run", "codex")
    timing.bind_actor(str(second), "second-run", "actor", "session", "source:v1",
                      source_run_id="dispatch-2")

    first_binding = timing.resolve_binding(str(tmp_path), "codex", "session", "actor",
                                           source_run_id="dispatch-1")
    second_binding = timing.resolve_binding(str(tmp_path), "codex", "session", "actor",
                                            source_run_id="dispatch-2")
    assert first_binding["run_id"] == "run"
    assert second_binding["run_id"] == "second-run"

    normalized = []
    def normalize(platform, payload, binding):
        normalized.append(binding["run_id"])
        return [event("gap", "routed-gap", run_id=binding["run_id"],
                      stage=binding["stage"], actor_id=binding["actor_id"], reason="test")]
    monkeypatch.setattr(timing_sources, "normalize_event", normalize)
    assert timing.collect_event(str(tmp_path), "codex", "session", "actor",
                                "dispatch-1", {}) == ["test"]
    assert normalized == ["run"]
    assert timing.resolve_binding(str(tmp_path), "codex", "session", "actor",
                                  source_run_id="missing") is None


def test_binding_and_run_close_are_one_atomic_transition(tmp_path, monkeypatch):
    path = track(tmp_path)
    original = timing._check_binding
    binding_checked = threading.Event()
    allow_binding_write = threading.Event()
    run_end_checked = threading.Event()
    errors = []
    events_during_binding = []

    def pause_binding(events, candidate):
        original(events, candidate)
        if candidate["kind"] == "actor_bind" and candidate["actor_id"] == "late":
            events_during_binding.append([row["kind"] for row in events])
            binding_checked.set()
            assert allow_binding_write.wait(5)
        if candidate["kind"] == "run_end":
            run_end_checked.set()

    monkeypatch.setattr(timing, "_check_binding", pause_binding)

    def bind():
        try:
            timing.bind_actor(str(path), "run", "late", "session", "source:v1",
                              source_run_id="dispatch-late")
        except Exception as exc:
            errors.append(("bind", repr(exc)))

    def close():
        try:
            timing.append_event(str(path), event("run_end", "end"))
        except Exception as exc:
            errors.append(("close", repr(exc)))

    binding_thread = threading.Thread(target=bind)
    binding_thread.start()
    assert binding_checked.wait(5)
    close_thread = threading.Thread(target=close)
    close_thread.start()
    assert not run_end_checked.wait(0.05)
    allow_binding_write.set()
    binding_thread.join(5)
    close_thread.join(5)

    assert not binding_thread.is_alive()
    assert not close_thread.is_alive()
    assert not errors, (errors, events_during_binding)
    kinds = [row["kind"] for row in timing.read_events(str(path))[0]]
    assert kinds.index("actor_bind") < kinds.index("run_end")


def test_eight_processes_append_fifty_records_without_loss(tmp_path):
    path = track(tmp_path)
    script = """import sys
import timing
for index in range(50):
    timing.append_event(sys.argv[1], dict(format=1, event_id=sys.argv[2]+':'+str(index),
        run_id='run', stage='build', platform='codex', kind='gap',
        actor_id='actor', reason='source-unverified'))
"""
    env = dict(os.environ, PYTHONPATH=os.path.dirname(timing.__file__))
    processes = [subprocess.Popen([sys.executable, "-c", script, str(path), str(index)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in range(8)]
    for process in processes:
        stdout, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, (stdout, stderr)
    events, problems = timing.read_events(str(path))
    assert not problems
    assert len(events) == 402


def project_track(tmp_path, name="feature"):
    return tmp_path / ".claude" / "track" / name


def begin(tmp_path, capsys, name="feature", stage="build", platform="claude"):
    code = timing.main(["begin", "--track-dir", str(project_track(tmp_path, name)),
                        "--stage", stage, "--platform", platform])
    return code, capsys.readouterr()


def test_begin_prints_one_marker_line_and_opens_a_marker_file(tmp_path, capsys):
    code, out = begin(tmp_path, capsys)
    assert code == 0 and out.err == ""
    lines = out.out.splitlines()
    assert len(lines) == 1 and lines[0].startswith("cai-timing-run: ")
    run_id = lines[0].split(": ", 1)[1]
    assert (tmp_path / ".claude" / "track" / ("timing-open." + run_id)).is_file()
    events, problems = timing.read_events(str(project_track(tmp_path)))
    assert not problems and [(e["kind"], e["run_id"], e["stage"], e["platform"]) for e in events] == [
        ("run_begin", run_id, "build", "claude")]
    # the marker is a file, so preflight's count of track directories is unchanged
    assert [p.name for p in (tmp_path / ".claude" / "track").iterdir() if p.is_dir()] == ["feature"]


@pytest.mark.parametrize("stage,platform", [("nonsense", "claude"), ("build", "codex"), ("build", "other")])
def test_begin_failure_prints_no_marker_and_exits_2(tmp_path, capsys, stage, platform):
    code, out = begin(tmp_path, capsys, stage=stage, platform=platform)
    assert code == 2 and out.out == ""
    assert len(out.err.strip().splitlines()) == 1
    assert not list((tmp_path / ".claude" / "track").glob("timing-open.*")) if (tmp_path / ".claude").exists() else True


def test_end_writes_run_end_removes_marker_and_is_repeatable(tmp_path, capsys):
    _, out = begin(tmp_path, capsys)
    run_id = out.out.split(": ", 1)[1].strip()
    args = ["end", "--track-dir", str(project_track(tmp_path)), "--run", run_id]
    assert timing.main(args) == 0
    assert timing.main(args) == 0  # a resend is a success
    events, _ = timing.read_events(str(project_track(tmp_path)))
    assert [e["kind"] for e in events] == ["run_begin", "run_end"]
    assert events[1]["stage"] == "build" and events[1]["platform"] == "claude"
    assert not list((tmp_path / ".claude" / "track").glob("timing-open.*"))


def test_end_of_unknown_run_exits_2(tmp_path, capsys):
    begin(tmp_path, capsys)
    capsys.readouterr()
    assert timing.main(["end", "--track-dir", str(project_track(tmp_path)), "--run", "nope"]) == 2
    assert timing.main(["end", "--track-dir", str(project_track(tmp_path, "other")), "--run", "nope"]) == 2


def test_begin_and_end_sweep_markers_of_closed_runs(tmp_path, capsys):
    _, first = begin(tmp_path, capsys)
    first_id = first.out.split(": ", 1)[1].strip()
    timing.end_run(str(project_track(tmp_path)), first_id)  # closed without the CLI: marker left behind
    stale = tmp_path / ".claude" / "track" / ("timing-open." + first_id)
    assert stale.exists()
    _, second = begin(tmp_path, capsys, "second")
    assert not stale.exists()
    second_id = second.out.split(": ", 1)[1].strip()
    assert (tmp_path / ".claude" / "track" / ("timing-open." + second_id)).exists()


def test_find_run_needs_exactly_one_track_and_reports_closed(tmp_path):
    one, two = project_track(tmp_path, "one"), project_track(tmp_path, "two")
    timing.begin_run(str(one), "build", "run-a", "claude")
    timing.begin_run(str(two), "verify", "run-b", "claude")
    found = timing.find_run(str(tmp_path), "run-a")
    assert found == {"track_dir": str(one), "stage": "build", "platform": "claude", "closed": False}
    timing.end_run(str(two), "run-b")
    assert timing.find_run(str(tmp_path), "run-b")["closed"] is True
    assert timing.find_run(str(tmp_path), "missing") is None
    timing.begin_run(str(two), "build", "run-a", "claude")  # same run id in a second track
    assert timing.find_run(str(tmp_path), "run-a") is None
    assert timing.find_run(str(tmp_path / "nowhere"), "run-a") is None
