#!/usr/bin/env python3
"""
Make a user's `~/.codex` match this installed cai-codex tree. The Codex setup
skill (`skills/setup/SKILL.md`) runs this with no arguments; the launcher does
not exist yet the first time it runs, so `<cai-root>` is this file's own
grandparent directory rather than anything the launcher resolves.

    python install_codex.py

Writes, in order (design: docs/design/2026-09-18-codex-support-detail.md,
"### install_codex.py"):
    1. `$HOME/.codex/cai/launcher.py` -- fixed under the real home directory,
       not `$CODEX_HOME` (D1=C).
    2. `$CODEX_HOME/agents/cai_*.toml` -- copied from `<cai-root>/agents/`;
       a `cai_*.toml` this tree no longer ships is removed.
    3. `$CODEX_HOME/hooks.json` -- adds or replaces the one PreToolUse entry
       whose command contains `.codex/cai/launcher.py`; every other entry is
       left byte for byte alone.
    4. `$CODEX_HOME/AGENTS.md` -- replaces the `<!-- cai-codex:begin -->` /
       `<!-- cai-codex:end -->` region (or appends it) with the cai command
       line (this installer's own recorded interpreter, `sys.executable`,
       plus the launcher path) followed by the rules from
       `<cai-root>/rules/*.md`.

Every write goes to a temp file in the destination's own directory and then
`os.replace`s it into place, so a crash mid-write leaves the previous file
intact rather than a half-written one.

Exit codes: 0 ok; 1 a write failed or an existing file could not be parsed,
with the failing path printed.

Idempotent: running this twice ends in the same state, because each step
either fully replaces its own file or replaces only the one entry it owns.

Reuses: the naming and single-purpose shape of install_statusline.py
(plugins/cai/scripts/install_statusline.py:1); the "copy wholesale, updates
propagate" behaviour of /cai:setup's own step 2 (Claude-side
plugins/cai/skills/setup/SKILL.md:25-31).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

CAI_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_MARKER = ".codex/cai/launcher.py"
AGENTS_BEGIN = "<!-- cai-codex:begin -->"
AGENTS_END = "<!-- cai-codex:end -->"


class HooksParseError(Exception):
    """`hooks.json` exists but is not valid JSON -- never overwritten."""


class MarkerError(Exception):
    """`AGENTS.md` has a begin marker with no matching end marker."""


def codex_home() -> Path:
    home = os.environ.get("CODEX_HOME")
    return Path(home) if home else Path.home() / ".codex"


def _atomic_write_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# Step 1 -- the launcher
# ---------------------------------------------------------------------------

def install_launcher(root: Path, home: Path) -> Path:
    dest = home / ".codex" / "cai" / "launcher.py"
    src = root / "scripts" / "launcher.py"
    _atomic_write_bytes(dest, src.read_bytes())
    return dest


# ---------------------------------------------------------------------------
# Step 2 -- agents
# ---------------------------------------------------------------------------

def install_agents(root: Path, home: Path):
    """(written paths, removed paths). Removes only `cai_*.toml` files this
    tree no longer ships -- never a user's own personal agent of another
    name."""
    src_dir = root / "agents"
    dest_dir = home / "agents"
    shipped = sorted(src_dir.glob("cai_*.toml"))
    shipped_names = {p.name for p in shipped}

    written = []
    for p in shipped:
        dest = dest_dir / p.name
        _atomic_write_bytes(dest, p.read_bytes())
        written.append(dest)

    removed = []
    if dest_dir.is_dir():
        for p in sorted(dest_dir.glob("cai_*.toml")):
            if p.name not in shipped_names:
                p.unlink()
                removed.append(p)
    return written, removed


# ---------------------------------------------------------------------------
# Step 3 -- hooks.json
# ---------------------------------------------------------------------------

def _is_our_hook_entry(entry: dict) -> bool:
    for h in entry.get("hooks", []) or []:
        cmd = str(h.get("command", "")).replace("\\", "/")
        if LAUNCHER_MARKER in cmd:
            return True
    return False


def _ps_quote(value) -> str:
    """A PowerShell single-quoted string literal for `value`. A *double*-
    quoted one is not safe here: PowerShell expands a `$(...)`
    subexpression (or a bare `$name`) inside it even with no `"` to break
    out of, so a path containing one would run as code the moment this
    string reaches `powershell.exe -Command`. A single-quoted string expands
    nothing -- doubling an embedded `'` is how PowerShell escapes one
    inside it, so a path (or, in principle, sys.executable) containing a
    quote, a backtick, or a `$(...)` sequence can't end the literal early
    or execute as a subexpression."""
    return "'" + str(value).replace("'", "''") + "'"


def _posix_quote(value) -> str:
    """A POSIX `sh` single-quoted string literal for `value`. A *double*-
    quoted one is not safe here either: `sh` still expands `$(...)`/`` ` ``
    command substitution and `$name` inside double quotes, so a path
    containing one would run as a command. Nothing is special inside a
    single-quoted string except the quote character itself, which has to
    close the literal, insert a literal quote, and reopen it (`'\\''`), the
    standard POSIX splice -- so a path containing a quote, a backtick, or a
    `$(...)` sequence can't end the literal early or run as a command."""
    return "'" + str(value).replace("'", "'\\''") + "'"


def cai_command_line(python: str, launcher_path: str, os_name: str) -> str:
    """The command line to invoke the fixed-path launcher with, given the
    interpreter the installer recorded (`sys.executable`) and the launcher's
    own path -- both plain, separator-normalized strings, not `Path`
    objects. `os_name` is `"nt"` or `"posix"` (i.e. `os.name`).

    - `"nt"`: a PowerShell scriptblock,
      `& { & '<python>' '<launcher_path>' @args 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }`.
      The block has no named parameters, so tokens the model appends after
      the closing `}` (the script name and its args -- the unchanged "one
      command line, script name appended" contract) become `$args` inside
      it, splatted into the inner `&` call via `@args`. `2>&1 |
      ForEach-Object { "$_" }` routes both stdout and stderr through the
      PowerShell pipeline: observed in the real Codex TUI (Windows 11,
      codex-cli 0.155.x) a bare `& '<python>' '<launcher>' @args` line's own
      stdout never reached the tool output, while piping it through
      PowerShell like this did. `exit $LASTEXITCODE` still surfaces the
      launcher's real exit code once it has passed through the pipeline --
      same reasoning as `_our_hook_entry`'s `command_windows`. Single-quoted,
      not double-quoted: see `_ps_quote`.
    - anything else (posix): `'<python>' '<launcher_path>'` -- a POSIX shell
      runs a quoted-string command directly, no `&` prefix needed.
      Single-quoted, not double-quoted: see `_posix_quote`.
    """
    if os_name == "nt":
        return ('& { & ' + _ps_quote(python) + ' ' + _ps_quote(launcher_path) +
                ' @args 2>&1 | ForEach-Object { "$_" }; exit $LASTEXITCODE }')
    return _posix_quote(python) + " " + _posix_quote(launcher_path)


def _our_hook_entry(python: str, launcher_path: Path) -> dict:
    # Absolute paths only, computed now -- no variable expands at hook time.
    # matcher "Bash" scopes the hook to shell commands only, per
    # learn.chatgpt.com/docs/hooks ("Shell commands: Matched as \"Bash\"",
    # file edits as "apply_patch"/"Edit"/"Write", MCP tools by full name;
    # UNVERIFIED, C9 -- real verify captures what Codex actually sends). A
    # wildcard would fire the guard before every tool call, edits and MCP
    # calls included, and risk false blocks if an edit tool's `tool_input`
    # carries patch text through the same `command` field bash_guard reads.
    # Single-quoted, not double-quoted -- see _posix_quote: a *double*-quoted
    # `sh` string still expands `$(...)`/backtick command substitution inside
    # it, so a path (or, in principle, sys.executable) containing one would
    # run as a command the moment Codex hands this to a POSIX shell.
    command = f'{_posix_quote(python)} {_posix_quote(launcher_path.as_posix())} guard'
    # Codex runs a hook's `command` through `powershell.exe -Command` on
    # Windows (observed, codex-cli 0.155.0): a bare `'prog' 'arg' ...` line
    # parses as an expression whose second quoted token is a syntax error, so
    # PowerShell exits 1 before the guard ever runs -- Codex reports "Hook
    # failed" and runs the command anyway, guard or no guard. `commandWindows`
    # (learn.chatgpt.com/docs/hooks: "Windows-specific command overrides") is
    # Codex's own escape hatch for this: `&` forces PowerShell to invoke the
    # quoted string as a command, and `exit $LASTEXITCODE` re-surfaces the
    # child's real exit code, since PowerShell otherwise collapses any
    # nonzero child exit to 1 -- which would read as "hook failed", not
    # "hook blocked it", exactly the ambiguity this override exists to avoid.
    command_windows = (f'& {_ps_quote(python)} {_ps_quote(launcher_path.as_posix())} guard'
                        '; exit $LASTEXITCODE')
    return {"matcher": "Bash",
            "hooks": [{"type": "command", "command": command,
                       "commandWindows": command_windows}]}


def install_hooks(home: Path, launcher_path: Path) -> Path:
    dest = home / "hooks.json"
    if dest.is_file():
        raw = dest.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HooksParseError(f"{dest}: {e}") from e
    else:
        data = {}

    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    entry = _our_hook_entry(sys.executable, launcher_path)
    for i, existing in enumerate(pre):
        if _is_our_hook_entry(existing):
            pre[i] = entry
            break
    else:
        pre.append(entry)

    body = json.dumps(data, indent=2) + "\n"
    _atomic_write_bytes(dest, body.encode("utf-8"))
    return dest


# ---------------------------------------------------------------------------
# Step 4 -- AGENTS.md
# ---------------------------------------------------------------------------

def rules_block(root: Path) -> str:
    """The generated rules from `<cai-root>/rules/*.md`, concatenated."""
    rules_dir = root / "rules"
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(rules_dir.glob("*.md")))


def cai_command_block(cai_line: str) -> str:
    """The paragraph install_agents_md writes above the rules, telling the
    model what `<cai>` means in every generated `<cai> <script>` call."""
    return (
        "To run a cai-codex script, run this command followed by the "
        "script name and its arguments:\n\n"
        f"    {cai_line}\n"
    )


def install_agents_md(home: Path, block_body: str) -> Path:
    dest = home / "AGENTS.md"
    block = f"{AGENTS_BEGIN}\n{block_body}\n{AGENTS_END}"

    if dest.is_file():
        text = dest.read_text(encoding="utf-8")
    else:
        text = ""

    begin_at = text.find(AGENTS_BEGIN)
    if begin_at == -1:
        sep = "" if text == "" or text.endswith("\n") else "\n"
        new_text = text + sep + block + "\n"
    else:
        end_at = text.find(AGENTS_END)
        if end_at == -1:
            raise MarkerError(f"{dest}: begin marker without end marker")
        new_text = text[:begin_at] + block + text[end_at + len(AGENTS_END):]

    _atomic_write_bytes(dest, new_text.encode("utf-8"))
    return dest


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    root = CAI_ROOT
    home_dir = Path.home()
    chome = codex_home()

    try:
        launcher_dest = install_launcher(root, home_dir)
    except OSError as e:
        print(f"write failed: {home_dir / '.codex' / 'cai' / 'launcher.py'}: {e}")
        return 1
    print(f"wrote {launcher_dest}")

    launcher_str = str(launcher_dest) if os.name == "nt" else launcher_dest.as_posix()
    cai_line = cai_command_line(sys.executable, launcher_str, os.name)
    print(f"cai command: {cai_line}")

    try:
        written, removed = install_agents(root, chome)
    except OSError as e:
        print(f"write failed: {chome / 'agents'}: {e}")
        return 1
    for p in written:
        print(f"wrote {p}")
    for p in removed:
        print(f"removed {p}")

    try:
        hooks_path = install_hooks(chome, launcher_dest)
    except HooksParseError as e:
        print(f"invalid hooks.json, not overwritten: {e}")
        return 1
    except OSError as e:
        print(f"write failed: {chome / 'hooks.json'}: {e}")
        return 1
    print(f"wrote {hooks_path}")

    rules_text = rules_block(root)
    block_body = cai_command_block(cai_line) + "\n" + rules_text
    try:
        agents_md_path = install_agents_md(chome, block_body)
    except MarkerError as e:
        print(f"invalid AGENTS.md, not overwritten: {e}")
        return 1
    except OSError as e:
        print(f"write failed: {chome / 'AGENTS.md'}: {e}")
        return 1
    print(f"wrote {agents_md_path}")

    print(f"rules: {len(rules_text.encode('utf-8'))} bytes "
          "(Codex's AGENTS.md cap is unverified)")
    print("guard: installed, inactive until you trust it with /hooks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
