"""viewer.py's ### liveness component: "is this pid still the process I
started" without ever sending a signal (os.kill) to answer it -- signalling a
pid IS the recycle race this whole component exists to avoid (invariant V2).

Design: the viewer HLD/detail docs behind D5's integration scenario -- a
spawned child reports "alive" while it runs, and "gone" once it has exited
even while something (here, the Popen object itself) still holds a handle to
it, which is the realistic case Windows gives a caller.
"""
import os
import subprocess
import sys
import time

import pytest

import viewer


def test_no_os_kill_is_ever_called(monkeypatch):
    """V2: no code path in check_alive/count_processes may call os.kill."""
    def boom(*a, **k):
        raise AssertionError("os.kill must never be called by liveness code")
    monkeypatch.setattr(os, "kill", boom)

    # A grab-bag of branches: a definitely-alive pid (us), a definitely-gone
    # one, matching and mismatching expected_start, exact True/False.
    own_start = viewer.process_start(os.getpid())
    viewer.check_alive(os.getpid(), own_start, True)
    viewer.check_alive(os.getpid(), own_start, False)
    viewer.check_alive(os.getpid(), "not-a-real-start-value", True)
    viewer.check_alive(os.getpid(), "not-a-real-start-value", False)
    viewer.check_alive(os.getpid(), None, True)
    viewer.check_alive(999999999, "0", True)
    viewer.count_processes("definitely-not-a-real-process-name.exe")
    # The skip_app_server path opens every matching process to read its
    # image path (Windows) or command line (Linux): use a name that exists.
    viewer.count_processes(os.path.basename(sys.executable), skip_app_server=True)


def test_process_start_of_a_nonexistent_pid_is_none():
    assert viewer.process_start(999999999) is None


def test_process_start_of_own_pid_is_a_nonempty_string():
    start = viewer.process_start(os.getpid())
    assert isinstance(start, str) and start


def test_check_alive_while_running_then_gone_after_terminate():
    """D5: a real child, alive while it runs and matches its own start time,
    gone once terminated -- even while the Popen object still holds a
    reference to it (the exited-but-referenced case Windows gives us)."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        deadline = time.time() + 5
        start = None
        while time.time() < deadline:
            start = viewer.process_start(child.pid)
            if start:
                break
            time.sleep(0.05)
        assert start, "child never reported a start time"

        assert viewer.check_alive(child.pid, start, True) == "alive"

        child.terminate()
        child.wait(timeout=5)

        # Still holding `child` (the Popen) open here -- the realistic
        # Windows case where a handle survives the process exiting.
        assert viewer.check_alive(child.pid, start, True) == "gone"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.skipif(os.name == "nt", reason="_check_alive_linux is Linux-only "
                    "(module-level `if os.name == \"nt\":` gates its very "
                    "definition, so it does not exist to call on Windows)")
def test_check_alive_linux_mismatch_depends_on_exact():
    """D10 (docs/design/2026-09-25-agent-viewer-web-portal-detail.md:492):
    unlike Windows (C1, procStart is exactly comparable so any mismatch is
    conclusive "gone"), Claude's procStart format on Linux is UNVERIFIED
    (C5) -- a mismatch against `exact=True` (our own state file) is a real
    pid reuse ("gone"), but against `exact=False` (Claude's procStart) it
    may just be a format difference, so "alive-unverified", not "gone"."""
    assert viewer.check_alive(os.getpid(), "not-the-real-start-value", True) == "gone"
    assert viewer.check_alive(os.getpid(), "not-the-real-start-value", False) == "alive-unverified"


def test_check_alive_gone_when_exit_code_not_still_active():
    """GetExitCodeProcess != STILL_ACTIVE, covered directly against a
    Popen we've .wait()ed on -- a handle can still be open (ours) on an
    already-exited process."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    start = viewer.process_start(child.pid) or "0"
    assert viewer.check_alive(child.pid, start, True) == "gone"


def test_count_processes_counts_a_spawned_child():
    name = os.path.basename(sys.executable)
    before = viewer.count_processes(name)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        deadline = time.time() + 5
        after = before
        while time.time() < deadline:
            after = viewer.count_processes(name)
            if after > before:
                break
            time.sleep(0.05)
        assert after >= before + 1
    finally:
        child.kill()
        child.wait(timeout=5)


def test_count_processes_never_raises_for_an_unknown_name():
    assert viewer.count_processes("") == 0 or viewer.count_processes("") >= 0


def test_is_app_server_recognises_the_daemon_image_and_command_line():
    daemon_image = "C:\\made-up\\.codex\\packages\\app-server-daemon\\releases\\1.0.0\\bin\\codex.exe"
    assert viewer._is_app_server(daemon_image)
    assert viewer._is_app_server("codex app-server --listen unix://made-up")
    assert not viewer._is_app_server("C:\\made-up\\Programs\\OpenAI\\Codex\\bin\\codex.exe")
    assert not viewer._is_app_server("codex resume made-up-thread")
    assert not viewer._is_app_server(None)


def test_count_processes_can_skip_an_app_server_process(tmp_path):
    """A copy of a real executable run from under an app-server-daemon
    directory: its image path (Windows) and command line (Linux) both say
    app-server, so skip_app_server leaves it out while the plain count
    still sees it."""
    import shutil
    if os.name == "nt":
        # ping itself, not cmd.exe running ping: killing a cmd.exe would
        # orphan the ping it started for the rest of its 30 seconds.
        source = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PING.EXE")
        args, exe_name = ["-n", "30", "127.0.0.1"], "asrv-probe.exe"
    else:
        source, args = shutil.which("sleep") or "", ["30"]
        exe_name = "asrv-probe"  # short enough for /proc/<pid>/comm's 15 chars
    if not os.path.isfile(source):
        pytest.skip("no executable to copy")
    probe_dir = tmp_path / "app-server-daemon" / "bin"
    probe_dir.mkdir(parents=True)
    probe = str(probe_dir / exe_name)
    shutil.copyfile(source, probe)
    os.chmod(probe, 0o755)

    child = subprocess.Popen([probe] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 5
        seen = 0
        while time.time() < deadline:
            seen = viewer.count_processes(exe_name)
            if seen >= 1:
                break
            time.sleep(0.05)
        assert seen >= 1
        assert viewer.count_processes(exe_name, skip_app_server=True) == 0
    finally:
        child.kill()
        child.wait(timeout=5)
