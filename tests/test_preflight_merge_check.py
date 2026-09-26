"""merges_cleanly: a trial merge against the remote's default branch, done
with `git merge-tree --write-tree` so it never touches the working tree or
HEAD. ship() gates on it so a branch that would conflict on merge is caught
before the PR, not after.

Unit 1 of 4 (docs/design/2026-09-25-ship-preflight-merge-check-detail.md).
Units 2-3's own tests (approval-gates.md, MANUAL.md wiring) are added later
and deliberately absent here.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ledger
import preflight

PREFLIGHT_PY = os.path.join(os.path.dirname(ledger.__file__), "preflight.py")
GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]

_version = preflight.parse_git_version(
    subprocess.run(["git", "--version"], capture_output=True,
                   text=True).stdout)
needs_merge_tree = pytest.mark.skipif(
    _version is None or _version < preflight.MERGE_TREE_MIN_VERSION,
    reason="needs git >= 2.38 for merge-tree --write-tree")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def make_track(tmp_path):
    """A six-row state.md fixture with verify's status set to done, so
    ship()'s status_check always passes -- these tests are about the new
    merge_check, not the pre-existing one."""
    track = tmp_path / "track"
    track.mkdir()
    rows = [("intake", "", "—", ""), ("discover", "", "", ""),
            ("design", "", "", ""), ("build", "", "", ""),
            ("verify", "done", "—", ""), ("ship", "", "", "")]
    lines = ["# fixture", "", "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def write_lines(path, second_line):
    path.write_text("line1\n%s\nline3\n" % second_line, encoding="utf-8")


def conflict_fixture(tmp_path, names=("f.txt",), conflict=True):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    other = tmp_path / "other"

    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)],
                   capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "main", str(work)],
                   capture_output=True, text=True)
    git(work, "remote", "add", "origin", str(remote))
    for name in names:
        write_lines(work / name, "orig")
    git(work, "add", *names)
    git(work, "commit", "-m", "root")
    git(work, "push", "-u", "origin", "main")

    subprocess.run(["git", "clone", str(remote), str(other)],
                   capture_output=True, text=True)
    for name in names:
        write_lines(other / name, "main")
    git(other, "add", *names)
    git(other, "commit", "-m", "other advances")
    git(other, "push", "origin", "main")

    git(work, "checkout", "-b", "feat", "main")
    if conflict:
        for name in names:
            write_lines(work / name, "feat")
        git(work, "add", *names)
    else:
        (work / "other.txt").write_text("feat side\n", encoding="utf-8")
        git(work, "add", "other.txt")
    git(work, "commit", "-m", "feat advances")

    git(work, "fetch", "origin")
    return str(work), str(remote), str(other)


def run_ship(track, project):
    return subprocess.run(
        [sys.executable, PREFLIGHT_PY, "ship", "--track-dir", track,
         "--project-dir", project],
        capture_output=True, encoding="utf-8")


@needs_merge_tree
def test_conflict_blocks_and_names_base_and_files(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    track = make_track(tmp_path)
    sha, _ = git(work, "rev-parse", "refs/remotes/origin/main")
    sha7 = sha[:7]

    done = run_ship(track, work)
    assert done.returncode == 2, done.stdout
    expected = ("FAIL merges_cleanly (conflicts with origin/main at %s in 1 "
                "file(s): f.txt -- git fetch origin, merge origin/main into "
                "this branch, resolve the conflicts, then run verify again)"
                % sha7)
    assert expected in done.stdout


@needs_merge_tree
def test_clean_branch_passes_with_ref_and_sha(tmp_path):
    work, remote, other = conflict_fixture(tmp_path, conflict=False)
    track = make_track(tmp_path)
    sha, _ = git(work, "rev-parse", "refs/remotes/origin/main")
    sha7 = sha[:7]

    done = run_ship(track, work)
    assert done.returncode == 0, done.stdout
    expected = "PASS merges_cleanly (origin/main at %s -- merges cleanly)" % sha7
    assert expected in done.stdout


def test_no_base_ref_is_not_checked(tmp_path):
    work = tmp_path / "feature"
    subprocess.run(["git", "init", "-b", "feature", str(work)],
                   capture_output=True, text=True)
    (work / "f.txt").write_text("x\n", encoding="utf-8")
    git(work, "add", "f.txt")
    git(work, "commit", "-m", "root")
    track = make_track(tmp_path)

    done = run_ship(track, str(work))
    assert done.returncode == 0, done.stdout
    assert ("PASS merges_cleanly (not checked: none of origin/HEAD, "
            "origin/main, origin/master resolves to a commit)") in done.stdout


@needs_merge_tree
def test_dangling_origin_head_is_not_a_conflict(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    git(work, "remote", "set-head", "origin", "main")
    git(work, "update-ref", "-d", "refs/remotes/origin/main")
    track = make_track(tmp_path)

    done = run_ship(track, work)
    assert done.returncode == 0, done.stdout
    assert ("PASS merges_cleanly (not checked: none of origin/HEAD, "
            "origin/main, origin/master resolves to a commit)") in done.stdout


@needs_merge_tree
def test_local_branch_named_like_the_remote_is_ignored(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    git(work, "branch", "origin/main", "feat")
    track = make_track(tmp_path)
    sha, _ = git(work, "rev-parse", "refs/remotes/origin/main")
    sha7 = sha[:7]

    done = run_ship(track, work)
    assert done.returncode == 2, done.stdout
    expected = ("FAIL merges_cleanly (conflicts with origin/main at %s in 1 "
                "file(s): f.txt -- git fetch origin, merge origin/main into "
                "this branch, resolve the conflicts, then run verify again)"
                % sha7)
    assert expected in done.stdout


def test_unborn_head_is_not_checked(tmp_path):
    _work, remote, _other = conflict_fixture(tmp_path)
    unborn = tmp_path / "unborn"
    subprocess.run(["git", "init", "-b", "work", str(unborn)],
                   capture_output=True, text=True)
    git(unborn, "remote", "add", "origin", remote)
    git(unborn, "fetch", "origin")
    track = make_track(tmp_path)

    done = run_ship(track, str(unborn))
    assert done.returncode == 0, done.stdout
    assert "PASS merges_cleanly (not checked: HEAD has no commit yet)" in done.stdout


@needs_merge_tree
def test_shallow_clone_without_merge_base_is_not_checked(tmp_path):
    _work, remote, other = conflict_fixture(tmp_path, conflict=False)
    other = Path(other)
    shallow = tmp_path / "shallow"
    remote_uri = "file:///" + str(remote).replace("\\", "/")
    subprocess.run(["git", "clone", "--depth", "1", remote_uri, str(shallow)],
                   capture_output=True, text=True)
    git(shallow, "checkout", "-b", "feat")
    (shallow / "new.txt").write_text("shallow side\n", encoding="utf-8")
    git(shallow, "add", "new.txt")
    git(shallow, "commit", "-m", "shallow advances")

    (other / "another.txt").write_text("1\n", encoding="utf-8")
    git(other, "add", "another.txt")
    git(other, "commit", "-m", "other advances again")
    git(other, "push", "origin", "main")
    (other / "another2.txt").write_text("2\n", encoding="utf-8")
    git(other, "add", "another2.txt")
    git(other, "commit", "-m", "other advances yet again")
    git(other, "push", "origin", "main")

    git(shallow, "fetch", "--depth", "1", "origin", "main")
    track = make_track(tmp_path)

    done = run_ship(track, str(shallow))
    assert done.returncode == 0, done.stdout
    assert any(line.startswith("PASS merges_cleanly (not checked: git merge-tree exited 128: ")
               for line in done.stdout.splitlines()), done.stdout


@needs_merge_tree
def test_old_git_is_not_checked(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    real_git = preflight.git

    class FakeDone:
        stdout = "git version 2.37.1"
        returncode = 0

    def fake_git(cwd, *args, encoding=None):
        if args == ("--version",):
            return FakeDone()
        return real_git(cwd, *args, encoding=encoding)

    try:
        preflight.git = fake_git
        result = preflight.merges_cleanly(work)
    finally:
        preflight.git = real_git

    assert result == (True, "merges_cleanly (not checked: git 2.37 has no "
                             "merge-tree --write-tree, needs 2.38+)")


@needs_merge_tree
def test_unreadable_version_still_checks(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    real_git = preflight.git

    class FakeDone:
        stdout = "nonsense"
        returncode = 0

    def fake_git(cwd, *args, encoding=None):
        if args == ("--version",):
            return FakeDone()
        return real_git(cwd, *args, encoding=encoding)

    try:
        preflight.git = fake_git
        result = preflight.merges_cleanly(work)
    finally:
        preflight.git = real_git

    assert result[0] is False


def test_git_not_answering_is_not_checked(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args == ("--version",):
            return None
        return real_git(cwd, *args, encoding=encoding)

    try:
        preflight.git = fake_git
        result = preflight.merges_cleanly(work)
    finally:
        preflight.git = real_git

    assert result == (True, "merges_cleanly (not checked: git did not answer)")


@needs_merge_tree
def test_merge_tree_timeout_is_not_checked(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    real_git = preflight.git

    def fake_git(cwd, *args, encoding=None):
        if args and args[0] == "merge-tree":
            return None
        return real_git(cwd, *args, encoding=encoding)

    try:
        preflight.git = fake_git
        result = preflight.merges_cleanly(work)
    finally:
        preflight.git = real_git

    assert result == (True, "merges_cleanly (not checked: git merge-tree did not answer)")


@pytest.mark.parametrize("text,expected", [
    ("git version 2.39.2.windows.1", (2, 39)),
    ("git version 2.38.0\n", (2, 38)),
    ("nonsense", None),
])
def test_parse_git_version(text, expected):
    assert preflight.parse_git_version(text) == expected


@needs_merge_tree
def test_non_ascii_conflicting_filename_is_named(tmp_path):
    work, remote, other = conflict_fixture(tmp_path, names=("中文.txt",))
    track = make_track(tmp_path)

    done = run_ship(track, work)
    assert done.returncode == 2, done.stdout
    assert "中文.txt" in done.stdout
    assert "\\344" not in done.stdout


@needs_merge_tree
def test_control_char_in_conflicting_filename_is_escaped(tmp_path):
    """A git tree-entry name (unlike a ref name) can carry control
    characters, such as an embedded newline, that `git add` on a real
    checkout would never produce but a scripted push can -- built here with
    plumbing (mktree/commit-tree), never a checkout, since Windows itself
    refuses to create a file whose name contains one. Gate 2 quotes a FAIL
    line verbatim into the ledger's `--note`, so an unescaped one could forge
    a fake extra line -- e.g. a spoofed `PASS clean_tree (...)` -- inside
    what preflight and the ledger both treat as a single entry."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    name = "evil\nFAKE PASS clean_tree line\n.txt"

    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)],
                   capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "main", str(work)],
                   capture_output=True, text=True)
    git(work, "remote", "add", "origin", str(remote))

    def blob(content):
        done = subprocess.run(["git", "-C", str(work), "hash-object", "-w", "--stdin"],
                              input=content, capture_output=True)
        return done.stdout.decode().strip()

    def tree(sha):
        entry = ("100644 blob %s\t%s\0" % (sha, name)).encode()
        done = subprocess.run(["git", "-C", str(work), "mktree", "-z"],
                              input=entry, capture_output=True)
        return done.stdout.decode().strip()

    def commit(tree_sha, parent=None):
        args = ["git", "-C", str(work)] + GIT_ID + ["commit-tree", tree_sha, "-m", "c"]
        if parent:
            args += ["-p", parent]
        done = subprocess.run(args, capture_output=True)
        return done.stdout.decode().strip()

    root = commit(tree(blob(b"orig\n")))
    c1 = commit(tree(blob(b"b1\n")), root)
    c2 = commit(tree(blob(b"b2\n")), root)

    subprocess.run(["git", "-C", str(work), "push", "origin", "%s:refs/heads/main" % c2],
                   capture_output=True, text=True)
    git(work, "update-ref", "refs/heads/feat", c1)
    git(work, "symbolic-ref", "HEAD", "refs/heads/feat")
    git(work, "fetch", "origin")

    result = preflight.merges_cleanly(str(work))
    assert result[0] is False, result
    assert "\n" not in result[1], result[1]
    assert "evil" in result[1] and ".txt" in result[1]


@needs_merge_tree
def test_more_than_ten_conflicts_are_elided(tmp_path):
    names = tuple("c%02d.txt" % n for n in range(1, 13))
    work, remote, other = conflict_fixture(tmp_path, names=names)
    track = make_track(tmp_path)

    done = run_ship(track, work)
    assert done.returncode == 2, done.stdout
    assert "in 12 file(s): " in done.stdout
    assert " and 2 more -- " in done.stdout


@needs_merge_tree
def test_answers_offline_from_the_last_fetch(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    missing = tmp_path / "does-not-exist.git"
    git(work, "remote", "set-url", "origin", str(missing))

    _out, code = git(work, "fetch", "origin")
    assert code != 0

    track = make_track(tmp_path)
    done = run_ship(track, work)
    assert done.returncode == 2, done.stdout
    assert "FAIL merges_cleanly (conflicts with origin/main" in done.stdout


FORBIDDEN_GIT_SUBCOMMANDS = {"fetch", "pull", "push", "clone", "ls-remote", "remote"}


def _collect_git_and_run_args(source_text):
    """The AST scan `test_preflight_calls_no_network_git_subcommand` runs,
    factored out so `test_ast_check_catches_a_fetch_regression` can prove it
    against a synthetic snippet rather than only against the real file (which
    -- being clean -- would pass identically whether or not the scan actually
    looks at the right argument)."""
    import ast

    tree = ast.parse(source_text)
    git_subcommands = []
    run_first_args = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if name == "git" and len(node.args) > 1:
                # git(cwd, *args) -- args[0] is always `cwd`; the subcommand
                # is the second positional argument.
                second = node.args[1]
                if isinstance(second, ast.Constant) and isinstance(second.value, str):
                    git_subcommands.append(second.value)
            if (isinstance(func, ast.Attribute) and func.attr == "run"
                    and node.args and isinstance(node.args[0], ast.List)
                    and node.args[0].elts):
                elt0 = node.args[0].elts[0]
                if isinstance(elt0, ast.Constant) and isinstance(elt0.value, str):
                    run_first_args.append(elt0.value)

    return git_subcommands, run_first_args


def test_preflight_calls_no_network_git_subcommand():
    with open(os.path.join(os.path.dirname(ledger.__file__), "preflight.py"),
               encoding="utf-8") as fh:
        git_subcommands, run_first_args = _collect_git_and_run_args(fh.read())

    assert not (set(git_subcommands) & FORBIDDEN_GIT_SUBCOMMANDS), git_subcommands
    assert "gh" not in run_first_args


def test_ast_check_catches_a_fetch_regression():
    """A `git(cwd, "fetch", "origin")` call -- the exact regression S1 (no
    network in preflight) exists to forbid -- must show up in
    `git_subcommands`. Proves the scan above is not vacuous."""
    source = (
        "def leak(cwd):\n"
        "    return git(cwd, \"fetch\", \"origin\")\n")
    git_subcommands, _ = _collect_git_and_run_args(source)
    assert "fetch" in git_subcommands


@needs_merge_tree
def test_trial_merge_leaves_repo_untouched(tmp_path):
    work, remote, other = conflict_fixture(tmp_path)
    track = make_track(tmp_path)

    def snapshot():
        refs, _ = git(work, "for-each-ref")
        head, _ = git(work, "rev-parse", "HEAD")
        symref, _ = git(work, "symbolic-ref", "HEAD")
        status, _ = git(work, "status", "--porcelain")
        index_path = os.path.join(work, ".git", "index")
        with open(index_path, "rb") as fh:
            index_hash = hashlib.sha256(fh.read()).hexdigest()
        return refs, head, symref, index_hash, status

    before = snapshot()
    run_ship(track, work)
    after = snapshot()

    assert before == after


def test_not_a_git_repo_is_not_checked(tmp_path):
    project = tmp_path / "plain"
    project.mkdir()
    track = make_track(tmp_path)

    done = run_ship(track, str(project))
    assert done.returncode == 2, done.stdout  # clean_tree/not_main_branch also fail
    assert "PASS merges_cleanly (not checked: " in done.stdout
    assert " is not a git repository)" in done.stdout


APPROVAL_GATES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "skills", "track", "references", "approval-gates.md")


def test_gate2_fetches_then_reruns_preflight_inside_a_track():
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        text = fh.read()

    assert ("git fetch origin\n"
            "python ${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py ship "
            "--track-dir .claude/track/<feature> --project-dir <project root>") in text
    assert "**Exit 0** → the quoted commands run." in text
    assert "**Exit 2** → none of the quoted commands runs." in text
    assert "record `ship` as `blocked` (`--gate auto`)" in text
    assert "FAIL ledger_attempts" in text


def test_gate2_standalone_ship_says_the_merge_was_not_checked():
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        text = fh.read()

    assert "**Standing alone** (`/cai:ship`, no track)" in text
    assert "you say in one line that the merge with the base branch was not\nchecked." in text


MANUAL_MD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MANUAL.md")


def test_manual_blocks_table_names_merges_cleanly():
    with open(MANUAL_MD, encoding="utf-8") as fh:
        text = fh.read()

    expected = ('| `merges_cleanly` | `ship`: your branch conflicts with the remote\'s default branch — `origin/HEAD`, else `origin/main`, else `origin/master` — as this clone last fetched it. Checked when `ship` starts, and again when you pick "Run them", right after a `git fetch origin`. `/cai:ship` on its own does not check it | `git fetch origin`, merge that branch into yours, resolve the files the line names, and run verify again. When it cannot tell — no such branch, git older than 2.38, a shallow clone with no common history, any other git error — it prints `PASS` with `not checked: <why>` and never blocks |')
    assert expected in text


CODEX_APPROVAL_GATES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai-codex", "skills", "track", "references", "approval-gates.md")


def test_codex_gate2_uses_the_launcher():
    with open(CODEX_APPROVAL_GATES, encoding="utf-8") as fh:
        text = fh.read()

    assert "<cai> preflight ship" in text
    assert "git fetch origin" in text
    assert "${CLAUDE_PLUGIN_ROOT}" not in text
