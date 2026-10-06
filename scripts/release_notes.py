#!/usr/bin/env python3
"""Draft a release's CHANGELOG section with Copilot CLI, and check the draft.

Run by `release_actions.py notes` in the cut-release workflow. Everything here
except `run_copilot` and `collect` is pure, so the tests need neither a model
nor GitHub. The Copilot flags and the session check come from the smoke test
recorded in the release-notes design: an empty `--available-tools=` restricts
nothing, a non-empty one and `--deny-tool` do, so every call is locked down
and every session is checked for the tools it was actually offered.
"""
import json
import os
import re
import tempfile
from pathlib import Path

import release

PROMPT_FILE = Path(__file__).with_name("release-notes-prompt.md")
MODEL = "claude-sonnet-5"
# One tool, because whether zero can be requested was never tested; this one
# reads only Copilot's own documentation.
ALLOWED_TOOLS = frozenset({"fetch_copilot_cli_documentation"})
# Linux caps a single argv string at 128 KiB, and stdin is not read as a prompt.
MAX_PROMPT_BYTES = 100_000
MAX_BODY_CHARS = 4_000
MAX_SECTION_CHARS = 20_000
COPILOT_TIMEOUT = 600

_SQUASH_REF = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_REF = re.compile(r"^Merge pull request #(\d+) from (\S+)")
_VERDICT = re.compile(r"^TRACK_FORMAT_CHANGED:\s*(yes|no)\s*$", re.IGNORECASE)


def pr_refs(subjects: list) -> list:
    """PR numbers in first-parent commit subjects, oldest mention first. A
    release PR's own merge is not a change to describe."""
    found = []
    for subject in subjects:
        merge = _MERGE_REF.match(subject)
        if merge:
            if "/release/v" in merge.group(2) or merge.group(2).startswith("release/v"):
                continue
            number = int(merge.group(1))
        else:
            squash = _SQUASH_REF.search(subject)
            if not squash or subject.startswith("chore(release): v"):
                continue
            number = int(squash.group(1))
        if number not in found:
            found.append(number)
    return found


def is_maintainer_only(paths: list) -> bool:
    # Users receive only what is under plugins/; cai-codex has hand-written
    # files of its own, so the whole tree counts.
    return not any(p.replace("\\", "/").startswith("plugins/") for p in paths)


def floors_line(previous_section: str, previous_version: str) -> str:
    floors = dict(release.FLOORS)
    pair = f"Claude Code {floors['Claude Code']} or later and codex-cli {floors['codex-cli']} or later"
    if pair in previous_section:
        return f"Requires {pair}, unchanged from v{previous_version}."
    return f"Requires {pair}."


def _data(text: str) -> str:
    # Data must not be able to close its own <<<BEGIN/<<<END block.
    return text.replace("<<<", "<<")


def _pr_block(prs: list, body_chars: int) -> str:
    parts = []
    for pr in prs:
        body = (pr.get("body") or "").strip()
        if len(body) > body_chars:
            body = body[:body_chars] + "\n[... trimmed]"
        parts.append(f"#{pr['number']} {pr['title']}\n{body}".rstrip())
    return "\n\n".join(parts) if parts else "(none)"


def build_prompt(template: str, *, date: str, previous_version: str, previous_section: str,
                 user_prs: list, maintainer_prs: list, track_diff: str) -> str:
    values = {
        "{{DATE}}": date,
        "{{PREVIOUS_VERSION}}": previous_version,
        "{{FLOORS_LINE}}": floors_line(previous_section, previous_version),
        "{{PREVIOUS_SECTION}}": _data(previous_section),
        "{{USER_PRS}}": _data(_pr_block(user_prs, MAX_BODY_CHARS)),
        "{{MAINTAINER_PRS}}": _data(_pr_block(maintainer_prs, 0)),
        "{{TRACK_DIFF}}": _data(track_diff) or "(empty)",
    }
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(key, value)
    size = len(prompt.encode("utf-8"))
    if size >= MAX_PROMPT_BYTES:
        raise ValueError(f"prompt too large for one argument: {size} bytes")
    return prompt


def read_session(jsonl: str) -> tuple:
    """The model's last reply, and every reason not to trust the session."""
    failures, reply, tools_seen, exit_code = [], "", None, None
    servers = {}
    for line in jsonl.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            failures.append("Copilot output has a line that is not JSON")
            continue
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "assistant.message" and data.get("content"):
            reply = data["content"]
        elif kind == "session.mcp_servers_loaded":
            servers.update({s.get("name"): s.get("status") for s in data.get("servers", [])})
        elif kind == "session.usage_checkpoint":
            for state in data.get("promptCacheBreakState", []):
                for model in (state.get("models") or {}).values():
                    names = {t.get("name") for t in model.get("tools", [])}
                    tools_seen = names if tools_seen is None else tools_seen | names
        elif kind == "result":
            exit_code = event.get("exitCode")
    if tools_seen is None:
        failures.append("Copilot reported no tool list; cannot confirm tools were locked")
    elif tools_seen != ALLOWED_TOOLS:
        failures.append(f"Copilot offered tools {sorted(tools_seen)}, "
                        f"not exactly {sorted(ALLOWED_TOOLS)}")
    for name, status in sorted(servers.items()):
        if status != "disabled":
            failures.append(f"MCP server {name} was {status}, not disabled")
    if exit_code != 0:
        failures.append(f"Copilot run exit code was {exit_code}")
    if not reply:
        failures.append("Copilot returned no reply")
    return reply, failures


def split_verdict(reply: str) -> tuple:
    lines = reply.rstrip().splitlines()
    if lines:
        match = _VERDICT.match(lines[-1].strip())
        if match:
            return "\n".join(lines[:-1]).rstrip(), match.group(1).lower() == "yes"
    return reply.rstrip(), None


def validate_section(section: str, *, version: str, date: str, user_prs: set) -> list:
    failures = []
    lines = section.splitlines()
    first = f"## v{version} — {date}"
    if not lines or lines[0] != first:
        failures.append(f"first line is not '{first}'")
    if "### What to do when you update" not in lines:
        failures.append("no '### What to do when you update' heading")
    if "/plugin update cai" not in section:
        failures.append("no Claude Code update instruction ('/plugin update cai')")
    if "codex plugin" not in section:
        failures.append("no Codex update instruction ('codex plugin')")
    if "{{NEW_VERSION}}" in section:
        failures.append("a {{NEW_VERSION}} placeholder was left in the section")
    if any(re.match(r"#{1,2} ", line) for line in lines[1:]):
        failures.append("a second '#' or '##' heading inside the section")
    cited = {int(n) for n in re.findall(r"#(\d+)\b", section)}
    for number in sorted(cited - set(user_prs)):
        failures.append(f"cites #{number}, which is not a user-facing PR of this release")
    for number in sorted(set(user_prs) - cited):
        failures.append(f"does not mention #{number}")
    if len(section) > MAX_SECTION_CHARS:
        failures.append(f"section is too long ({len(section)} characters)")
    return failures


def suggest_bump(subjects: list, skill_changes: list, track_changed: bool) -> str:
    """README's Compatibility table: removing or renaming a skill is MAJOR;
    adding one, a track-format change or a new feature is MINOR."""
    statuses = [line.split("\t", 1)[0][:1] for line in skill_changes if line.strip()]
    if any(s in ("D", "R") for s in statuses):
        return "major"
    if "A" in statuses or track_changed or any(re.match(r"feat(\(|!|:)", s) for s in subjects):
        return "minor"
    return "patch"


def next_version(current: str, bump: str) -> str:
    major, minor, patch = release.parse_version(current)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def copilot_argv(copilot: str, prompt: str) -> list:
    return [copilot, "-p", prompt, f"--model={MODEL}", "--no-ask-user", "--output-format=json",
            "--available-tools=" + ",".join(sorted(ALLOWED_TOOLS)),
            "--deny-tool=shell", "--deny-tool=write", "--deny-tool=read", "--deny-tool=url",
            "--disable-builtin-mcps", "--secret-env-vars=COPILOT_GITHUB_TOKEN"]


def copilot_env(environ: dict) -> dict:
    # The job's GH_TOKEN and anything else stays out of the model's process.
    keep = ("PATH", "HOME", "COPILOT_GITHUB_TOKEN", "SYSTEMROOT", "TEMP", "TMP")
    env = {k: environ[k] for k in keep if k in environ}
    env["COPILOT_AUTO_UPDATE"] = "false"
    return env


def replace_section(changelog_text: str, version: str, section: str) -> str:
    heading = re.compile(rf"^## v{re.escape(version)}(?!\d)")
    lines = changelog_text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md has no v{version} section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## v")),
               len(lines))
    tail = "".join(lines[end:])
    return "".join(lines[:start]) + section.rstrip("\n") + ("\n\n" + tail if tail else "\n")


def _git_out(repo: Path, *args) -> str:
    done = release._git(repo, *args, timeout=None)
    if done.returncode:
        raise RuntimeError(f"git {args[0]} failed: {done.stderr.strip()}")
    return done.stdout


def gh_pr(repo: Path, number: int) -> dict:
    done = release.run([release._tool_path("gh"), "pr", "view", str(number), "--json",
                        "number,title,body,files"], cwd=repo, timeout=120)
    if done.returncode:
        raise RuntimeError(f"gh pr view {number} failed: {done.stderr.strip()}")
    return json.loads(done.stdout)


def collect(repo: Path, served_ref: str, head: str, pr=gh_pr) -> dict:
    """What changed since the served tag, read from git and each PR."""
    subjects = [s for s in _git_out(repo, "log", "--first-parent", "--format=%s",
                                    f"{served_ref}..{head}").splitlines() if s.strip()]
    user, maintainer = [], []
    for number in pr_refs(subjects):
        info = pr(repo, number)
        paths = [f.get("path", "") for f in info.get("files", [])]
        (maintainer if is_maintainer_only(paths) else user).append(info)
    previous_version = served_ref[1:] if served_ref.startswith("v") else served_ref
    changelog = _git_out(repo, "show", f"{head}:CHANGELOG.md")
    header = re.search(rf"^## v{re.escape(previous_version)}(?!\d).*$", changelog, re.MULTILINE)
    body = release.extract_section(changelog, previous_version) or ""
    return {
        "subjects": subjects,
        "user_prs": user,
        "maintainer_prs": maintainer,
        "previous_version": previous_version,
        "previous_section": (header.group(0) + "\n\n" + body) if header else body,
        "track_diff": _git_out(repo, "diff", served_ref, head, "--", *release.TRACK_FORMAT_FILES),
        "skill_changes": _git_out(repo, "diff", "--name-status", served_ref, head, "--",
                                  "plugins/cai/skills/*/SKILL.md").splitlines(),
    }


def run_copilot(prompt: str):
    # An empty working directory: even a tool that slipped past the flags
    # would find no checkout to read.
    with tempfile.TemporaryDirectory() as empty:
        return release.run(copilot_argv(release._tool_path("copilot"), prompt), cwd=empty,
                           env=copilot_env(dict(os.environ)), timeout=COPILOT_TIMEOUT)
