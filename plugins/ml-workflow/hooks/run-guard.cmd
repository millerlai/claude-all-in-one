: << 'CMDBLOCK'
@echo off
REM Polyglot launcher: CMD.exe runs this block, POSIX shells swallow it as a
REM heredoc and fall through to the sh section below. Needed because Claude Code
REM runs hook commands under CMD.exe on Windows and sh on macOS/Linux, and the
REM Python interpreter is named differently on each (`py`/`python` vs `python3`).
REM
REM Exit code passthrough matters: bash_guard.py returns 2 to block a command.
REM `exit /b %ERRORLEVEL%` must stay outside any parenthesised block, otherwise
REM CMD expands it at parse time and always reports 0.

set "GUARD=%~dp0..\scripts\bash_guard.py"

where py >nul 2>nul
if not errorlevel 1 goto usepy
where python >nul 2>nul
if not errorlevel 1 goto usepython

REM No interpreter: allow the command through rather than blocking every Bash
REM call. `/ml-workflow:setup` verifies the guard actually fires.
exit /b 0

:usepy
py -3 "%GUARD%"
exit /b %ERRORLEVEL%

:usepython
python "%GUARD%"
exit /b %ERRORLEVEL%
CMDBLOCK

GUARD="$(cd "$(dirname "$0")" && pwd)/../scripts/bash_guard.py"

for interpreter in python3 python; do
    if command -v "$interpreter" >/dev/null 2>&1; then
        exec "$interpreter" "$GUARD"
    fi
done

exit 0
