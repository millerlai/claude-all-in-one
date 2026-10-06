"""#234: validate.py built its fixtures with `tempfile.mkdtemp` and removed only
eight of them at the end, as a fixed tuple every new fixture had to be added
to by hand -- and most never were. The removal was also plain top-level code,
so a run that stopped early skipped even those eight. The PostToolUse hook
runs validate.py on every edit under plugins/cai/, and in six days that left
206k directories (~2.9 GB) in one developer's %TEMP%.

Each test points TMP, TEMP and TMPDIR at an empty directory of its own, so
every `mkdtemp` validate.py -- or any nested validate.py it spawns -- makes
lands there, and anything still there afterwards was leaked.
"""
import os
import stat
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")

# Stops validate.py partway through: the `tempfile.mkdtemp` audit event fires
# after the directory exists, so raising there leaves that directory, and every
# fixture made before it, for the cleanup to find. argv[2] names the fixture
# prefix to stop at.
STOP_MID_RUN = r'''
import runpy
import sys

prefix = sys.argv[2]

def stop(event, args):
    if event == "tempfile.mkdtemp" and prefix in args[0]:
        raise RuntimeError("stopped mid-run by the test")

sys.addaudithook(stop)
# validate.py reads section names from sys.argv (#305); it gets none, so this
# is a full run.
sys.argv = sys.argv[1:2]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def _env(tmp_dir):
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    for name in ("TMP", "TEMP", "TMPDIR"):
        env[name] = str(tmp_dir)
    return env


def test_a_full_run_leaves_nothing_in_the_temp_dir(tmp_path):
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()

    done = subprocess.run([sys.executable, VALIDATE], cwd=REPO_ROOT, env=_env(tmp_dir),
                          capture_output=True, encoding="utf-8")

    assert sorted(os.listdir(tmp_dir)) == [], done.stderr[-2000:]


def test_a_run_that_stops_early_still_leaves_nothing(tmp_path):
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()

    done = subprocess.run([sys.executable, "-c", STOP_MID_RUN, VALIDATE, "cai-ship-track-"],
                          cwd=REPO_ROOT, env=_env(tmp_dir), capture_output=True,
                          encoding="utf-8")

    # Without this the test would pass vacuously the day that prefix is renamed.
    assert "stopped mid-run by the test" in done.stderr, done.stderr[-2000:]
    assert done.returncode != 0
    assert sorted(os.listdir(tmp_dir)) == []


def test_a_run_removes_the_root_a_killed_run_left_behind(tmp_path):
    """A run killed outright -- a hook timeout, a closed terminal -- never
    reaches atexit, so its root stays. The next run removes a root untouched
    for a day, and leaves a fresh one (a run still going) and anything that is
    not a validate.py root alone."""
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    two_days_ago = time.time() - 2 * 24 * 60 * 60

    killed = tmp_dir / "cai-validate-killed"
    obj = killed / "repo" / ".git" / "objects" / "ab"
    obj.mkdir(parents=True)
    # Read-only like a git loose object, which Windows refuses to delete as is.
    (obj / "cdef").write_text("blob", encoding="utf-8")
    os.chmod(obj / "cdef", stat.S_IREAD)
    os.utime(killed, (two_days_ago, two_days_ago))

    (tmp_dir / "cai-validate-live").mkdir()
    (tmp_dir / "cai-check").mkdir()
    os.utime(tmp_dir / "cai-check", (two_days_ago, two_days_ago))

    done = subprocess.run([sys.executable, "-c", STOP_MID_RUN, VALIDATE, "cai-gen-commands-"],
                          cwd=REPO_ROOT, env=_env(tmp_dir), capture_output=True,
                          encoding="utf-8")

    assert "stopped mid-run by the test" in done.stderr, done.stderr[-2000:]
    assert sorted(os.listdir(tmp_dir)) == ["cai-check", "cai-validate-live"]
