#!/usr/bin/env python3
"""viewer.py -- the one-process, one-port local server behind the agent
viewer. Zero deps.

A track's model has no way to show a person what several running agents are
doing right now; this is the process that answers that, on demand, without
becoming a service that has to be managed. One instance per machine (per
POSIX user) is enough, so most of this file is about finding that one
instance rather than starting a second: a state file in the temp directory
names it, a liveness check (never a signal -- see the note on invariant V2
below) confirms it is still the same process rather than a reused pid, and
the launcher commands (start/stop/serve) agree on both before doing anything.

Usage:  viewer.py [start [--port N]]   -- start, or report the one running
        viewer.py stop                 -- stop it, if one is running
        viewer.py serve --port N       -- the server itself (spawned by
                                           `start`; not meant to be run by
                                           hand in a foreground shell)

This is unit 1 of the viewer build: liveness, the state file, the launcher,
and an http skeleton whose /api/rows always answers an empty snapshot. The
poller that fills it in lives in a later unit and is left as a marked TODO
in cmd_serve() below.
"""
import ctypes
import datetime
import glob
import hmac
import http.server
import json
import os
import platform
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import usage_collector  # noqa: E402
import track_state  # noqa: E402
import preflight  # noqa: E402
import ledger  # noqa: E402

DEFAULT_PORT = 7788
PORT_TRIES = 10
READY_TIMEOUT_S = 5.0
READY_POLL_S = 0.1
IDENTITY_TIMEOUT_S = 1.0
SHUTDOWN_TIMEOUT_S = 2.0
STOP_WAIT_S = 3.0
STOP_KILL_WAIT_S = 1.0
STATE_RETRY_DELAY_S = 0.1
TOKEN_HEADER = "X-Cai-Viewer-Token"

USAGE = ("usage: viewer.py [start [--port N]] | stop | serve --port N")


# =========================================================== liveness ====
# Answers "is this pid still the process I started" without ever sending a
# signal -- os.kill(pid, 0) would "work" but a pid can be reused the instant
# the original process exits, so a signal-based check can true-positive
# against a stranger that happens to reuse the number. This is invariant V2
# and has its own test (test_no_os_kill_is_ever_called in
# tests/test_viewer_liveness.py).

if os.name == "nt":
    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                    ("dwHighDateTime", ctypes.c_uint32)]

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _ERROR_ACCESS_DENIED = 5
    _STILL_ACTIVE = 259

    def _win_kernel32():
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        k.GetProcessTimes.argtypes = [ctypes.c_void_p, ctypes.POINTER(_FILETIME),
                                      ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
                                      ctypes.POINTER(_FILETIME)]
        return k

    def _process_start_windows(pid):
        try:
            kernel32 = _win_kernel32()
            handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle is None:
                return None
            try:
                creation, exit_ft, kernel_ft, user_ft = (
                    _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME())
                ok = kernel32.GetProcessTimes(
                    handle, ctypes.byref(creation), ctypes.byref(exit_ft),
                    ctypes.byref(kernel_ft), ctypes.byref(user_ft))
                if not ok:
                    return None
                return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None

    def _check_alive_windows(pid, expected_start, exact):
        kernel32 = _win_kernel32()
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle is None:
            if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                return "alive-unverified"
            return "gone"
        try:
            exit_code = ctypes.c_uint32(0)
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                if exit_code.value != _STILL_ACTIVE:
                    return "gone"
            else:
                return "gone"

            creation, exit_ft, kernel_ft, user_ft = (
                _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME())
            if not kernel32.GetProcessTimes(
                    handle, ctypes.byref(creation), ctypes.byref(exit_ft),
                    ctypes.byref(kernel_ft), ctypes.byref(user_ft)):
                return "gone"
            start = str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)

            if expected_start is None:
                return "alive-unverified"
            return "alive" if start == expected_start else "gone"
        finally:
            kernel32.CloseHandle(handle)

else:
    def _read_proc_stat_fields(pid):
        """Fields after the last ')' in /proc/<pid>/stat, index 0 == whole
        line's field 3 (state) -- so whole-line field N is fields[N - 3]."""
        with open("/proc/%d/stat" % pid, encoding="utf-8") as fh:
            text = fh.read()
        idx = text.rfind(")")
        if idx == -1:
            return None
        return text[idx + 1:].split()

    def _process_start_linux(pid):
        try:
            fields = _read_proc_stat_fields(pid)
        except OSError:
            return None
        if not fields or len(fields) <= 19:
            return None
        return fields[19]

    def _check_alive_linux(pid, expected_start, exact):
        try:
            fields = _read_proc_stat_fields(pid)
        except OSError:
            return "gone"
        if not fields:
            return "gone"
        if fields[0] == "Z":
            return "gone"
        if len(fields) <= 19:
            return "gone"
        start = fields[19]
        # D10 (docs/design/...-detail.md:492): unlike Windows (C1, exactly
        # comparable), Claude's procStart format on Linux is UNVERIFIED
        # (C5) -- so a mismatch here (including expected_start is None,
        # which can never equal a real stat field) is only conclusive when
        # exact is True (our own state file); otherwise it may just be a
        # format difference, not real pid reuse, so "alive-unverified".
        if start == expected_start:
            return "alive"
        return "gone" if exact else "alive-unverified"

def process_start(pid):
    if os.name == "nt":
        return _process_start_windows(pid)
    return _process_start_linux(pid)


def check_alive(pid, expected_start, exact):
    if os.name == "nt":
        return _check_alive_windows(pid, expected_start, exact)
    return _check_alive_linux(pid, expected_start, exact)


# ========================================================= state-file ====
# The one state file in the temp directory -- one per machine (POSIX: one
# per uid, since /tmp can be shared across accounts). No temp-file-then-
# rename: the design decided a direct write is enough here.

def state_path():
    tmp = tempfile.gettempdir()
    if os.name == "nt":
        return os.path.join(tmp, "cai-viewer.json")
    return os.path.join(tmp, "cai-viewer-%d.json" % os.getuid())


def _parse_state(text):
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    pid, port, token = data.get("pid"), data.get("port"), data.get("token")
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    if not isinstance(port, int) or isinstance(port, bool):
        return None
    if not isinstance(token, str):
        return None
    return {"format": data.get("format"), "pid": pid,
            "procStart": data.get("procStart"), "port": port,
            "token": token, "startedAt": data.get("startedAt")}


def read_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None

    state = _parse_state(text)
    if state is not None:
        return state

    # JSON-corruption retry: the writer may be mid-write. One retry after a
    # short sleep, then treat it as absent.
    time.sleep(STATE_RETRY_DELAY_S)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    return _parse_state(text)


def write_state(path, state):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def remove_state(path, pid):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or data.get("pid") != pid:
        return
    try:
        os.remove(path)
    except OSError:
        pass


# ==================================================================http===
# 127.0.0.1-only server: identity/shutdown guarded by a token, plus the
# snapshot endpoint and the page. Unit 1 leaves /api/rows always-empty (no
# poller yet -- unit 5) and the page a placeholder (PAGE_HTML lands in unit
# 5 too).

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
      "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

# PAGE_HTML is a static, self-contained page (no external requests except
# its own /api/rows) adapted from the user-approved mockup at
# .claude/track/agent-viewer-web-portal/mockup.html. See
# implementation-notes.md's Unit 5 deviations for what was cut (the mockup's
# demo simulator, the free-text tdetail/timeline lines neither has a real
# field for) and why.
PAGE_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Viewer</title>
<script>
// Resolve the theme before first paint so a light-mode user never sees a dark flash.
try {
  var p = localStorage.getItem('agent-viewer-theme') || 'system';
  document.documentElement.dataset.theme =
    p === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : p;
} catch (e) {}
</script>
<style>
:root{
  --bg:#060a13; --glow1:rgba(34,211,238,.11); --glow2:rgba(167,139,250,.10); --grid:rgba(56,189,248,.045);
  --panel:rgba(11,18,33,.80); --panel2:rgba(19,30,52,.88); --border:#1a2a45; --border-hi:#2a4270;
  --text:#dbe6ff; --muted:#7f92b8; --faint:#46577a; --code:#03070f;
  --accent:#22d3ee; --accent2:#a78bfa;
  --ask:#fbbf24; --perm:#ff4d8d; --done:#60a5fa; --work:#4ade80; --ended:#475569; --bad:#f43f5e; --cai:#a78bfa;
  --on-color:#04101a;
  --shadow:0 12px 32px rgba(0,0,0,.45);
  --label-glow:0 0 10px currentColor;
  --mono:"JetBrains Mono","Cascadia Code","Cascadia Mono",Consolas,ui-monospace,monospace;
  color-scheme:dark;
}
:root[data-theme="light"]{
  --bg:#eef3fa; --glow1:rgba(8,145,178,.12); --glow2:rgba(124,58,237,.08); --grid:rgba(15,76,129,.06);
  --panel:rgba(255,255,255,.86); --panel2:rgba(240,245,251,.96); --border:#d2ddeb; --border-hi:#b3c5dc;
  --text:#0e1a2e; --muted:#4f6180; --faint:#9aa9c0; --code:#e7edf6;
  --accent:#0891b2; --accent2:#7c3aed;
  --ask:#d97706; --perm:#db2777; --done:#2563eb; --work:#059669; --ended:#94a3b8; --bad:#e11d48; --cai:#7c3aed;
  --on-color:#ffffff;
  --shadow:0 8px 24px rgba(15,40,80,.08);
  --label-glow:none;
  color-scheme:light;
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--text);
  background:
    radial-gradient(900px 520px at 8% -12%,var(--glow1),transparent 60%),
    radial-gradient(820px 520px at 100% -5%,var(--glow2),transparent 60%),
    linear-gradient(var(--grid) 1px,transparent 1px) 0 0/32px 32px,
    linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/32px 32px,
    var(--bg);
  background-attachment:fixed;
  font:14px/1.5 "Segoe UI Variable","Segoe UI",system-ui,-apple-system,"Microsoft JhengHei","PingFang TC",sans-serif;
  transition:background-color .25s,color .25s}
code,.mono{font-family:var(--mono);font-size:12.5px}
button{font:inherit;color:inherit;background:var(--panel2);border:1px solid var(--border);border-radius:8px;
  padding:5px 10px;cursor:pointer;transition:border-color .15s,box-shadow .15s}
button:hover{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}

header.top{display:flex;flex-wrap:wrap;gap:14px 20px;align-items:center;justify-content:space-between;
  padding:14px 20px;position:sticky;top:0;z-index:5;
  background:color-mix(in srgb,var(--bg) 72%,transparent);backdrop-filter:blur(14px)}
header.top::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--accent) 25%,var(--accent2) 75%,transparent)}
.brand{display:flex;gap:12px;align-items:center}
.logo{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:var(--panel2);
  border:1px solid color-mix(in srgb,var(--accent) 60%,transparent);
  box-shadow:0 0 18px color-mix(in srgb,var(--accent) 30%,transparent),inset 0 0 12px color-mix(in srgb,var(--accent) 22%,transparent)}
.logo i{width:12px;height:12px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent);
  animation:breathe 2.4s ease-in-out infinite}
h1{font-size:17px;margin:0;letter-spacing:.03em;
  background:linear-gradient(90deg,var(--text) 30%,var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);font:11.5px var(--mono);letter-spacing:.04em}
.live{color:var(--work)}
.live i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--work);margin-right:5px;
  box-shadow:0 0 8px var(--work);animation:blink 1.6s infinite}
#offlineNote,#staleNote{color:var(--ask);margin-left:8px;font:11px var(--mono)}
.summary{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:flex;align-items:baseline;gap:7px;padding:5px 12px;border-radius:8px;background:var(--panel2);
  border:1px solid var(--border);font-size:12px;color:var(--muted)}
.chip b{font:600 16px var(--mono);color:var(--text)}
.chip em{font-style:normal;font-size:11.5px}
.chip.human.hot{border-color:var(--ask);color:var(--ask);box-shadow:0 0 16px color-mix(in srgb,var(--ask) 30%,transparent)}
.chip.human.hot b{color:var(--ask);text-shadow:var(--label-glow)}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13px}
.toggle.on{border-color:var(--work);color:var(--work)}
.controls label{display:flex;gap:5px;align-items:center;color:var(--muted);cursor:pointer}
.seg{display:flex;padding:3px;gap:2px;border-radius:9px;background:var(--panel2);border:1px solid var(--border)}
.seg button{border:0;background:transparent;padding:4px 10px;border-radius:6px;color:var(--muted);font-size:12.5px}
.seg button:hover{box-shadow:none;color:var(--text)}
.seg button.active{color:var(--accent);background:color-mix(in srgb,var(--accent) 15%,transparent);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 55%,transparent)}

.unlock{margin:14px 20px 0;padding:10px 14px;border:1px dashed var(--ask);border-radius:10px;color:var(--ask);
  background:color-mix(in srgb,var(--ask) 7%,var(--panel));display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.unlock[hidden]{display:none}
.filters{display:flex;gap:6px;padding:14px 20px 4px;flex-wrap:wrap}
.filters button.active{color:var(--accent);border-color:var(--accent);
  background:color-mix(in srgb,var(--accent) 12%,var(--panel2))}
main{padding:8px 20px 36px;display:flex;flex-direction:column;gap:10px}
.empty{color:var(--muted);padding:40px;text-align:center;border:1px dashed var(--border);border-radius:12px}

/* one row per agent main session */
.row{--c:var(--faint);position:relative;display:grid;grid-template-columns:150px 240px minmax(0,1fr) auto;
  gap:18px;align-items:start;padding:14px 14px 14px 22px;border:1px solid var(--border);border-radius:12px;
  background:linear-gradient(90deg,color-mix(in srgb,var(--c) 9%,transparent),transparent 38%),var(--panel);
  backdrop-filter:blur(6px);box-shadow:var(--shadow)}
.s-ask{--c:var(--ask)} .s-perm{--c:var(--perm)} .s-done{--c:var(--done)}
.s-work{--c:var(--work)} .s-unk{--c:var(--ended)}
.stripe{position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c);border-radius:12px 0 0 12px;
  box-shadow:0 0 12px var(--c)}
.row.alert{border-color:color-mix(in srgb,var(--c) 70%,transparent);animation:glow 1.8s ease-in-out infinite}
.row.acked{border-color:color-mix(in srgb,var(--c) 40%,var(--border))}
.row.enter{animation:enter .7s ease-out,glow 1.8s ease-in-out .7s infinite}
@keyframes glow{
  0%,100%{box-shadow:var(--shadow),0 0 0 0 color-mix(in srgb,var(--c) 0%,transparent)}
  50%{box-shadow:var(--shadow),0 0 0 2px color-mix(in srgb,var(--c) 35%,transparent),0 0 30px color-mix(in srgb,var(--c) 32%,transparent)}}
@keyframes enter{0%{transform:translateY(-8px);filter:brightness(1.5)}100%{transform:none;filter:none}}
@keyframes blink{50%{opacity:.35}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes lamp{0%,45%{opacity:1;box-shadow:0 0 14px 4px var(--c)}55%,100%{opacity:.25;box-shadow:none}}
@keyframes breathe{50%{opacity:.45}}

.status{display:flex;gap:10px;align-items:flex-start}
.lamp{width:12px;height:12px;border-radius:50%;background:var(--c);margin-top:4px;flex:none;
  box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 20%,transparent),0 0 10px var(--c)}
.row.alert .lamp{animation:lamp 1s infinite}
.s-work .lamp{animation:breathe 2s ease-in-out infinite}
.slabel{font-weight:700;color:var(--c);text-shadow:var(--label-glow)}
.ctag{font:10px var(--mono);color:var(--muted);border:1px solid var(--border);border-radius:4px;
  padding:0 4px;margin-left:6px;vertical-align:middle}
.since{color:var(--muted);font:12px var(--mono)}
.proj{font-weight:650;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.kind{font:600 10.5px var(--mono);letter-spacing:.04em;padding:1px 7px;border-radius:5px;
  border:1px solid var(--border);color:var(--muted)}
.plat{font:600 10.5px var(--mono);letter-spacing:.04em;padding:1px 7px;border-radius:5px;color:var(--accent);
  border:1px solid color-mix(in srgb,var(--accent) 45%,transparent)}
.plat.codex{color:var(--text);border-color:var(--border-hi);background:var(--panel2)}
.kind.cai{color:var(--cai);border-color:color-mix(in srgb,var(--cai) 60%,transparent);
  background:color-mix(in srgb,var(--cai) 10%,transparent)}
.meta{color:var(--muted);font:11.5px/1.6 var(--mono);overflow-wrap:anywhere}
.activity{min-width:0;display:flex;flex-direction:column;gap:8px}
.actions{display:flex;flex-direction:column;gap:6px;align-items:stretch}
.actions .ack{border-color:var(--c);color:var(--c);font-weight:600;
  background:color-mix(in srgb,var(--c) 10%,var(--panel2))}
.actions .icon{padding:4px 8px;font-size:12.5px}

/* cai 6-stage stepper */
.tname{font:11.5px var(--mono);color:var(--muted);letter-spacing:.03em}
.tname b{color:var(--cai);font-weight:600}
.stepper{list-style:none;margin:5px 0 0;padding:0;display:flex;align-items:center;flex-wrap:wrap;gap:4px}
.stage{display:flex;align-items:center;gap:5px;padding:2px 9px 2px 4px;border-radius:6px;background:var(--panel2);
  border:1px solid var(--border);font:11.5px var(--mono);color:var(--muted)}
.stage .dot{width:15px;height:15px;border-radius:50%;display:grid;place-items:center;font-size:9.5px;
  border:1.5px solid var(--faint);font-weight:700}
.st-done{color:var(--text)}
.st-done .dot{background:var(--work);border-color:var(--work);color:var(--on-color);
  box-shadow:0 0 8px color-mix(in srgb,var(--work) 55%,transparent)}
.st-skipped .dot{border-style:dashed}
.st-skipped{text-decoration:line-through;text-decoration-color:var(--faint)}
.st-in-progress .dot{border-color:var(--done);border-top-color:transparent;animation:spin 1s linear infinite}
.st-failed .dot,.st-blocked .dot{background:var(--bad);border-color:var(--bad);color:#fff;
  box-shadow:0 0 8px color-mix(in srgb,var(--bad) 55%,transparent)}
.stage.cur{color:var(--text);border-color:var(--c);box-shadow:0 0 10px color-mix(in srgb,var(--c) 30%,transparent)}
.sep{width:10px;height:1px;background:var(--border-hi)}
.gate{font-size:12px;color:var(--faint);line-height:1;padding:2px 4px;border-radius:4px}
.gate.waiting{color:var(--on-color);background:var(--ask);box-shadow:0 0 10px var(--ask);animation:blink .9s infinite}

.box{padding:9px 12px;border-radius:10px;background:color-mix(in srgb,var(--c) 7%,var(--panel2));
  border:1px solid color-mix(in srgb,var(--c) 42%,transparent);
  box-shadow:inset 0 0 22px color-mix(in srgb,var(--c) 7%,transparent)}
.q{font-weight:600}
.opts{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.opt{font-size:12px;padding:2px 9px;border-radius:6px;border:1px solid var(--border);background:var(--panel)}
.hint{font:11px var(--mono);color:var(--muted);margin-top:7px;letter-spacing:.02em}
.now{display:flex;gap:8px;align-items:center;min-width:0}
.tool{font:700 11px var(--mono);padding:1px 7px;border-radius:5px;flex:none;color:var(--accent);
  background:color-mix(in srgb,var(--accent) 10%,var(--panel2));border:1px solid color-mix(in srgb,var(--accent) 40%,transparent)}
.now code{background:var(--code);border:1px solid var(--border);padding:2px 7px;border-radius:5px;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dur{color:var(--muted);font:12px var(--mono);flex:none}
.spin{width:12px;height:12px;border-radius:50%;border:2px solid var(--work);border-top-color:transparent;
  animation:spin .8s linear infinite;flex:none;filter:drop-shadow(0 0 4px var(--work))}
.recent{font-size:12px;color:var(--muted);display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.recent span{font:11.5px var(--mono);padding:1px 6px;border-radius:5px;background:var(--panel2);border:1px solid var(--border)}
.subs{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--muted)}
.sub-a{font:11px var(--mono);padding:1px 8px;border-radius:5px;border:1px solid var(--border)}

.timeline{grid-column:1/-1;margin:0;padding:10px 0 0;border-top:1px dashed var(--border);list-style:none;
  display:flex;flex-direction:column;gap:3px}
.timeline li{display:grid;grid-template-columns:72px 1fr;gap:10px;font-size:12.5px}
.timeline .t{color:var(--accent);font:11.5px var(--mono);opacity:.8}

footer{color:var(--muted);font-size:12px;padding:0 20px 40px;line-height:1.7}
footer code{background:var(--panel2);border:1px solid var(--border);padding:1px 5px;border-radius:4px}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);color:var(--text);
  background:var(--panel2);border:1px solid var(--accent);box-shadow:0 0 18px color-mix(in srgb,var(--accent) 30%,transparent);
  padding:8px 14px;border-radius:8px;font-size:13px;opacity:0;transition:opacity .2s;pointer-events:none;z-index:20}
.toast.show{opacity:1}

@media (max-width:960px){
  .row{grid-template-columns:minmax(0,1fr) auto}
  .ident,.activity{grid-column:1/-1}
  .actions{grid-row:1;grid-column:2;flex-direction:row}
}
@media (max-width:700px){
  header.top,.filters,main,footer{padding-left:16px;padding-right:16px}
  .unlock{margin-left:16px;margin-right:16px}
}
@media (prefers-reduced-motion: reduce){ *{animation:none !important} }
</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <div class="logo"><i></i></div>
    <div>
      <h1>Agent Viewer</h1>
      <div class="sub">CAI · LOCAL · <span class="live" id="liveBadge"><i></i>LIVE</span> · 127.0.0.1:__PORT__
        <span id="offlineNote" hidden></span><span id="staleNote" hidden></span></div>
    </div>
  </div>
  <div class="summary" id="summary"></div>
  <div class="controls">
    <div class="seg" id="themeSeg" role="radiogroup" aria-label="主題">
      <button data-theme-pref="system" title="跟隨作業系統設定">◐ 系統</button>
      <button data-theme-pref="dark">☾ 深色</button>
      <button data-theme-pref="light">☀ 淺色</button>
    </div>
    <button id="soundBtn" class="toggle on">🔔 聲音：開</button>
    <label><input type="checkbox" id="doneChime"> 完成時也響</label>
    <label><input type="checkbox" id="inferredChime" checked> 推斷的等權限也響</label>
  </div>
</header>

<div id="unlock" class="unlock">
  瀏覽器規定頁面要先被點過一次才能發出聲音 →
  <button id="unlockBtn">啟用提示音（會先響一次給你聽）</button>
</div>

<nav class="filters" id="filters">
  <button data-f="all" class="active">全部</button>
  <button data-f="human">需要你</button>
  <button data-f="cai">cai track</button>
  <button data-f="plain">一般 agent</button>
</nav>

<main id="list"></main>

<footer>
  <span id="codexLockNote" hidden>Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著<br></span>
  回答問題、核准權限、簽核仍然在終端機做；這一頁只負責讓你<b>看見</b>誰在等你。<br>
  同一張表列出 Claude Code 與 Codex 的主 session。「可能在等權限」只出現在 Codex 的列上，是推斷出來的：
  一次工具呼叫超過 30 秒還沒有結果就算，只是跑得比較久的呼叫看起來會一樣；
  Claude 的「等你核准權限」是從它自己的登記檔讀到的，是確定，不是推斷。<br>
  排序：需要你的在最上面（等最久的優先）→ 執行中。按「已讀」停止閃爍，狀態再變時會重新亮起。<br>
  主題選擇記在這個瀏覽器裡，下次打開沿用。
</footer>

<div class="toast" id="toast"></div>

<script>
const STAGES = ['intake','discover','design','build','verify','ship'];
// A human gate sits in front of these two stages (after design; before ship's irreversible steps).
const GATED = new Set(['build','ship']);
const META = {
  question:   {cls:'ask',  human:true,  rank:0},
  permission: {cls:'perm', human:true,  rank:0},
  attention:  {cls:'ask',  human:true,  rank:0},
  done:       {cls:'done', human:true,  rank:1},
  working:    {cls:'work', human:false, rank:2},
  unknown:    {cls:'unk',  human:false, rank:3},
};

// ---- theme: system / dark / light, remembered per browser ----
const THEME_KEY = 'agent-viewer-theme';
const lightMq = window.matchMedia('(prefers-color-scheme: light)');
let themePref = 'system';
try { themePref = localStorage.getItem(THEME_KEY) || 'system'; } catch (e) {}
function applyTheme(){
  const resolved = themePref === 'system' ? (lightMq.matches ? 'light' : 'dark') : themePref;
  document.documentElement.dataset.theme = resolved;
  for (const b of document.querySelectorAll('[data-theme-pref]')) {
    b.classList.toggle('active', b.dataset.themePref === themePref);
    b.setAttribute('aria-checked', b.dataset.themePref === themePref);
  }
}
lightMq.addEventListener('change', () => { if (themePref === 'system') applyTheme(); });
document.getElementById('themeSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-theme-pref]');
  if (!b) return;
  themePref = b.dataset.themePref;
  try { localStorage.setItem(THEME_KEY, themePref); } catch (err) {}
  applyTheme();
});
applyTheme();

// ---- sound preferences: master toggle unpersisted (matches the mockup); the
// two per-sound checkboxes are persisted, unlike the mockup which never did. ----
const DONE_CHIME_KEY = 'agent-viewer-done-chime';
const INFERRED_CHIME_KEY = 'agent-viewer-inferred-chime';
const doneChimeEl = document.getElementById('doneChime');
const inferredChimeEl = document.getElementById('inferredChime');
try { doneChimeEl.checked = localStorage.getItem(DONE_CHIME_KEY) === '1'; } catch (e) {}
try {
  const v = localStorage.getItem(INFERRED_CHIME_KEY);
  inferredChimeEl.checked = v === null ? true : v === '1';
} catch (e) {}
doneChimeEl.addEventListener('change', () => {
  try { localStorage.setItem(DONE_CHIME_KEY, doneChimeEl.checked ? '1' : '0'); } catch (e) {}
});
inferredChimeEl.addEventListener('change', () => {
  try { localStorage.setItem(INFERRED_CHIME_KEY, inferredChimeEl.checked ? '1' : '0'); } catch (e) {}
});

let filter = 'all';
let soundOn = true;
let actx = null;
const acks = new Set();
const expanded = new Set();
const nodes = new Map();
const listEl = document.getElementById('list');
let rows = [];

const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad = n => String(n).padStart(2, '0');
function clockFmt(ms){
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}
function humanFmt(ms){
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return s + ' 秒';
  if (s < 3600) return Math.floor(s / 60) + ' 分鐘';
  return Math.floor(s / 3600) + ' 小時 ' + Math.floor(s % 3600 / 60) + ' 分';
}
const clock = t => new Date(t).toLocaleTimeString('zh-TW', {hour12:false});

function stateLabel(row){
  if (row.state === 'question') {
    if (row.track && row.track.gateWaiting) return {label:'等你簽核', icon:'🛡️'};
    return {label:'等你回答', icon:'❓'};
  }
  if (row.state === 'permission') {
    return row.certainty === 'confirmed'
      ? {label:'等你核准權限', icon:'🔐'}
      : {label:'可能在等權限', icon:'🔐'};
  }
  if (row.state === 'attention') return {label:'等你處理', icon:'⚠️'};
  if (row.state === 'done') return {label:'完成，等指示', icon:'✅'};
  if (row.state === 'working') return {label: row.background === true ? '執行中（背景）' : '執行中', icon:''};
  return {label:'未知', icon:''};
}

function stepperHTML(row){
  const t = row.track;
  const byId = {};
  for (const stg of t.stages) byId[stg.id] = stg.status;
  const waitingGate = (row.state === 'question' && t.gateWaiting) ? t.gateWaiting : null;
  const items = STAGES.map((s, i) => {
    const st = byId[s] || 'todo';
    const icon = {done:'✓', skipped:'–', failed:'✕', blocked:'‖'}[st] || '';
    const gateHTML = GATED.has(s)
      ? '<li class="gate ' + (waitingGate === s ? 'waiting' : '') + '" title="人工閘門">⚑</li><li class="sep"></li>'
      : '';
    const sepHTML = i ? '<li class="sep"></li>' : '';
    const curCls = s === t.current ? 'cur' : '';
    return sepHTML + gateHTML + '<li class="stage st-' + esc(st) + ' ' + curCls +
      '"><span class="dot">' + esc(icon) + '</span>' + esc(s) + '</li>';
  }).join('');
  return `<div><div class="tname">TRACK · <b>${esc(t.name)}</b></div><ol class="stepper">${items}</ol></div>`;
}

function nowHTML(row){
  const cur = row.current || {};
  // 「剛剛」shows only the most recent 3 of row.recent's up-to-8 entries
  // (oldest-first order) -- the restored 「經過」 button below expands the
  // full list.
  const r = (row.recent || []).slice(-3).map(x =>
    '<span>' + esc(x.tool) + ' ' + esc(String(x.input || '').split('/').pop()) + '</span>').join('');
  const subs = (row.subagents || []).map(s => '<span class="sub-a">' + esc(s) + '</span>').join('');
  const since = cur.since || row.since;
  const recentHTML = r ? '<div class="recent">剛剛：' + r + '</div>' : '';
  const subsHTML = subs ? '<div class="subs">subagents：' + subs + '</div>' : '';
  return `<div class="now"><span class="spin"></span><span class="tool">${esc(cur.tool || '')}</span>
      <code>${esc(cur.input || '')}</code><span class="dur" data-since="${esc(since)}" data-mode="dur"></span></div>
    ${recentHTML}
    ${subsHTML}`;
}

function activityHTML(row){
  let h = row.track ? stepperHTML(row) : '';
  if (row.state === 'question') {
    const opts = (row.question && row.question.options) || [];
    const icon = (row.track && row.track.gateWaiting) ? '🛡️' : '❓';
    const text = row.question ? (row.question.text || '') : '';
    const optsHTML = opts.map(o => '<span class="opt">' + esc(o) + '</span>').join('');
    h += `<div class="box"><div class="q">${esc(icon)} ${esc(text)}</div>
      <div class="opts">${optsHTML}</div>
      <div class="hint">回終端機作答 · 這一頁只顯示，不代答</div></div>`;
  } else if (row.state === 'permission') {
    const perm = row.permission || {};
    const confirmed = row.certainty === 'confirmed';
    const qline = confirmed ? '等你核准權限' : '可能在等你核准權限（推斷）';
    const hint = confirmed
      ? '要核准請回終端機'
      : '推斷：這個工具呼叫太久沒有結果 · 若只是跑得久會自己恢復 · 要核准請回終端機';
    h += `<div class="box"><div class="q">🔐 ${esc(qline)}</div>
      <div class="now" style="margin-top:7px"><span class="tool">${esc(perm.tool || '')}</span><code>${esc(perm.input || '')}</code></div>
      <div class="hint">${esc(hint)}</div></div>`;
  } else if (row.state === 'attention') {
    const notes = (row.notes || []).join('、');
    if (notes) h += `<div class="box">${esc(notes)}</div>`;
  } else if (row.state === 'done') {
    if (row.summary) h += `<div class="box">✅ ${esc(row.summary)}</div>`;
  } else if (row.state === 'working') {
    h += nowHTML(row);
  }
  return h;
}

function rowHTML(row){
  const m = META[row.state];
  const info = stateLabel(row);
  const isAlert = m.human && !acks.has(row.key);
  const alertCls = isAlert ? 'alert' : '';
  const ackedCls = (m.human && !isAlert) ? 'acked' : '';
  const mode = m.human ? 'wait' : (row.state === 'working' ? 'run' : 'ago');
  const platLabel = row.platform === 'codex' ? 'CODEX' : 'CLAUDE';
  const kindHTML = row.track ? '<span class="kind cai">CAI TRACK</span>' : '<span class="kind">AGENT</span>';
  const certaintyTag = row.certainty === 'confirmed' ? '確定' : '推斷';
  const sinceNote = row.aliveCertainty === 'inferred' ? '<div class="meta">存活：推斷</div>' : '';
  const branchHTML = row.branch ? `<div class="meta">⎇ ${esc(row.branch)}</div>` : '';
  const ackBtn = isAlert ? '<button class="ack" data-act="ack">已讀</button>' : '';
  // 「經過」 expands row.recent's up-to-8 entries (D2 rule 2) -- unlike the
  // mockup's timeline interpolation (a sibling placed after the closing
  // article tag, which the render() DOM-parse below then silently drops),
  // this one goes inside the article so it actually renders.
  const tl = expanded.has(row.key)
    ? '<ul class="timeline">' + (row.recent || []).map(x =>
        '<li><span class="t">' + esc(x.at != null ? clock(x.at) : '') + '</span><span>' +
        esc(x.tool) + ' ' + esc(x.input || '') + '</span></li>').join('') + '</ul>'
    : '';
  const expandBtn = '<button class="icon" data-act="expand">' +
    (expanded.has(row.key) ? '▴ 收起' : '▾ 經過') + '</button>';

  return `<article class="row s-${m.cls} ${alertCls} ${ackedCls}" data-id="${esc(row.key)}">
    <div class="stripe"></div>
    <div class="status"><span class="lamp"></span><div>
      <div class="slabel">${esc(info.icon)} ${esc(info.label)} <span class="ctag">${esc(certaintyTag)}</span></div>
      <div class="since" data-since="${esc(row.since)}" data-mode="${mode}"></div></div></div>
    <div class="ident">
      <div class="proj">${esc(row.project)}<span class="plat ${row.platform}">${platLabel}</span>${kindHTML}</div>
      ${branchHTML}
      <div class="meta">${esc(row.cwd || '')}</div>
      <div class="meta">SID ${esc(row.sessionId || '')} · ${esc(row.model || '')}</div>
      ${sinceNote}
    </div>
    <div class="activity">${activityHTML(row)}</div>
    <div class="actions">
      ${ackBtn}
      <button class="icon" data-act="copy" title="複製 resume 指令">⧉ resume</button>
      ${expandBtn}
    </div>
    ${tl}
  </article>`;
}

const pass = row => filter === 'all' || (filter === 'human' ? META[row.state].human :
  (filter === 'cai' ? row.track != null : row.track == null));
const cmp = (x, y) => META[x.state].rank - META[y.state].rank || x.since - y.since;

// Keyed update: only rows whose content changed are replaced, so the glow on the others keeps its rhythm.
function render(){
  const vis = rows.filter(pass).sort(cmp);
  const keep = new Set(vis.map(r => r.key));
  for (const [key, n] of nodes) if (!keep.has(key)) { n.el.remove(); nodes.delete(key); }
  let prev = null;
  for (const row of vis) {
    const sig = JSON.stringify([row, acks.has(row.key), expanded.has(row.key)]);
    let n = nodes.get(row.key);
    if (!n || n.sig !== sig) {
      const tmp = document.createElement('div');
      tmp.innerHTML = rowHTML(row).trim();
      const el = tmp.firstElementChild;
      if (n) n.el.replaceWith(el);
      n = {el, sig};
      nodes.set(row.key, n);
    }
    const want = prev ? prev.nextElementSibling : listEl.firstElementChild;
    if (want !== n.el) listEl.insertBefore(n.el, want);
    prev = n.el;
  }
  let empty = listEl.querySelector('.empty');
  if (!vis.length && !empty) listEl.insertAdjacentHTML('beforeend', '<div class="empty">這個分類目前沒有 agent</div>');
  if (vis.length && empty) empty.remove();
  summary();
  tick();
}

function summary(){
  const human = rows.filter(r => META[r.state].human);
  const unread = human.filter(r => !acks.has(r.key)).length;
  const work = rows.filter(r => r.state === 'working').length;
  const hotCls = unread ? 'hot' : '';
  const unreadHTML = unread ? '<em>未讀 ' + unread + '</em>' : '';
  document.getElementById('summary').innerHTML =
    `<span class="chip human ${hotCls}">需要你<b>${pad(human.length)}</b>${unreadHTML}</span>
     <span class="chip">執行中<b>${pad(work)}</b></span>`;
  document.title = unread ? '(' + unread + ') 需要你 · Agent Viewer' : 'Agent Viewer';
}

function checkStale(){
  const note = document.getElementById('staleNote');
  if (lastGeneratedAt && Date.now() - lastGeneratedAt > 10000) {
    note.hidden = false;
    note.textContent = '資料停在 ' + clock(lastGeneratedAt);
  } else {
    note.hidden = true;
  }
}

function tick(){
  const now = Date.now();
  for (const el of document.querySelectorAll('[data-since]')) {
    const d = now - Number(el.dataset.since);
    el.textContent = {wait:'已等 ' + clockFmt(d), run:'本輪 ' + clockFmt(d), ago:humanFmt(d) + '前結束', dur:clockFmt(d)}[el.dataset.mode];
  }
  checkStale();
}

function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove('show'), 2200);
}

// Synthesised bell: a few inharmonic partials per note, so nothing has to be downloaded.
function chime(kind){
  if (!soundOn || !actx) return;
  const t0 = actx.currentTime + 0.02;
  let notes, partials, tail;
  if (kind === 'done') { notes = [[880, 0]]; partials = [[1, 0.28], [2.76, 0.06], [5.4, 0.02]]; tail = 1.4; }
  else if (kind === 'tick') { notes = [[440, 0]]; partials = [[1, 0.12]]; tail = 0.25; }
  else { notes = [[659.25, 0], [523.25, 0.34]]; partials = [[1, 0.28], [2.76, 0.06], [5.4, 0.02]]; tail = 1.4; }
  for (const [f, dt] of notes) {
    for (const [mult, amp] of partials) {
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = 'sine';
      o.frequency.value = f * mult;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(amp, t0 + dt + 0.015);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + tail);
      o.connect(g); g.connect(actx.destination);
      o.start(t0 + dt); o.stop(t0 + dt + tail + 0.1);
    }
  }
}

// ---- real data: poll /api/rows every second (V1); 3 consecutive failures
// counts as offline (V2); ring/flash rules are V7's four-part reading. ----
const HUMAN_STATES = new Set(['question', 'permission', 'attention', 'done']);
let lastGeneratedAt = 0;
let failCount = 0;
let firstFetch = true;
const lastSeenEntryId = new Map();

function setOffline(off){
  const badge = document.getElementById('liveBadge');
  const note = document.getElementById('offlineNote');
  if (off) {
    badge.classList.remove('live');
    badge.innerHTML = '離線';
    note.hidden = false;
    note.textContent = 'viewer 沒有回應（可能已經 stop）';
  } else {
    badge.classList.add('live');
    badge.innerHTML = '<i></i>LIVE';
    note.hidden = true;
    note.textContent = '';
  }
}

function ringForRows(newRows){
  for (const row of newRows) {
    if (!HUMAN_STATES.has(row.state)) continue;
    const prevId = lastSeenEntryId.get(row.key);
    const changed = prevId === undefined || prevId !== row.entryId;
    if (changed && !firstFetch) {
      acks.delete(row.key);
      if (soundOn) {
        if (row.state === 'permission' && row.certainty === 'inferred') {
          if (inferredChimeEl.checked) chime('tick');
        } else if (row.state === 'done') {
          if (doneChimeEl.checked) chime('done');
        } else {
          chime('ask');
        }
      }
    }
    lastSeenEntryId.set(row.key, row.entryId);
  }
  firstFetch = false;
}

async function poll(){
  let data = null;
  try {
    const resp = await fetch('/api/rows', {cache: 'no-store'});
    if (!resp.ok) throw new Error('bad status');
    data = await resp.json();
    if (!data || !Array.isArray(data.rows)) throw new Error('bad json');
  } catch (err) {
    failCount++;
    setOffline(failCount >= 3);
    return;
  }
  failCount = 0;
  setOffline(false);
  ringForRows(data.rows);
  rows = data.rows;
  lastGeneratedAt = data.generatedAt;
  document.getElementById('codexLockNote').hidden = data.codexLockDirMissing !== true;
  render();
}

listEl.addEventListener('click', e => {
  const b = e.target.closest('button[data-act]');
  if (!b) return;
  const row = rows.find(r => r.key === b.closest('.row').dataset.id);
  if (!row) return;
  if (b.dataset.act === 'ack') acks.add(row.key);
  if (b.dataset.act === 'copy') {
    const cmd = (row.platform === 'codex' ? 'codex resume ' : 'claude --resume ') + row.sessionId;
    try { navigator.clipboard.writeText(cmd).catch(() => {}); } catch (err) {}
    toast('已複製：' + cmd);
  }
  if (b.dataset.act === 'expand') {
    expanded.has(row.key) ? expanded.delete(row.key) : expanded.add(row.key);
  }
  render();
});
document.getElementById('filters').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]');
  if (!b) return;
  filter = b.dataset.f;
  for (const x of document.querySelectorAll('.filters button')) x.classList.toggle('active', x === b);
  render();
});
document.getElementById('soundBtn').addEventListener('click', e => {
  soundOn = !soundOn;
  e.currentTarget.classList.toggle('on', soundOn);
  e.currentTarget.textContent = soundOn ? '🔔 聲音：開' : '🔕 聲音：關';
});
document.getElementById('unlockBtn').addEventListener('click', () => {
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    actx.resume();
  } catch (err) { toast('這個瀏覽器不支援 Web Audio'); }
  document.getElementById('unlock').hidden = true;
  chime('ask');
});

render();
poll();
setInterval(poll, 1000);
setInterval(tick, 1000);
</script>
</body>
</html>
"""


class ViewerServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    poller = None  # set by cmd_serve before serve_forever(); a bare test
                   # server (no poller attached) falls back to an empty
                   # snapshot rather than crashing the request thread.


def host_ok(host_header, port):
    if not host_header:
        return False
    want = ("127.0.0.1:%d" % port, "localhost:%d" % port)
    return host_header.strip().lower() in want


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # stdio is DEVNULL in the real deployment; nothing reads this.

    def _security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send(self, status, body, content_type, extra_headers=None):
        self.send_response(status)
        self._security_headers()
        if content_type is not None:
            self.send_header("Content-Type", content_type)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _check_host(self):
        port = self.server.server_address[1]
        if not host_ok(self.headers.get("Host"), port):
            self._send(403, b"forbidden host", "text/plain; charset=utf-8")
            return False
        return True

    def _token_ok(self):
        return hmac.compare_digest(
            self.headers.get(TOKEN_HEADER, ""), self.server.token)

    def do_GET(self):
        if not self._check_host():
            return
        if self.path == "/":
            port = self.server.server_address[1]
            body = PAGE_HTML.replace("__PORT__", str(port)).encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8",
                       extra_headers={"Content-Security-Policy": CSP})
        elif self.path == "/api/rows":
            self._serve_rows()
        elif self.path == "/identity":
            self._serve_identity()
        else:
            self._send(404, b"", None)

    def do_POST(self):
        if not self._check_host():
            return
        if self.path == "/shutdown":
            self._serve_shutdown()
        else:
            self._send(404, b"", None)

    def _serve_rows(self):
        poller = self.server.poller
        if poller is None:
            payload = {"format": 1, "generatedAt": int(time.time() * 1000),
                      "rows": [], "problems": []}
            body = json.dumps(payload).encode("utf-8")
        else:
            body = poller.snapshot()
        self._send(200, body, "application/json; charset=utf-8")

    def _serve_identity(self):
        if not self._token_ok():
            self._send(403, b"", None)
            return
        payload = {"app": "cai-viewer", "format": 1,
                  "pid": os.getpid(), "port": self.server.server_address[1]}
        self._send(200, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _serve_shutdown(self):
        if not self._token_ok():
            self._send(403, b"", None)
            return
        self._send(202, b"", None)
        # shutdown() deadlocks if called from the handler's own thread.
        threading.Thread(target=self.server.shutdown, daemon=True).start()


# ==================================================================tail====
# Bounded reads: a fixed tail of bytes from a file, whatever JSON objects
# parse out of it. Cached keyed on (path, size, mtime_ns) so a poller loop
# that reads the same unchanged file every tick does not re-read it -- a
# plain module-level dict is enough because only the poller thread (unit 5)
# ever touches this cache.

_tail_cache = {}


def read_tail(path, max_bytes):
    try:
        stat = os.stat(path)
    except OSError:
        return []
    key = (path, stat.st_size, stat.st_mtime_ns)

    cached = _tail_cache.get(path)
    if cached is not None and cached[0] == key:
        return cached[1]

    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, stat.st_size - max_bytes))
            offset = fh.tell()
            data = fh.read()
    except OSError:
        return []

    if offset > 0:
        # The tail may start mid-line; discard the partial line at the front.
        newline = data.find(b"\n")
        data = data[newline + 1:] if newline != -1 else b""

    rows = []
    for line in data.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)

    _tail_cache[path] = (key, rows)
    return rows


def read_first_line(path, max_bytes=65536):
    """Independent of read_tail(): reads from the FRONT of a (small) file
    and needs only its first line -- unit 3 uses this for a Codex rollout's
    session_meta line. No cache, no tail-from-the-end logic."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(max_bytes)
    except OSError:
        return None
    first = data.decode("utf-8", "replace").split("\n", 1)[0]
    try:
        obj = json.loads(first)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


# ================================================ claude_source =========
# Turns a Claude registry file into zero or one row. classify_claude() is a
# pure function of (registry, transcript tail, now); claude_rows() is the
# only place that touches the filesystem.

REGISTRY_READ_MAX = 65536
TRANSCRIPT_TAIL_MAX = 262144
QUESTION_TEXT_MAX = 1000
QUESTION_OPTION_MAX = 200
QUESTION_OPTIONS_MAX = 10
PERMISSION_INPUT_MAX = 500
ACTION_INPUT_MAX = 120
# D2 derivation rules (approved by the user during verify, 2026-09-25 --
# see implementation-notes.md's addendum). Shared by both claude_source and
# codex_source, so defined once here rather than in each section.
SUMMARY_MAX = 200          # rule 1 -- 做完的摘要
RECENT_ACTIONS_LIMIT = 8   # rule 2 -- 最近 8 筆動作; the restored 「經過」
                          # button expands exactly this list.
RECENT_ACTION_INPUT_MAX = 80  # rule 2's "80 字元" cut

KNOWN_CLAUDE_STATUSES = {"busy", "idle", "waiting", "shell"}
ESCALATED_WAITING_FOR = {"sandbox request", "worker request", "dialog open"}


def _truncate(text, limit):
    return text if len(text) <= limit else text[:limit]


_PARAM_SUMMARY_KEYS = ("file_path", "path", "pattern", "command", "cmd", "url", "description")
# D2 rule 3's exception for a `shell` row's `current`: a background Bash's
# own description says what it is doing, so it is read before "command"
# there -- everywhere else "description" stays last (only an Agent-like call
# with none of the other keys ever reaches it).
_BACKGROUND_BASH_SUMMARY_KEYS = ("description", "command")


def _param_summary(tool_input, limit, key_order=_PARAM_SUMMARY_KEYS):
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    for key in key_order:
        if key in tool_input:
            return _truncate(str(tool_input[key]), limit)
    return _truncate(json.dumps(tool_input), limit)


def _unresolved_tool_uses(tail):
    """All tool_use blocks (inside any assistant message) with no later
    tool_result carrying its id, in tail order -- shared by
    _last_unresolved_tool_use() (just the most recent one) and
    _claude_subagents() (every still-running Agent/Task call, D2 rule 3,
    since more than one subagent can run at once)."""
    tool_uses = []
    resolved_ids = set()
    for row in tail:
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        if row.get("type") == "assistant":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append(block)
        elif row.get("type") == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    if tool_use_id is not None:
                        resolved_ids.add(tool_use_id)
    return [block for block in tool_uses if block.get("id") not in resolved_ids]


def _last_unresolved_tool_use(tail):
    """The last tool_use block (inside any assistant message) with no later
    tool_result carrying its id -- the thing Claude is still waiting on."""
    unresolved = _unresolved_tool_uses(tail)
    return unresolved[-1] if unresolved else None


def _question_payload(tool_use):
    tool_input = tool_use.get("input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    questions = tool_input.get("questions")
    questions = questions if isinstance(questions, list) else []

    texts, options = [], []
    for question in questions:
        if not isinstance(question, dict):
            continue
        text = question.get("question")
        if isinstance(text, str):
            texts.append(text)
        for option in question.get("options") or []:
            if len(options) >= QUESTION_OPTIONS_MAX:
                break
            if isinstance(option, dict) and isinstance(option.get("label"), str):
                options.append(_truncate(option["label"], QUESTION_OPTION_MAX))
        if len(options) >= QUESTION_OPTIONS_MAX:
            break

    return {"text": _truncate(" ".join(texts), QUESTION_TEXT_MAX),
           "options": options}


def _parse_iso_ms(ts):
    """ISO8601 (with a trailing "Z", as both Claude transcript and Codex
    rollout timestamps use) to epoch milliseconds. Shared by claude_source
    and codex_source -- moved up here from its original codex_source-only
    spot since D2 rule 2 (最近 8 筆動作) needs it on both sides."""
    try:
        parsed = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    return int(parsed.timestamp() * 1000)


# ---- D2 rule 1 (做完的摘要) and rule 2 (最近 8 筆動作), Claude side. Key
# names (message.content[].type == "text"/"text"; row-level "timestamp")
# confirmed read-only against real local transcripts, verify round 2
# 2026-09-25; no conversation content copied anywhere.

def _last_assistant_text(tail):
    """The last assistant message's text block(s), joined with "\\n". None
    if the last assistant message (if any) carries no text block -- this
    does not keep searching further back for one that does."""
    for row in reversed(tail):
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return None
        texts = [block["text"] for block in content
                if isinstance(block, dict) and block.get("type") == "text"
                and isinstance(block.get("text"), str)]
        return "\n".join(texts) if texts else None
    return None


def _recent_claude_actions(tail):
    """The last RECENT_ACTIONS_LIMIT tool_use blocks in tail, oldest of the
    kept ones first -- the order both nowHTML's 「剛剛」 (its last 3) and the
    restored 「經過」 expand (all of them) render in."""
    calls = []
    for row in tail:
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        ts = row.get("timestamp")
        at = _parse_iso_ms(ts) if isinstance(ts, str) else None
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append({"at": at, "tool": block.get("name"),
                              "input": _param_summary(block.get("input"),
                                                      RECENT_ACTION_INPUT_MAX)})
    return calls[-RECENT_ACTIONS_LIMIT:]


# ---- D2 rule 3 (subagent), Claude side. subagent_type key confirmed
# read-only 2026-09-25, same batch as above.

CLAUDE_SUBAGENT_TOOLS = ("Agent", "Task")
# The calls that keep running after their tool_result: the subagent tools,
# and Workflow, which runs a script of subagents.
CLAUDE_BACKGROUND_TOOLS = CLAUDE_SUBAGENT_TOOLS + ("Workflow",)
ASYNC_LAUNCHED_STATUS = "async_launched"
TASK_NOTIFICATION_TAG = "<task-notification>"
# V8 (docs/design/2026-09-26-viewer-live-status-stance.md:29): the pending
# counts a turn_duration row may carry, and the <task-notification> statuses
# that count as a background launch having finished. Both lists are closed
# on purpose (decisions Ruled out) -- a key or status not named here is not
# background work, even if a future Claude Code adds one.
CLAUDE_PENDING_COUNT_KEYS = ("pendingBackgroundAgentCount", "pendingWorkflowCount")
TASK_END_STATUSES = ("completed", "failed", "killed", "stopped")


def _subagent_name(block):
    """input.subagent_type, falling back to the tool's own name
    ("Agent"/"Task") when that key is missing."""
    tool_input = block.get("input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    name = tool_input.get("subagent_type")
    return name if isinstance(name, str) and name else block.get("name")


def _task_end(row):
    """The <task-id> of a queue-operation row that ends a background launch
    (its <status> is one of TASK_END_STATUSES), or None -- for any other
    row, or a queue-operation whose status isn't a closing one. Used by
    _async_subagents() (pairing -- popping an id this tail never launched
    is a harmless no-op) and by _last_turn_end() ("does anything after the
    last turn_duration count as the turn having moved on"), which also
    checks _launched_task_ids() before trusting a notice: one for some
    other tail's task -- e.g. a nested subagent's own lens calls, whose
    notification can land in this transcript instead of theirs -- must not
    read as this session's turn having moved on (verify 2026-09-26)."""
    if row.get("type") != "queue-operation":
        return None
    content = row.get("content")
    if not (isinstance(content, str) and TASK_NOTIFICATION_TAG in content):
        return None
    status = content.partition("<status>")[2].partition("</status>")[0]
    if status not in TASK_END_STATUSES:
        return None
    task_id = content.partition("<task-id>")[2].partition("</task-id>")[0]
    return task_id or None


def _async_subagents(tail):
    """(name, tool_use block) for every Agent/Task/Workflow call launched in
    the background and not yet reported back, in launch order. Claude
    answers such a call at once with a tool_result whose row-level
    toolUseResult says status "async_launched" and carries the task's id
    (agentId for a subagent, taskId for a workflow) -- so to
    _unresolved_tool_uses(), which reads "has a tool_result" as "finished",
    a running background subagent is invisible. Its real finish is the
    later queue-operation row carrying a <task-notification> for that id
    (its <status> is completed, failed, killed or stopped; every one means
    not running). A subagent is named by its subagent_type, a workflow by
    the result's workflowName. Shapes confirmed read-only against real
    local transcripts 2026-09-26. A task the user resumes after its
    notification is not re-listed."""
    calls = {}      # tool_use id -> block, for the background tools only
    running = {}    # task id -> (name, block), insertion order == launch order
    for row in tail:
        row_type = row.get("type")
        if row_type == "queue-operation":
            task_id = _task_end(row)
            if task_id is not None:
                running.pop(task_id, None)
            continue
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        if row_type == "assistant":
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") in CLAUDE_BACKGROUND_TOOLS):
                    calls[block.get("id")] = block
        elif row_type == "user":
            result = row.get("toolUseResult")
            if not (isinstance(result, dict)
                    and result.get("status") == ASYNC_LAUNCHED_STATUS):
                continue
            task_id = result.get("agentId") or result.get("taskId")
            if not isinstance(task_id, str):
                continue
            answered = [block for block in content
                        if isinstance(block, dict) and block.get("type") == "tool_result"
                        and block.get("tool_use_id") in calls]
            # One row-level toolUseResult describes one call. A row answering
            # several background calls at once has never been seen; if it
            # ever is, it cannot say which call the id belongs to, so none is
            # attributed rather than one guessed and later evicted wrongly.
            if len(answered) != 1:
                continue
            call = calls[answered[0]["tool_use_id"]]
            if call.get("name") == "Workflow":
                workflow = result.get("workflowName")
                name = ("Workflow %s" % workflow
                        if isinstance(workflow, str) and workflow else "Workflow")
            else:
                name = _subagent_name(call)
            running[task_id] = (name, call)
    return list(running.values())


def _running_background_bash(tail):
    """The tool_use block for the newest still-running background Bash call
    (input.run_in_background True) -- D2 rule 3's `current` for a `shell`
    row. Its tool_result differs from _async_subagents()'s shape: the task
    id sits directly on the row-level toolUseResult as "backgroundTaskId",
    not inside an "async_launched" status. Finish is the same later
    queue-operation row carrying a <task-notification> for that id used
    there. Shapes confirmed read-only against a real local transcript
    2026-09-26. None when nothing is currently running (e.g. the launch
    already scrolled out of the tail)."""
    calls = {}      # tool_use id -> block, for background Bash calls only
    running = {}    # task id -> block, insertion order == launch order
    for row in tail:
        row_type = row.get("type")
        if row_type == "queue-operation":
            content = row.get("content")
            if isinstance(content, str) and TASK_NOTIFICATION_TAG in content:
                task_id = content.partition("<task-id>")[2].partition("</task-id>")[0]
                running.pop(task_id, None)
            continue
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        if row_type == "assistant":
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") == "Bash"):
                    continue
                tool_input = block.get("input")
                if isinstance(tool_input, dict) and tool_input.get("run_in_background") is True:
                    calls[block.get("id")] = block
        elif row_type == "user":
            result = row.get("toolUseResult")
            task_id = result.get("backgroundTaskId") if isinstance(result, dict) else None
            if not isinstance(task_id, str):
                continue
            answered = [block for block in content
                        if isinstance(block, dict) and block.get("type") == "tool_result"
                        and block.get("tool_use_id") in calls]
            # Same one-call-per-row assumption as _async_subagents().
            if len(answered) != 1:
                continue
            running[task_id] = calls[answered[0]["tool_use_id"]]
    return list(running.values())[-1] if running else None


def _claude_subagents(tail):
    """Names of the subagents still running: Agent/Task calls with no
    tool_result yet (a foreground call), then the background launches
    _async_subagents() knows have not reported back."""
    foreground = [_subagent_name(block) for block in _unresolved_tool_uses(tail)
                  if block.get("name") in CLAUDE_SUBAGENT_TOOLS]
    return foreground + [name for name, _ in _async_subagents(tail)]


def _turn_still_pending(row):
    """True when a turn_duration row says the turn ended with background
    work still running -- either of CLAUDE_PENDING_COUNT_KEYS above zero."""
    return any(isinstance(row.get(key), (int, float)) and row[key] > 0
               for key in CLAUDE_PENDING_COUNT_KEYS)


def _launched_task_ids(tail):
    """The task ids (agentId/taskId) of every background Agent/Task/Workflow
    call this tail itself launched, whether or not it has since ended.
    _last_turn_end() needs this to tell "our own background task ended"
    from "some other tail's task notification landed in this one" -- four
    of this session's own nested review-lens subagents' completion notices
    were seen interleaved into the parent session's transcript instead of
    staying in the lens's own (verify 2026-09-26, AC8 live check). Scans
    the same rows _async_subagents() does, but keeps every id it ever saw
    launched instead of dropping the ones a later notification removed."""
    calls = {}
    ids = set()
    for row in tail:
        row_type = row.get("type")
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        if row_type == "assistant":
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") in CLAUDE_BACKGROUND_TOOLS):
                    calls[block.get("id")] = block
        elif row_type == "user":
            result = row.get("toolUseResult")
            if not (isinstance(result, dict)
                    and result.get("status") == ASYNC_LAUNCHED_STATUS):
                continue
            task_id = result.get("agentId") or result.get("taskId")
            if not isinstance(task_id, str):
                continue
            answered = [block for block in content
                        if isinstance(block, dict) and block.get("type") == "tool_result"
                        and block.get("tool_use_id") in calls]
            if len(answered) != 1:
                continue
            ids.add(task_id)
    return ids


def _last_turn_end(tail):
    """The tail's last turn_duration row, but only if the turn it ended is
    still the current one -- walking from the tail backwards, a user/
    assistant row or one of this tail's own background launches ending
    (_task_end, but only for a task id _launched_task_ids() says this tail
    launched) means a newer turn has already started, so None. A
    bookkeeping row, and a completion notice for a task this tail never
    launched, do not end the search -- Claude Code can write a bookkeeping
    row (last-prompt, mode, pr-link, cost-state, ...) between a turn_duration
    and the next user/assistant row without that meaning the turn moved on
    (decisions D2), and a foreign notice is not evidence of anything this
    session did (verify 2026-09-26). Known consequence, not coded around: if
    our own launch fell outside the tail, its notice looks foreign too --
    harmless, because the main session's own next turn (a user/assistant
    row) ends the search anyway."""
    launched_ids = _launched_task_ids(tail)
    for row in reversed(tail):
        row_type = row.get("type")
        if row_type == "system" and row.get("subtype") == "turn_duration":
            return row
        if row_type in ("user", "assistant"):
            return None
        task_id = _task_end(row)
        if task_id is not None and task_id in launched_ids:
            return None
    return None


def _background_pending(tail):
    """V8: only background work counts. Either signal is enough -- the last
    turn_duration still counting pending work, or a background launch
    _async_subagents() has not yet paired with its end."""
    turn_end = _last_turn_end(tail)
    return (turn_end is not None and _turn_still_pending(turn_end)) or bool(_async_subagents(tail))


def _as_background(result, tail, since):
    """Mutates `result` into 「執行中（背景）」: `working`/`inferred` with
    `background: True`, `current` taken from the newest unpaired background
    launch (None if pairing found none, e.g. the launch itself fell out of
    the tail -- decisions D4)."""
    background = _async_subagents(tail)
    current = None
    if background:
        _name, block = background[-1]
        current = {"tool": block.get("name"),
                   "input": _param_summary(block.get("input"), ACTION_INPUT_MAX),
                   "since": since}
    result["current"] = current
    result.update(state="working", certainty="inferred",
                  entryId="working:%s" % since, notes=[], background=True)
    return result


def classify_claude(reg, tail, now_ms):
    """Pure classification of one registry row plus its transcript tail.
    Convention: the returned dict always carries "question", "permission"
    and "current" keys, `None` when not applicable, so a caller never needs
    an `in`-check to read one."""
    since = reg["statusUpdatedAt"]
    status = reg.get("status")
    result = {"since": since, "question": None, "permission": None, "current": None,
             "background": False}

    if status not in KNOWN_CLAUDE_STATUSES:
        result.update(state="unknown", certainty="confirmed",
                      entryId="unknown:%s" % since, notes=[])
        return result

    if status == "waiting":
        waiting_for = reg.get("waitingFor")
        if waiting_for in ESCALATED_WAITING_FOR:
            result.update(state="attention", certainty="confirmed",
                          entryId="attention:%s" % since, notes=[waiting_for])
            return result

        block = _last_unresolved_tool_use(tail)
        if block is not None and block.get("name") == "AskUserQuestion":
            result["question"] = _question_payload(block)
            result.update(state="question", certainty="confirmed",
                          entryId=block.get("id"), notes=[])
            return result
        if block is not None:
            result["permission"] = {
                "tool": block.get("name"),
                "input": _param_summary(block.get("input"), PERMISSION_INPUT_MAX),
            }
            result.update(state="permission", certainty="confirmed",
                          entryId=block.get("id"), notes=[])
            return result

        result.update(state="attention", certainty="confirmed",
                      entryId="attention:%s" % since,
                      notes=[waiting_for if waiting_for else "原因未知"])
        return result

    if status == "idle":
        if _background_pending(tail):
            return _as_background(result, tail, since)
        result.update(state="done", certainty="confirmed",
                      entryId="done:%s" % since, notes=[])
        return result

    if status == "shell":
        # 2026-09-26 correction: Claude writes "shell" when a turn ended with
        # a background Bash still running, and picks the turn back up itself
        # once it finishes -- no human needed, so this is "working".
        block = _running_background_bash(tail)
        if block is not None:
            result["current"] = {
                "tool": "Bash",
                "input": _param_summary(block.get("input"), ACTION_INPUT_MAX,
                                        key_order=_BACKGROUND_BASH_SUMMARY_KEYS),
                "since": since,
            }
        result.update(state="working", certainty="confirmed",
                      entryId="working:%s" % since, notes=["背景 shell 執行中"])
        return result

    # status == "busy"
    if _last_turn_end(tail) is not None and _background_pending(tail):
        return _as_background(result, tail, since)

    last = tail[-1] if tail else None
    # A turn_duration at the tail that still counts pending background work
    # is a turn that ended while a subagent or workflow kept running --
    # Claude keeps the registry at busy on purpose then, so only a turn
    # with nothing pending can mean the registry went stale.
    stale = (isinstance(last, dict) and last.get("type") == "system"
            and last.get("subtype") == "turn_duration"
            and not _turn_still_pending(last)
            and now_ms - since > 60000)
    if stale:
        result.update(state="done", certainty="inferred",
                      entryId="done:%s" % since, notes=["登記檔可能過時"])
        return result

    block = _last_unresolved_tool_use(tail)
    if block is None:
        # Nothing in flight in the foreground: the newest background
        # subagent or workflow still running is what this session waits on.
        background = _async_subagents(tail)
        block = background[-1][1] if background else None
    if block is not None:
        result["current"] = {
            "tool": block.get("name"),
            "input": _param_summary(block.get("input"), ACTION_INPUT_MAX),
            "since": since,
        }
    result.update(state="working", certainty="confirmed",
                  entryId="working:%s" % since, notes=[])
    return result


def _read_registry_file(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read(REGISTRY_READ_MAX)
    except OSError as exc:
        return None, "cannot read %s: %s" % (path, exc)
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except ValueError as exc:
        return None, "unparseable registry file %s: %s" % (path, exc)
    if not isinstance(obj, dict):
        return None, "registry file %s is not a JSON object" % path
    return obj, None


def _unknown_domain_row(reg):
    since = reg.get("statusUpdatedAt")
    return {"key": "claude:%s:%s" % (reg.get("pid"), reg.get("procStart")),
           "platform": "claude", "project": os.path.basename(reg.get("cwd") or ""),
           "cwd": reg.get("cwd"), "sessionId": reg.get("sessionId"), "model": None,
           "state": "unknown", "certainty": "confirmed",
           "entryId": "unknown:%s" % since, "since": since, "notes": [],
           "question": None, "permission": None, "current": None,
           # No liveness check happens for a foreign pidDomain (see
           # _local_pid_domain_match), so no tail is ever read either --
           # D2's fields stay at their defaults, same as any other row with
           # an empty tail.
           "summary": None, "recent": [], "subagents": []}


def _local_pid_domain_match(pid_domain):
    """pidDomain is "<platform>:<hostname>". win32's hostname part must also
    match the local machine's (case-insensitively); other platforms only
    check the platform part -- a registry file from a different machine on
    a shared home directory must not be liveness-checked."""
    platform_part, _, host_part = (pid_domain or "").partition(":")
    if platform_part != sys.platform:
        return False
    if sys.platform == "win32":
        return host_part.lower() == platform.node().lower()
    return True


def claude_rows(config_root, now_ms):
    rows, problems = [], []
    for path in sorted(glob.glob(os.path.join(config_root, "sessions", "*.json"))):
        reg, problem = _read_registry_file(path)
        if reg is None:
            problems.append(problem)
            continue

        kind = reg.get("kind")
        if kind is not None and kind != "interactive":
            continue

        if not _local_pid_domain_match(reg.get("pidDomain")):
            rows.append(_unknown_domain_row(reg))
            continue

        alive = check_alive(reg.get("pid"), reg.get("procStart"), False)
        if alive == "gone":
            continue
        notes = ["存活：推斷"] if alive == "alive-unverified" else []

        transcript_path = usage_collector.session_transcript(
            os.path.join(config_root, "projects"), reg.get("cwd"), reg.get("sessionId"))
        tail = read_tail(transcript_path, TRANSCRIPT_TAIL_MAX) if transcript_path else []

        classified = classify_claude(reg, tail, now_ms)
        classified["notes"] = notes + classified["notes"]
        summary_text = _last_assistant_text(tail)

        row = {"key": "claude:%s:%s" % (reg.get("pid"), reg.get("procStart")),
              "platform": "claude", "project": os.path.basename(reg.get("cwd") or ""),
              "cwd": reg.get("cwd"), "sessionId": reg.get("sessionId"), "model": None,
              "aliveCertainty": "inferred" if alive == "alive-unverified" else "confirmed",
              "summary": _truncate(summary_text, SUMMARY_MAX) if summary_text else None,
              "recent": _recent_claude_actions(tail),
              "subagents": _claude_subagents(tail)}
        row.update(classified)
        rows.append(row)

    return rows, problems


# ================================================= codex_source =========
# Turns a Codex thread (sqlite row, or -- when sqlite is unusable -- a
# rollout file on its own) into zero or one row. classify_codex() is a pure
# function of (turn status, rollout tail, now, tail mtime); codex_rows() is
# the only place that touches sqlite or the filesystem. Two sqlite files are
# involved -- state_*.sqlite (threads) and thread_history_*.sqlite
# (thread_turns) -- each opened, queried and closed within one codex_rows()
# call; no connection is held across calls.

CODEX_ROLLOUT_TAIL_MAX = 262144
CODEX_ROLLOUT_FIRST_LINE_MAX = 65536
CODEX_PERMISSION_THRESHOLD_MS = 30000
CODEX_FALLBACK_MAX_AGE_MS = 24 * 3600 * 1000
CODEX_FALLBACK_MAX_FILES = 200
CODEX_LOCK_DIR = "thread-writer-locks"
CODEX_LOCK_SUFFIX = ".lock"
CODEX_THREAD_ID_LENGTH = 36


def _codex_event_time_ms(item, tail_mtime_ms):
    ts = item.get("timestamp")
    parsed = _parse_iso_ms(ts) if isinstance(ts, str) else None
    return parsed if parsed is not None else tail_mtime_ms


def _last_task_started_index(tail):
    idx = None
    for i, item in enumerate(tail):
        if item.get("type") != "event_msg":
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "task_started":
            idx = i
    return idx


def _codex_in_progress(turn_status, tail):
    """(in_progress, certainty). A known turn_status is authoritative
    ("confirmed"); otherwise infer from the tail's last task_started vs.
    last task_complete event_msg, in file order ("inferred")."""
    if turn_status is not None:
        return turn_status == "inProgress", "confirmed"

    started_idx = _last_task_started_index(tail)
    complete_idx = None
    for i, item in enumerate(tail):
        if item.get("type") != "event_msg":
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "task_complete":
            complete_idx = i
    if started_idx is None:
        return False, "inferred"
    return (complete_idx is None or started_idx > complete_idx), "inferred"


def _unresolved_function_calls(tail):
    """response_item/function_call entries (payload.type == "function_call")
    with no matching function_call_output (matched by call_id) appearing
    later in the tail, in tail order."""
    unresolved = []
    for i, item in enumerate(tail):
        payload = item.get("payload")
        if item.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "function_call":
            continue
        call_id = payload.get("call_id")
        resolved = False
        for later in tail[i + 1:]:
            later_payload = later.get("payload")
            if (later.get("type") == "response_item" and isinstance(later_payload, dict)
                    and later_payload.get("type") == "function_call_output"
                    and later_payload.get("call_id") == call_id):
                resolved = True
                break
        if not resolved:
            unresolved.append(item)
    return unresolved


def _parse_json_object(text):
    """A function_call's `arguments` field is a JSON-encoded string
    (confirmed 2026-09-25, same batch as the rest of D2); {} for anything
    that doesn't decode to a JSON object, so every caller can just .get()."""
    if not isinstance(text, str):
        return {}
    try:
        obj = json.loads(text)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def classify_codex(turn_status, tail, now_ms, tail_mtime_ms):
    """Pure classification of one Codex thread's turn status plus rollout
    tail. Mirrors classify_claude()'s convention: always returns
    question/permission/current keys (None when not applicable).

    entryId scheme (judgement call -- the design pins the in-progress
    question/permission cases to the triggering function_call's call_id, but
    is silent on the "done turn with a dangling request_user_input_async"
    case, where there may be no unresolved call_id to anchor on since
    presence anywhere in the last turn is what matters, not resolution):
    that case uses "question:<turn_status or 'done'>:<tail_mtime_ms>",
    deterministic per (status, file state) the same way classify_claude's
    "done:%s" % since is deterministic per registry state.
    """
    in_progress, in_progress_certainty = _codex_in_progress(turn_status, tail)
    result = {"question": None, "permission": None, "current": None}

    if not tail:
        result.update(since=tail_mtime_ms, state="unknown", certainty="confirmed",
                      entryId="unknown:%d" % tail_mtime_ms, notes=[])
        return result

    if in_progress:
        unresolved = _unresolved_function_calls(tail)
        call_item = unresolved[-1] if unresolved else None
        if call_item is not None:
            payload = call_item.get("payload", {})
            name = payload.get("name")
            call_id = payload.get("call_id")
            event_time = _codex_event_time_ms(call_item, tail_mtime_ms)
            if name == "request_user_input":
                # D2 rule 4 -- decode arguments (a JSON string) the same
                # way Claude's AskUserQuestion tool_use.input is read;
                # request_user_input's "questions" shape is identical.
                args = _parse_json_object(payload.get("arguments"))
                result["question"] = _question_payload({"input": args})
                result.update(since=event_time, state="question", certainty="confirmed",
                              entryId=call_id, notes=[])
                return result
            if now_ms - event_time > CODEX_PERMISSION_THRESHOLD_MS:
                result["permission"] = {"tool": name}
                result.update(since=event_time, state="permission", certainty="inferred",
                              entryId=call_id, notes=[])
                return result
        result.update(since=tail_mtime_ms, state="working", certainty=in_progress_certainty,
                      entryId="working:%d" % tail_mtime_ms, notes=[])
        return result

    # Not in progress: a dangling request_user_input_async anywhere in the
    # last turn (resolved or not -- presence is what matters here).
    started_idx = _last_task_started_index(tail)
    last_turn = tail[started_idx:] if started_idx is not None else tail
    async_calls = [
        item for item in last_turn
        if item.get("type") == "response_item"
        and isinstance(item.get("payload"), dict)
        and item["payload"].get("type") == "function_call"
        and item["payload"].get("name") == "request_user_input_async"]
    if async_calls:
        # D2 rule 4, same decode as the in-progress/sync case above; the
        # last dangling call in the turn is the one still open.
        args = _parse_json_object(async_calls[-1].get("payload", {}).get("arguments"))
        result["question"] = _question_payload({"input": args})
        result.update(since=tail_mtime_ms, state="question", certainty="confirmed",
                      entryId="question:%s:%d" % (turn_status or "done", tail_mtime_ms),
                      notes=[])
        return result

    notes = ["上一輪 failed／interrupted"] if turn_status in ("failed", "interrupted") else []
    result.update(since=tail_mtime_ms, state="done", certainty="confirmed",
                  entryId="done:%s:%d" % (turn_status or "done", tail_mtime_ms), notes=notes)
    return result


def _sqlite_uri(path):
    return "file:%s?mode=ro" % path.replace("\\", "/")


def _highest_numbered_sqlite(codex_home, prefix):
    best_path, best_n = None, -1
    for path in glob.glob(os.path.join(codex_home, prefix + "_*.sqlite")):
        stem = os.path.basename(path)[:-len(".sqlite")]
        try:
            n = int(stem.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            continue
        if n > best_n:
            best_n, best_path = n, path
    return best_path


# ---- D2 rule 1 (做完的摘要) and rule 2 (最近 8 筆動作), Codex side. Key
# names (response_item/message/role/content[].type == "output_text"/"text";
# function_call's own "cmd" argument key) confirmed read-only against real
# local Codex data, verify round 2 2026-09-25; no conversation content
# copied anywhere.

def _last_assistant_text_codex(tail):
    """The last response_item/message with role == "assistant", its
    output_text content block(s) joined with "\\n". None if that message
    (if any) carries no output_text block."""
    for item in reversed(tail):
        payload = item.get("payload")
        if item.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "message" or payload.get("role") != "assistant":
            continue
        content = payload.get("content")
        if not isinstance(content, list):
            return None
        texts = [block["text"] for block in content
                if isinstance(block, dict) and block.get("type") == "output_text"
                and isinstance(block.get("text"), str)]
        return "\n".join(texts) if texts else None
    return None


def _recent_codex_actions(tail, tail_mtime_ms):
    """The last RECENT_ACTIONS_LIMIT response_item/function_call entries,
    oldest of the kept ones first -- mirrors _recent_claude_actions()."""
    calls = []
    for item in tail:
        payload = item.get("payload")
        if item.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "function_call":
            continue
        args = _parse_json_object(payload.get("arguments"))
        calls.append({"at": _codex_event_time_ms(item, tail_mtime_ms),
                      "tool": payload.get("name"),
                      "input": _param_summary(args, RECENT_ACTION_INPUT_MAX)})
    return calls[-RECENT_ACTIONS_LIMIT:]


# ---- D2 rule 3 (subagent), Codex side, no-sqlite fallback. spawn_agent's
# own "agent_type" argument key confirmed read-only 2026-09-25 against real
# local rollout data that actually called it. The primary (sqlite) path
# overrides this with thread_spawn_edges instead -- see
# _codex_subagents_by_parent() -- which is authoritative when it's there.

CODEX_SUBAGENT_TOOL = "spawn_agent"


def _codex_tail_subagents(tail):
    names = []
    for item in _unresolved_function_calls(tail):
        payload = item.get("payload", {})
        if payload.get("name") != CODEX_SUBAGENT_TOOL:
            continue
        args = _parse_json_object(payload.get("arguments"))
        name = args.get("agent_type")
        names.append(name if isinstance(name, str) and name else CODEX_SUBAGENT_TOOL)
    return names


# ---- Codex aliveness by lock filename (V9, diagnosis's Fix): a Codex TUI
# holds a writer lock on its own thread for as long as it's open, so the
# lock directory's filenames are the set of thread ids actually alive right
# now -- no process count, no "most recently updated" guess. Only the
# directory is listed, never a lock file's contents (V1, V9).

def codex_locked_thread_ids(codex_home):
    """The set of thread ids with an open writer lock under
    `codex_home`/thread-writer-locks/, or None if that directory cannot be
    listed (missing, not a directory, no permission)."""
    lock_dir = os.path.join(codex_home, CODEX_LOCK_DIR)
    try:
        names = os.listdir(lock_dir)
    except OSError:
        return None
    ids = set()
    for name in names:
        if name.startswith(".") or not name.endswith(CODEX_LOCK_SUFFIX):
            continue
        stem = name[:-len(CODEX_LOCK_SUFFIX)]
        if len(stem) == CODEX_THREAD_ID_LENGTH:
            ids.add(stem)
    return ids


def _codex_row(thread_id, cwd, name, alive_certainty, turn_status, rollout_path, now_ms):
    tail = read_tail(rollout_path, CODEX_ROLLOUT_TAIL_MAX)
    try:
        tail_mtime_ms = int(os.stat(rollout_path).st_mtime * 1000)
    except OSError:
        tail_mtime_ms = now_ms

    classified = classify_codex(turn_status, tail, now_ms, tail_mtime_ms)
    summary_text = _last_assistant_text_codex(tail)
    row = {"key": "codex:%s" % thread_id, "platform": "codex",
          "project": os.path.basename(cwd or ""), "cwd": cwd,
          "sessionId": thread_id, "name": name, "aliveCertainty": alive_certainty,
          "summary": _truncate(summary_text, SUMMARY_MAX) if summary_text else None,
          "recent": _recent_codex_actions(tail, tail_mtime_ms),
          "subagents": _codex_tail_subagents(tail)}
    row.update(classified)
    return row


def _codex_subagents_by_parent(state_conn, thread_ids):
    """D2 rule 3, Codex primary (sqlite) path -- open (still running) child
    threads per parent thread id, named from threads.name (falls back to
    the child's own id when unnamed). thread_spawn_edges' columns
    (parent_thread_id, child_thread_id, status) and its only status seen
    locally ("open") were confirmed read-only 2026-09-25 (verify round 2).
    Catches OperationalError on its own (not the broader sqlite3.Error the
    caller already catches) so an older Codex schema without this table
    degrades to "no subagents data", not a fall-all-the-way-back to the
    no-sqlite path."""
    if not thread_ids:
        return {}
    placeholders = ",".join("?" * len(thread_ids))
    try:
        edges = state_conn.execute(
            "SELECT parent_thread_id, child_thread_id FROM thread_spawn_edges "
            "WHERE status = 'open' AND parent_thread_id IN (%s)" % placeholders,
            thread_ids).fetchall()
    except sqlite3.OperationalError:
        return {}
    child_ids = sorted({child_id for _parent_id, child_id in edges})
    names_by_child = {}
    if child_ids:
        child_placeholders = ",".join("?" * len(child_ids))
        names_by_child = dict(state_conn.execute(
            "SELECT id, name FROM threads WHERE id IN (%s)" % child_placeholders,
            child_ids).fetchall())
    result = {}
    for parent_id, child_id in edges:
        result.setdefault(parent_id, []).append(names_by_child.get(child_id) or child_id)
    return result


def _codex_rows_primary(state_db, history_db, now_ms, locked_ids):
    state_conn = sqlite3.connect(_sqlite_uri(state_db), uri=True)
    try:
        placeholders = ",".join("?" * len(locked_ids))
        threads = state_conn.execute(
            "SELECT id, rollout_path, cwd, updated_at_ms, name FROM threads "
            "WHERE archived = 0 AND originator = 'codex-tui' AND thread_source = 'user' "
            "AND id IN (%s) ORDER BY updated_at_ms DESC" % placeholders,
            sorted(locked_ids)).fetchall()
        subagents_by_parent = _codex_subagents_by_parent(state_conn, [t[0] for t in threads])
    finally:
        state_conn.close()

    history_conn = sqlite3.connect(_sqlite_uri(history_db), uri=True)
    try:
        turn_status_by_thread = {}
        for thread_id, _rollout_path, _cwd, _updated_at_ms, _name in threads:
            row = history_conn.execute(
                "SELECT status FROM thread_turns WHERE thread_id = ? "
                "ORDER BY started_at DESC LIMIT 1", (thread_id,)).fetchone()
            turn_status_by_thread[thread_id] = row[0] if row else None
    finally:
        history_conn.close()

    rows = []
    for thread_id, rollout_path, cwd, _updated_at_ms, name in threads:
        row = _codex_row(thread_id, cwd, name, "inferred",
                         turn_status_by_thread.get(thread_id), rollout_path, now_ms)
        # sqlite is authoritative here, same as turn_status above -- replace
        # the tail-derived fallback subagents list with the real one.
        row["subagents"] = subagents_by_parent.get(thread_id, [])
        rows.append(row)
    return rows, []


def _codex_rows_fallback(codex_home, now_ms, locked_ids):
    rows, problems = [], []
    cutoff_ms = now_ms - CODEX_FALLBACK_MAX_AGE_MS

    candidates = []
    for path in glob.glob(os.path.join(codex_home, "sessions", "**", "rollout-*.jsonl"),
                          recursive=True):
        try:
            mtime_ms = int(os.stat(path).st_mtime * 1000)
        except OSError as exc:
            problems.append("cannot stat %s: %s" % (path, exc))
            continue
        if mtime_ms < cutoff_ms:
            continue
        stem = os.path.basename(path)
        if stem.endswith(".jsonl"):
            stem = stem[:-len(".jsonl")]
        thread_id = stem[-36:]
        if thread_id not in locked_ids:
            continue
        candidates.append((path, mtime_ms, thread_id))
    candidates.sort(key=lambda entry: entry[1], reverse=True)
    candidates = candidates[:CODEX_FALLBACK_MAX_FILES]

    for path, _mtime_ms, thread_id in candidates:
        meta = read_first_line(path, CODEX_ROLLOUT_FIRST_LINE_MAX)
        if meta is None:
            problems.append("unparseable rollout %s" % path)
            continue
        payload = meta.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if payload.get("originator") != "codex-tui" or payload.get("thread_source") != "user":
            continue
        row = _codex_row(thread_id, payload.get("cwd"), None, "inferred", None, path, now_ms)
        row["certainty"] = "inferred"
        rows.append(row)

    return rows, problems


def codex_rows(codex_home, now_ms, locked_ids):
    """locked_ids (codex_locked_thread_ids()'s return) is the set of thread
    ids with an open writer lock right now -- None or empty means no Codex
    row at all, without opening any sqlite file."""
    if not locked_ids:
        return [], []

    state_db = _highest_numbered_sqlite(codex_home, "state")
    history_db = _highest_numbered_sqlite(codex_home, "thread_history")

    if state_db is not None and history_db is not None:
        try:
            return _codex_rows_primary(state_db, history_db, now_ms, locked_ids)
        except sqlite3.Error:
            pass

    rows, problems = _codex_rows_fallback(codex_home, now_ms, locked_ids)
    return rows, ["Codex 資料庫讀不了，改看紀錄檔"] + problems


# ================================================== cai_mapper ==========
# Maps a row's (cwd, sessionId) to the cai track it belongs to, and that
# track's six-stage status. find_track() is the only entry point; it does
# its own I/O (state.md, ledger.jsonl, the `current` file) but caches
# nothing itself -- a poller-level cache, if one is ever needed, wraps calls
# to this function instead of being built into it.

TRACK_ROOT_SEARCH_LEVELS = 20


def _find_track_root(cwd):
    """Walk upward from `cwd` (itself included) up to
    TRACK_ROOT_SEARCH_LEVELS parents, looking for a directory that contains
    a `.claude/track` subdirectory. Returns that `.claude/track` path, or
    None if not found within the budget."""
    candidate = cwd
    for _ in range(TRACK_ROOT_SEARCH_LEVELS):
        track_root = os.path.join(candidate, ".claude", "track")
        if os.path.isdir(track_root):
            return track_root
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return None


def _track_names(track_root):
    return sorted(n for n in os.listdir(track_root)
                  if n != "done" and os.path.isdir(os.path.join(track_root, n)))


def _find_by_session_id(track_root, session_id):
    """The one track directory whose ledger has a record naming this
    session_id, or None if no track matches (including session_id is None,
    or the match is ambiguous across more than one track)."""
    if session_id is None:
        return None
    matches = []
    for name in _track_names(track_root):
        track_dir = os.path.join(track_root, name)
        for record in ledger.records(track_dir):
            if not record.get("malformed") and record.get("session_id") == session_id:
                matches.append(name)
                break
    if len(matches) == 1:
        return matches[0]
    return None


def _build_stages(track_dir):
    stages = []
    for sid in track_state.stage_ids():
        try:
            row = preflight.state_row(track_dir, sid)
        except OSError:
            row = None
        status = row[1] if row and len(row) > 1 else ""
        stages.append({"id": sid, "status": status})
    return stages


def _current_stage(stages):
    for stage in stages:
        if stage["status"] not in ("done", "skipped"):
            return stage["id"]
    return None


def _gate_waiting(stages, current):
    by_id = {s["id"]: s["status"] for s in stages}
    if by_id.get("design") == "done" and by_id.get("build") == "":
        return "build"
    if current == "ship":
        return "ship"
    return None


def find_track(cwd, session_id):
    track_root = _find_track_root(cwd)
    if track_root is None:
        return None

    name = _find_by_session_id(track_root, session_id)
    certainty = "confirmed"
    if name is None:
        certainty = "inferred"
        feature = track_state.current_feature(track_root)
        if not feature:
            return None
        if not os.path.isdir(os.path.join(track_root, feature)):
            return None
        name = feature

    track_dir = os.path.join(track_root, name)
    stages = _build_stages(track_dir)
    current = _current_stage(stages)
    gate_waiting = _gate_waiting(stages, current)

    return {"name": name, "certainty": certainty, "stages": stages,
           "current": current, "gateWaiting": gate_waiting}


# ================================================================poller====
# Assembles a fresh snapshot every SERVER_POLL_INTERVAL_S seconds and checks
# this instance against whatever the state file currently names -- the
# mechanism that makes "two instances started at once" converge to one.

SERVER_POLL_INTERVAL_S = 2
EMPTY_SNAPSHOT = {"format": 1, "generatedAt": 0, "rows": [], "problems": []}


def _codex_home():
    home = os.environ.get("CODEX_HOME")
    return home if home else os.path.expanduser("~/.codex")


def _git_head_branch(git_dir):
    try:
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    if not text.startswith(prefix):
        return None
    return text[len(prefix):].strip() or None


def branch_for_cwd(cwd):
    """The current branch name for `cwd`'s git checkout, or None on any
    failure -- missing .git, detached HEAD, permission error, worktree
    pointer that doesn't resolve. Never raises."""
    if not cwd:
        return None
    git_path = os.path.join(cwd, ".git")
    try:
        if os.path.isdir(git_path):
            return _git_head_branch(git_path)
        if os.path.isfile(git_path):
            with open(git_path, encoding="utf-8") as fh:
                content = fh.read().strip()
            prefix = "gitdir: "
            if not content.startswith(prefix):
                return None
            real_git_dir = content[len(prefix):].strip()
            if not os.path.isabs(real_git_dir):
                real_git_dir = os.path.join(cwd, real_git_dir)
            return _git_head_branch(real_git_dir)
    except OSError:
        return None
    return None


def build_snapshot(config_root, codex_home, now_ms):
    """Pure assembly of one snapshot from the pieces units 2-4 already
    built. Can raise on a truly unexpected bug -- the caller (Poller.run())
    is the safety net that keeps the previous snapshot on failure, not this
    function."""
    claude_list, claude_problems = claude_rows(config_root, now_ms)
    locked_ids = codex_locked_thread_ids(codex_home)
    codex_list, codex_problems = codex_rows(codex_home, now_ms, locked_ids)
    problems = claude_problems + codex_problems

    rows = claude_list + codex_list
    for row in rows:
        row["branch"] = branch_for_cwd(row.get("cwd"))
        # summary/recent/subagents (D2) are claude_rows()/codex_rows()'s own
        # job now (see their D2 sections) -- build_snapshot only adds
        # branch/track, it does not touch them.
        cwd = row.get("cwd")
        if not cwd:
            row["track"] = None
        elif row["platform"] == "claude":
            row["track"] = find_track(cwd, row.get("sessionId"))
        else:
            row["track"] = find_track(cwd, None)

    codex_lock_dir_missing = locked_ids is None and os.path.isdir(codex_home)
    return {"format": 1, "generatedAt": now_ms, "rows": rows, "problems": problems,
           "codexLockDirMissing": codex_lock_dir_missing}


class Poller(threading.Thread):
    """Deviation from the design's verbatim constructor: `own_port`/
    `own_token` are added as two extra trailing parameters. The design's
    self-check spec requires reclaiming the state file with "this
    instance's own ... port/token" when the file names a dead pid, but the
    five-argument signature it also specifies has no way to know either
    value -- cmd_serve is the only real caller and always supplies both."""

    def __init__(self, config_root, codex_home, state_path, own_pid,
                on_superseded, own_port=None, own_token=None):
        super(Poller, self).__init__(daemon=True)
        self.config_root = config_root
        self.codex_home = codex_home
        self.state_path = state_path
        self.own_pid = own_pid
        self.on_superseded = on_superseded
        self.own_port = own_port
        self.own_token = own_token
        self._lock = threading.Lock()
        self._snapshot_bytes = json.dumps(EMPTY_SNAPSHOT).encode("utf-8")
        # Not `_stop`: Python 3.12's Thread.join() calls self._stop().
        self._stop_event = threading.Event()

    def snapshot(self):
        with self._lock:
            return self._snapshot_bytes

    def stop(self):
        self._stop_event.set()

    def _self_check(self):
        """True to keep polling, False if this instance was just told to
        stop (state file absent, or another pid is confirmed alive there)."""
        state = read_state(self.state_path)
        if state is None:
            self.on_superseded()
            return False
        if state["pid"] == self.own_pid:
            return True
        if check_alive(state["pid"], state.get("procStart"), True) != "gone":
            self.on_superseded()
            return False
        # The named pid is gone -- reclaim the file for this instance.
        write_state(self.state_path, {
            "format": 1, "pid": self.own_pid,
            "procStart": process_start(self.own_pid), "port": self.own_port,
            "token": self.own_token, "startedAt": int(time.time() * 1000)})
        return True

    def run(self):
        while not self._stop_event.is_set():
            if not self._self_check():
                return
            try:
                snap = build_snapshot(self.config_root, self.codex_home,
                                      int(time.time() * 1000))
                encoded = json.dumps(snap).encode("utf-8")
            except Exception as exc:
                with self._lock:
                    prev = json.loads(self._snapshot_bytes.decode("utf-8"))
                # Replace, not append: a sustained failure must report only
                # the current cycle's problem, not grow forever.
                prev["problems"] = ["poller error: %s" % exc]
                encoded = json.dumps(prev).encode("utf-8")
            with self._lock:
                self._snapshot_bytes = encoded
            self._stop_event.wait(SERVER_POLL_INTERVAL_S)


# =============================================================launcher====

def spawn_server(port):
    args = [sys.executable, os.path.abspath(__file__), "serve", "--port", str(port)]
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, cwd=tempfile.gettempdir(),
                 close_fds=True)
    if os.name == "nt":
        DETACHED_PROCESS = 0x8
        CREATE_NEW_PROCESS_GROUP = 0x200
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        try:
            return subprocess.Popen(
                args, creationflags=(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                                     | CREATE_BREAKAWAY_FROM_JOB), **kwargs)
        except OSError:
            return subprocess.Popen(
                args, creationflags=(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP),
                **kwargs)
    return subprocess.Popen(args, start_new_session=True, **kwargs)


def _get_identity(port, token, timeout):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/identity" % port, headers={TOKEN_HEADER: token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _post_shutdown(port, token, timeout):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/shutdown" % port, method="POST", data=b"",
        headers={TOKEN_HEADER: token})
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        pass  # 202, non-202, refused, or timeout all proceed the same way.


def _wait_for_gone(pid, proc_start, timeout_s):
    deadline = time.time() + timeout_s
    status = check_alive(pid, proc_start, True)
    while status != "gone" and time.time() < deadline:
        time.sleep(READY_POLL_S)
        status = check_alive(pid, proc_start, True)
    return status


def _start_new_server(port):
    try:
        child = spawn_server(port)
    except OSError as exc:
        print("error: %s" % exc)
        return 1

    deadline = time.time() + READY_TIMEOUT_S
    while True:
        state = read_state(state_path())
        if state is not None and state["pid"] == child.pid:
            print("Agent Viewer: http://127.0.0.1:%d" % state["port"])
            print("started (pid %d)" % state["pid"])
            return 0
        if child.poll() is not None:
            if child.returncode == 3:
                print("error: ports %d-%d are all in use"
                     % (port, port + PORT_TRIES - 1))
                return 1
            break
        if time.time() >= deadline:
            break
        time.sleep(READY_POLL_S)

    print("error: the viewer did not come up within 5 seconds")
    return 1


def cmd_start(port=DEFAULT_PORT):
    path = state_path()
    state = read_state(path)
    if state is None:
        return _start_new_server(port)

    identity = _get_identity(state["port"], state["token"], IDENTITY_TIMEOUT_S)
    if identity is None or identity.get("pid") != state["pid"]:
        return _start_new_server(port)

    if identity.get("format") != 1:
        print("Agent Viewer: http://127.0.0.1:%d" % state["port"])
        print("a different viewer version is running (pid %d); run stop, "
             "then start again" % state["pid"])
        return 0

    if check_alive(state["pid"], state.get("procStart"), True) == "gone":
        return _start_new_server(port)

    print("Agent Viewer: http://127.0.0.1:%d" % state["port"])
    print("already running (pid %d)" % state["pid"])
    return 0


def cmd_stop():
    path = state_path()
    state = read_state(path)
    if state is None:
        print("not running")
        return 0

    pid, proc_start, port = state["pid"], state.get("procStart"), state["port"]

    if check_alive(pid, proc_start, True) == "gone":
        remove_state(path, pid)
        print("Agent Viewer: http://127.0.0.1:%d" % port)
        print("not running (removed a stale state file)")
        return 0

    _post_shutdown(port, state["token"], SHUTDOWN_TIMEOUT_S)

    status = _wait_for_gone(pid, proc_start, STOP_WAIT_S)
    if status == "alive-unverified":
        print("error: could not stop pid %d" % pid)
        return 1
    if status != "gone":
        # status == "alive": this is ending our own server process, just
        # confirmed ours by pid+creation-time match -- not a liveness
        # probe, so V2 does not apply here.
        os.kill(pid, signal.SIGTERM)
        status = _wait_for_gone(pid, proc_start, STOP_KILL_WAIT_S)
        if status != "gone":
            print("error: could not stop pid %d" % pid)
            return 1

    remove_state(path, pid)
    print("Agent Viewer: http://127.0.0.1:%d" % port)
    print("stopped (pid %d)" % pid)
    return 0


def cmd_serve(port):
    token = secrets.token_hex(32)

    server, bound_port = None, None
    for candidate in range(port, port + PORT_TRIES):
        try:
            server = ViewerServer(("127.0.0.1", candidate), Handler)
        except OSError:
            continue
        bound_port = candidate
        break
    if server is None:
        return 3
    server.token = token

    state = {"format": 1, "pid": os.getpid(),
            "procStart": process_start(os.getpid()), "port": bound_port,
            "token": token, "startedAt": int(time.time() * 1000)}
    try:
        write_state(state_path(), state)
    except OSError:
        server.server_close()
        return 2

    poller = Poller(usage_collector.config_root(), _codex_home(), state_path(),
                    os.getpid(), server.shutdown, bound_port, token)
    server.poller = poller
    poller.start()

    try:
        server.serve_forever()
    finally:
        poller.stop()
        remove_state(state_path(), os.getpid())
    return 0


def _parse_port(args):
    """The one optional flag start/serve take. Not a general argparse
    surface -- viewer.py's whole grammar is three fixed commands, so a
    hand-rolled parser says exactly what main()'s spec says and no more."""
    if not args:
        return DEFAULT_PORT, True
    if len(args) == 2 and args[0] == "--port":
        try:
            return int(args[1]), True
        except ValueError:
            return None, False
    return None, False


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:  # Python < 3.7
        pass

    if not argv or argv[0] == "start":
        port, ok = _parse_port(argv[1:] if argv else [])
        if not ok:
            print(USAGE)
            return 1
        return cmd_start(port)

    if argv == ["stop"]:
        return cmd_stop()

    if argv[0] == "serve":
        port, ok = _parse_port(argv[1:])
        if not ok:
            print(USAGE)
            return 1
        return cmd_serve(port)

    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
