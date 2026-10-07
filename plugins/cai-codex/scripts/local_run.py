#!/usr/bin/env python3
"""The local-run executor: start the program the project declares, wait until
it answers, run each local-run AC's check against it, keep the evidence, and be
sure that every process it spawned is gone afterwards (I5).

  python local_run.py --track-dir DIR --stage verify|build [--unit N]
                      [--ac AC3,AC5] [--project-dir DIR]

Exit 0 every check passed; 3 a check failed, timed out or was not run; 4
nothing runnable (or the fixed port is taken); 5 bad arguments or intake; 6 a
process was left behind. What runs comes from verify_plan.build_plan -- this
file never reads the intake itself. Standard library only -- Windows job
objects go through ctypes.

POSIX: each tree is its own session (so its pid is also its process-group id);
stopping sends SIGTERM to the group, waits, then SIGKILLs it. A SIGKILL of the
runner itself cannot be intercepted, so descendants outlive it there (C4).

Windows: the runner puts itself in a job, J0, that kills everything in it when
its last handle closes, so however the runner dies the kernel clears every
descendant. Each tree also gets its own job, assigned right after Popen
returns, so one tree can be ended without touching another.
"""
import argparse
import ctypes
import datetime
import hashlib
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

import resolve_test_command
import tool_path
import verify_plan

EXIT_PASS, EXIT_FAILED, EXIT_NOTHING_RUN, EXIT_INVALID, EXIT_TREE_LEFT = 0, 3, 4, 5, 6

TERM_WAIT = 5  # seconds a group gets after SIGTERM before SIGKILL
KILL_WAIT = 5  # seconds to confirm (and reap) after SIGKILL
_POLL = 0.05

# Budgets (seconds unless noted), module-level so tests can shrink them.
READY_WAIT = 120        # for the ready URL to answer
CHECK_WAIT = 120        # per check
TOTAL_BUDGET = 540      # whole run, before the Bash cap is applied (DD9)
RESERVE = 15            # kept back at every step start for stopping trees and writing files
BASH_MARGIN = 60        # the run ends this long before the Bash tool would cut it off
DEFAULT_BASH_CAP_MS = 600000
READY_POLL = 0.5
REQUEST_TIMEOUT = 5     # per readiness request
PORT_PROBE_TIMEOUT = 1  # "does something already answer on the fixed port"
EVIDENCE_LIMIT = 1048576  # bytes; over it, keep LIMIT//2 at each end
CHUNK = 65536
PORT = "{port}"

# State, deliberately module-level: signal handlers and survivors() have no
# other way to find what the runner started.
_J0 = None          # Windows: the runner's own kill-on-close job handle; kept
                    # open for the life of the process -- closing it kills us
_LIVE = []          # Trees started and not yet stopped
_STARTED_PGIDS = []  # POSIX: every group ever started, for survivors()


class Tree:
    """popen: the started process. handle: POSIX the pgid, Windows the tree job."""

    def __init__(self, popen, handle):
        self.popen = popen
        self.handle = handle


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if sys.platform == "win32":
    from ctypes import wintypes

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JobObjectBasicProcessIdList = 3
    _JobObjectExtendedLimitInformation = 9
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _SYNCHRONIZE = 0x00100000
    _STILL_ACTIVE = 259
    _MAX_IDS = 4096

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimits),
                    ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _PidList(ctypes.Structure):
        _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD),
                    ("NumberOfProcessIdsInList", wintypes.DWORD),
                    ("ProcessIdList", ctypes.c_size_t * _MAX_IDS)]

    def _k32():
        # Typed signatures: the default int conversion truncates 64-bit handles.
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, ctypes.c_uint]
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.TerminateProcess.argtypes = [wintypes.HANDLE, ctypes.c_uint]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.GetCurrentProcess.restype = wintypes.HANDLE
        return k

    def _new_job(kill_on_close):
        k = _k32()
        job = k.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        if kill_on_close:
            info = _ExtendedLimits()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k.SetInformationJobObject(
                    job, _JobObjectExtendedLimitInformation, ctypes.byref(info),
                    ctypes.sizeof(info)):
                err = ctypes.get_last_error()
                k.CloseHandle(job)
                raise ctypes.WinError(err)
        return job

    def _job_pids(job):
        info = _PidList()
        if not _k32().QueryInformationJobObject(
                job, _JobObjectBasicProcessIdList, ctypes.byref(info),
                ctypes.sizeof(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return list(info.ProcessIdList[:info.NumberOfProcessIdsInList])

    def _terminate_pid(pid):
        k = _k32()
        h = k.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if h:
            k.TerminateProcess(h, 1)
            k.CloseHandle(h)


def install_job():
    """Windows: put this process in J0. Idempotent. Raises OSError if the
    kernel refuses (e.g. an enclosing job that forbids nesting) -- the caller
    must treat that as "runner cannot guarantee cleanup", not carry on."""
    global _J0
    if sys.platform != "win32" or _J0 is not None:
        return
    k = _k32()
    job = _new_job(kill_on_close=True)
    if not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        err = ctypes.get_last_error()
        k.CloseHandle(job)
        raise ctypes.WinError(err)
    _J0 = job  # never closed on purpose: its closing is the safety net


def _on_signal(signum, _frame):
    stop_all()
    sys.exit(128 + signum)


def install_signal_handlers():
    """POSIX: on SIGTERM/SIGINT/SIGHUP stop every live tree, then exit."""
    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        signal.signal(getattr(signal, name), _on_signal)


def install_safety_net():
    """Whatever the platform offers for "however the runner ends, trees go"."""
    if sys.platform == "win32":
        install_job()
    else:
        install_signal_handlers()


def start_tree(argv, cwd, out_path):
    """Start argv as the root of a new tree; stdout and stderr merged into out_path."""
    with open(out_path, "wb") as out:
        kwargs = dict(cwd=cwd, stdin=subprocess.DEVNULL, stdout=out,
                      stderr=subprocess.STDOUT)
        if sys.platform == "win32":
            popen = subprocess.Popen(argv, **kwargs)
            # Children it spawns before this line stay only in J0; stop_tree's
            # J0 sweep is what catches those.
            try:
                handle = _new_job(kill_on_close=False)
                k = _k32()
                proc = k.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False,
                                     popen.pid)
                if not proc:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if not k.AssignProcessToJobObject(handle, proc):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    k.CloseHandle(proc)
            except OSError:
                popen.kill()
                popen.wait()
                raise
        else:
            popen = subprocess.Popen(argv, start_new_session=True, **kwargs)
            handle = popen.pid  # new session: pid == pgid
            _STARTED_PGIDS.append(handle)
    tree = Tree(popen, handle)
    _LIVE.append(tree)
    return tree


def _group_populated(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_group_empty(tree, seconds):
    import time
    end = time.monotonic() + seconds
    while True:
        # Reaping the leader matters: an unreaped zombie leader keeps the
        # group "populated" and would read as a failed stop.
        tree.popen.poll()
        if not _group_populated(tree.handle):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(_POLL)


def stop_tree(tree, sweep=True):
    """End the whole tree. Returns the pids still alive afterwards: on POSIX
    the group id if the group is not empty, on Windows every process left in J0
    besides this one. A grandchild that is a zombie nobody has reaped still
    counts as populated on POSIX; the caller reports it, a person judges.

    sweep=False (Windows only) ends just this tree's own job and leaves the J0
    sweep to the final stop, because J0 also holds the other trees -- stopping
    one e2e check must not kill the app under test. Returns [] then."""
    if tree in _LIVE:
        _LIVE.remove(tree)
    if sys.platform == "win32":
        k = _k32()
        k.TerminateJobObject(tree.handle, 1)
        k.CloseHandle(tree.handle)
        tree.popen.wait()
        if not sweep:
            return []
        for pid in survivors():
            _terminate_pid(pid)
        import time
        end = time.monotonic() + KILL_WAIT
        left = survivors()
        while left and time.monotonic() < end:
            time.sleep(_POLL)
            left = survivors()
        return left
    pgid = tree.handle
    for sig, seconds in ((signal.SIGTERM, TERM_WAIT), (signal.SIGKILL, KILL_WAIT)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        if _wait_group_empty(tree, seconds):
            return []
    return [pgid]


def stop_all():
    """Stop every tree not yet stopped; the pids still alive afterwards."""
    left = []
    for tree in list(_LIVE):
        left.extend(stop_tree(tree))
    return left


def survivors():
    """Windows: every process in J0 except this one. POSIX: every group this
    process started that still has a member."""
    if sys.platform == "win32":
        if _J0 is None:
            return []
        me = os.getpid()
        return [p for p in _job_pids(_J0) if p != me]
    return [g for g in _STARTED_PGIDS if _group_populated(g)]


# ---------------------------------------------------------------------------
# The runner: plan -> start -> ready -> checks -> stop -> record


class _Interrupted(Exception):
    """Raised by the signal handler so run() can still stop trees and write run.json."""


# Read by the handler; module-level for the same reason as _LIVE.
_SIG = {"stopping": False, "defer": 0, "pending": None}


def _now():
    return time.monotonic()


def _utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def total_budget(environ=None):
    """Seconds the whole run may take (DD9): TOTAL_BUDGET, but BASH_MARGIN short
    of the Bash tool's cap (the larger of the two variables; 600000 ms when
    neither is readable) so the tool never cuts the runner off mid-write."""
    environ = os.environ if environ is None else environ
    caps = []
    for name in ("BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS"):
        try:
            value = int(environ[name])
        except (KeyError, ValueError):
            continue
        if value > 0:
            caps.append(value)
    cap_ms = max(caps) if caps else DEFAULT_BASH_CAP_MS
    seconds = max(0, min(TOTAL_BUDGET, cap_ms / 1000 - BASH_MARGIN))
    return int(seconds) if seconds == int(seconds) else seconds


class _Capture:
    """First and last EVIDENCE_LIMIT//2 bytes of a stream plus a count of the
    rest; also looks for `needle` on the whole stream, across chunk edges, so
    cutting the evidence cannot change a verdict."""

    def __init__(self, needle=None):
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0
        self.needle = needle
        self.found = not needle  # no needle (or an empty one) is trivially found
        self._window = b""

    def feed(self, chunk):
        keep = EVIDENCE_LIMIT // 2
        self.total += len(chunk)
        if not self.found:
            data = self._window + chunk
            self.found = self.needle in data
            n = len(self.needle) - 1
            self._window = data[-n:] if n else b""
        room = keep - len(self.head)
        if room > 0:
            self.head += chunk[:room]
            chunk = chunk[room:]
        self.tail += chunk
        if len(self.tail) > 2 * keep:
            del self.tail[:len(self.tail) - keep]

    def render(self):
        """(bytes to store, truncated)."""
        keep = EVIDENCE_LIMIT // 2
        if self.total <= EVIDENCE_LIMIT:
            return bytes(self.head) + bytes(self.tail), False
        tail = bytes(self.tail[-keep:])
        cut = self.total - len(self.head) - len(tail)
        marker = ("\n[... %d bytes cut ...]\n" % cut).encode("ascii")
        return bytes(self.head) + marker + tail, True


def _feed_file(path, capture):
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                return
            capture.feed(chunk)


def _cap_file(path):
    """Cut a file down in place to the evidence limit."""
    capture = _Capture()
    _feed_file(path, capture)
    data, truncated = capture.render()
    if truncated:
        with open(path, "wb") as fh:
            fh.write(data)


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # the 3xx then raises HTTPError, which callers read as a response


# No environment proxy may stand between the runner and the app, and a redirect
# must not leave the declared origin (same opener shape as viewer.py).
_LOOPBACK = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def _http_url(base, path):
    # http.client sends the request line as ASCII; an intake written in another
    # language can plan a path like "/健康", so encode what is not ASCII and leave
    # every URL delimiter and existing %XX escape as the intake wrote it.
    return base + quote(path, safe="/?&=%#:@!$'()*+,;~[]")


def _answers_ready(url, timeout):
    """True when `url` answers with a status below 500 (a 3xx counts)."""
    try:
        with _LOOPBACK.open(urllib.request.Request(url), timeout=timeout):
            return True
    except urllib.error.HTTPError as err:
        err.close()
        return err.code < 500
    except (OSError, http.client.HTTPException):
        return False


def _port_answers(host, port):
    try:
        socket.create_connection((host, port), timeout=PORT_PROBE_TIMEOUT).close()
        return True
    except OSError:
        return False


def _wait_ready(tree, url, limit):
    """"ready", "exited" (the program ended first) or "timeout"."""
    end = _now() + limit
    while True:
        if tree.popen.poll() is not None:
            return "exited"
        remaining = end - _now()
        if remaining <= 0:
            return "timeout"
        if _answers_ready(url, min(REQUEST_TIMEOUT, remaining)):
            return "ready"
        time.sleep(max(0, min(READY_POLL, end - _now())))


def _do_http(url, parsed, evidence_path, limit):
    """One HTTP check; writes the evidence file; returns the check fields."""
    needle = None if parsed["text"] is None else parsed["text"].encode("utf-8")
    capture = _Capture(needle)
    lines = ["%s %s" % (parsed["method"], url)]
    outcome = reason = status = None
    deadline = _now() + limit
    try:
        try:
            resp = _LOOPBACK.open(urllib.request.Request(url, method=parsed["method"]),
                                  timeout=limit)
        except urllib.error.HTTPError as err:
            resp = err  # 3xx, 4xx and 5xx still carry a response worth recording
        with resp:
            status = resp.status
            lines.append("%d %s" % (status, resp.reason))
            lines += ["%s: %s" % kv for kv in resp.headers.items()]
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                capture.feed(chunk)
                if _now() > deadline:
                    raise TimeoutError("check ran past %s s" % limit)
    except (TimeoutError, socket.timeout) as exc:
        outcome, reason = "TIMEOUT", "timeout: %s" % exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            outcome, reason = "TIMEOUT", "timeout: %s" % exc.reason
        else:
            outcome, reason = "FAIL", "cannot connect: %s" % exc.reason
    except (OSError, http.client.HTTPException) as exc:
        outcome, reason = "FAIL", "request failed: %s" % exc
    if outcome is None:
        if status != parsed["status"]:
            outcome, reason = "FAIL", "status %d, expected %d" % (status, parsed["status"])
        elif not capture.found:
            outcome, reason = "FAIL", 'body does not contain "%s"' % parsed["text"]
        else:
            outcome = "PASS"
    elif status is None:
        lines.append("error: %s" % reason)
    body, truncated = capture.render()
    with open(evidence_path, "wb") as fh:
        fh.write(("\n".join(lines) + "\n\n").encode("utf-8", "replace") + body)
    return {"outcome": outcome, "reason": reason, "bytes_seen": capture.total,
            "truncated": truncated, "wrote": True}


def _stop_e2e_tree(tree):
    """Stop one e2e tree without letting an interrupt arrive half-way: the
    interrupt is replayed after, so the tree is never left half-stopped."""
    _SIG["defer"] += 1
    try:
        return stop_tree(tree, sweep=False)
    finally:
        _SIG["defer"] -= 1
        if not _SIG["defer"] and _SIG["pending"] is not None and not _SIG["stopping"]:
            _SIG["pending"] = None
            raise _Interrupted()


def _run_e2e(argv, cwd, out_path, limit):
    """(exit code or None on timeout, seconds). The tree is ended either way."""
    began = _now()
    tree = start_tree(argv, cwd, out_path)
    code = None
    try:
        while True:
            code = tree.popen.poll()
            if code is not None or _now() - began >= limit:
                break
            time.sleep(_POLL)
    finally:
        _stop_e2e_tree(tree)
    return code, _now() - began


def _do_e2e(argv, cwd, evidence_path, limit):
    """One e2e check; writes the evidence file; returns the check fields."""
    tmp = evidence_path + ".out"
    capture = _Capture()
    try:
        try:
            code, seconds = _run_e2e(tool_path.resolve_argv(argv, cwd), cwd, tmp, limit)
        except OSError as exc:
            return {"outcome": "FAIL", "reason": "e2e-not-started: %s" % exc,
                    "bytes_seen": None, "truncated": False, "wrote": False}
        _feed_file(tmp, capture)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if code is None:
        outcome, reason, shown = "TIMEOUT", "timeout after %s s" % limit, "timeout"
    elif code == 0:
        outcome, reason, shown = "PASS", None, "0"
    else:
        outcome, reason, shown = "FAIL", "exit code %d" % code, str(code)
    head = "argv: %s\nexit code: %s\nseconds: %.1f\n\n" % (
        json.dumps(argv, ensure_ascii=False), shown, seconds)
    body, truncated = capture.render()
    with open(evidence_path, "wb") as fh:
        fh.write(head.encode("utf-8") + body)
    return {"outcome": outcome, "reason": reason, "bytes_seen": capture.total,
            "truncated": truncated, "wrote": True}


def _new_evidence_dir(base):
    os.makedirs(base, exist_ok=True)
    stamp = _utc_stamp()
    n = 1
    while True:
        path = os.path.join(base, stamp if n == 1 else "%s-%d" % (stamp, n))
        try:
            os.mkdir(path)  # mkdir, not exists-then-make: two runners may race here
        except FileExistsError:
            n += 1
            continue
        return path


def _mark_rest(checks, outcome, reason):
    for c in checks:
        if c["outcome"] is None:
            c["outcome"], c["reason"] = outcome, reason


def _expand(decl):
    """(start argv, ready url, e2e, port) with {port} replaced; port is None
    when the declaration has no placeholder."""
    if not any(PORT in w for w in decl["start"]):
        return list(decl["start"]), decl["ready"], decl["e2e"], None
    port = free_port()

    def sub(text):
        return text.replace(PORT, str(port))
    return ([sub(w) for w in decl["start"]], sub(decl["ready"]),
            {name: [sub(w) for w in words] for name, words in decl["e2e"].items()}, port)


def _execute(plan, rows, root, evidence_dir, st, budget):
    """Everything between "plan says run" and "trees need stopping". Fills st."""
    checks, start = st["checks"], st["start"]
    deadline = _now() + budget

    def left():
        return deadline - _now() - RESERVE

    argv, ready, e2e, port = _expand(plan["start"]["declaration"])
    parts = urlsplit(ready)
    start.update(argv=argv, ready=ready, port=port)
    if port is None:
        start["port"] = port = parts.port or 80
        if _port_answers(parts.hostname, port):
            start["outcome"] = "port-in-use"
            _mark_rest(checks, "NOT-RUN", "port-in-use")
            return
    if left() <= 0:
        _mark_rest(checks, "NOT-RUN", "time-budget-exhausted")
        return
    log = os.path.join(evidence_dir, "start.log")
    began = _now()
    try:
        tree = start_tree(tool_path.resolve_argv(argv, root), root, log)
    except OSError as exc:
        _mark_rest(checks, "FAIL", "start-failed: %s" % exc)
        return
    start["outcome"] = "interrupted"  # stands unless the wait below finishes
    result = _wait_ready(tree, ready, min(READY_WAIT, left()))
    start["seconds"] = round(_now() - began, 1)
    start["outcome"] = result
    if result == "exited":
        _mark_rest(checks, "FAIL", "start-exited (exit code %s)" % tree.popen.returncode)
        return
    if result == "timeout":
        _mark_rest(checks, "TIMEOUT", "ready-timeout")
        return
    base = "%s://%s" % (parts.scheme, parts.netloc)
    for c in checks:
        if left() <= 0:
            _mark_rest(checks, "NOT-RUN", "time-budget-exhausted")
            return
        limit = min(CHECK_WAIT, left())
        parsed = rows[c["ac"]]["parsed"]
        path = os.path.join(evidence_dir, c["ac"] + ".txt")
        if parsed["kind"] == "http":
            res = _do_http(_http_url(base, parsed["path"]), parsed, path, limit)
        else:
            res = _do_e2e(e2e[parsed["name"]], root, path, limit)
        if res.pop("wrote"):
            c["evidence"], c["sha256"] = c["ac"] + ".txt", _sha256(path)
        c.update(res)


def _install_interrupt():
    """Route the interrupt signals into _Interrupted; returns the undo function."""
    names = ("SIGINT", "SIGBREAK") if sys.platform == "win32" else (
        "SIGTERM", "SIGINT", "SIGHUP")

    def handler(signum, _frame):
        if _SIG["stopping"]:
            return
        if _SIG["defer"]:
            _SIG["pending"] = signum
            return
        raise _Interrupted(signum)
    old = []
    try:
        for name in names:
            sig = getattr(signal, name)
            old.append((sig, signal.signal(sig, handler)))
    except ValueError:  # not the main thread: nothing to intercept
        pass

    def restore():
        for sig, previous in old:
            if previous is not None:
                signal.signal(sig, previous)
    return restore


def _utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(path, track_dir):
    return os.path.relpath(path, track_dir).replace(os.sep, "/")


def run(track_dir, project_root, stage, unit, only):
    """Run the plan's local-run ACs; (exit code, run record). Prints the
    documented stdout lines. The record is {} when nothing was run."""
    plan = verify_plan.build_plan(track_dir, project_root)
    if plan["intake_status"] == "invalid":
        for problem in plan["problems"]:
            print(problem, file=sys.stderr)
        return EXIT_INVALID, {}
    if stage == "build" and unit is None:
        print("--stage build needs --unit N", file=sys.stderr)
        return EXIT_INVALID, {}
    runtime = plan["runtime"]
    if runtime["status"] != "will-run":
        print("nothing to run: runtime skipped (%s)" % runtime["reason"])
        if plan["start"]["problem"]:
            print(plan["start"]["problem"])
        return EXIT_NOTHING_RUN, {}
    if only is not None:
        bad = [ac for ac in only if ac not in runtime["acs"]]
        if bad:
            print("--ac names %s, which the plan does not route to local-run"
                  % ", ".join(bad), file=sys.stderr)
            return EXIT_INVALID, {}
    selected = [ac for ac in runtime["acs"] if only is None or ac in only]
    rows = {r["ac"]: r for r in plan["rows"]}

    unit = unit if stage == "build" else None
    parts = ["evidence", stage] + (["unit-%d" % unit] if unit is not None else [])
    evidence_dir = _new_evidence_dir(os.path.join(track_dir, *parts))
    budget = total_budget()
    st = {"checks": [{"ac": ac, "check": rows[ac]["check"], "outcome": None, "reason": None,
                      "evidence": None, "sha256": None, "bytes_seen": None,
                      "truncated": False} for ac in selected],
          "start": {"argv": None, "port": None, "ready": None, "outcome": "not-started",
                    "seconds": None, "log": None, "log_sha256": None}}
    started = _utc_iso()
    _SIG.update(stopping=False, defer=0, pending=None)
    restore = _install_interrupt()
    interrupted = False
    try:
        try:
            _execute(plan, rows, project_root, evidence_dir, st, budget)
        except _Interrupted:
            interrupted = True
        finally:
            _SIG["stopping"] = True
            left = stop_all()
    finally:
        restore()
    left = sorted(set(left) | set(survivors()))
    _mark_rest(st["checks"], "NOT-RUN", "interrupted")

    log = os.path.join(evidence_dir, "start.log")
    if os.path.exists(log):
        _cap_file(log)
        st["start"].update(log="start.log", log_sha256=_sha256(log))
    record = {"format": 1, "stage": stage, "unit": unit, "platform": sys.platform,
              "started": started, "ended": _utc_iso(),
              "budget": {"total": budget, "ready": READY_WAIT, "check": CHECK_WAIT},
              "start": st["start"], "checks": st["checks"], "survivors": left}
    record_path = os.path.join(evidence_dir, "run.json")
    with open(record_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    for c in st["checks"]:
        if c["evidence"]:
            print("%s %s %s sha256=%s" % (c["ac"], c["outcome"], _rel(
                os.path.join(evidence_dir, c["evidence"]), track_dir), c["sha256"]))
            if c["reason"]:
                print("%s: %s" % (c["ac"], c["reason"]), file=sys.stderr)
        else:
            print("%s %s %s" % (c["ac"], c["outcome"], c["reason"]))
    if left:
        print("processes left running after stop: %s" % " ".join(str(p) for p in left))
    print("run record: %s" % os.path.abspath(record_path))
    sys.stdout.flush()

    if left:
        code = EXIT_TREE_LEFT
    elif st["start"]["outcome"] == "port-in-use":
        code = EXIT_NOTHING_RUN
    elif interrupted or any(c["outcome"] != "PASS" for c in st["checks"]):
        code = EXIT_FAILED
    else:
        code = EXIT_PASS
    return code, record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track-dir", required=True, help="the track directory (holds intake.md)")
    ap.add_argument("--stage", required=True, choices=("verify", "build"))
    ap.add_argument("--unit", type=int, help="build unit number (required for --stage build)")
    ap.add_argument("--ac", help="comma-separated AC ids to run (default: every local-run AC)")
    ap.add_argument("--project-dir", default=".", help="project directory (default: .)")
    args = ap.parse_args(argv)
    try:
        install_safety_net()
    except OSError as exc:
        # Without the net a hard kill of the runner would leave the app running.
        print("cannot install the process safety net: %s" % exc, file=sys.stderr)
        return EXIT_INVALID
    only = [a.strip() for a in args.ac.split(",") if a.strip()] if args.ac else None
    root = resolve_test_command.find_root(os.path.abspath(args.project_dir))
    code, _ = run(os.path.abspath(args.track_dir), root, args.stage, args.unit, only)
    return code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
