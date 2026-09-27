"""#221: validate.py used to test its own PostToolUse hook by creating
plugins/cai/skills/_validate_hook_probe -- a skill with a deliberately broken
SKILL.md -- inside the very tree it was checking, and deleting it afterwards.
Anything else reading that tree meanwhile saw the broken skill: a second
validate.py globbed it up with every other `skills/*/SKILL.md` and printed
FAIL lines that were not really there, and a test copying the repo
(test_validate.py's `_copy_repo`) could copy it. Under pytest-xdist several
workers do both at once.

Rather than try to win that race, this pins the rule behind it: a validate.py
run creates, writes, renames and deletes nothing inside the tree it checks.
A Python audit hook reports every such call, and a `sitecustomize.py` on
PYTHONPATH installs it in validate.py and in every Python process it spawns
that inherits the environment. Non-Python children (git) are not seen.

Runs against a copy, not REPO_ROOT, so a regression dirties only this test's
copy and not every other worker's view of the real tree.
"""
import json
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SITECUSTOMIZE = r'''
import json
import os
import sys

_ROOT = os.environ["CAI_AUDIT_ROOT"]
_LOG = os.environ["CAI_AUDIT_LOG"]
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT
_busy = False


def _inside(path):
    """The path relative to the checked tree, or None if it is outside."""
    if not isinstance(path, (str, bytes, os.PathLike)):
        return None
    full = os.path.normcase(os.path.realpath(os.fsdecode(path)))
    if not full.startswith(_ROOT + os.sep) or "__pycache__" in full:
        return None
    return os.path.relpath(full, _ROOT).replace(os.sep, "/")


def _log(event, hits):
    global _busy
    _busy = True
    try:
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps([event, hits]) + "\n")
    finally:
        _busy = False


def _hook(event, args):
    # An exception escaping an audit hook aborts the call it audits, which
    # would break validate.py instead of observing it -- so a hook bug is
    # logged as a hit and fails the test visibly rather than silently.
    if _busy:
        return
    try:
        if event == "open":
            flags = args[2] if isinstance(args[2], int) else 0
            paths = [args[0]] if flags & _WRITE_FLAGS else []
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "shutil.rmtree"):
            paths = [args[0]]
        elif event == "os.rename":
            paths = [args[0], args[1]]
        else:
            return
        hits = [rel for rel in map(_inside, paths) if rel]
    except Exception as exc:
        _log("hook-error", [repr(exc)])
        return
    if hits:
        _log(event, hits)


sys.addaudithook(_hook)
'''


def _copy_repo(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache"))
    return dest


def test_validate_writes_nothing_inside_the_tree_it_checks(tmp_path):
    repo = _copy_repo(tmp_path)
    hook_dir = tmp_path / "audit"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    log = tmp_path / "writes.jsonl"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(hook_dir)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CAI_AUDIT_ROOT"] = os.path.normcase(os.path.realpath(repo))
    env["CAI_AUDIT_LOG"] = str(log)

    done = subprocess.run([sys.executable, "scripts/validate.py"], cwd=repo,
                          env=env, capture_output=True, encoding="utf-8")

    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    writes = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            event, paths = json.loads(line)
            writes += [f"{event} {p}" for p in paths]
    assert writes == []
