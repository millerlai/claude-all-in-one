#!/usr/bin/env python3
"""
Produce plugins/cai-codex/ from plugins/cai/, or check that it is current.

    python scripts/gen-codex.py                      # write plugins/cai-codex
    python scripts/gen-codex.py --check               # report drift, write nothing
    python scripts/gen-codex.py --source S --out O     # for tests, on temp trees

This is Ours (CLAUDE.md, "Who a file is for"): it assumes this repo's layout,
so it lives at scripts/ rather than under plugins/cai/scripts/.

Design: docs/design/2026-09-18-codex-support-detail.md, "### gen-codex.py".
U1 owns: collect/exclude, the override engine and its anchor rule, the
`${CLAUDE_PLUGIN_ROOT}` and `/cai:` rewrites, `--check`/`--source`/`--out`,
and the first override. U2 adds every other override and the rest of the
deny-list, including the fenced-code-block-only bash-syntax tokens. U3 (this
build) adds emit() -- agent TOMLs, `openai.yaml`, the manifest, the
`stages.json` agent prefix -- plus the fingerprint and `--release`, per D13
as modified 2026-09-19 (implementation-notes.md, "Unit 3 (decided before it
started)"): the fingerprint also covers the hand-written files that exist on
disk, and `--release` refuses only a version already published on the base
ref, not merely a non-increasing one.

Exit codes: 0 ok; 1 drift, anchor miss, deny-list hit, or an unreleased
change under `--check`; 2 bad arguments, an unreadable input file, or a
`--release` version already published on the base ref.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "plugins" / "cai"
DEFAULT_OUT = ROOT / "plugins" / "cai-codex"
SCRIPT_DIR = Path(__file__).resolve().parent
OVERRIDES_FILE = SCRIPT_DIR / "codex-overrides.json"
TIERS_FILE = SCRIPT_DIR / "codex-models.json"
RELEASE_FILE = SCRIPT_DIR / "codex-release.json"

# Design decisions, "Excluded from the Codex tree." Directories are matched
# by path prefix, files by exact relative path.
EXCLUDE_DIRS = {
    "skills/usage",       # replaced by nothing -- Codex has no usage report
    "skills/setup",       # replaced by the hand-written Codex setup skill
    "evals",              # `claude plugin eval` is Claude-only tooling
    "hooks",              # D4=B: setup writes the hook, not the generator
    ".claude-plugin",     # Claude's own manifest (name "cai", version 1.27.0); emit() writes the Codex one at .codex-plugin/ instead
}
# A directory name excluded wherever it occurs, not just at the tree root --
# unlike EXCLUDE_DIRS above, which names top-level paths. Not in the design's
# exclusion list, but not source either: a gitignored build artifact
# (.gitignore:6) holding binary .pyc a UTF-8 decode would crash on. Deviation,
# logged in implementation-notes.md.
EXCLUDE_DIR_NAMES = {"__pycache__"}
EXCLUDE_FILES = {
    "prices.json",
    "scripts/statusline.py",
    "scripts/install_statusline.py",
    "scripts/usage_report.py",
    "scripts/context_peak.py",
    "scripts/gen-models.py",
    "scripts/gen-commands.py",
}

# The hand-written files (D18) -- the generator never writes or deletes
# these, only leaves them alone. Paths are relative to the Codex tree root.
# `skills/setup/agents/openai.yaml` is not itself hand-written text -- it is
# `emit()`'s own OPENAI_YAML constant, added here (U5) only because the
# setup skill lives under EXCLUDE_DIRS's "skills/setup" and so never reaches
# emit()'s per-skill loop; without this entry --check would report it as
# stale drift and write mode would delete it.
HAND_WRITTEN = {
    "scripts/launcher.py",
    "scripts/install_codex.py",
    "skills/setup/SKILL.md",
    "skills/setup/agents/openai.yaml",
    "README.md",
}

# D2=A: every stages.json agent and every dispatch sentence names one of
# these, prefixed `cai_`. Fixed rather than derived from agents/*.md, so a
# rename shows up as a KeyError instead of silently changing what "dispatch
# position" matches.
AGENT_SHORT_NAMES = [
    "architect", "designer", "explorer", "implementer",
    "refactoring-detector", "reviewer", "security-reviewer",
    "shipper", "test-runner", "verifier",
]
_AGENT_NAME_ALT = "|".join(AGENT_SHORT_NAMES)
# A dispatch sentence names an agent in backticks (agents/verifier.md:15-16,
# rules/model-selection.md:42-44, stage-build.md's tier table, ...); the
# `stages.json` "agent" field is a separate JSON string, prefixed by
# _prefix_stages_json instead.
BARE_AGENT_NAME = re.compile(r"`(%s)`" % _AGENT_NAME_ALT)

MANIFEST_PATH = ".codex-plugin/plugin.json"
STAGES_JSON_PATH = "skills/track/stages.json"
MODELS_JSON_PATH = "models.json"

# `python ${CLAUDE_PLUGIN_ROOT}/scripts/<x>.py` -> the launcher call (D1=C).
PY_LAUNCHER = re.compile(r"python \$\{CLAUDE_PLUGIN_ROOT\}/scripts/([\w-]+)\.py")
PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"
# U7: no hard-coded interpreter name -- `<cai>` stands for whichever command
# line `$setup` recorded (its own `sys.executable`) and wrote into AGENTS.md.
CAI_ROOT_PREAMBLE = (
    '> `<cai>` is the cai-codex command line that `$setup` wrote into your '
    'instructions (the cai-codex block in AGENTS.md). `<cai-root>` is what '
    '`<cai> --root` prints.'
)

# Anywhere in the file, with one comment per entry citing the invariant it
# enforces (design's "gen-codex.py" / Deny-list). CLAUDE.md is additionally
# scoped below to rules/ and agents/ only -- a skill may still mention the
# user's own project file.
DENY_LIST = [
    "${CLAUDE_PLUGIN_ROOT}",  # R1/I6: the rewrite above must clear every one
    "/cai:",                  # I5: Claude dispatch syntax must not leak through
    "AskUserQuestion",        # I4/D10: Claude's menu tool name; Codex asks with request_user_input or numbered text
    "subagent_type",          # D9: Claude's `Agent(subagent_type=...)` parameter; Codex dispatch has no such parameter
    "CLAUDE_CODE_",           # I1: Claude Code's own env var prefix must not leak into Codex-facing text
    "~/.claude/",             # I1/D11: Claude's user config path; the Codex equivalent is under $CODEX_HOME (D1)
    'python "$HOME/.codex/cai/launcher.py"',  # U7: the old hard-coded interpreter form the rewrite above must no longer produce
]
# U7: the `python3`/bare-`py` variants of the same hard-coded interpreter
# form -- a survivor here means some text still names one interpreter
# literally instead of using the recorded `<cai>` command line.
HARD_CODED_LAUNCHER_PATTERN = re.compile(r'\b(?:python3|py) "\$HOME/\.codex/cai/launcher\.py"')
# D2/I5: a bare backtick-quoted agent name is the one rewrite() above should
# already have prefixed; a survivor means a dispatch site rewrite() missed,
# not intentional prose -- every real mention in this tree is the agent, not
# an English word (checked in implementation-notes.md, U3).
CLAUDE_MD_TOKEN = "CLAUDE.md"  # D11: Claude's project-instructions filename, scoped to rules/ and agents/ only

# Inside fenced code blocks only -- bash syntax PowerShell 5.1 does not
# parse (D16, C18). `${VAR:-` is matched as a pattern (any `${name:-`), the
# others as literal substrings.
FENCE = "```"
FENCED_DENY_LIST = [
    "&&",           # C18: PowerShell 5.1 has no `&&` (D16)
    "$(date",       # D16: bash command substitution, not PowerShell syntax
    "2>/dev/null",  # D16: bash-only stderr redirect target
]
FENCED_DENY_PATTERN = re.compile(r"\$\{\w+:-")  # D16: bash default-value expansion, not PowerShell syntax


class Override(NamedTuple):
    target: str
    anchor: str
    replacement: str
    why: str


class AnchorError(Exception):
    def __init__(self, target, detail):
        self.target = target
        self.detail = detail
        super().__init__(f"{target}: {detail}")


def _under_excluded_dir(rel: str) -> bool:
    """Whether `rel`'s directory chain contains an EXCLUDE_DIR_NAMES entry.
    Shared by the source-side exclusion below and, separately, by the
    `--out`-side comparison and stale-file deletion: a `__pycache__` under
    `--out` is git-ignored (.gitignore:6) and never shipped, but running any
    Codex-tree script from this checkout (a test import, or a maintainer
    running one by hand) creates one, and the design's on-disk comparison did
    not anticipate a bytecode cache inside the generated tree. Deviation,
    logged in implementation-notes.md, U4."""
    parts = rel.split("/")
    return any(part in EXCLUDE_DIR_NAMES for part in parts[:-1])


def _excluded(rel):
    if rel in EXCLUDE_FILES:
        return True
    if _under_excluded_dir(rel):
        return True
    for d in EXCLUDE_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return True
    return False


def collect(source: Path) -> dict:
    """Every non-excluded file under `source`, as relative-path -> bytes."""
    files = {}
    for p in sorted(source.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(source).as_posix()
        if _excluded(rel):
            continue
        files[rel] = p.read_bytes()
    return files


def relocate_catalog(files: dict) -> dict:
    """`refactoring-catalog/<name>/**` -> `skills/<name>/**`.

    Codex "discover[s] skills from the root `skills/` directory" and a
    manifest's own `skills` declaration "can't ... add to" what a portable
    package already ships (openai docs, developers.openai.com/plugins/build/
    plugins, fetched 2026-09-19) -- unlike Claude, there is no second,
    manifest-listed skills directory. Not in the design's tree layout;
    deviation, logged in implementation-notes.md, U3."""
    out = {}
    for rel in sorted(files):
        new_rel = "skills/" + rel[len("refactoring-catalog/") :] if rel.startswith(
            "refactoring-catalog/") else rel
        if new_rel in out:
            raise ValueError(
                f"relocate_catalog: {new_rel} already exists -- a catalog "
                "skill's name collides with an existing skill")
        out[new_rel] = files[rel]
    return out


def load_overrides(path: Path = OVERRIDES_FILE) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Override(o["target"], "\n".join(o["anchor"]), "\n".join(o["replacement"]), o["why"])
        for o in data["overrides"]
    ]


def apply_overrides(files: dict, overrides: list) -> dict:
    """Replace each override's anchor with its replacement. Raises
    AnchorError when a target is missing or its anchor is not found exactly
    once."""
    out = dict(files)
    for ov in overrides:
        if ov.target not in out:
            raise AnchorError(ov.target, "missing file")
        text = out[ov.target]
        count = text.count(ov.anchor)
        if count != 1:
            raise AnchorError(ov.target, f"found {count}")
        out[ov.target] = text.replace(ov.anchor, ov.replacement, 1)
    return out


def _split_frontmatter(text):
    """(end index just past the frontmatter's closing line, or 0). Mirrors
    gen-models.py's split_frontmatter (plugins/cai/scripts/gen-models.py:45-52),
    reimplemented rather than imported (that file sits under plugins/cai/)."""
    if not text.startswith("---"):
        return 0
    end = text.find("\n---", 3)
    if end == -1:
        return 0
    end += 4
    nl = text.find("\n", end)
    return len(text) if nl == -1 else nl + 1


def rewrite(files: dict) -> dict:
    """Mechanical token substitutions (D1=C, glossary "rewrite rule")."""
    out = {}
    for path, text in files.items():
        new, py_hits = PY_LAUNCHER.subn(r'<cai> \1', text)
        needs_preamble = py_hits > 0
        if PLUGIN_ROOT_TOKEN in new:
            new = new.replace(PLUGIN_ROOT_TOKEN, "<cai-root>")
            needs_preamble = True
        if needs_preamble:
            at = _split_frontmatter(new)
            new = new[:at] + CAI_ROOT_PREAMBLE + "\n\n" + new[at:]
        new = new.replace("/cai:", "$")
        new = BARE_AGENT_NAME.sub(lambda m: f"`cai_{m.group(1)}`", new)
        out[path] = new
    return out


def deny_hits(files: dict) -> list:
    """(path, line, token) for every DENY_LIST token found anywhere, plus
    CLAUDE.md scoped to rules/ and agents/, plus the fenced-code-block-only
    bash-syntax tokens (FENCED_DENY_LIST / FENCED_DENY_PATTERN)."""
    hits = []
    for path, text in files.items():
        claude_md_scoped = path.startswith("rules/") or path.startswith("agents/")
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(FENCE):
                in_fence = not in_fence
                continue
            for token in DENY_LIST:
                if token in line:
                    hits.append((path, lineno, token))
            m = HARD_CODED_LAUNCHER_PATTERN.search(line)
            if m:
                hits.append((path, lineno, m.group(0)))
            if claude_md_scoped and CLAUDE_MD_TOKEN in line:
                hits.append((path, lineno, CLAUDE_MD_TOKEN))
            for m in BARE_AGENT_NAME.finditer(line):
                hits.append((path, lineno, m.group(0)))
            if in_fence:
                for token in FENCED_DENY_LIST:
                    if token in line:
                        hits.append((path, lineno, token))
                if FENCED_DENY_PATTERN.search(line):
                    hits.append((path, lineno, "${VAR:-"))
    return hits


# ---------------------------------------------------------------------------
# emit() -- agent TOMLs, openai.yaml, the manifest, the stages.json prefix
# (design "Design decisions" / "Agents" and "Implicit invocation"; ### gen-codex.py)
# ---------------------------------------------------------------------------

OPENAI_YAML = "policy:\n  allow_implicit_invocation: false\n"

FRONTMATTER_KEY = re.compile(r"^([A-Za-z][\w-]*):", re.MULTILINE)
# Bash entries whose whole effect is reading history, not changing anything --
# the rest of a source agent's `tools:` line (Write, Edit, an unscoped Bash,
# or any other Bash scope such as `git:*`/`gh:*`/a test runner) means the
# agent can leave a mark, so `sandbox_mode` reads "workspace-write" for it.
# This is D17's "declared intent", not an enforced policy (E5: Codex does not
# honour sandbox_mode on a subagent) -- documentation only.
READ_ONLY_BASH_VERBS = {"git log", "git grep", "git diff", "git show"}
BASH_ENTRY = re.compile(r"Bash(?:\(([^)]*)\))?")


def _split_frontmatter_body(text):
    """(frontmatter body between the `---` delimiters, exclusive; rest of the
    text after the closing delimiter). (None, text) when there is none."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end], text[end + 4 :]


def _frontmatter_blocks(fm_body):
    """[(key, block)] for a frontmatter body, one entry per top-level key,
    each block carrying that key's own line(s) including any folded or
    block-scalar continuation lines. Reimplemented rather than sharing
    gen-models.py's split_frontmatter (that file sits under plugins/cai/)."""
    matches = list(FRONTMATTER_KEY.finditer(fm_body))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(fm_body)
        blocks.append((m.group(1), fm_body[start:stop]))
    return blocks


def _frontmatter_value(blocks, key):
    """A frontmatter key's scalar value, as one line: a YAML `>`/`>-` folded
    block scalar has its continuation lines joined with spaces (agent
    descriptions use this form, e.g. plugins/cai/agents/architect.md:3-6); a
    quoted one-liner (plugins/cai/skills/ship/SKILL.md:3) has its quotes
    stripped; anything else is returned as written after the colon."""
    for k, block in blocks:
        if k != key:
            continue
        text = block[len(key) + 1 :].strip()
        if text.startswith(">"):
            lines = text.splitlines()[1:]
            return " ".join(line.strip() for line in lines if line.strip())
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text
    return ""


def is_flagged_skill(text: str) -> bool:
    """Whether a SKILL.md's frontmatter declares `disable-model-invocation:
    true` (D8's source flag, C3)."""
    fm_body, _ = _split_frontmatter_body(text)
    if fm_body is None:
        return False
    blocks = _frontmatter_blocks(fm_body)
    return _frontmatter_value(blocks, "disable-model-invocation") == "true"


def trim_skill_frontmatter(text: str) -> str:
    """Keep only `name` and `description` in a flagged skill's frontmatter --
    the subset the E3/E4 probes used (design "Implicit invocation")."""
    fm_body, rest = _split_frontmatter_body(text)
    if fm_body is None:
        return text
    blocks = _frontmatter_blocks(fm_body)
    kept = "".join(block for key, block in blocks if key in ("name", "description"))
    return "---\n" + kept + "---" + rest


def _sandbox_mode(tools: str) -> str:
    if "Write" in tools or "Edit" in tools:
        return "workspace-write"
    for m in BASH_ENTRY.finditer(tools):
        scope = m.group(1)
        if scope is None:
            return "workspace-write"  # unscoped Bash
        verb = scope.rstrip("*").rstrip(":").strip()
        if verb not in READ_ONLY_BASH_VERBS:
            return "workspace-write"
    return "read-only"


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _agent_toml(short: str, source_text: str, role: str, tiers: dict, version: str) -> str:
    """The `agents/cai_<short>.toml` text for one source `agents/<short>.md`
    (design "Agents (D2=A, D3=A, D17)")."""
    fm_body, body = _split_frontmatter_body(source_text)
    blocks = _frontmatter_blocks(fm_body) if fm_body is not None else []
    description = _frontmatter_value(blocks, "description")
    tools = _frontmatter_value(blocks, "tools")
    tier = tiers[role]
    preamble = f"Tools declared allowed by the source (not enforced by Codex): {tools}"
    instructions = preamble + "\n\n" + body.strip("\n") + "\n"
    return (
        f"# cai-codex-version: {version}\n"
        f"name = \"cai_{short}\"\n"
        f"description = {_toml_string(description)}\n"
        f"model = {_toml_string(tier['model'])}\n"
        f"model_reasoning_effort = {_toml_string(tier['effort'])}\n"
        f"sandbox_mode = {_toml_string(_sandbox_mode(tools))}  # declared intent, unenforced by Codex (E5)\n"
        f"developer_instructions = '''\n{instructions}'''\n"
    )


def load_tiers(path: Path = TIERS_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["roles"]


def _load_roles(files: dict) -> dict:
    """`agents/<name>.md` -> role, read from the source's own models.json
    (glossary: "role"), so re-tiering a role there does not need a second
    edit here."""
    spec = json.loads(files[MODELS_JSON_PATH])
    return spec["assignments"]


def _prefix_stages_json(text: str) -> str:
    """`"agent": "x"` -> `"agent": "cai_x"`, a targeted edit rather than a
    JSON round-trip so the source file's own formatting survives untouched
    (design "Agents": "the stages.json ... agent column")."""
    return re.sub(r'("agent":\s*)"([\w-]+)"', r'\1"cai_\2"', text)


def _manifest(version: str) -> str:
    """`.codex-plugin/plugin.json` (D13; the shape E3 observed under a cached
    version directory, raw/e3-exec-dollar-form.jsonl:5)."""
    return json.dumps(
        {
            "name": "cai-codex",
            "version": version,
            "description": (
                "Codex CLI counterpart of the cai plugin: the same "
                "cost-tiered agents, skills and rules, generated from "
                "plugins/cai by scripts/gen-codex.py."
            ),
            "skills": "./skills/",
        },
        indent=2,
    ) + "\n"


def emit(files: dict, tiers: dict, version: str) -> dict:
    """Step 4 of the generation order: agent TOMLs, `openai.yaml`, the
    manifest, and the `stages.json` prefix. `files` is the fully overridden
    and rewritten source tree (str -> str); returns a new str -> str dict,
    ready for the caller to UTF-8-encode."""
    out = dict(files)
    roles = _load_roles(files)

    for path in sorted(files):
        if path.startswith("agents/") and path.endswith(".md"):
            short = path[len("agents/") : -len(".md")]
            role = roles[path]
            out[f"agents/cai_{short}.toml"] = _agent_toml(short, files[path], role, tiers, version)
            del out[path]
        elif path.endswith("SKILL.md") and is_flagged_skill(files[path]):
            skill_dir = path[: -len("SKILL.md")]
            out[skill_dir + "agents/openai.yaml"] = OPENAI_YAML
            out[path] = trim_skill_frontmatter(files[path])

    if STAGES_JSON_PATH in out:
        out[STAGES_JSON_PATH] = _prefix_stages_json(out[STAGES_JSON_PATH])

    out[MANIFEST_PATH] = _manifest(version)
    return out


def fingerprint(files: dict) -> str:
    """SHA-256 over the sorted (relative path, bytes) pairs of every file in
    `files`, the manifest excluded (D13 as modified 2026-09-19: the caller
    adds the hand-written files that exist on disk before calling this)."""
    h = hashlib.sha256()
    for rel in sorted(files):
        if rel == MANIFEST_PATH:
            continue
        content = files[rel]
        if isinstance(content, str):
            content = content.encode("utf-8")
        h.update(rel.encode("utf-8") + b"\x00" + content + b"\x00")
    return "sha256:" + h.hexdigest()


# ---------------------------------------------------------------------------
# Release record (D13 as modified 2026-09-19, implementation-notes.md "Unit 3
# (decided before it started)"): the fingerprint also covers the hand-written
# files that exist on disk, and `--release` refuses only a version already
# published on the base ref, not merely a non-increasing one.
# ---------------------------------------------------------------------------

def load_release_record(path: Path = RELEASE_FILE):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _git(cwd, *args):
    """Same shape as preflight.py's own git() helper -- duplicated rather
    than imported, since preflight.py is out of scope for this change and
    the two would otherwise couple two independently-versioned CLI surfaces."""
    try:
        return subprocess.run(["git", *args], cwd=cwd or None,
                               capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None


def find_base_ref(cwd):
    """The same chain as preflight.py's find_base_ref: the remote's default
    branch if origin answers, else a local main or master."""
    done = _git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if done and done.returncode == 0:
        return done.stdout.strip()
    for ref in ("origin/main", "origin/master", "main", "master"):
        done = _git(cwd, "rev-parse", "--verify", "--quiet", ref)
        if done and done.returncode == 0:
            return ref
    return None


def read_published_record(cwd, ref, rel_path="scripts/codex-release.json"):
    """The release record committed at `ref`, or None when `ref` is None, the
    file does not exist there, or its contents are not the expected JSON."""
    if ref is None:
        return None
    done = _git(cwd, "show", f"{ref}:{rel_path}")
    if done is None or done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def check_unreleased(working_record, published_record, current_fingerprint):
    """(is_unreleased, reason) for `--check`'s UNRELEASED rule. Pure: takes
    the working record (this repo's scripts/codex-release.json, or None), the
    base ref's published record (or None -- no base ref, or no file there,
    both skip rule (b)), and the freshly computed fingerprint."""
    if working_record is None:
        return True, "no release record recorded -- run --release <version>"
    if working_record.get("fingerprint") != current_fingerprint:
        return True, "output changed, run --release <greater version>"
    if published_record is not None:
        same_version = published_record.get("version") == working_record.get("version")
        if same_version and published_record.get("fingerprint") != current_fingerprint:
            return True, ("output changed after %s was published without a "
                          "version bump" % working_record.get("version"))
    return False, ""


def _version_tuple(v):
    try:
        return tuple(int(p) for p in v.split("."))
    except (AttributeError, ValueError):
        return (0,)


def release_refusal(new_version, published_record):
    """Whether `--release new_version` must be refused (exit 2): D13 as
    modified -- refuse only when new_version is lower than, or equal to, the
    version already published on the base ref. Re-recording the working
    version is allowed when the base ref has no record, or a different one."""
    if published_record is None:
        return False
    return _version_tuple(new_version) <= _version_tuple(published_record.get("version", "0.0.0"))


def _diff_with_disk(out: Path, files: dict) -> list:
    """Relative paths that differ from, or are missing from, the on-disk
    tree, plus generated files on disk that this run no longer produces."""
    drift = []
    for rel, content in files.items():
        p = out / rel
        if not p.is_file() or p.read_bytes() != content:
            drift.append(rel)
    if out.is_dir():
        for p in out.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(out).as_posix()
            if _under_excluded_dir(rel):
                continue
            if rel not in files and rel not in HAND_WRITTEN:
                drift.append(rel)
    return sorted(set(drift))


def _write_tree(out: Path, files: dict):
    out.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    for p in out.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(out).as_posix()
        if _under_excluded_dir(rel):
            continue
        if rel not in files and rel not in HAND_WRITTEN:
            p.unlink()


def build(source: Path, out: Path, check: bool, release: str = None,
          release_file: Path = RELEASE_FILE, project_dir: Path = ROOT) -> int:
    raw = relocate_catalog(collect(source))
    try:
        text_files = {rel: content.decode("utf-8") for rel, content in raw.items()}
    except UnicodeDecodeError as e:
        print(f"{e}")
        return 2

    try:
        overridden = apply_overrides(text_files, load_overrides())
    except AnchorError as e:
        print(f"ANCHOR {e}")
        return 1

    rewritten = rewrite(overridden)

    # The version stamp: --release's own value while writing a release, else
    # whatever is currently recorded (glossary "version stamp"; D13).
    working_record = load_release_record(release_file)
    version = release or (working_record["version"] if working_record else "0.0.0")
    emitted = emit(rewritten, load_tiers(), version)

    hits = deny_hits(emitted)
    for path, lineno, token in hits:
        print(f"DENY {path}:{lineno}: {token}")
    if hits:
        print(f"{len(hits)} finding(s)")
        return 1

    encoded = {rel: text.encode("utf-8") for rel, text in emitted.items()}

    # Fingerprint: every emitted file, the manifest excluded, plus whichever
    # hand-written files (D18) already exist under `out` (D13 as modified).
    fp_files = dict(encoded)
    for hw in HAND_WRITTEN:
        p = out / hw
        if p.is_file():
            fp_files[hw] = p.read_bytes()
    current_fp = fingerprint(fp_files)

    base = find_base_ref(project_dir)
    if base is None:
        print("SKIP release base unavailable")
        published_record = None
    else:
        published_record = read_published_record(project_dir, base)

    if check:
        drift = _diff_with_disk(out, encoded)
        for rel in drift:
            print(f"DRIFT {rel}")
        unreleased, reason = check_unreleased(working_record, published_record, current_fp)
        if unreleased:
            print(f"UNRELEASED: {reason}")
        print(f"{len(encoded)} file(s) checked, {len(drift)} finding(s)")
        return 1 if (drift or unreleased) else 0

    if release and release_refusal(release, published_record):
        print(f"--release {release}: {published_record['version']} is already "
              f"published on {base}")
        return 2

    _write_tree(out, encoded)

    if release:
        # newline="" -- write_text's platform newline translation would turn
        # this file's "\n" into "\r\n" on Windows, churning it against the
        # LF-only copy already committed.
        release_file.write_text(
            json.dumps({"version": release, "fingerprint": current_fp}, indent=2) + "\n",
            encoding="utf-8", newline="")
        print(f"released {release}")

    print(f"{len(encoded)} file(s) generated, 0 finding(s)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report drift, write nothing")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--release", metavar="X.Y.Z", help="write the release record at this version")
    args = ap.parse_args(argv)

    if not args.source.is_dir():
        print(f"no such source directory: {args.source}")
        return 2

    return build(args.source, args.out, args.check, args.release)


if __name__ == "__main__":
    sys.exit(main())
