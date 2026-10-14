: << 'CMDBLOCK'
@echo off
REM Polyglot launcher: CMD.exe runs this block, POSIX shells swallow it as a
REM heredoc and fall through to the sh section below. Needed because Claude Code
REM runs hook commands under CMD.exe on Windows and sh on macOS/Linux, and the
REM Python interpreter is named differently on each (py or python vs python3).
REM
REM One call ends one of three ways, and never in an unchecked pass.
REM Healthy: the interpreter recorded under the Claude config directory runs
REM bash_guard.py on the hook input and its 0 or 2 is passed on. Failed: that
REM interpreter exits with anything else once it has the real input, so this
REM call is blocked for every caller and the record is dropped unless the
REM interpreter still runs the guard on empty input. Degraded: no candidate
REM runs the guard, so a pattern file checks the untouched input instead.
REM Write mode (Write, Edit, NotebookEdit) is the exception: a failed call, or a
REM write pattern file that cannot be read, is let through with exit 1; a
REM degraded call the file does not match passes silently, as here; only a
REM subagent's write to ledger.jsonl or to the guard's launcher record that
REM the file matches is blocked.
REM
REM Exit codes are compared as strings, never with errorlevel tests: those mean
REM greater or equal, and a negative Windows exit code would read as success.
REM The line that reads the exit code stays outside any parenthesised block,
REM otherwise CMD expands it at parse time. Nothing here uses a block at all,
REM since a config directory like Program Files (x86) holds a closing bracket.
REM
REM Probing sends empty input (nul) so the hook input on stdin is read exactly
REM once, by the guard or by the reduced check. Every interpreter is started
REM with call so control comes back here and exit 2 can still be decided.

set "GUARD=%~dp0..\scripts\bash_guard.py"
set "WRITER=%~dp0record_launcher.py"
set "PATTERNS=%~dp0reduced-check-patterns.txt"
REM hooks.json passes agent for Agent calls: a prompt is not a command, so the
REM reduced check only looks for the verifier there (#277).
if "%~1"=="agent" set "PATTERNS=%~dp0reduced-check-agent-patterns.txt"
REM hooks.json passes write for Write, Edit and NotebookEdit calls. A broken
REM interpreter must not stop every file write of a session, so write mode lets
REM a failed call through (exit 1, hook error), and its pattern file knows only
REM a subagent's write to ledger.jsonl or to the guard's launcher record.
set "WRITEMODE="
REM Case folding avoids FINDSTR's compiled-pattern limit on long record names.
set "SCANCASE="
if "%~1"=="write" set "WRITEMODE=1"
if "%~1"=="write" set "SCANCASE=/I"
if "%~1"=="write" set "PATTERNS=%~dp0reduced-check-write-patterns.txt"
if not defined CLAUDE_CONFIG_DIR goto defaultroot
set "REC=%CLAUDE_CONFIG_DIR%\cai\guard-launcher-cmd.txt"
goto haveroot
:defaultroot
set "REC=%USERPROFILE%\.claude\cai\guard-launcher-cmd.txt"
:haveroot

call :readrecord
if defined LAUNCHER goto runrecord

REM No record: probe each candidate. The variable below keeps a py stand-in in
REM the current directory from being found first, and only lives until endlocal.
setlocal
set "NoDefaultCurrentDirectoryInExePath=1"
set "CAI_GUARD_RECORD=%REC%"
set "CAND=py -3"
call :probeone
if "%RESULT%"=="failed" set "CAND=python"
if "%RESULT%"=="failed" call :probeone
endlocal & set "RESULT=%RESULT%" & set "CAND=%CAND%"
if "%RESULT%"=="written" goto afterwrite
if "%RESULT%"=="nowrite" goto runbyname
goto reduced

:afterwrite
call :readrecord
if defined LAUNCHER goto runrecord
goto runbyname

:runrecord
if not "%KIND%"=="path" goto runlauncher
if exist "%LAUNCHER%" goto runlauncher
del "%REC%" >nul 2>nul
if defined WRITEMODE goto reduced
>&2 echo cai guard launcher failed: %LAUNCHER% no longer exists, record dropped. This call is blocked for every caller, the next call probes again.
exit /b 2

:runlauncher
if "%KIND%"=="path" call "%%LAUNCHER%%" "%%GUARD%%" %*
if "%KIND%"=="name" call %%LAUNCHER%% "%%GUARD%%" %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
if "%RC%"=="2" exit /b 2
REM Any other code: is it this input or the launcher? Ask the guard once more
REM with empty input, which it answers 0 whenever it runs at all.
if "%KIND%"=="path" call "%%LAUNCHER%%" "%%GUARD%%" <nul >nul 2>nul
if "%KIND%"=="name" call %%LAUNCHER%% "%%GUARD%%" <nul >nul 2>nul
set "AGAIN=%ERRORLEVEL%"
if "%AGAIN%"=="0" goto keeprecord
del "%REC%" >nul 2>nul
if defined WRITEMODE goto writedropped
>&2 echo cai guard launcher failed: %LAUNCHER% exited %RC% on this input, record dropped. This call is blocked for every caller, the next call probes again.
exit /b 2
:keeprecord
if defined WRITEMODE goto writekept
>&2 echo cai guard launcher failed: %LAUNCHER% exited %RC% on this input but still runs the guard on empty input, record kept. This call is blocked for every caller.
exit /b 2

REM The record could not be written (or a concurrent call dropped it), but the
REM candidate ran the guard a moment ago: run it by name, as before records.
:runbyname
call %%CAND%% "%%GUARD%%" %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
if "%RC%"=="2" exit /b 2
if defined WRITEMODE goto writebyname
>&2 echo cai guard launcher failed: %CAND% exited %RC% on this input, nothing was recorded. This call is blocked for every caller, the next call probes again.
exit /b 2

REM Nothing runs the guard, and nothing has read stdin. findstr exits 1 for no
REM match; a match blocks. findstr exits 2 when it cannot open the pattern file,
REM which also happens while another call's findstr has it open. It fails before
REM reading stdin, so wait a second and ask again, up to three more times, and
REM block only if it still cannot. The retries are straight lines, not a loop:
REM validate.py models only forward jumps.
:reduced
call :scan
if "%RC%"=="2" call :scanwait
if "%RC%"=="2" call :scanwait
if "%RC%"=="2" call :scanwait
if "%RC%"=="1" exit /b 0
if defined WRITEMODE goto writeverdict
>&2 echo cai guard reduced check: no working Python 3 was found, so only force push, reset --hard, git clean -f, --no-verify, rm -rf, gh pr merge and the scoped agents are checked. This call is blocked.
exit /b 2

REM Write mode ends here. A match blocks; a scan that itself failed is no
REM verdict, so the call goes through with exit 1 and shows a hook error.
:writeverdict
if not "%RC%"=="0" goto writepass
>&2 echo cai guard reduced check: the Python guard did not run, so only a subagent's write to ledger.jsonl or to the guard's launcher record is checked. This call is blocked.
exit /b 2
:writepass
>&2 echo cai guard reduced check: the Python guard did not run and the write pattern file could not be read, so this call is let through without the ledger check.
exit /b 1
:writedropped
>&2 echo cai guard launcher failed: %LAUNCHER% exited %RC% on this input, record dropped. Write mode: this call is let through without the ledger check, the next call probes again.
exit /b 1
:writekept
>&2 echo cai guard launcher failed: %LAUNCHER% exited %RC% on this input but still runs the guard on empty input, record kept. Write mode: this call is let through without the ledger check.
exit /b 1
:writebyname
>&2 echo cai guard launcher failed: %CAND% exited %RC% on this input, nothing was recorded. Write mode: this call is let through without the ledger check, the next call probes again.
exit /b 1

:scanwait
ping -n 2 127.0.0.1 >nul 2>nul
:scan
findstr /R %SCANCASE% /G:"%PATTERNS%" >nul 2>nul
set "RC=%ERRORLEVEL%"
goto :eof

REM Step 1: the candidate must run the guard on empty input and exit 0. Step 2:
REM it runs the record writer, which exits 0 (written), 73 (cannot write) or
REM anything else (failed). RESULT is failed, nowrite or written.
:probeone
set "RESULT=failed"
call %%CAND%% "%%GUARD%%" <nul >nul 2>nul
if not "%ERRORLEVEL%"=="0" goto :eof
call %%CAND%% "%%WRITER%%" cmd "%%CAND%%" <nul >nul 2>nul
set "RC=%ERRORLEVEL%"
if "%RC%"=="73" set "RESULT=nowrite"
if not "%RC%"=="0" goto :eof
call :readrecord
if defined LAUNCHER set "RESULT=written"
goto :eof

REM One line: cai-launcher 1, a four letter kind (path or name), the launcher,
REM and a closing end field. Anything else counts as no record.
:readrecord
set "LAUNCHER="
set "KIND="
set "LINE="
if not exist "%REC%" goto :eof
set /p LINE=<"%REC%"
if not defined LINE goto :eof
if not "%LINE:~0,15%"=="cai-launcher 1 " goto :eof
if not "%LINE:~-4%"==" end" goto :eof
set "KIND=%LINE:~15,4%"
set "LAUNCHER=%LINE:~20,-4%"
if not "%KIND%"=="path" if not "%KIND%"=="name" set "LAUNCHER="
goto :eof
CMDBLOCK

# Same three endings as the CMD block above (healthy, failed, degraded), and no
# `exec`: control has to come back here so a failing recorded interpreter can be
# turned into exit 2. Probing reads /dev/null, so the hook input on stdin is
# read once, by the guard or by the reduced check. Write mode is the exception
# the CMD block's header names: a failed call, or a write pattern file that
# cannot be read, is let through with exit 1; a degraded call the file does not
# match passes silently; only a subagent's write to ledger.jsonl or to the
# guard's launcher record it matches is blocked.
DIR="$(cd "$(dirname "$0")" && pwd)"
GUARD="$DIR/../scripts/bash_guard.py"
WRITER="$DIR/record_launcher.py"
PATTERNS="$DIR/reduced-check-patterns.txt"
# hooks.json passes agent for Agent calls: a prompt is not a command, so the
# reduced check only looks for the verifier there (#277).
[ "$1" = agent ] && PATTERNS="$DIR/reduced-check-agent-patterns.txt"
# hooks.json passes write for Write, Edit and NotebookEdit calls: a broken
# interpreter must not stop every file write, so a failed call is let through
# with exit 1 and the pattern file knows only a subagent's write to ledger.jsonl
# or to the guard's launcher record.
WRITE_MODE=
if [ "$1" = write ]; then
    WRITE_MODE=1
    PATTERNS="$DIR/reduced-check-write-patterns.txt"
fi
REC="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/cai/guard-launcher-sh.txt"

# One line: cai-launcher 1, a kind (path or name), the launcher, a closing end
# field. Anything else is no record. `case` ignores read's status on purpose:
# a last line without a newline still fills LINE.
read_record() {
    LINE=""; KIND=""; LAUNCHER=""
    [ -f "$REC" ] && IFS= read -r LINE < "$REC"
    case "$LINE" in
        "cai-launcher 1 path "*" end") KIND=path ;;
        "cai-launcher 1 name "*" end") KIND=name ;;
        *) return 1 ;;
    esac
    LAUNCHER=${LINE#cai-launcher 1 ???? }
    LAUNCHER=${LAUNCHER% end}
    [ -n "$LAUNCHER" ] || return 1
}

# A path is run quoted; a name is run unquoted so `py -3` splits into two words.
run_launcher() {
    if [ "$KIND" = path ]; then "$LAUNCHER" "$@"; else $LAUNCHER "$@"; fi
}

# Write mode, and nothing has read stdin: the write pattern file decides. No
# match is a silent pass, a match blocks, and a grep that failed (a missing
# pattern file) lets the call through with a hook error. Never returns.
write_scan() {
    grep -i -q -f "$PATTERNS"
    RC=$?
    [ "$RC" -eq 1 ] && exit 0
    if [ "$RC" -eq 0 ]; then
        printf '%s\n' "cai guard reduced check: the Python guard did not run, so only a subagent's write to ledger.jsonl or to the guard's launcher record is checked. This call is blocked." >&2
        exit 2
    fi
    printf '%s\n' "cai guard reduced check: the Python guard did not run and the write pattern file could not be read, so this call is let through without the ledger check." >&2
    exit 1
}

# The record is valid: run the guard on the real input and pass 0 or 2 on. Any
# other code is this input or the launcher, so ask the guard once more with
# empty input: it answers 0 whenever it runs at all. Either way this call is
# blocked for every caller (write mode: let through with exit 1). Never returns.
run_recorded() {
    if [ "$KIND" = path ] && [ ! -x "$LAUNCHER" ]; then
        rm -f "$REC"
        [ -n "$WRITE_MODE" ] && write_scan
        printf '%s\n' "cai guard launcher failed: $LAUNCHER no longer exists, record dropped. This call is blocked for every caller, the next call probes again." >&2
        exit 2
    fi
    run_launcher "$GUARD" "$@"
    RC=$?
    [ "$RC" -eq 0 ] && exit 0
    [ "$RC" -eq 2 ] && exit 2
    if run_launcher "$GUARD" </dev/null >/dev/null 2>&1; then
        if [ -n "$WRITE_MODE" ]; then
            printf '%s\n' "cai guard launcher failed: $LAUNCHER exited $RC on this input but still runs the guard on empty input, record kept. Write mode: this call is let through without the ledger check." >&2
            exit 1
        fi
        printf '%s\n' "cai guard launcher failed: $LAUNCHER exited $RC on this input but still runs the guard on empty input, record kept. This call is blocked for every caller." >&2
    else
        rm -f "$REC"
        if [ -n "$WRITE_MODE" ]; then
            printf '%s\n' "cai guard launcher failed: $LAUNCHER exited $RC on this input, record dropped. Write mode: this call is let through without the ledger check, the next call probes again." >&2
            exit 1
        fi
        printf '%s\n' "cai guard launcher failed: $LAUNCHER exited $RC on this input, record dropped. This call is blocked for every caller, the next call probes again." >&2
    fi
    exit 2
}

if read_record; then
    run_recorded "$@"
fi

# No record: probe. Step 1, the candidate runs the guard on empty input and
# exits 0. Step 2, it runs the record writer: 0 written, 73 cannot write, any
# other code a failed probe.
for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" "$GUARD" </dev/null >/dev/null 2>&1 || continue
    CAI_GUARD_RECORD="$REC" "$c" "$WRITER" sh "$c" </dev/null >/dev/null 2>&1
    W=$?
    if [ "$W" -eq 0 ]; then
        # Written but unreadable, or dropped by a concurrent call: not recorded.
        read_record || continue
        run_recorded "$@"
    elif [ "$W" -eq 73 ]; then
        # The interpreter works and the record cannot be written: run it by name.
        "$c" "$GUARD" "$@"
        RC=$?
        [ "$RC" -eq 0 ] && exit 0
        [ "$RC" -eq 2 ] && exit 2
        if [ -n "$WRITE_MODE" ]; then
            printf '%s\n' "cai guard launcher failed: $c exited $RC on this input, nothing was recorded. Write mode: this call is let through without the ledger check, the next call probes again." >&2
            exit 1
        fi
        printf '%s\n' "cai guard launcher failed: $c exited $RC on this input, nothing was recorded. This call is blocked for every caller, the next call probes again." >&2
        exit 2
    fi
done

# Nothing runs the guard and nothing has read stdin. grep exits 1 for no match;
# a match, or grep failing (a missing pattern file), blocks.
[ -n "$WRITE_MODE" ] && write_scan
grep -q -f "$PATTERNS"
RC=$?
[ "$RC" -eq 1 ] && exit 0
printf '%s\n' "cai guard reduced check: no working Python 3 was found, so only force push, reset --hard, git clean -f, --no-verify, rm -rf, gh pr merge and the scoped agents are checked. This call is blocked." >&2
exit 2
