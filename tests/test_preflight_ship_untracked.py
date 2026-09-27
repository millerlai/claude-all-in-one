"""ship's clean_tree used to block on any `git status --porcelain` output,
untracked files included, and named no path -- five of the last seven days'
blocked ship rows were tripped only by files unrelated to the branch (#198).

The maintainer's decision: untracked files this track did not produce never
block; tracked files with uncommitted changes still do, and are named.
`untracked_since_start` and `docs_not_in_git` are always-PASS reminders,
never gates.
"""
import json
import os
import subprocess
import sys

import pytest

import ledger
import preflight

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   capture_output=True, text=True)
    (repo / "f.txt").write_text("orig\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "root")
    git(repo, "checkout", "-b", "feat")
    return repo


def make_track(tmp_path, name="track"):
    """A six-row state.md fixture with verify's status set to done, so
    ship()'s status_check always passes -- these tests are about clean_tree
    and the two new probes, the same shape test_preflight_merge_check.py's
    make_track uses."""
    track = tmp_path / name
    track.mkdir(parents=True)
    rows = [("intake", "", "—", ""), ("discover", "", "", ""),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", "done", "—", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def write_design_row(track_dir, artifact):
    path = os.path.join(track_dir, "state.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("| design |  |  |  |", "| design |  | %s |  |" % artifact)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def clean_label(track_dir, repo):
    result = preflight.ship(track_dir, str(repo))
    return result[1]


def test_untracked_only_passes_clean_tree(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "scratch.txt").write_text("nobody committed this\n", encoding="utf-8")
    ok, label = clean_label(track, repo)
    assert ok is True
    assert "does not block" in label or "neither includes nor touches" in label


def test_modified_tracked_file_fails_and_is_named(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "f.txt").write_text("changed\n", encoding="utf-8")
    ok, label = clean_label(track, repo)
    assert ok is False
    assert label.startswith("clean_tree (")
    assert "f.txt" in label


def test_staged_new_file_blocks(tmp_path):
    """A staged new file counts as a tracked change: `git reset --soft` then
    commit would sweep it into the squash."""
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "new.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "new.txt")
    ok, label = clean_label(track, repo)
    assert ok is False
    assert "new.txt" in label


def test_more_than_ten_tracked_paths_are_capped(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    for i in range(12):
        (repo / ("f%d.txt" % i)).write_text("x\n", encoding="utf-8")
    git(repo, "add", *["f%d.txt" % i for i in range(12)])
    ok, label = clean_label(track, repo)
    assert ok is False
    assert "and 2 more" in label


@pytest.mark.skipif(os.name == "nt", reason="a control character is not a legal Windows filename")
def test_control_char_path_is_escaped(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    name = "evil\nname.txt"
    path = repo / name
    path.write_bytes(b"x")
    git(repo, "add", name)
    ok, label = clean_label(track, repo)
    assert ok is False
    assert "\n" not in label
    assert "\\x0a" in label


def test_untracked_since_start_lists_only_new_paths(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "a.txt").write_text("old\n", encoding="utf-8")
    with open(os.path.join(track, preflight.UNTRACKED_BASELINE_NAME), "w",
              encoding="utf-8") as fh:
        json.dump(["a.txt"], fh)
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    result = preflight.ship(track, str(repo))
    ok, label = result[4]
    assert ok is True
    assert label.startswith("untracked_since_start (")
    assert "b.txt" in label
    assert "a.txt" not in label


def test_track_dir_and_artifacts_are_not_listed_as_code(tmp_path):
    repo = make_repo(tmp_path)
    track_dir = os.path.join(str(repo), ".claude", "track", "feat")
    track = make_track(repo / ".claude" / "track", "feat")
    assert track == track_dir
    with open(os.path.join(track, preflight.UNTRACKED_BASELINE_NAME), "w",
              encoding="utf-8") as fh:
        json.dump([], fh)
    doc = repo / "docs" / "design" / "y-detail.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# y\n\n## Work breakdown\n\n| # | Unit |\n|---|---|\n| 1 | a |\n",
                   encoding="utf-8")
    write_design_row(track, "docs/design/y-detail.md")
    result = preflight.ship(track, str(repo))
    ok, label = result[4]
    assert ok is True
    assert "state.md" not in label
    assert "y-detail.md" not in label


def test_detail_doc_with_undecodable_bytes_does_not_crash_ship(tmp_path):
    """A detail design's `## Reference` section is read as UTF-8 to find the
    decisions doc it names (#198's _artifact_paths). A stray non-UTF-8 byte
    in that file -- a pasted smart quote, say -- must not crash the whole
    `ship` probe; the artifact is just skipped."""
    repo = make_repo(tmp_path)
    track_dir = os.path.join(str(repo), ".claude", "track", "feat")
    track = make_track(repo / ".claude" / "track", "feat")
    assert track == track_dir
    doc = repo / "docs" / "design" / "y-detail.md"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"# y\n\n## Reference\n\nsome text with byte \x93 here\n")
    write_design_row(track, "docs/design/y-detail.md")
    result = preflight.ship(track, str(repo))
    ok, label = result[4]
    assert ok is True


def test_detail_reference_and_ledger_artifact_both_reported(tmp_path):
    """`_artifact_paths` unions three sources (#198 critique): state.md's
    design row, a detail design's `## Reference`-named decisions doc, and an
    earlier pass's own `--artifact` recorded in the ledger. A track that has
    produced both a stance/decisions pair (via the ledger) and a later detail
    design referencing a *different* decisions doc must have both named."""
    repo = make_repo(tmp_path)
    track_dir = os.path.join(str(repo), ".claude", "track", "feat")
    track = make_track(repo / ".claude" / "track", "feat")
    assert track == track_dir

    stance_doc = repo / "stray-decisions.md"
    stance_doc.write_text("# stance\n", encoding="utf-8")
    ledger.append(track, "design", "passed", artifact=str(stance_doc))

    doc = repo / "docs" / "design" / "y-detail.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# y\n\n## Reference\n\n[decisions](docs/design/y-decisions.md)\n",
        encoding="utf-8")
    decisions_doc = repo / "docs" / "design" / "y-decisions.md"
    decisions_doc.write_text("# y decisions\n", encoding="utf-8")
    write_design_row(track, "docs/design/y-detail.md")

    result = preflight.ship(track, str(repo))
    ok, label = result[5]
    assert ok is True
    assert "stray-decisions.md" in label
    assert "y-decisions.md" in label


def test_no_baseline_says_so_and_lists_all(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    result = preflight.ship(track, str(repo))
    ok, label = result[4]
    assert ok is True
    assert "no baseline recorded" in label
    assert "b.txt" in label


def test_docs_not_in_git_lists_untracked_or_ignored_artifacts(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)

    kept_doc = repo / "kept-decisions.md"
    kept_doc.write_text("# t\n", encoding="utf-8")
    git(repo, "add", "kept-decisions.md")
    git(repo, "commit", "-m", "add tracked doc")

    stray_doc = repo / "stray-decisions.md"
    stray_doc.write_text("# u\n", encoding="utf-8")

    ledger.append(track, "design", "passed", artifact=str(kept_doc))
    ledger.append(track, "design", "passed", artifact=str(stray_doc))

    result = preflight.ship(track, str(repo))
    ok, label = result[5]
    assert ok is True
    assert label.startswith("docs_not_in_git (")
    assert "stray-decisions.md" in label
    assert "kept-decisions.md" not in label


def test_new_probes_pass_not_checked_outside_a_git_repo(tmp_path):
    track = make_track(tmp_path)
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    result = preflight.ship(track, str(non_repo))
    ok, label = result[4]
    assert ok is True
    assert "not checked" in label
    ok, label = result[5]
    assert ok is True
    assert "not checked" in label


def test_new_probes_come_after_merge_check(tmp_path):
    repo = make_repo(tmp_path)
    track = make_track(tmp_path)
    result = preflight.ship(track, str(repo))
    assert len(result) == 6
    assert result[1][1].startswith("clean_tree (")
    assert result[3][1].startswith("merges_cleanly (")
    assert result[4][1].startswith("untracked_since_start (")
    assert result[5][1].startswith("docs_not_in_git (")


def test_stage_ship_step1_ignores_untracked():
    path = os.path.join(os.path.dirname(ledger.__file__), "..", "skills",
                        "track", "references", "stage-ship.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("## Step 1")
    end = text.index("## Step 2")
    step1 = text[start:end]
    assert "--untracked-files=no" in step1


def test_shipper_md_ignores_untracked():
    """shipper.md's own preflight bullet has to match #198's decision, or the
    chore-tier subagent stops on a file the script no longer blocks on."""
    path = os.path.join(os.path.dirname(ledger.__file__), "..", "agents",
                        "shipper.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "untracked" in text
    assert "Dirty tree" not in text


def test_gate2_names_both_probes():
    path = os.path.join(os.path.dirname(ledger.__file__), "..", "skills",
                        "track", "references", "approval-gates.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("## Gate 2")
    end = text.index("## The other stops")
    gate2 = text[start:end]
    assert "untracked_since_start" in gate2
    assert "docs_not_in_git" in gate2
