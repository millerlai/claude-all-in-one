"""Pure timing summaries; synthetic admission is not platform evidence."""
import json

import pytest

import ledger
import timing
import timing_report
import timing_sources


def event(kind, ident, **fields):
    return dict(format=1, event_id=ident, run_id="run", stage="build",
                platform="codex", kind=kind, **fields)


def run(coverage=True):
    rows = [event("run_begin", "run"), event("actor_bind", "actor",
        actor_id="main", session_id="session", source_id="synthetic:v1",
        source_run_id="synthetic-run", parent_actor_id=None), event("run_end", "end")]
    if coverage:
        rows.append(event("source_coverage", "coverage", source_id="synthetic:v1",
            capture_id="capture", start_token="start", end_token="end",
            actor_ids=["main"], coverage_scope=sorted(timing.COVERAGE_SCOPE)))
    return rows


def activity(ident="work", start=0, end=30000):
    return [event(kind, ident + kind, actor_id="main", source_id="synthetic:v1",
                  activity_id=ident, at_ms=value)
            for kind, value in (("work_begin", start), ("work_end", end))]


@pytest.fixture(autouse=True)
def synthetic_source(monkeypatch):
    monkeypatch.setattr(timing_sources, "source_admitted",
                        lambda source, platform: source == "synthetic:v1")


def test_union_overlaps_adjacency_and_empty():
    assert timing_report.union_ms([(0, 30000), (10000, 50000)]) == 50000
    assert timing_report.union_ms([(0, 30000), (10000, 50000), (120000, 140000)]) == 70000
    assert timing_report.union_ms([(3, 5), (0, 3), (5, 5)]) == 5
    assert timing_report.union_ms([]) == 0


def test_out_of_order_duplicates_and_shared_example():
    rows = run() + activity() + activity("child", 10000, 50000) + activity("resume", 120000, 140000)
    intervals, gaps = timing_report.work_intervals(list(reversed(rows)) + rows)
    assert not gaps
    assert timing_report.union_ms(intervals["build"]) == 70000
    assert timing_report.track_timing(rows, [])["build"] == {
        "elapsed_ms": 70000, "timing_status": "complete", "timing_reasons": []}


def test_complete_zero_requires_positive_coverage():
    assert timing_report.track_timing(run(), [])["build"]["elapsed_ms"] == 0
    result = timing_report.track_timing(run(False), [])["build"]
    assert result["elapsed_ms"] is None
    assert result["timing_status"] == "incomplete"
    assert "coverage-missing" in result["timing_reasons"]


@pytest.mark.parametrize("change,reason", [
    (lambda rows: rows.pop(), "open-activity"),
    (lambda rows: rows.pop(-2), "begin-missing"),
    (lambda rows: rows[-1].update(at_ms=-1), "invalid-boundary"),
    (lambda rows: rows[-1].update(at_ms=True), "invalid-boundary"),
    (lambda rows: rows[-2].update(at_ms=40000), "invalid-boundary"),
    (lambda rows: rows[-1].update(source_id="unknown"), "source-unverified"),
    (lambda rows: rows.pop(1), "binding-missing"),
    (lambda rows: rows.append(dict(rows[1], event_id="other", session_id="other")), "binding-ambiguous"),
])
def test_unreliable_activity_is_never_guessed(change, reason):
    rows = run() + activity()
    change(rows)
    result = timing_report.track_timing(rows, [])["build"]
    assert result["timing_status"] == "incomplete"
    assert result["elapsed_ms"] is None
    assert reason in result["timing_reasons"]


def test_conflicting_id_excludes_all_variants_but_preserves_lower_bound():
    rows = run() + activity() + activity("good", 50000, 60000)
    rows.append(dict(rows[4], at_ms=5))
    result = timing_report.track_timing(rows, [])["build"]
    assert result["elapsed_ms"] == 10000
    assert result["timing_status"] == "incomplete"
    assert "event-conflict" in result["timing_reasons"]


def test_gap_and_open_run_preserve_lower_bound():
    rows = [row for row in run() if row["kind"] != "run_end"] + activity()
    rows.append(event("gap", "gap", actor_id="main", reason="source-lost"))
    result = timing_report.track_timing(rows, [])["build"]
    assert result["elapsed_ms"] == 30000
    assert result["timing_reasons"] == ["run-open", "source-lost"]


def test_work_intervals_returns_explicit_gap_and_reliable_intervals():
    rows = run() + activity()
    rows.append(event("gap", "gap", actor_id="main", reason="source-lost"))
    intervals, gaps = timing_report.work_intervals(rows)
    assert intervals["build"] == [(0, 30000)]
    assert gaps == [{"stage": "build", "run_id": "run", "reason": "source-lost"}]


def test_runs_union_within_stage_only_and_all_six_stages():
    rows = run() + activity()
    retry = [dict(row, run_id="retry", event_id="retry-" + row["event_id"]) for row in rows]
    for row in retry:
        if row["kind"] == "actor_bind":
            row["source_run_id"] = "synthetic-retry"
    rows += retry
    verify = [dict(row, stage="verify", run_id="verify", event_id="verify-" + row["event_id"])
              for row in run() + activity()]
    for row in verify:
        if row["kind"] == "actor_bind":
            row["source_run_id"] = "synthetic-verify"
    rows += verify
    result = timing_report.track_timing(rows, [])
    assert list(result) == ledger.stage_ids()
    assert result["build"]["elapsed_ms"] == result["verify"]["elapsed_ms"] == 30000
    assert result["intake"]["timing_status"] == "no-data"


def test_reruns_with_disjoint_work_accumulate_in_one_stage():
    # AC6: a failed run and its rerun both keep their real work. The copies in
    # the test above would give 30000 even if only one run were counted.
    first = run() + activity()
    second = [dict(row, run_id="rerun", event_id="rerun-" + row["event_id"])
              for row in run() + activity("again", 120000, 140000)]
    for row in second:
        if row["kind"] == "actor_bind":
            row["session_id"] = "session-2"
            row["source_run_id"] = "synthetic-rerun"
    result = timing_report.track_timing(first + second, [])["build"]
    assert result == {"elapsed_ms": 50000, "timing_status": "complete", "timing_reasons": []}


def test_run_with_no_actor_binding_is_incomplete_not_zero():
    # AC8: the marker was never seen, so nothing proves the stage had no work.
    rows = [event("run_begin", "run"), event("run_end", "end")]
    result = timing_report.track_timing(rows, [])["build"]
    assert result["elapsed_ms"] is None
    assert result["timing_status"] == "incomplete"
    assert "coverage-missing" in result["timing_reasons"]


@pytest.mark.parametrize("alter", [
    lambda rows: rows[-1].update(actor_ids=[]),
    lambda rows: rows[-1].update(coverage_scope=["model"]),
    lambda rows: rows.pop(2),
])
def test_insufficient_coverage_or_missing_run_end_cannot_report_zero(alter):
    rows = run()
    alter(rows)
    result = timing_report.track_timing(rows, [])["build"]
    assert result["timing_status"] == "incomplete"
    assert result["elapsed_ms"] is None


def test_missing_empty_malformed_and_unknown_format_journals(tmp_path):
    assert all(row["timing_status"] == "no-data" for row in timing_report.timing_report(str(tmp_path)).values())
    path = tmp_path / "timing.jsonl"
    for content in ("", "broken\n", json.dumps(dict(run()[0], format=2))):
        path.write_text(content, encoding="utf-8")
        assert all(row["timing_status"] == "incomplete" and row["elapsed_ms"] is None
                   for row in timing_report.timing_report(str(tmp_path)).values())


def test_read_problem_affects_unknown_scope_and_unknown_format_disables_intervals():
    result = timing_report.track_timing(run() + activity(), ["journal-malformed"])
    assert all(row["timing_status"] == "incomplete" for row in result.values())
    assert result["build"]["elapsed_ms"] == 30000
    result = timing_report.track_timing(run() + activity(), ["unsupported-format"])
    assert all(row["elapsed_ms"] is None for row in result.values())


def test_report_reads_durable_snapshot_without_changing_file(tmp_path):
    path = tmp_path / "timing.jsonl"
    raw = "".join(json.dumps(row) + "\n" for row in run() + activity())
    path.write_text(raw, encoding="utf-8")
    assert timing_report.timing_report(str(tmp_path))["build"]["elapsed_ms"] == 30000
    assert path.read_text(encoding="utf-8") == raw


def test_conflicting_run_ownership_cannot_produce_intervals():
    rows = run() + activity()
    rows.append(dict(rows[0], stage="verify", event_id="different-stage"))
    result = timing_report.track_timing(rows, [])
    for stage in ("build", "verify"):
        assert result[stage]["elapsed_ms"] is None
        assert "binding-ambiguous" in result[stage]["timing_reasons"]
    rows = run() + activity()
    rows.append(dict(rows[0], event_id="second-begin"))
    assert timing_report.track_timing(rows, [])["build"]["elapsed_ms"] is None


def test_unadmitted_independent_source_preserves_reliable_lower_bound():
    rows = run() + activity()
    rows += [dict(row, source_id="unknown", event_id="unknown-" + row["event_id"])
             for row in activity("unknown", 40000, 50000)]
    result = timing_report.track_timing(rows, [])["build"]
    assert result["elapsed_ms"] == 30000
    assert result["timing_status"] == "incomplete"
    assert "source-unverified" in result["timing_reasons"]


def test_malformed_tail_retains_reliable_durable_lower_bound(tmp_path):
    path = tmp_path / "timing.jsonl"
    raw = "".join(json.dumps(row) + "\n" for row in run() + activity()) + '{"format":'
    path.write_text(raw, encoding="utf-8")
    result = timing_report.timing_report(str(tmp_path))
    assert result["build"]["elapsed_ms"] == 30000
    assert all("journal-malformed" in row["timing_reasons"] for row in result.values())


def test_source_proof_cannot_cover_another_source_actor():
    rows = run()
    rows.append(event("actor_bind", "child", actor_id="child", session_id="child-session",
                      source_id="unknown", source_run_id="synthetic-child",
                      parent_actor_id="main"))
    result = timing_report.track_timing(rows, [])["build"]
    assert result["elapsed_ms"] is None
    assert "coverage-missing" in result["timing_reasons"]


def test_unreadable_journal_is_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(timing, "read_events", lambda path: ([], ["journal-unreadable"]))
    assert all(row["timing_status"] == "incomplete" and row["elapsed_ms"] is None
               for row in timing_report.timing_report(str(tmp_path)).values())
