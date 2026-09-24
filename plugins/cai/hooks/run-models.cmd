: << 'CMDBLOCK'
@echo off
REM Polyglot launcher for the SessionStart hook, the same shape as
REM run-guard.cmd: CMD.exe runs this block, POSIX shells swallow it as a
REM heredoc and fall through to the sh section below.
REM
REM It puts the person's saved tier -> model choice back into this installed
REM copy (model_choice.py apply --hook). Always exits 0: a session must never
REM fail to start because of it.

set "SCRIPT=%~dp0..\scripts\model_choice.py"

where py >nul 2>nul
if not errorlevel 1 goto usepy
where python >nul 2>nul
if not errorlevel 1 goto usepython
exit /b 0

:usepy
py -3 "%SCRIPT%" apply --hook
exit /b 0

:usepython
python "%SCRIPT%" apply --hook
exit /b 0
CMDBLOCK

SCRIPT="$(cd "$(dirname "$0")" && pwd)/../scripts/model_choice.py"

for interpreter in python3 python; do
    if command -v "$interpreter" >/dev/null 2>&1; then
        "$interpreter" "$SCRIPT" apply --hook
        exit 0
    fi
done

exit 0
