#!/usr/bin/env python3
"""
Make a user's `~/.codex` match this installed cai-codex tree. The Codex setup
skill (`skills/setup/SKILL.md`) runs this with no arguments; the launcher does
not exist yet the first time it runs, so `<cai-root>` is this file's own
grandparent directory rather than anything the launcher resolves.

    python install_codex.py            # run 1: install, then print the mapping
    python install_codex.py --models   # print the mapping only; write nothing
    python install_codex.py --apply    # write the answers a skill collected

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

Run 1 (no `--apply`) additionally validates the model detection cache, the
saved model choice, and every role's TOML header before writing anything
(model fallback design:
docs/design/2026-09-22-codex-model-fallback-detail.md, "Run 1 order"), then
removes a leftover `cai-model-answers.json`, and prints a mapping block
(`render_mapping`) describing the roles and the question `skills/setup/SKILL.md`
should ask next. `--models` prints that same block and writes nothing at all,
so `skills/models/SKILL.md` can change a role's model without a reinstall;
either skill then writes its answers with `--apply`.

Every write goes to a temp file in the destination's own directory and then
`os.replace`s it into place, so a crash mid-write leaves the previous file
intact rather than a half-written one.

Exit codes: 0 ok; 1 a write failed or an existing file could not be parsed,
with the failing path printed; 2 bad arguments.

Idempotent: running this twice ends in the same state, because each step
either fully replaces its own file or replaces only the one entry it owns.

Reuses: the naming and single-purpose shape of install_statusline.py
(plugins/cai/scripts/install_statusline.py:1); the "copy wholesale, updates
propagate" behaviour of /cai:setup's own step 2 (Claude-side
plugins/cai/skills/setup/SKILL.md:25-31).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

CAI_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_MARKER = ".codex/cai/launcher.py"
AGENTS_BEGIN = "<!-- cai-codex:begin -->"
AGENTS_END = "<!-- cai-codex:end -->"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}\Z")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max", "ultra")
MODELS_CACHE_NAME = "models_cache.json"
CHOICE_NAME = "cai-model-choice.json"      # chosen by the person 2026-09-22 (P1)
ANSWERS_NAME = "cai-model-answers.json"    # chosen by the person 2026-09-22 (P1)
FORMAT = 1


class HooksParseError(Exception):
    """`hooks.json` exists but is not valid JSON -- never overwritten."""


class MarkerError(Exception):
    """`AGENTS.md` has a begin marker with no matching end marker."""


class AnchorError(Exception):
    """An anchor pattern was missing or repeated in a TOML's header region."""


class ChoiceParseError(Exception):
    """`cai-model-choice.json` exists but is not a valid saved choice."""


class AnswersError(Exception):
    """`cai-model-answers.json` exists but is not a valid answers file, or an
    answer fails validation."""


# ---------------------------------------------------------------------------
# Line rewriter -- rewrite_model_lines, fallback_effort
# ---------------------------------------------------------------------------

_MODEL_RE = rb'^model = "[^"\r\n]*"(?=\r?$)'
_EFFORT_RE = rb'^model_reasoning_effort = "[^"\r\n]*"(?=\r?$)'
_DEVELOPER_INSTRUCTIONS_RE = rb"^developer_instructions = "


def _replace_anchor(header: bytes, pattern: bytes, replacement: bytes, name: str) -> bytes:
    matches = list(re.finditer(pattern, header, re.MULTILINE))
    if len(matches) != 1:
        raise AnchorError(f"{name}: found {len(matches)} times")
    m = matches[0]
    return header[:m.start()] + replacement + header[m.end():]


def rewrite_model_lines(toml: bytes, model: str, effort: str) -> bytes:
    """`toml` with only its `model =` and `model_reasoning_effort =` lines
    changed, both in the header region before `developer_instructions = `
    (line 1, the `# cai-codex-version:` stamp, is always in that region and
    never matched, since the anchors only match a bare `model = "..."` line).
    A `\\r` before the matched line ending stays outside the replaced span,
    so CRLF input keeps CRLF."""
    if not SLUG_RE.match(model):
        raise ValueError(f"invalid model: {model!r}")
    if effort not in EFFORT_ORDER:
        raise ValueError(f"invalid effort: {effort!r}")

    split = re.search(_DEVELOPER_INSTRUCTIONS_RE, toml, re.MULTILINE)
    if split:
        header, rest = toml[:split.start()], toml[split.start():]
    else:
        header, rest = toml, b""

    header = _replace_anchor(header, _MODEL_RE, f'model = "{model}"'.encode(), "model")
    header = _replace_anchor(header, _EFFORT_RE,
                              f'model_reasoning_effort = "{effort}"'.encode(),
                              "model_reasoning_effort")
    return header + rest


def fallback_effort(own: str, levels: tuple[str, ...] | None) -> str:
    """`own` if `levels` doesn't narrow the choice (None, or none of its
    entries are recognized effort names), else `own` if it's offered, else
    the highest-ranked offered entry below `own`, else the lowest-ranked
    offered entry."""
    if levels is None:
        return own
    known = [l for l in levels if l in EFFORT_ORDER]
    if not known:
        return own
    if own in known:
        return own
    own_rank = EFFORT_ORDER.index(own) if own in EFFORT_ORDER else len(EFFORT_ORDER)
    lower = [l for l in known if EFFORT_ORDER.index(l) < own_rank]
    if lower:
        return max(lower, key=EFFORT_ORDER.index)
    return min(known, key=EFFORT_ORDER.index)


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

def install_agents(root: Path, home: Path, contents: dict[str, bytes] | None = None):
    """(written paths, removed paths). Removes only `cai_*.toml` files this
    tree no longer ships -- never a user's own personal agent of another
    name. `contents`, when given, supplies the bytes for each shipped file
    (`agent_bytes`'s per-role rewritten TOMLs) in place of the file's own
    shipped bytes."""
    src_dir = root / "agents"
    dest_dir = home / "agents"
    shipped = sorted(src_dir.glob("cai_*.toml"))
    shipped_names = {p.name for p in shipped}

    written = []
    for p in shipped:
        dest = dest_dir / p.name
        data = contents[p.name] if contents is not None else p.read_bytes()
        _atomic_write_bytes(dest, data)
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
# Detection -- detect
# Design: docs/design/2026-09-22-codex-model-fallback-detail.md, "Detection".
# ---------------------------------------------------------------------------

class Detection(NamedTuple):
    ok: bool
    reason: str                         # "" when ok
    source: Path
    offered: tuple[str, ...]            # catalog order
    levels: dict[str, tuple[str, ...]]  # offered slug -> known efforts, catalog order
    total: int                          # catalog entries with a str slug
    ignored: int                        # listed slugs dropped by SLUG_RE
    fetched_at: str | None


def detect(chome: Path) -> Detection:
    """Turns `$CODEX_HOME/models_cache.json` into the offered slugs and
    their effort lists, or a failure reason. Read-only, no subprocess or
    network calls -- never runs `codex`."""
    source = chome / MODELS_CACHE_NAME

    if not source.is_file():
        return Detection(False, f"{source} is missing", source, (), {}, 0, 0, None)

    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        models = data.get("models")
        if not isinstance(models, list):
            raise ValueError("models is not a list")
        for entry in models:
            if not isinstance(entry, dict):
                raise ValueError("a models entry is not an object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        return Detection(False, f"{source} cannot be parsed: {e}", source, (), {}, 0, 0, None)

    fetched_at = data.get("fetched_at")
    if not isinstance(fetched_at, str):
        fetched_at = None

    total = ignored = 0
    offered: list[str] = []
    levels: dict[str, tuple[str, ...]] = {}
    for entry in models:
        slug = entry.get("slug")
        if not isinstance(slug, str):
            continue  # not fatal, not counted anywhere
        total += 1
        if entry.get("visibility") != "list":
            continue  # D5: only visibility == "list" is offered
        if not SLUG_RE.match(slug):
            ignored += 1
            continue
        offered.append(slug)
        srl = entry.get("supported_reasoning_levels")
        efforts = tuple(
            lvl.get("effort") for lvl in srl
            if isinstance(lvl, dict) and isinstance(lvl.get("effort"), str)
        ) if isinstance(srl, list) else ()
        levels[slug] = efforts

    if not offered:
        return Detection(False, f"{source} lists no offered models", source,
                          (), {}, total, ignored, fetched_at)

    return Detection(True, "", source, tuple(offered), levels, total, ignored, fetched_at)


# ---------------------------------------------------------------------------
# Saved choice -- load_choice, save_choice
# ---------------------------------------------------------------------------

def load_choice(chome: Path) -> dict[str, str]:
    """The role -> slug map that survives plugin updates. `{}` when the file
    is absent."""
    path = chome / CHOICE_NAME
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        if data.get("format") != FORMAT:
            raise ValueError(f"format is not {FORMAT}")
        roles = data.get("roles")
        if not isinstance(roles, dict):
            raise ValueError("roles is not an object")
        for value in roles.values():
            if not isinstance(value, str) or not SLUG_RE.match(value):
                raise ValueError(f"invalid role slug: {value!r}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise ChoiceParseError(f"{path}: {e}") from e

    return roles


def save_choice(chome: Path, roles: dict[str, str]) -> Path:
    path = chome / CHOICE_NAME
    body = json.dumps({"format": FORMAT, "roles": roles}, indent=2, sort_keys=True) + "\n"
    _atomic_write_bytes(path, body.encode("utf-8"))
    return path


# ---------------------------------------------------------------------------
# Answers -- read_answers, merge_answers
# ---------------------------------------------------------------------------

def read_answers(chome: Path, roles: tuple[str, ...], detection: Detection) -> dict[str, str]:
    """The role -> slug map from `cai-model-answers.json`, validated against
    `roles` (the known role names) and, when `detection.ok`, `detection.offered`.
    Raises `AnswersError` on the first failing role."""
    path = chome / ANSWERS_NAME
    if not path.is_file():
        raise AnswersError(f"{path} is missing")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        if data.get("format") != FORMAT:
            raise ValueError(f"format is not {FORMAT}")
        answer_roles = data.get("roles")
        if not isinstance(answer_roles, dict):
            raise ValueError("roles is not an object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise AnswersError(f"{path} cannot be parsed: {e}") from e

    result: dict[str, str] = {}
    for role, value in answer_roles.items():
        if role not in roles:
            raise AnswersError(f"unknown role {role!r}")
        if not isinstance(value, str) or not SLUG_RE.match(value):
            raise AnswersError(
                f"rejected {role}: {value!r} is not a model name (allowed: {SLUG_RE.pattern})")
        if detection.ok and value not in detection.offered:
            raise AnswersError(
                f"rejected {role}: {value} is not offered by this detection; "
                "run $models to pick one it offers")
        result[role] = value
    return result


def merge_answers(saved: dict[str, str], answers: dict[str, str],
                   defaults: dict[str, tuple[str, str]]) -> dict[str, str]:
    """`saved` with each `answers` role applied: choosing the cai default
    (D6) removes any saved entry for that role instead of storing it."""
    merged = dict(saved)
    for role, slug in answers.items():
        if slug == defaults[role][0]:
            merged.pop(role, None)
        else:
            merged[role] = slug
    return merged


# ---------------------------------------------------------------------------
# Role map -- role_agents, shipped_defaults
# ---------------------------------------------------------------------------

def role_agents(root: Path) -> dict[str, list[str]]:
    """Role -> the `cai_*.toml` files installed for it, sorted, role order
    matching `root/models.json`'s own `roles` key order."""
    spec = json.loads((root / "models.json").read_text(encoding="utf-8"))
    agents_dir = root / "agents"
    result: dict[str, list[str]] = {role: [] for role in spec["roles"]}

    for key, role in spec["assignments"].items():
        if not key.startswith("agents/") or not key.endswith(".md"):
            continue  # skills/ keys are not per-agent
        short = key[len("agents/"):-len(".md")]
        toml_name = f"cai_{short}.toml"
        if (agents_dir / toml_name).is_file():
            result[role].append(toml_name)

    for tomls in result.values():
        tomls.sort()
    return result


def _extract_anchor(header: bytes, pattern: bytes, name: str) -> str:
    """The quoted string value of the single line matching `pattern` in
    `header` -- the "extract" counterpart of `_replace_anchor`'s "replace",
    same anchor-count contract."""
    matches = list(re.finditer(pattern, header, re.MULTILINE))
    if len(matches) != 1:
        raise AnchorError(f"{name}: found {len(matches)} times")
    m = re.search(rb'"([^"\r\n]*)"', matches[0].group(0))
    return m.group(1).decode("utf-8")


def shipped_defaults(root: Path, agents: dict[str, list[str]]) -> dict[str, tuple[str, str]]:
    """Role -> (model, effort) read from the first (sorted) TOML installed
    for that role."""
    result: dict[str, tuple[str, str]] = {}
    for role, tomls in agents.items():
        toml_bytes = (root / "agents" / tomls[0]).read_bytes()
        split = re.search(_DEVELOPER_INSTRUCTIONS_RE, toml_bytes, re.MULTILINE)
        header = toml_bytes[:split.start()] if split else toml_bytes
        model = _extract_anchor(header, _MODEL_RE, "model")
        effort = _extract_anchor(header, _EFFORT_RE, "model_reasoning_effort")
        result[role] = (model, effort)
    return result


# ---------------------------------------------------------------------------
# Planner -- plan_roles, ask_directive
# ---------------------------------------------------------------------------

class RolePlan(NamedTuple):
    role: str
    agents: tuple[str, ...]
    default_model: str
    default_effort: str
    in_effect: str           # saved slug, else default_model
    saved: bool
    effort: str              # fallback_effort(default_effort, levels.get(in_effect))
    reask: bool              # detection.ok and saved and in_effect not in offered
    unlisted_default: bool   # detection.ok and not saved and default_model not in offered
    offer: tuple[str, ...]   # () when not detection.ok


def plan_roles(agents: dict[str, list[str]], defaults: dict[str, tuple[str, str]],
                detection: Detection, saved: dict[str, str]) -> dict[str, RolePlan]:
    """A role plan per role in `agents` (role order preserved). A `saved`
    role name not present in `agents` is silently dropped (D13)."""
    plans: dict[str, RolePlan] = {}
    for role, agent_list in agents.items():
        default_model, default_effort = defaults[role]
        saved_slug = saved.get(role)
        is_saved = saved_slug is not None
        in_effect = saved_slug if is_saved else default_model
        effort = fallback_effort(default_effort, detection.levels.get(in_effect))
        reask = detection.ok and is_saved and in_effect not in detection.offered
        unlisted_default = (detection.ok and not is_saved
                             and default_model not in detection.offered)

        if not detection.ok:
            offer: tuple[str, ...] = ()
        else:
            offer_list: list[str] = []
            if in_effect in detection.offered:
                offer_list.append(in_effect)
            if default_model in detection.offered and default_model != in_effect:
                offer_list.append(default_model)
            for slug in detection.offered:
                if slug not in offer_list:
                    offer_list.append(slug)
            offer = tuple(offer_list)

        plans[role] = RolePlan(role, tuple(agent_list), default_model, default_effort,
                                in_effect, is_saved, effort, reask, unlisted_default, offer)
    return plans


def ask_directive(plans: dict[str, RolePlan], detection: Detection) -> str:
    if detection.ok:
        return "ask: keep-or-switch"
    unsaved = [role for role, plan in plans.items() if not plan.saved]
    if not unsaved:
        return "ask: nothing"
    return "ask: keep-or-type " + " ".join(unsaved)


# ---------------------------------------------------------------------------
# Agent bytes -- agent_bytes
# ---------------------------------------------------------------------------

def agent_bytes(root: Path, plans: dict[str, RolePlan]) -> dict[str, bytes]:
    """Every shipped `cai_*.toml` name -> bytes: a saved role's files are
    `rewrite_model_lines(shipped, plan.in_effect, plan.effort)`; every other
    file (role not saved, or a TOML not listed in any plan's `agents`) is
    the shipped bytes unchanged. Read-only -- no writes."""
    agent_to_plan: dict[str, RolePlan] = {}
    for plan in plans.values():
        for name in plan.agents:
            agent_to_plan[name] = plan

    result: dict[str, bytes] = {}
    for p in sorted((root / "agents").glob("cai_*.toml")):
        shipped = p.read_bytes()
        plan = agent_to_plan.get(p.name)
        if plan is not None and plan.saved:
            result[p.name] = rewrite_model_lines(shipped, plan.in_effect, plan.effort)
        else:
            result[p.name] = shipped
    return result


# ---------------------------------------------------------------------------
# Mapping printer -- render_mapping
# ---------------------------------------------------------------------------

def render_mapping(plans: dict[str, RolePlan], detection: Detection, chome: Path,
                    full: bool) -> list[str]:
    """The roles and questions, in a form both a person and `SKILL.md` can
    read line by line. `full=True` for run 1, `False` for the apply run."""
    lines: list[str] = []

    if detection.ok:
        fetched = f" (fetched {detection.fetched_at})" if detection.fetched_at else ""
        lines.append(f"models: detected {len(detection.offered)} of {detection.total} "
                      f"from {detection.source}{fetched}")
    else:
        lines.append(f"models: detection failed: {detection.reason}")
    if detection.ignored > 0:
        lines.append(f"models: ignored {detection.ignored} slug(s) outside [a-z0-9.-]")

    for role, plan in plans.items():
        tag = "cai default" if not plan.saved else f"saved; cai default {plan.default_model}"
        agent_names = ", ".join(name[:-len(".toml")] for name in plan.agents)
        lines.append(f"role {role}: {plan.in_effect} / {plan.effort} ({tag}) -- {agent_names}")

    if full and detection.ok:
        for role, plan in plans.items():
            entries = []
            for slug in plan.offer:
                marks = []
                if slug == plan.in_effect:
                    marks.append("in effect")
                if slug == plan.default_model:
                    marks.append("cai default")
                entries.append(f"{slug} ({', '.join(marks)})" if marks else slug)
            lines.append(f"offer {role}: {', '.join(entries)}")

    for role, plan in plans.items():
        if plan.reask:
            lines.append(f"ask again {role}: saved {plan.in_effect} is not offered by "
                          f"this detection; default answer {plan.offer[0]}")

    for role, plan in plans.items():
        if plan.unlisted_default:
            lines.append(f"not offered {role}: {plan.in_effect} is in effect but this "
                          "detection does not list it")

    if full:
        lines.append(ask_directive(plans, detection))
        lines.append(f"answers file: {chome / ANSWERS_NAME}")
    else:
        n = sum(1 for plan in plans.values() if plan.saved)
        lines.append(f"applied: {n} role(s) saved")

    return lines


# ---------------------------------------------------------------------------
# Apply run -- apply_answers
# ---------------------------------------------------------------------------

def apply_answers(root: Path, chome: Path) -> int:
    """The `--apply` run: merges `cai-model-answers.json` into the saved
    choice, rewrites the affected TOMLs, and removes the answers file on
    success."""
    detection = detect(chome)
    try:
        saved = load_choice(chome)
    except ChoiceParseError as e:
        print(f"invalid saved model choice, not overwritten: {e}")
        return 1

    try:
        agents = role_agents(root)
        defaults = shipped_defaults(root, agents)
    except AnchorError as e:
        print(f"cannot rewrite {root / 'agents'}: {e}")
        return 1
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"cannot read {root / 'models.json'}: {e}")
        return 1

    try:
        answers = read_answers(chome, tuple(agents.keys()), detection)
    except AnswersError as e:
        print(f"answers not applied: {e}")
        return 1

    merged = merge_answers(saved, answers, defaults)
    plans = plan_roles(agents, defaults, detection, merged)
    try:
        contents = agent_bytes(root, plans)
    except AnchorError as e:
        print(f"cannot rewrite {root / 'agents'}: {e}")
        return 1

    try:
        save_choice(chome, merged)
    except OSError as e:
        print(f"write failed: {chome / CHOICE_NAME}: {e}")
        print("re-run $setup to finish")
        return 1
    print(f"saved {chome / CHOICE_NAME}")

    try:
        written, removed = install_agents(root, chome, contents)
    except OSError as e:
        print(f"write failed: {chome / 'agents'}: {e}")
        print("re-run $setup to finish")
        return 1
    for p in written:
        print(f"wrote {p}")
    for p in removed:
        print(f"removed {p}")

    answers_path = chome / ANSWERS_NAME
    try:
        answers_path.unlink()
    except OSError as e:
        print(f"could not remove {answers_path}: {e}")
    else:
        print(f"removed {answers_path}")

    for line in render_mapping(plans, detection, chome, full=False):
        print(line)
    return 0


# ---------------------------------------------------------------------------
# Models run -- show_models
# ---------------------------------------------------------------------------

def show_models(root: Path, chome: Path) -> int:
    """The `--models` run: run 1's mapping block, and no write of any kind --
    no launcher, agents, hooks or AGENTS.md -- so changing one role's model
    does not reinstall the rest."""
    detection = detect(chome)
    try:
        saved = load_choice(chome)
    except ChoiceParseError as e:
        print(f"invalid saved model choice, not overwritten: {e}")
        return 1

    try:
        agents = role_agents(root)
        defaults = shipped_defaults(root, agents)
    except AnchorError as e:
        print(f"cannot read {root / 'agents'}: {e}")
        return 1
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"cannot read {root / 'models.json'}: {e}")
        return 1

    plans = plan_roles(agents, defaults, detection, saved)
    for line in render_mapping(plans, detection, chome, full=True):
        print(line)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--models", action="store_true")
    args = parser.parse_args(argv)

    root = CAI_ROOT
    home_dir = Path.home()
    chome = codex_home()

    if args.apply:
        return apply_answers(root, chome)
    if args.models:
        return show_models(root, chome)

    detection = detect(chome)
    try:
        saved = load_choice(chome)
    except ChoiceParseError as e:
        print(f"invalid saved model choice, not overwritten: {e}")
        return 1

    try:
        agents = role_agents(root)
        defaults = shipped_defaults(root, agents)
    except AnchorError as e:
        print(f"cannot rewrite {root / 'agents'}: {e}")
        return 1
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"cannot read {root / 'models.json'}: {e}")
        return 1

    plans = plan_roles(agents, defaults, detection, saved)
    try:
        contents = agent_bytes(root, plans)
    except AnchorError as e:
        print(f"cannot rewrite {root / 'agents'}: {e}")
        return 1

    answers_path = chome / ANSWERS_NAME
    if answers_path.is_file():
        try:
            answers_path.unlink()
        except OSError as e:
            print(f"could not remove stale {answers_path}: {e}")
        else:
            print(f"removed stale {answers_path}")

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
        written, removed = install_agents(root, chome, contents)
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

    for name in saved:
        if name not in agents:
            print(f"ignored saved role {name}: cai-codex has no such role")
    for line in render_mapping(plans, detection, chome, full=True):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
