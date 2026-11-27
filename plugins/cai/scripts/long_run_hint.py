"""Decide whether one shell call starts work in the background (#499).

bash_guard.py prints the returned text as PreToolUse `additionalContext` on
its allow path. Pure: no I/O, no environment, no state. The text is one
constant and never carries any part of the command, so a command that quotes
"SYSTEM: ..." cannot ride into the model's context through it.
"""
from __future__ import annotations

import re

# Written as facts about the rule, not as orders: the hooks reference warns
# that out-of-band imperative text can be surfaced as a suspected injection.
# Conditional on the call running, because the hint fires before Claude Code's
# own permission layer and on accepted false positives.
HINT = (
    "cai: this call asks to start work in the background. If it runs and is a "
    "trial, measurement or benchmark, the cai rule \"Exploring and measuring: "
    "small first\" has it reported with its estimated duration and what it can "
    "show. Under that rule, one expected to run past about an hour that the "
    "person did not ask for is stopped, replaced by a smaller run first, and "
    "put to the person before it starts again; a subagent hands that question "
    "back to the main session instead of asking."
)

# A lone `&`: not `&&`, `2>&1`, `&>`, `>&` or `|&`.
_BASH_AMP = re.compile(r"(?<![&|<>])&(?![&>])")
# A path prefix counts (`/usr/bin/setsid`); a longer name does not (`nohup.out`,
# `foo-setsid`). `start /b` may carry a quoted window title, and Git Bash
# writes the switch as `//b` so MSYS does not turn it into a path.
_START_B = r"(?<![\w./-])start[ \t]+(?:\"[^\"\n]*\"[ \t]+)?/{1,2}b(?!\w)"
_BASH_WORDS = re.compile(
    # The lookbehind includes `/`, so a match only starts where a path starts;
    # starting inside one would rescan the rest of it, quadratic on `/a/a/a...`.
    r"(?<![\w./-])(?:[\w./-]*/)?(?:nohup|setsid|disown)(?![\w.-])|" + _START_B, re.I)
# `cmd /c "start /b x"` hides the switch inside a quoted string, so this one
# reads the text before quotes are blanked. `start` has to follow `/c` directly
# (one quote allowed), which keeps each attempt a fixed number of steps.
_CMD_START_B = re.compile(
    r"(?<![\w.-])cmd(?:\.exe)?[ \t]+/{1,2}c[ \t]+[\"']?[ \t]*" + _START_B, re.I)
# `saps` and `sajb` are the aliases of Start-Process and Start-Job everywhere;
# a bare `start` is Start-Process on Windows, counted only where a command
# starts, so `npm start` is not.
_PS_CMDLETS = re.compile(
    r"(?<![\w-])(?:Start-Process|Start-Job|Start-ThreadJob|saps|sajb)(?![\w-])"
    r"|(?:^|[;|({])[ \t]*start(?![\w-])", re.I | re.M)
# PowerShell's background `&` ends the statement it follows (`a & b` runs `a`
# as a job), so it is an `&` with something before it on its line. The call
# operator `& "x.exe"` starts a statement instead: nothing, `;`, `|`, `{`, `(`
# or `=` before it. Blanked quotes keep their delimiters, so `& "x.exe"` still
# has its closing quote after the `&`, never a command before it.
_PS_AMP = re.compile(r"[^\s;|{(=&>][ \t]*&(?![&>])")

# Each pattern lists, in order: an escape (so `\'` never opens a quote), the
# quoted forms, then a comment. A `#` starts a comment only where a word starts.
# Double-quoted spans are written unrolled, so a 1 MB string costs one pass
# and no backtracking state. Unterminated spans run to the end of the text.
# `${...}` is a parameter expansion, so an `&` in `${s//&/and}` is text.
_BASH_QUOTES = re.compile(
    r"""\\.|\$\{[^}]*(\})?|\$'[^'\\]*(?:\\.[^'\\]*)*('?)|'[^']*('?)|"[^"\\]*(?:\\.[^"\\]*)*("?)"""
    r"""|(?<![^\s;&|()])#[^\n]*""", re.S)
_PS_QUOTES = re.compile(
    r"""`.|<\#[^#]*(?:\#(?!>)[^#]*)*(\#>)?|@'[^']*(?:'(?!@)[^']*)*('@)?"""
    r"""|@"[^"]*(?:"(?!@)[^"]*)*("@)?|'[^']*(')?|"[^"`]*(?:`.[^"`]*)*(")?"""
    r"""|(?<![^\s;|(){}])\#[^\n]*""", re.S)
# A here-doc opener: `<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"`; not `<<<`.
_HEREDOC = re.compile(r"""(?<![<\w])<<(-?)[ \t]*(['"]?)([A-Za-z_]\w*)\2""")
# Bounds the work a crafted command full of openers can cause: each opener
# searches forward for its terminator once, a delimiter whose terminator was
# not found is never searched for again, and only the first few are read.
_HEREDOC_MAX = 10


def _blank_heredocs(text: str) -> str:
    """`text` with each here-doc body and terminator line replaced by spaces.

    Same length, newlines kept. A body is data whether or not its opener is
    quoted, so an `&` or an apostrophe in it means nothing. An opener with no
    terminator line is left alone: Bash would read to the end, but a `<<WORD`
    inside a quoted string has none either, and leaving it alone keeps that
    case from hiding the rest of the command.
    """
    out, pos, missing = [], 0, set()
    for n, m in enumerate(_HEREDOC.finditer(text)):
        if n >= _HEREDOC_MAX:
            break
        if m.start() < pos or (m.group(1), m.group(3)) in missing:
            continue
        body = text.find("\n", m.end())
        if body < 0:
            break
        tabs = r"\t*" if m.group(1) else ""
        end = re.compile(r"^%s%s[ \t]*$" % (tabs, re.escape(m.group(3))), re.M).search(text, body + 1)
        if not end:
            missing.add((m.group(1), m.group(3)))
            continue
        out.append(text[pos:body + 1])
        out.append(re.sub(r"[^\n]", " ", text[body + 1:end.end()]))
        pos = end.end()
    out.append(text[pos:])
    return "".join(out)


def _blank_quotes(text: str, escape: str) -> str:
    """`text` with quoted spans, comments and escaped characters blanked.

    Same length. Quote delimiters and escape characters are kept, so a quoted
    or escaped `&` cannot match and `& "x"` does not end in `&`; a comment is
    blanked whole. One regex pass, so a crafted 1 MB command stays linear.
    """
    def blank(m: re.Match[str]) -> str:
        s = m.group()
        if s[0] == escape:
            return s[0] + " "
        if s[0] == "#":
            return " " * len(s)
        closed = next((g for g in m.groups() if g is not None), "")
        opener = 2 if s[:2] in ("${", "$'", "@'", '@"', "<#") else 1
        return s[:opener] + " " * (len(s) - opener - len(closed)) + closed

    return (_BASH_QUOTES if escape == "\\" else _PS_QUOTES).sub(blank, text)


def background_hint(tool_name: object, tool_input: object, code: str) -> str | None:
    """HINT when the call starts background work, else None."""
    # A Monitor always runs in the background; the guard has already returned
    # for a WebSocket watch, which carries no command.
    if tool_name == "Monitor":
        return HINT
    if tool_name not in ("Bash", "PowerShell"):
        return None
    if isinstance(tool_input, dict) and tool_input.get("run_in_background") is True:
        return HINT
    if tool_name == "Bash":
        unquoted = _blank_heredocs(code)
        text = _blank_quotes(unquoted, "\\")
        if _BASH_AMP.search(text) or _BASH_WORDS.search(text) or _CMD_START_B.search(unquoted):
            return HINT
        return None
    text = _blank_quotes(code, "`")
    if _PS_CMDLETS.search(text) or _PS_AMP.search(text):
        return HINT
    return None
