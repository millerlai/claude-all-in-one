: << 'CMDBLOCK'
@echo off
REM Polyglot launcher for the stage-timing hooks, the same shape as
REM run-guard.cmd: CMD.exe runs this block, POSIX shells swallow it as a
REM heredoc and fall through to the sh section below.
REM
REM It runs on every tool call in every session, so the common case has to cost
REM almost nothing: with no timing-open.* marker file in the project's
REM .claude/track it exits before any interpreter starts. With one, it runs
REM timing_hook.py through the interpreter run-guard.cmd already recorded
REM (read only; it never probes and never writes). No record, a bad record or a
REM missing interpreter all mean exit 0. Always exit 0, print nothing: a
REM PreToolUse hook's output is parsed as a decision.

if not defined CLAUDE_PROJECT_DIR exit /b 0
if not exist "%CLAUDE_PROJECT_DIR%\.claude\track\timing-open.*" exit /b 0
set "SCRIPT=%~dp0..\scripts\timing_hook.py"
if not defined CLAUDE_CONFIG_DIR goto defaultroot
set "REC=%CLAUDE_CONFIG_DIR%\cai\guard-launcher-cmd.txt"
goto haveroot
:defaultroot
set "REC=%USERPROFILE%\.claude\cai\guard-launcher-cmd.txt"
:haveroot
set "LINE="
if not exist "%REC%" exit /b 0
set /p LINE=<"%REC%"
if not defined LINE exit /b 0
if not "%LINE:~0,15%"=="cai-launcher 1 " exit /b 0
if not "%LINE:~-4%"==" end" exit /b 0
set "KIND=%LINE:~15,4%"
set "LAUNCHER=%LINE:~20,-4%"
if "%KIND%"=="path" goto runpath
if "%KIND%"=="name" goto runname
exit /b 0

:runpath
if not exist "%LAUNCHER%" exit /b 0
call "%%LAUNCHER%%" "%%SCRIPT%%"
exit /b 0

:runname
call %%LAUNCHER%% "%%SCRIPT%%"
exit /b 0
CMDBLOCK

[ -n "$CLAUDE_PROJECT_DIR" ] || exit 0
set -- "$CLAUDE_PROJECT_DIR"/.claude/track/timing-open.*
[ -e "$1" ] || exit 0

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$DIR/../scripts/timing_hook.py"
REC="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/cai/guard-launcher-sh.txt"

LINE=""
[ -f "$REC" ] && IFS= read -r LINE < "$REC"
case "$LINE" in
    "cai-launcher 1 path "*" end") KIND=path ;;
    "cai-launcher 1 name "*" end") KIND=name ;;
    *) exit 0 ;;
esac
LAUNCHER=${LINE#cai-launcher 1 ???? }
LAUNCHER=${LAUNCHER% end}
[ -n "$LAUNCHER" ] || exit 0

# A path is run quoted; a name is run unquoted so `py -3` splits into two words.
if [ "$KIND" = path ]; then
    [ -x "$LAUNCHER" ] || exit 0
    "$LAUNCHER" "$SCRIPT"
else
    $LAUNCHER "$SCRIPT"
fi
exit 0
