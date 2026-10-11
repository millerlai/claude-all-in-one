"""ship's preflight names the stages a track skipped (#367).

`verify_status` passes a `skipped` verify row exactly as it passes a `done`
one -- on purpose, and test_preflight_status_gates.py pins it. So nothing the
person reads before the push said the branch was never reviewed: #363's audit
found the fact in state.md and in no line Gate 2 is told to quote.
`skipped_stages` is that line -- always PASS, a reminder and never a gate.
"""
import os
import subprocess
import sys

import ledger
import preflight

SCRIPTS = os.path.dirname(ledger.__file__)
PREFLIGHT_PY = os.path.join(SCRIPTS, "preflight.py")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
STAGES = ("intake", "discover", "design", "build", "verify", "ship")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def make_repo(tmp_path):
    """A clean repo on a feature branch: every blocking ship check passes."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   capture_output=True, text=True)
    (repo / "f.txt").write_text("orig\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "root")
    git(repo, "checkout", "-b", "feat")
    return repo


def make_track(tmp_path, newline="\n", **rows):
    """A six-row state.md. `rows` maps a stage to its (status, note); verify
    defaults to done so ship's own verify_status passes, the rest to empty.
    A skipped row carries the `—` artifact `/cai:track skip` writes."""
    track = tmp_path / "track"
    track.mkdir()
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    for stage in STAGES:
        status, note = rows.get(stage, ("done", "") if stage == "verify" else ("", ""))
        artifact = "—" if status == "skipped" else ""
        lines.append("| %s | %s | %s | %s |" % (stage, status, artifact, note))
    (track / "state.md").write_bytes((newline.join(lines) + newline).encode("utf-8"))
    return str(track)


def skipped_line(track, project):
    """ship()'s skipped_stages check, found by label so these tests say what
    is missing rather than tripping over a position."""
    found = [check for check in preflight.ship(track, str(project))
             if check[1].startswith("skipped_stages (")]
    assert len(found) == 1, "ship() returned %d skipped_stages line(s)" % len(found)
    return found[0]


def run_ship(track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, "ship", "--track-dir", track,
         "--project-dir", str(project)],
        capture_output=True, text=True, encoding="utf-8")


def test_skipped_verify_is_named_with_its_reason(tmp_path):
    track = make_track(tmp_path, verify=("skipped", "docs only"))
    assert skipped_line(track, tmp_path) == (True, "skipped_stages (verify: docs only)")


def test_every_skipped_stage_is_listed_in_table_order(tmp_path):
    track = make_track(tmp_path, verify=("skipped", "docs only"),
                       discover=("skipped", "solution space already clear"),
                       intake=("done", "problem statement confirmed"))
    assert skipped_line(track, tmp_path) == (
        True, "skipped_stages (discover: solution space already clear; verify: docs only)")


def test_no_skipped_stage_says_none(tmp_path):
    track = make_track(tmp_path, intake=("done", "x"), build=("in-progress", "unit 1 of 2"))
    assert skipped_line(track, tmp_path) == (True, "skipped_stages (none)")


def test_a_skipped_row_with_no_reason_says_so(tmp_path):
    # `/cai:track skip` refuses without --reason, but state.md is a file a
    # person can edit, and "verify: " would read as a truncated line.
    track = make_track(tmp_path, verify=("skipped", ""))
    assert skipped_line(track, tmp_path) == (
        True, "skipped_stages (verify: no reason recorded)")


def test_control_characters_in_a_reason_are_escaped(tmp_path):
    # Gate 2 quotes preflight's output verbatim into the ledger's --note.
    track = make_track(tmp_path, verify=("skipped", "docs \x1b[2K only"))
    ok, label = skipped_line(track, tmp_path)
    assert ok is True
    assert label == "skipped_stages (verify: docs \\x1b[2K only)"


def test_crlf_state_md_reads_the_same(tmp_path):
    track = make_track(tmp_path, newline="\r\n", verify=("skipped", "docs only"))
    assert skipped_line(track, tmp_path) == (True, "skipped_stages (verify: docs only)")


def test_ship_prints_the_line_and_still_exits_0(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path, verify=("skipped", "解法空間已清楚"))
    done = run_ship(track, repo)
    assert done.returncode == 0, done.stdout
    assert "PASS skipped_stages (verify: 解法空間已清楚)" in done.stdout.splitlines()
    assert "FAIL" not in done.stdout


def test_the_line_stays_pass_when_another_check_blocks(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "f.txt").write_text("changed\n", encoding="utf-8")   # trips clean_tree
    track = make_track(tmp_path, verify=("skipped", "docs only"))
    done = run_ship(track, repo)
    assert done.returncode == 2, done.stdout
    assert "FAIL clean_tree" in done.stdout
    assert "PASS skipped_stages (verify: docs only)" in done.stdout.splitlines()


def test_gate2_says_to_quote_the_line():
    path = os.path.join(SCRIPTS, "..", "skills", "track", "references",
                        "approval-gates.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    gate2 = text[text.index("## Gate 2"):text.index("## The other stops")]
    reminders = gate2[gate2.index("reminders ride along with this gate"):]
    reminders = " ".join(reminders[:reminders.index("**Standing alone**")].split())
    assert "`skipped_stages`" in reminders
    assert "in the same message" in reminders[reminders.index("`skipped_stages`"):]


def test_manual_counts_the_line_among_the_always_pass_ones():
    with open(os.path.join(REPO_ROOT, "MANUAL.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    paragraph = text[text.index("more lines always print as `PASS`"):]
    paragraph = paragraph[:paragraph.index("ever blocks.")]
    assert "`skipped_stages`" in paragraph
