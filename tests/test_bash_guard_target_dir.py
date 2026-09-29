"""bash_guard.py judges the directory a git invocation acts on, not the
session's cwd (#233).

The commit and discard rules read the branch / dirty state of the payload's
`cwd`, and the push rule honoured `git -C <dir>` but not a `cd <dir> &&`
prefix -- so work in a linked worktree was blocked from a session sitting on
main, and a command reaching main from a session on a feature worktree got
through. Every repo here is built under tmp_path so the verdicts never depend
on the branch this test run's own checkout is on (#232).
"""
import json
import os
import subprocess
import sys

import pytest

GUARD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "scripts", "bash_guard.py")


def _git(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, (args, done.stderr)


@pytest.fixture
def repos(tmp_path):
    """`main-checkout` on main with a pushed origin/main, and a linked
    worktree `feature-wt` on feat; `f.txt` is tracked in both."""
    origin = tmp_path / "origin.git"
    main = tmp_path / "main-checkout"
    wt = tmp_path / "feature-wt"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-b", "main", str(main))
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"),
                       ("commit.gpgsign", "false")):
        _git(main, "config", key, value)
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "f.txt")
    _git(main, "commit", "-m", "init")
    _git(main, "remote", "add", "origin", str(origin))
    _git(main, "push", "-u", "origin", "main")
    _git(main, "worktree", "add", "-b", "feat", str(wt))
    return {"main": str(main), "wt": str(wt), "tmp": tmp_path}


def run(command, cwd, tool="Bash"):
    env = dict(os.environ)
    env.pop("CAI_CODEX_GUARD", None)
    return subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def dirty(path):
    with open(os.path.join(path, "f.txt"), "a") as fh:
        fh.write("uncommitted\n")


# (session, command template, dirty tree, expected exit code) -- the table in
# #233, row for row. {main} and {wt} are the two checkouts' absolute paths.
TABLE = [
    ("main", 'cd "{wt}" && git commit -m x', None, 0),
    ("main", 'git -C "{wt}" commit -m x', None, 0),
    ("wt", 'git -C "{main}" commit -m x', None, 2),
    ("wt", 'cd "{main}" && git commit -m x', None, 2),
    ("main", 'git -C "{wt}" checkout -- f.txt', "wt", 2),
    ("main", 'cd "{wt}" && git restore f.txt', "wt", 2),
    ("main", 'git -C "{wt}" restore f.txt', "main", 0),
    ("wt", 'cd "{main}" && git push', None, 2),
    ("wt", 'git -C "{main}" push', None, 2),
    ("main", 'cd "{wt}" && git push -u origin feat', None, 0),
]


@pytest.mark.parametrize("session,template,dirty_tree,expected", TABLE,
                         ids=[f"row{i + 1}" for i in range(len(TABLE))])
def test_issue_table(repos, session, template, dirty_tree, expected):
    if dirty_tree:
        dirty(repos[dirty_tree])
    command = template.format(main=repos["main"], wt=repos["wt"])
    done = run(command, repos[session])
    assert done.returncode == expected, (command, done.stderr)


def test_deny_names_the_directory_it_read(repos):
    done = run(f'cd "{repos["main"]}" && git commit -m x', repos["wt"])
    assert done.returncode == 2
    assert f"Branch read from {repos['main']}" in done.stderr


@pytest.mark.parametrize("template,expected", [
    # Relative cd, resolved against the session cwd.
    ("cd ../main-checkout && git commit -m x", 2),
    # Several cds compose; the last one decides.
    ('cd "{main}" && cd ../feature-wt && git commit -m x', 0),
    # `;` chains as well as `&&`.
    ('cd "{main}"; git commit -m x', 2),
    # A cd inside a subshell that already closed does not move the git after it.
    ('(cd "{main}" && git status); git commit -m x', 0),
    # ...but one enclosing the git does.
    ('(cd "{main}" && git commit -m x)', 2),
    ('pushd "{main}" && git commit -m x', 2),
    # cd then a relative -C: git resolves -C against the cd'd directory.
    ('cd "{tmp}" && git -C main-checkout commit -m x', 2),
    # Unresolvable statically: today's fallback, the session cwd (feat).
    ('cd "$DIR" && git commit -m x', 0),
    ("cd - && git commit -m x", 0),
])
def test_cd_forms_from_a_feature_session(repos, template, expected):
    command = template.format(main=repos["main"], wt=repos["wt"], tmp=repos["tmp"])
    done = run(command, repos["wt"])
    assert done.returncode == expected, (command, done.stderr)


def test_unresolvable_cd_falls_back_to_the_session_cwd_on_main(repos):
    done = run('cd "$DIR" && git commit -m x', repos["main"])
    assert done.returncode == 2
    assert f"Branch read from {repos['main']}" in done.stderr


def test_powershell_set_location(repos):
    done = run(f'Set-Location "{repos["main"]}"; git commit -m x', repos["wt"],
               tool="PowerShell")
    assert done.returncode == 2, done.stderr
    done = run(f'Set-Location -Path "{repos["wt"]}"; git commit -m x', repos["main"],
               tool="PowerShell")
    assert done.returncode == 0, done.stderr


def test_second_invocation_in_another_tree_is_judged_too(repos):
    # The first commit lands on feat and is fine; the second reaches main.
    command = f'git commit -m a && git -C "{repos["main"]}" commit -m b'
    done = run(command, repos["wt"])
    assert done.returncode == 2, done.stderr
