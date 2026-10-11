"""The upgrade axis: files a released version left on disk, read by the
scripts in this checkout (#361).

Every other test builds its state.md, ledger.jsonl, pending.md and
model-choice.json with the code under test, so a change in what those files
look like passes all of them -- the writer and the reader moved together. A
person who updates the plugin in the middle of a track has no such luck: their
files were written by the release they came from.

Each directory under tests/fixtures/releases/ is that: the scripts of one
tag, run once, and their output never edited afterwards (its SOURCE.md says
which script wrote which file). A red test here means this checkout no longer
reads what that release wrote. Fix the reader, or name a deliberate break in
XFAIL below -- never edit a sample to turn it green. CONTRIBUTING.md,
`### Upgrade-axis samples`, has the rules and how to add a release.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ledger
import model_choice
import pending

RELEASES = Path(__file__).resolve().parent / "fixtures" / "releases"
TRACK_STATE = Path(ledger.__file__).resolve().parent / "track_state.py"
FEATURE = "export-csv"
VERSIONS = sorted(p.name for p in RELEASES.glob("v*") if p.is_dir())

# The releases #361 backfilled. Named so that a glob which stops matching
# fails a test instead of leaving every parametrized one with nothing to run.
BACKFILLED = ("v1.44.0", "v1.49.0", "v1.50.0")

# (release, reader) -> why this checkout deliberately no longer reads that
# file, naming the release that changed the format. The readers are the four
# names passed to releases() below. The sample itself stays as it is.
XFAIL = {}

# A drive letter or a home directory: what a path from the machine that
# generated a sample would start with.
LOCAL_PATH = re.compile(rb"\b[A-Za-z]:[\\/]|/home/|/Users/")


def releases(reader):
    return [pytest.param(v, marks=pytest.mark.xfail(reason=XFAIL[v, reader], strict=True))
            if (v, reader) in XFAIL else v for v in VERSIONS]


def install(version, tmp_path):
    """One release's sample, copied to where that release kept it: the track
    under <project>/.claude/track, the model choice under a config root.
    Returns the project root. Reading a copy is what keeps the sample itself
    from ever being written."""
    project = tmp_path / "project"
    shutil.copytree(RELEASES / version / "track", project / ".claude" / "track")
    shutil.copytree(RELEASES / version / "config", tmp_path / "config")
    return project


def test_the_backfilled_releases_are_present_each_with_its_source():
    assert set(BACKFILLED) <= set(VERSIONS)
    for version in VERSIONS:
        assert (RELEASES / version / "SOURCE.md").is_file(), version


@pytest.mark.parametrize("version", releases("status"))
def test_status_takes_an_old_track_to_its_next_stage(version, tmp_path):
    project = install(version, tmp_path)

    # From the project root with no --track-root: how the track skill runs it.
    done = subprocess.run([sys.executable, str(TRACK_STATE), "status"], cwd=project,
                          capture_output=True, text=True, encoding="utf-8")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "next: design" in done.stdout.splitlines()


@pytest.mark.parametrize("version", releases("ledger"))
def test_every_line_of_an_old_ledger_is_a_record(version, tmp_path):
    track = install(version, tmp_path) / ".claude" / "track" / FEATURE
    lines = [ln for ln in (track / "ledger.jsonl").read_bytes().split(b"\n") if ln.strip()]

    records = ledger.records(str(track))

    assert ledger.malformed_lines(str(track)) == []
    assert len(records) == len(lines)
    assert [(r["stage"], r["outcome"]) for r in records] == [
        ("intake", "passed"), ("discover", "skipped"), ("design", "failed")]


@pytest.mark.parametrize("version", releases("pending"))
def test_old_pending_questions_load_with_their_answers(version, tmp_path):
    track = install(version, tmp_path) / ".claude" / "track" / FEATURE

    data = pending.load(str(track / "pending.md"))

    assert (data["stage"], data["round"]) == ("design", 1)
    assert [(q["text"].split("\n")[0], q["status"], q["answer"])
            for q in data["questions"]] == [
        ("1. Which separator does the export write?", "answered", "A) comma"),
        ("2. Is the header row always written?", "open", None)]


@pytest.mark.parametrize("version", releases("model-choice"))
def test_an_old_model_choice_loads_from_where_it_was_saved(version, tmp_path, monkeypatch):
    install(version, tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    roles, _ = model_choice.load_spec(model_choice.ROOT)

    choice = model_choice.load_choice(model_choice.choice_path(), roles)

    assert choice == {"chore": "sonnet", "think": "fable"}


@pytest.mark.parametrize("version", VERSIONS)
def test_a_sample_holds_nothing_from_the_machine_that_made_it(version):
    """A sample is generated on a maintainer's machine, and this repository is
    public: a session id, a token count or a local path in one is a leak. The
    recipe avoids all three by running the old scripts with no session id."""
    root = RELEASES / version
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        assert not LOCAL_PATH.search(path.read_bytes()), path
    ledger_text = (root / "track" / FEATURE / "ledger.jsonl").read_text(encoding="utf-8")
    for line in ledger_text.splitlines():
        record = json.loads(line)
        assert record["session_id"] is None, line
        assert (record["orchestration"], record["agents"]) == ({}, {}), line
