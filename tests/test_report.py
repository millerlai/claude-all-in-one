"""usage_report.py's three query functions -- `track_report()`,
`range_report()`, `data_start_date()` -- and the CLI that wraps them (unit 6
of the work breakdown; the price-table half, unit 5, is covered in
tests/test_prices.py and is not touched here).

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
`report` section plus D9/D10/D11; each test names the Verification-table row
or the parent task's numbered rule it stands for.
"""
import json
import os
import subprocess
import sys

import ledger
import usage_collector
import usage_report

# A small, fixed price table -- deterministic dollar amounts independent of
# whatever the shipped plugins/cai/prices.json happens to contain today.
# "model-a" is priced; "model-b" is deliberately absent (UC7).
PRICE_TABLE = {
    "version": "test-1",
    "models": {
        "model-a": {"input_tokens": 2.0, "output_tokens": 10.0,
                    "cache_read_input_tokens": 0.2,
                    "ephemeral_1h_input_tokens": 4.0,
                    "ephemeral_5m_input_tokens": 2.5},
    },
    "aliases": {},
    "override_count": 0,
    "override_error": None,
    "shipped_error": None,
}

TOKENS_A = {"input_tokens": 100, "output_tokens": 50,
            "cache_read_input_tokens": 10, "ephemeral_1h_input_tokens": 0,
            "ephemeral_5m_input_tokens": 0}
# Rates are USD per million tokens (matches plugins/cai/prices.json's
# convention): 100*2.0 + 50*10.0 + 10*0.2 == 702 -> $0.000702.
SPEND_A = (100 * 2.0 + 50 * 10.0 + 10 * 0.2 + 0 * 4.0 + 0 * 2.5) / 1000000.0

TOKENS_B = {"input_tokens": 40, "output_tokens": 20,
            "cache_read_input_tokens": 0, "ephemeral_1h_input_tokens": 0,
            "ephemeral_5m_input_tokens": 0}
TOKENS_B_TOTAL = sum(TOKENS_B.values())


def _append_with_usage(track_dir, stage, outcome, monkeypatch, orchestration=None,
                       agents=None, session_id="sess-fixed"):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session_id)
    monkeypatch.setattr(ledger.usage_collector, "collect",
                        lambda *a, **k: (dict(orchestration or {}), dict(agents or {}), []))
    return ledger.append(track_dir, stage, outcome)


def _money_str(amount):
    return "%.4f" % amount


# --- UC3: one track, every stage, plus a total -----------------------------

def test_track_report_lists_every_stage_and_a_total(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    stages = ledger.stage_ids()
    for stage in stages:
        _append_with_usage(track, stage, "passed", monkeypatch,
                           orchestration={"model-a": dict(TOKENS_A)})

    report = usage_report.track_report(track, PRICE_TABLE)

    for stage in stages:
        assert stage in report
    assert "TOTAL" in report
    assert _money_str(SPEND_A) in report
    assert _money_str(SPEND_A * len(stages)) in report


# --- UC4: two projects, one central ledger, grouped by stage ---------------

def test_range_report_groups_across_projects(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))

    for project in ("proj-one", "proj-two"):
        track = str(tmp_path / project / "track")
        os.makedirs(track)
        monkeypatch.setattr(os, "getcwd", lambda p=project: str(tmp_path / p))
        _append_with_usage(track, "build", "passed", monkeypatch,
                           orchestration={"model-a": dict(TOKENS_A)},
                           session_id="sess-" + project)

    report = usage_report.range_report(str(central_path), 30, PRICE_TABLE)

    assert "build" in report
    assert _money_str(SPEND_A * 2) in report


# --- UC5: GAP-02's four questions in one query ------------------------------

def test_range_report_counts_attempts_including_failed_and_blocked(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))
    track = str(tmp_path / "track")
    os.makedirs(track)

    _append_with_usage(track, "build", "failed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})
    _append_with_usage(track, "build", "blocked", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})

    report = usage_report.range_report(str(central_path), 30, PRICE_TABLE)

    # Which stage: "build". How many models: 1 ("model-a"). How many
    # attempts, retries included: 3. All three answers must be findable in
    # the same report.
    assert "attempts=3" in report
    assert "models=1" in report


# --- UC6: a dollar figure is always explained by the header, once ----------

def test_dollar_amounts_are_explained_once_in_the_header(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})

    report = usage_report.track_report(track, PRICE_TABLE)

    # There is a dollar amount, and the report explains what it means.
    assert "$" in report
    assert "equivalent API spend" in report
    assert "not billed" in report or "subscription" in report
    # The full sentence is stated once, in the header -- not repeated on
    # every data row, which buried the numbers it was supposed to help read.
    caveat_lines = [line for line in report.splitlines()
                    if "equivalent API spend" in line]
    assert len(caveat_lines) == 1

    # User's tradeoff (2026-08-30): every row still carries its own marker
    # on the dollar figure itself, so a single line cut out of context and
    # pasted elsewhere still reads as "not a real charge" -- without
    # repeating the whole sentence on each one.
    money_lines = [line for line in report.splitlines() if "$" in line]
    assert money_lines  # sanity: there is at least one dollar figure to mark
    for line in money_lines:
        assert "spend_equiv=" in line
        assert "spend=" not in line  # no bare, unmarked dollar field survives


# --- UC7: unpriced tokens are listed, never folded into the total as 0 -----

def test_unpriced_model_excluded_from_total_but_counted_separately(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A), "model-b": dict(TOKENS_B)})

    report = usage_report.track_report(track, PRICE_TABLE)

    # The priced model's spend is the total -- model-b contributes nothing
    # to it because there is no rate for it, not because it is free.
    assert _money_str(SPEND_A) in report
    # And its tokens are visible somewhere as unpriced, not silently 0.
    assert str(TOKENS_B_TOTAL) in report
    assert "unpriced" in report


# --- UC8: a query spanning back before the import date shows "no data" ----

def test_range_report_marks_days_before_import_as_no_data(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))
    marker = tmp_path / "central" / "usage-start.txt"
    os.makedirs(marker.parent, exist_ok=True)
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    marker.write_text(today + "\n", encoding="utf-8")
    central_path.write_text("", encoding="utf-8")  # exists, just empty

    report = usage_report.range_report(str(central_path), 30, PRICE_TABLE)

    assert "no data" in report.lower()
    assert "29" in report


# --- UC9: deleting the central ledger does not break the per-track report --

def test_track_report_survives_a_missing_central_ledger(tmp_path, monkeypatch):
    central_path = tmp_path / "central" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(central_path))
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})
    assert os.path.isfile(central_path)

    os.remove(central_path)

    report = usage_report.track_report(track, PRICE_TABLE)
    assert "build" in report
    assert _money_str(SPEND_A) in report


# --- D11: a record with no usage fields at all counts as "no data", not 0 -

def test_legacy_record_without_usage_fields_is_uncovered_not_zero(tmp_path):
    track = str(tmp_path / "track")
    os.makedirs(track)
    legacy = {"ts": "2026-01-01T00:00:00Z", "stage": "build", "outcome": "passed",
              "artifact": None, "sha256": None, "gate": "auto", "note": "pre-feature"}
    with open(os.path.join(track, "ledger.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(legacy) + "\n")

    report = usage_report.track_report(track, PRICE_TABLE)

    assert "build" in report
    # This attempt happened -- it must still be counted -- but it must not
    # silently contribute a spend of 0 or a token count of 0 as if it were
    # measured and found to be nothing.
    assert "attempts=1" in report
    assert "no usage data" in report.lower() or "uncovered" in report.lower()


# --- Blocker: a stage/total with zero covered attempts must show the
# no-data marker in its fields, never a fabricated $0.0000 or a 0 token
# count. A real track made entirely of pre-feature records is exactly the
# shape the coordinator ran into. ----------------------------------------

def test_track_with_only_legacy_records_shows_no_data_not_zero(tmp_path):
    track = str(tmp_path / "track")
    os.makedirs(track)
    stages = ledger.stage_ids()
    lines = []
    for index, stage in enumerate(stages):
        lines.append(json.dumps({
            "ts": "2026-01-01T00:00:00Z", "stage": stage, "outcome": "passed",
            "artifact": None, "sha256": None, "gate": "auto",
            "note": "pre-feature-%d" % index}))
    with open(os.path.join(track, "ledger.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    report = usage_report.track_report(track, PRICE_TABLE)

    assert "$0.0000" not in report
    assert "tokens=0" not in report
    assert usage_report.NO_DATA in report
    # The attempt counts themselves are real numbers, not suppressed.
    for stage in stages:
        assert "attempts=1" in [l for l in report.splitlines() if l.startswith(stage)][0]
    assert "TOTAL" in report


def test_partial_coverage_states_how_many_attempts_have_data(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})
    legacy = {"ts": "2026-01-01T00:00:00Z", "stage": "build", "outcome": "passed",
              "artifact": None, "sha256": None, "gate": "auto", "note": "legacy"}
    with open(os.path.join(track, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(legacy) + "\n")

    report = usage_report.track_report(track, PRICE_TABLE)
    build_line = [l for l in report.splitlines() if l.startswith("build")][0]

    assert "attempts=2" in build_line
    # The reader must not be able to mistake the printed numbers for
    # covering both attempts -- only one of the two has usage data.
    assert "1 of 2" in build_line


# --- Major: collapsed tokens and unpriced tokens are different problems,
# counted separately -----------------------------------------------------

def test_collapsed_tokens_are_not_folded_into_unpriced(tmp_path):
    track = str(tmp_path / "track")
    os.makedirs(track)
    collapsed = {
        "ts": "2026-08-30T00:00:00Z", "stage": "build", "outcome": "passed",
        "artifact": None, "sha256": None, "gate": "auto", "note": "",
        "orchestration": {"input_tokens": 500, "output_tokens": 100,
                          "cache_read_input_tokens": 0,
                          "ephemeral_1h_input_tokens": 0,
                          "ephemeral_5m_input_tokens": 0},
        "agents": {}, "usage_collapsed": True}
    with open(os.path.join(track, "ledger.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(collapsed) + "\n")

    report = usage_report.track_report(track, PRICE_TABLE)
    build_line = [l for l in report.splitlines() if l.startswith("build")][0]

    # No model identifier survived the collapse, so there is nothing to
    # blame the price table for -- this must not show up as "unpriced".
    assert "unpriced=0" in build_line
    assert "collapsed=600" in build_line


# --- data_start_date() reads the marker D10 writes --------------------------

def test_data_start_date_reads_the_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CAI_USAGE_LEDGER", raising=False)
    os.makedirs(tmp_path / "cai", exist_ok=True)
    (tmp_path / "cai" / "usage-start.txt").write_text("2026-08-30\n", encoding="utf-8")

    assert usage_report.data_start_date(str(tmp_path)) == "2026-08-30"


def test_data_start_date_is_none_when_never_written(tmp_path, monkeypatch):
    monkeypatch.delenv("CAI_USAGE_LEDGER", raising=False)
    assert usage_report.data_start_date(str(tmp_path)) is None


def test_data_start_date_honors_central_ledger_override(tmp_path, monkeypatch):
    """`range_report()` already respects CAI_USAGE_LEDGER (it derives the
    marker from the actual central_path it was given); this pins that a
    standalone call to data_start_date() -- which unit 7's skill may well
    make on its own -- agrees, rather than looking at a config_root the
    override has moved data away from."""
    override_ledger = tmp_path / "elsewhere" / "usage.jsonl"
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(override_ledger))
    os.makedirs(override_ledger.parent, exist_ok=True)
    (override_ledger.parent / "usage-start.txt").write_text("2026-08-30\n", encoding="utf-8")

    unrelated_config_root = str(tmp_path / "unrelated-config-root")
    assert usage_report.data_start_date(unrelated_config_root) == "2026-08-30"


# --- price table unreadable: all models unpriced, header says so, no 0s ---

def test_broken_shipped_price_table_makes_everything_unpriced_not_zero(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    _append_with_usage(track, "build", "passed", monkeypatch,
                       orchestration={"model-a": dict(TOKENS_A)})

    broken_table = {"version": "unknown", "models": {}, "aliases": {},
                    "override_count": 0, "override_error": None,
                    "shipped_error": "prices.json: cannot read or parse (boom)"}

    report = usage_report.track_report(track, broken_table)
    assert "unpriced" in report
    assert str(sum(TOKENS_A.values())) in report


# --- CLI: stdout is UTF-8, and both subcommands exit 0 ----------------------

SCRIPTS = os.path.dirname(usage_report.__file__)


def _run(*args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "usage_report.py"), *args],
                          capture_output=True)


def test_cli_track_report_prints_utf8(tmp_path, monkeypatch):
    track = str(tmp_path / "track")
    os.makedirs(track)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-cli")
    ledger.append(track, "build", "failed", note="三個未知都在別的 repo")

    done = _run("track", "--track-dir", track)
    assert done.returncode == 0, done.stderr
    text = done.stdout.decode("utf-8")
    assert "build" in text


def test_cli_range_report_exits_zero_with_no_central_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("CAI_USAGE_LEDGER", str(tmp_path / "central" / "usage.jsonl"))
    env = dict(os.environ)
    env["CAI_USAGE_LEDGER"] = str(tmp_path / "central" / "usage.jsonl")
    done = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "usage_report.py"), "range", "--days", "7"],
        capture_output=True, env=env)
    assert done.returncode == 0, done.stderr
    text = done.stdout.decode("utf-8")
    assert "no" in text.lower()
