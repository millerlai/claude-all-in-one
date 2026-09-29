"""Pins for the five Minor findings the verify stage left on `fix-issues`:
each is a guard the first tests passed without exercising.

1. `errors="replace"` in `preflight.git` / `track_start.git`.
2. `diff --quiet` exiting 0 on a clean tree is "nothing to review".
3. Each `find_base_ref` "did not answer" guard alone.
4. The real "not a git repository" branch of every `is_git_repo` caller.
5. `_stderr_line` returns only the first line of multi-line stderr.
"""
import subprocess

import pytest

import preflight
import track_start
from test_preflight_git_answer_failures import (
    SEVEN_CALLERS, make_repo, make_track, stub)


# --- 1 ---------------------------------------------------------------------

@pytest.mark.parametrize("helper", [preflight.git, track_start.git],
                         ids=["preflight", "track_start"])
def test_git_replaces_undecodable_bytes_instead_of_failing(tmp_path, helper):
    # Real git, no locale patch: a blob of bytes that are not UTF-8 in any
    # locale, so dropping errors="replace" fails on Linux and Windows alike.
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], capture_output=True)
    made = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          input=b"\xff\xfe\n", cwd=repo, capture_output=True)
    sha = made.stdout.decode("ascii").strip()

    done = helper(str(repo), "cat-file", "-p", sha)

    assert isinstance(done.stdout, str)
    assert "�" in done.stdout


# --- 2 ---------------------------------------------------------------------

def test_verify_clean_tree_with_no_diff_is_nothing_to_review(tmp_path):
    repo = make_repo(tmp_path)  # `feat` is level with `main`: diff --quiet exits 0

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (nothing to review)")]


# --- 3 ---------------------------------------------------------------------

@pytest.mark.parametrize("failing", [
    ("symbolic-ref", "--short"),
    ("rev-parse", "--verify", "--quiet"),
], ids=["symbolic-ref-only", "rev-parse-verify-only"])
def test_verify_base_ref_one_source_no_answer_names_the_failure(
        tmp_path, monkeypatch, failing):
    repo = make_repo(tmp_path)
    stub(monkeypatch, failing)

    assert preflight.verify(str(tmp_path / "track"), str(repo)) == [
        (False, "has_changes (git did not answer while finding the base ref)")]


# --- 4 ---------------------------------------------------------------------

@pytest.mark.parametrize("name,call", [(c[0], c[1]) for c in SEVEN_CALLERS],
                         ids=[c[0] for c in SEVEN_CALLERS])
def test_real_not_a_git_repository_is_named_by_every_caller(tmp_path, name, call):
    plain = tmp_path / "plain"
    plain.mkdir()
    track = make_track(tmp_path)
    where = str(plain)
    said = "%s is not a git repository" % where
    expected = {
        "intake": (False, "not_main_branch (%s)" % said),
        "track_ignored": (True, "track_ignored (%s)" % said),
        "verify": [(False, "has_changes (%s)" % said)],
        "untracked_since_start": (
            True, "untracked_since_start (not checked: %s)" % said),
        "docs_not_in_git": (True, "docs_not_in_git (not checked: %s)" % said),
        "ship": [(False, "clean_tree (%s)" % said),
                 (False, "not_main_branch (%s)" % said),
                 (True, "merges_cleanly (not checked: %s)" % said)],
        "track_start": (0, "%s -- leaving branch alone" % said),
    }[name]

    assert call(plain, track) == expected


# --- 5 ---------------------------------------------------------------------

def test_stderr_line_keeps_only_the_first_line_escaped():
    done = subprocess.CompletedProcess(
        ["git"], 128, "", "fatal: bad \x1b[2K path\nhint: second line\nthird\n")

    assert preflight._stderr_line(done) == "fatal: bad \\x1b[2K path"
