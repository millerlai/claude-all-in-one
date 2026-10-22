: << 'CMDBLOCK'
@echo off
REM Polyglot launcher for the codemap SubagentStart hook, the same shape as
REM run-timing.cmd: CMD.exe runs this block, POSIX shells swallow it as a
REM heredoc and fall through to the sh section below.
REM
REM It runs on every subagent start in every session, and most projects never
REM build an index: with no .cai\codemap\state.json under the project directory
REM it exits before any interpreter starts. A session opened in a subdirectory
REM of the repository therefore gets no line, which only means the agent reads
REM the code as it would without an index. With one, it runs codemap_hook.py
REM through the interpreter run-guard.cmd already recorded (read only; it never
REM probes and never writes). No record, a bad record or a missing interpreter
REM all mean exit 0. Always exit 0: stdout is only ever the hook's JSON.

if not defined CLAUDE_PROJECT_DIR exit /b 0
if not exist "%CLAUDE_PROJECT_DIR%\.cai\codemap\state.json" exit /b 0
set "SCRIPT=%~dp0..\scripts\codemap_hook.py"
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
[ -f "$CLAUDE_PROJECT_DIR/.cai/codemap/state.json" ] || exit 0

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$DIR/../scripts/codemap_hook.py"
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
