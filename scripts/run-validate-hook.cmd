: << 'CMDBLOCK'
@echo off
REM Polyglot launcher, same shape as plugins/cai/hooks/run-guard.cmd: CMD.exe
REM runs this block, POSIX shells swallow it as a heredoc and fall through to
REM the sh section. README lists the interpreter as `python3` on macOS/Linux and
REM `python`/`py` on Windows, so a bare `python` here would fail on half the
REM platforms this repo is developed on.
REM
REM Keep this file pure ASCII. CMD.exe reads batch files through the OEM
REM codepage and a stray multi-byte character desyncs its parser, which shows
REM up as mangled commands like 'cho' instead of 'echo'.
REM
REM PostToolUse cannot block, so the exit code is only advisory. Pass it through
REM anyway, so a non-zero result still reaches Claude along with the stderr.

set "HOOK=%~dp0validate_hook.py"

where py >nul 2>nul
if not errorlevel 1 goto usepy
where python >nul 2>nul
if not errorlevel 1 goto usepython

REM No interpreter: stay quiet rather than erroring on every edit.
exit /b 0

:usepy
py -3 "%HOOK%"
exit /b %ERRORLEVEL%

:usepython
python "%HOOK%"
exit /b %ERRORLEVEL%
CMDBLOCK

HOOK="$(cd "$(dirname "$0")" && pwd)/validate_hook.py"

for interpreter in python3 python; do
    if command -v "$interpreter" >/dev/null 2>&1; then
        exec "$interpreter" "$HOOK"
    fi
done

exit 0
