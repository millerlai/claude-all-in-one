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
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE = os.path.join(REPO_ROOT, "scripts", "validate.py")

# Stops validate.py partway through: the `tempfile.mkdtemp` audit event fires
# after the directory exists, so raising there leaves that directory, and every
# fixture made before it, for the cleanup to find.
STOP_MID_RUN = r'''
import runpy
import sys

def stop(event, args):
    if event == "tempfile.mkdtemp" and "cai-ship-track-" in args[0]:
        raise RuntimeError("stopped mid-run by the test")

sys.addaudithook(stop)
runpy.run_path(sys.argv[1], run_name="__main__")
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

    done = subprocess.run([sys.executable, "-c", STOP_MID_RUN, VALIDATE], cwd=REPO_ROOT,
                          env=_env(tmp_dir), capture_output=True, encoding="utf-8")

    # Without this the test would pass vacuously the day that prefix is renamed.
    assert "stopped mid-run by the test" in done.stderr, done.stderr[-2000:]
    assert done.returncode != 0
    assert sorted(os.listdir(tmp_dir)) == []
