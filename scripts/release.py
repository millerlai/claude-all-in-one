#!/usr/bin/env python3
"""
Cut a unified release: one version number for both the Claude Code and Codex
plugin trees, pinned by a git-subdir source on both marketplace files.

    python scripts/release.py prepare X.Y.Z [--base REF]
    python scripts/release.py cut X.Y.Z
    python scripts/release.py verify X.Y.Z
    python scripts/release.py publish X.Y.Z

This is Ours (CLAUDE.md, "Who a file is for"): it assumes this repo's layout,
so it lives at scripts/ rather than under plugins/cai/scripts/.

Design: docs/design/2026-09-26-release-versioning-detail.md, "scripts/release.py".

Exit codes: 0 success; 1 some check or external command failed; 2 bad
arguments or an unmet precondition (nothing written in that case). Matches
scripts/gen-codex.py:24-26's split.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class Marketplace(NamedTuple):
    file: str      # repo-relative path, e.g. ".claude-plugin/marketplace.json"
    plugin: str    # plugin entry "name" in that marketplace file, e.g. "cai"
    path: str      # repo-relative directory that entry serves, e.g. "plugins/cai"
    manifest: str  # manifest inside that directory, e.g. ".claude-plugin/plugin.json"


MARKETPLACES: tuple = (
    Marketplace(".claude-plugin/marketplace.json", "cai", "plugins/cai", ".claude-plugin/plugin.json"),
    Marketplace(".agents/plugins/marketplace.json", "cai-codex", "plugins/cai-codex", ".codex-plugin/plugin.json"),
)
PRODUCT_MANIFEST = "plugins/cai/.claude-plugin/plugin.json"
TRACK_FORMAT_FILES = ("plugins/cai/skills/track/SKILL.md", "plugins/cai/scripts/ledger.py",
                      "plugins/cai/scripts/pending.py")
FLOORS = (("Claude Code", "2.1.283"), ("codex-cli", "0.157.1"))


# ---------------------------------------------------------------------------
# Shared pure functions
# ---------------------------------------------------------------------------

def parse_version(text: str) -> tuple:
    m = VERSION_RE.match(text)
    if not m:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(g) for g in m.groups())


_VERSION_VALUE_RE = re.compile(r'"version"\s*:\s*"([^"]*)"')
_VERSION_KEY_RE = re.compile(r'("version"\s*:\s*")([^"]*)(")')
_REPOSITORY_VALUE_RE = re.compile(r'"repository"\s*:\s*"([^"]*)"')


def product_version(manifest_text: str) -> str:
    m = _VERSION_VALUE_RE.search(manifest_text)
    if not m:
        raise ValueError('no "version" key found')
    return m.group(1)


def repository_git_url(manifest_text: str) -> str:
    m = _REPOSITORY_VALUE_RE.search(manifest_text)
    if not m:
        raise ValueError('no "repository" key found')
    return m.group(1) + ".git"


def set_version(manifest_text: str, version: str) -> str:
    count = len(_VERSION_KEY_RE.findall(manifest_text))
    if count != 1:
        raise ValueError(f'expected exactly one "version" key, found {count}')
    return _VERSION_KEY_RE.sub(lambda m: m.group(1) + version + m.group(3), manifest_text, count=1)


def git_subdir_source(url: str, path: str, ref: str) -> dict:
    return {"source": "git-subdir", "url": url, "path": path, "ref": ref}


def _find_plugin_entry(obj: dict, plugin_name: str) -> dict:
    matches = [p for p in obj.get("plugins", []) if p.get("name") == plugin_name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one plugin named {plugin_name!r}, found {len(matches)}")
    return matches[0]


def pin_marketplace(text: str, market: Marketplace, url: str, ref: str) -> str:
    obj = json.loads(text)
    entry = _find_plugin_entry(obj, market.plugin)
    entry["source"] = git_subdir_source(url, market.path, ref)
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def pinned_ref(text: str, market: Marketplace) -> "str | None":
    obj = json.loads(text)
    entry = _find_plugin_entry(obj, market.plugin)
    source = entry.get("source")
    if isinstance(source, str):
        return None
    return source["ref"]


def draft_section(version: str, date: str, subjects: list, *,
                   first: bool, track_format_changed: bool, skipped: list) -> str:
    header = f"## v{version} — {date}"
    if first:
        floors = dict(FLOORS)
        body = (
            "First unified version: Claude Code and Codex now share one "
            "version number, and both install from this tag.\n\n"
            f"Requires Claude Code {floors['Claude Code']} or later and "
            f"codex-cli {floors['codex-cli']} or later. Check with "
            "`claude --version` and `codex --version`. Update codex-cli the "
            "way you installed it (it also updates itself between runs) "
            "before updating this plugin; an older codex-cli stops seeing it."
        )
        return header + "\n\n" + body

    groups = {"Added": [], "Fixed": [], "Other": []}
    for subject in subjects:
        if subject.startswith("feat"):
            groups["Added"].append(subject)
        elif subject.startswith("fix"):
            groups["Fixed"].append(subject)
        else:
            groups["Other"].append(subject)

    parts = [header]
    for name in ("Added", "Fixed", "Other"):
        items = groups[name]
        if not items:
            continue
        lines = "\n".join(f"- {s}" for s in items)
        parts.append(f"### {name}\n{lines}")

    if track_format_changed:
        parts.append(
            "Finish any track in progress before updating: the track's "
            "state format changed in this release.")

    if skipped:
        parts.append(
            "\n".join(f"Skipped: {v} (tagged, failed its check, never served)." for v in skipped))

    return "\n\n".join(parts)


def insert_section(changelog_text: "str | None", section: str) -> str:
    if changelog_text is None:
        return "# Changelog\n\n" + section + "\n"

    lines = changelog_text.splitlines(keepends=True)
    title_idx = None
    for i, line in enumerate(lines):
        if line.startswith("# Changelog"):
            title_idx = i
            break
    if title_idx is None:
        # No title line found -- treat the whole thing as sections and put
        # a title in front.
        return "# Changelog\n\n" + section + "\n\n" + changelog_text.strip("\n") + "\n"

    # Find the first existing "## v" section start, if any, after the title.
    insert_at = None
    for i in range(title_idx + 1, len(lines)):
        if lines[i].startswith("## v"):
            insert_at = i
            break

    # Carry forward any preamble text between the title and the first "## v"
    # section (e.g. a "Keep a Changelog"-style intro line) -- it belongs to
    # neither `head`'s title-only slice nor `tail`'s section slice, so it was
    # silently dropped before this was added.
    end = insert_at if insert_at is not None else len(lines)
    preamble = "".join(lines[title_idx + 1:end]).strip("\n")
    head = "".join(lines[:title_idx + 1]).rstrip("\n") + "\n\n"
    if preamble:
        head += preamble + "\n\n"

    if insert_at is None:
        return head + section + "\n"
    tail = "".join(lines[insert_at:]).rstrip("\n") + "\n"
    return head + section + "\n\n" + tail


def extract_section(changelog_text: str, version: str) -> "str | None":
    # (?!\d): a bare startswith("## v{version}") would also match a longer
    # version sharing the same digits ("1.2.1" matching "## v1.2.10 ...").
    heading = re.compile(rf"^## v{re.escape(version)}(?!\d)")
    lines = changelog_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if heading.match(line):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## v"):
            end = i
            break
    return "".join(lines[start:end]).strip("\n")


def run(argv: list, *, cwd, env: dict = None, timeout: float = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env=env, timeout=timeout,
                           capture_output=True, encoding="utf-8")


_VERSION_SUBSTRING_RE = re.compile(r"\d+\.\d+\.\d+")


def _extract_version_substring(text: str) -> "str | None":
    m = _VERSION_SUBSTRING_RE.search(text or "")
    return m.group(0) if m else None


def tool_versions() -> dict:
    result = {}
    for name in ("git", "gh", "claude", "codex"):
        path = shutil.which(name)
        if not path:
            result[name] = None
            continue
        try:
            done = run([path, "--version"], cwd=Path.cwd(), timeout=10)
        except (OSError, subprocess.SubprocessError):
            result[name] = None
            continue
        if done.returncode != 0:
            result[name] = None
            continue
        result[name] = _extract_version_substring(done.stdout)
    return result


def local_gate(repo: Path) -> list:
    failures = []
    validate_done = run([sys.executable, "scripts/validate.py"], cwd=repo, timeout=None)
    if validate_done.returncode != 0:
        failures.append("FAIL validate.py:\n" + _tail(validate_done))
    # No -n here: pyproject.toml's addopts already runs the suite on one
    # worker per CPU, and without pytest-xdist this fails like any other test.
    pytest_done = run([sys.executable, "-m", "pytest"], cwd=repo, timeout=None)
    if pytest_done.returncode != 0:
        failures.append("FAIL pytest:\n" + _tail(pytest_done))
    return failures


def _tail(done: subprocess.CompletedProcess, lines: int = 40) -> str:
    output = ((done.stdout or "") + (done.stderr or "")).strip()
    return "\n".join(output.splitlines()[-lines:])


def _print_command_failure(done: subprocess.CompletedProcess):
    output = ((done.stdout or "") + (done.stderr or "")).strip()
    if output:
        print("    ", output.replace("\n", "\n     "))


class _ToolMissing(RuntimeError):
    """Raised by _tool_path when a CLI vanishes from PATH between `prepare`
    and a later stage -- a runtime tool going missing mid-flow is an
    execution failure, not a bad-argument case, so callers turn this into a
    normal exit-1 FAIL rather than an uncaught traceback."""


def _tool_path(name: str) -> str:
    """Resolve name's full path via shutil.which() so every external-CLI
    call's argv[0] is an absolute path, never a bare name (design decision
    #22) -- a same-named file checked out into the maintainer's own working
    tree would otherwise run instead of the real tool. Two independent
    layers guard against that, because neither is sufficient alone:

    1. A bare shutil.which(name) is not enough on its own: on Windows,
       absent the NoDefaultCurrentDirectoryInExePath environment variable,
       NeedCurrentDirectoryForExePath makes it insert the current directory
       ahead of every PATH entry regardless of a `path=` argument (verified:
       shutil.which(name, path=one_dir) still checks cwd before one_dir), so
       a planted file in cwd would resolve first. Setting that variable
       disables the check for this process outright; restore whatever was
       there after. But this only works on CPython 3.12+, which is the
       first version whose shutil.which() consults that variable at all
       (_win_path_needs_curdir) -- 3.11 and earlier insert cwd
       unconditionally (Lib/shutil.py:1505-1510 on the 3.11 branch), so on
       those versions this call still returns a planted cwd file, this
       process's own environment-variable setting notwithstanding.
    2. Because of that gap, distrust whatever shutil.which() hands back:
       if the resolved path's directory is the current working directory,
       refuse it outright rather than ever returning it, regardless of
       which Python version or code path put it there."""
    had_var = "NoDefaultCurrentDirectoryInExePath" in os.environ
    old_value = os.environ.get("NoDefaultCurrentDirectoryInExePath")
    os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"
    try:
        path = shutil.which(name)
    finally:
        if had_var:
            os.environ["NoDefaultCurrentDirectoryInExePath"] = old_value
        else:
            del os.environ["NoDefaultCurrentDirectoryInExePath"]
    if path is None:
        raise _ToolMissing(name)
    resolved_dir = os.path.normcase(os.path.abspath(os.path.dirname(path)))
    cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    if resolved_dir == cwd:
        raise _ToolMissing(name)
    return path


def _reports_tool_missing(fn):
    """Wrap one of the four public stage functions so a _ToolMissing raised
    anywhere inside it (via _tool_path) becomes that function's own normal
    "FAIL ... exit 1" instead of an uncaught exception -- see _ToolMissing's
    docstring for why 1, not the 2 main() gives ValueError."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _ToolMissing as e:
            print(f"FAIL {e} not found on PATH")
            return 1
    return wrapper


# ---------------------------------------------------------------------------
# git helpers -- all real external calls go through run()
# ---------------------------------------------------------------------------

def _git(repo: Path, *args, timeout: float = 5):
    return run([_tool_path("git"), *args], cwd=repo, timeout=timeout)


def _git_status_paths(repo: Path) -> list:
    done = _git(repo, "status", "--porcelain")
    paths = []
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        # "XY path" or "XY old -> new"; take the final path token.
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip())
    return paths


def _local_tags(repo: Path) -> list:
    done = _git(repo, "tag", "-l", "v*")
    return [t.strip() for t in done.stdout.splitlines() if t.strip()]


def _remote_tags(repo: Path) -> list:
    done = _git(repo, "ls-remote", "origin", "refs/tags/v*", timeout=None)
    tags = []
    for line in done.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/tags/"):
            tags.append(parts[1][len("refs/tags/"):])
    return tags


def _all_version_tags(repo: Path) -> set:
    versions = set()
    for tag in _local_tags(repo) + _remote_tags(repo):
        if tag.startswith("v") and VERSION_RE.match(tag[1:]):
            versions.add(tag[1:])
    return versions


def _read_at_ref(repo: Path, ref: str, rel_path: str) -> "str | None":
    done = _git(repo, "show", f"{ref}:{rel_path}", timeout=None)
    if done.returncode != 0:
        return None
    return done.stdout


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def _loose_version_tuple(text: str) -> "tuple | None":
    substr = _extract_version_substring(text or "")
    if substr is None:
        return None
    return tuple(int(p) for p in substr.split("."))


def _which(name: str) -> "str | None":
    """Thin wrapper over shutil.which -- like _gen_codex, a seam so tests can
    stub the presence check without needing gh/claude/codex actually on the
    test machine's PATH (release.tool_versions/local_gate alone do not cover
    this: presence and auth are checked separately from version numbers)."""
    return shutil.which(name)


def _gh_auth_ok(repo: Path) -> bool:
    """Thin wrapper over `gh auth status` -- a seam so tests never make the
    real network call it requires."""
    return run([_tool_path("gh"), "auth", "status"], cwd=repo, timeout=None).returncode == 0


def _gen_codex(repo: Path) -> subprocess.CompletedProcess:
    """Runs scripts/gen-codex.py as a subprocess (design: "gen-codex 以子程序
    呼叫，不 import"). A separate module-level wrapper, not inlined into
    prepare(), purely so tests can monkeypatch this one call and exercise
    prepare()'s own logic on a minimal fixture repo without needing a full
    plugins/cai tree gen-codex.py would accept -- not one of the design's two
    named test seams (tool_versions/local_gate), added under the same
    "your call" allowance the spec gives for stubbing gen-codex."""
    return run([sys.executable, "scripts/gen-codex.py"], cwd=repo, timeout=None)


@_reports_tool_missing
def prepare(version: str, base: str = "origin/main", repo: Path = ROOT) -> int:
    if not VERSION_RE.match(version):
        print(f"FAIL version: not a version: {version!r}")
        return 2
    print(f"PASS version {version} is well-formed")

    status = _git(repo, "status", "--porcelain")
    if status.stdout.strip():
        print("FAIL working tree is not clean")
        return 2
    print("PASS working tree is clean")

    fetch = _git(repo, "fetch", "origin", "--tags", timeout=None)
    if fetch.returncode != 0:
        print("FAIL git fetch origin --tags")
        _print_command_failure(fetch)
        return 2
    print("PASS git fetch origin --tags")

    manifest_at_ref = _read_at_ref(repo, base, PRODUCT_MANIFEST)
    if manifest_at_ref is None:
        print(f"FAIL {PRODUCT_MANIFEST} not found on {base}")
        return 2
    current_version = product_version(manifest_at_ref)
    new_tuple = parse_version(version)
    existing_versions = {current_version} | _all_version_tags(repo)
    higher_than_all = all(new_tuple > parse_version(v) for v in existing_versions
                           if VERSION_RE.match(v))
    if not higher_than_all:
        print(f"FAIL {version} is not greater than every existing version/tag")
        return 2
    print(f"PASS {version} is greater than every existing version and tag")

    tag_name = f"v{version}"
    branch_name = f"release/{tag_name}"
    if tag_name in _local_tags(repo) or tag_name in _remote_tags(repo):
        print(f"FAIL tag {tag_name} already exists")
        return 2
    local_branch = _git(repo, "rev-parse", "--verify", "--quiet", branch_name)
    remote_branch = _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch_name}")
    if local_branch.returncode == 0 or remote_branch.returncode == 0:
        print(f"FAIL branch {branch_name} already exists")
        return 2
    print(f"PASS neither {tag_name} nor {branch_name} exists yet")

    unmerged = _git(repo, "branch", "-r", "--no-merged", "origin/main")
    in_flight = [
        line.strip() for line in unmerged.stdout.splitlines()
        if line.strip().startswith("origin/release/v")
    ]
    if in_flight:
        print(f"FAIL a release is already in flight: {in_flight[0].strip()}")
        return 2
    print("PASS no other release/v* branch is in flight")

    for name in ("git", "gh", "claude", "codex"):
        if _which(name) is None:
            print(f"FAIL {name} not found on PATH")
            return 2
    if not _gh_auth_ok(repo):
        print("FAIL gh auth status")
        return 2
    versions = tool_versions()
    for tool_name, floor in FLOORS:
        cli_name = "claude" if tool_name == "Claude Code" else "codex"
        found = versions.get(cli_name)
        found_tuple = _loose_version_tuple(found) if found else None
        if found_tuple is None or found_tuple[:3] < parse_version(floor):
            print(f"FAIL {cli_name} --version below floor {floor} (found {found!r})")
            return 2
    print("PASS git, gh, claude, codex found; gh authenticated; both CLIs meet their floors")

    switch = _git(repo, "switch", "-c", branch_name, base, timeout=None)
    if switch.returncode != 0:
        print(f"FAIL git switch -c {branch_name} {base}")
        _print_command_failure(switch)
        return 1

    manifest_path = repo / PRODUCT_MANIFEST
    manifest_text = manifest_path.read_text(encoding="utf-8")
    served_ref = pinned_ref(
        (repo / MARKETPLACES[0].file).read_text(encoding="utf-8"), MARKETPLACES[0])
    new_manifest_text = set_version(manifest_text, version)
    manifest_path.write_text(new_manifest_text, encoding="utf-8", newline="")

    url = repository_git_url(new_manifest_text)
    for market in MARKETPLACES:
        market_path = repo / market.file
        market_text = market_path.read_text(encoding="utf-8")
        market_path.write_text(pin_marketplace(market_text, market, url, tag_name),
                                encoding="utf-8", newline="")

    gen_codex = _gen_codex(repo)
    if gen_codex.returncode != 0:
        print("FAIL python scripts/gen-codex.py")
        _print_command_failure(gen_codex)
        print("git switch - to go back, git branch -D " + branch_name + " to discard")
        return 1
    print("PASS python scripts/gen-codex.py")

    first = served_ref is None
    subjects = []
    if not first:
        served_version = served_ref[1:] if served_ref.startswith("v") else served_ref
        log = _git(repo, "log", f"--format=%s", f"{served_ref}..HEAD", timeout=None)
        subjects = [line for line in log.stdout.splitlines() if line.strip()]
        diff = _git(repo, "diff", "--name-only", served_ref, "HEAD", "--", *TRACK_FORMAT_FILES,
                    timeout=None)
        track_format_changed = bool(diff.stdout.strip())
        skipped = sorted(
            (v for v in _all_version_tags(repo)
             if parse_version(v) > parse_version(served_version) and parse_version(v) < new_tuple),
            key=parse_version)
        skipped = [f"v{v}" for v in skipped]
    else:
        track_format_changed = False
        skipped = []

    date = datetime.date.today().isoformat()
    section = draft_section(version, date, subjects, first=first,
                             track_format_changed=track_format_changed, skipped=skipped)

    changelog_path = repo / "CHANGELOG.md"
    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else None
    changelog_path.write_text(insert_section(changelog_text, section), encoding="utf-8", newline="")

    print(f"edit CHANGELOG.md's {tag_name} section, then run "
          f"`python scripts/release.py cut {version}`")
    return 0


# ---------------------------------------------------------------------------
# cut
# ---------------------------------------------------------------------------

def _current_branch(repo: Path) -> str:
    done = _git(repo, "branch", "--show-current")
    return done.stdout.strip()


def _allowed_cut_paths() -> set:
    allowed = {PRODUCT_MANIFEST, "CHANGELOG.md"}
    for market in MARKETPLACES:
        allowed.add(market.file)
    return allowed


def _path_is_allowed(path: str, allowed: set) -> bool:
    norm = path.replace("\\", "/")
    if norm in allowed:
        return True
    return norm.startswith("plugins/cai-codex/")


@_reports_tool_missing
def cut(version: str, repo: Path = ROOT) -> int:
    if not VERSION_RE.match(version):
        print(f"FAIL version: not a version: {version!r}")
        return 2
    tag_name = f"v{version}"
    branch_name = f"release/{tag_name}"

    if _current_branch(repo) != branch_name:
        print(f"FAIL current branch is not {branch_name}")
        return 2
    print(f"PASS current branch is {branch_name}")

    head_subject = _git(repo, "log", "-1", "--format=%s").stdout.strip()
    porcelain = _git_status_paths(repo)
    already_committed = (head_subject == f"chore(release): {tag_name}" and not porcelain)

    if not already_committed:
        allowed = _allowed_cut_paths()
        extra = [p for p in porcelain if not _path_is_allowed(p, allowed)]
        if extra:
            print("FAIL changes outside the allowed set: " + ", ".join(extra))
            return 2
        print("PASS all changed paths are in the allowed set")

        manifest_text = (repo / PRODUCT_MANIFEST).read_text(encoding="utf-8")
        if product_version(manifest_text) != version:
            print(f"FAIL product manifest version is not {version}")
            return 2
        for market in MARKETPLACES:
            market_text = (repo / market.file).read_text(encoding="utf-8")
            if pinned_ref(market_text, market) != tag_name:
                print(f"FAIL {market.file} is not pinned to {tag_name}")
                return 2
        changelog_text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        section = extract_section(changelog_text, version)
        if not section:
            print(f"FAIL CHANGELOG.md has no v{version} section")
            return 2
        print("PASS product manifest, marketplaces and CHANGELOG.md are consistent")

        before = set(porcelain)
        failures = local_gate(repo)
        if failures:
            for f in failures:
                print(f)
            return 1
        print("PASS local gate: validate.py")
        print("PASS local gate: pytest")
        after = set(_git_status_paths(repo))
        if after != before:
            print("FAIL working tree changed during the local gate")
            return 1

        for path in porcelain:
            add_done = _git(repo, "add", path)
            if add_done.returncode != 0:
                print(f"FAIL git add {path}")
                return 1

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as f:
            f.write(f"chore(release): {tag_name}\n")
            msg_path = f.name
        try:
            commit_done = _git(repo, "commit", "-F", msg_path)
        finally:
            os.unlink(msg_path)
        if commit_done.returncode != 0:
            print("FAIL git commit")
            _print_command_failure(commit_done)
            return 1
        print(f"PASS committed chore(release): {tag_name}")

    tag_check = _git(repo, "rev-parse", "-q", "--verify", tag_name)
    if tag_check.returncode != 0:
        tag_done = _git(repo, "tag", "-a", tag_name, "-m", f"cai {tag_name}")
        if tag_done.returncode != 0:
            print(f"FAIL git tag -a {tag_name}")
            return 1
        print(f"PASS tagged {tag_name}")
    else:
        # `rev-parse <tag>` on an annotated tag returns the tag *object*'s own
        # sha, not the commit it points at -- `^{commit}` dereferences it so
        # this compares like with like.
        tag_sha = _git(repo, "rev-parse", f"{tag_name}^{{commit}}").stdout.strip()
        head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        if tag_sha != head_sha:
            print(f"FAIL local tag {tag_name} does not point at HEAD")
            return 2
        print(f"PASS local tag {tag_name} already points at HEAD")

    remote_tag = _git(repo, "ls-remote", "origin", f"refs/tags/{tag_name}", timeout=None)
    if remote_tag.stdout.strip():
        print(f"already pushed, run `release.py verify {version}` instead")
        return 2

    push_done = _git(repo, "push", "origin", f"refs/tags/{tag_name}", timeout=None)
    if push_done.returncode != 0:
        print(f"FAIL git push origin refs/tags/{tag_name}")
        _print_command_failure(push_done)
        return 1
    print(f"PASS {tag_name} pushed: this number cannot be reused from now on")

    return verify(version, repo=repo)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class PlatformCheck(NamedTuple):
    market: Marketplace
    home_env: str
    home_dir: str
    empty_marker: str
    commands: tuple


PLATFORM_CHECKS: tuple = (
    PlatformCheck(
        MARKETPLACES[0], "CLAUDE_CONFIG_DIR", "claude", "No marketplaces configured",
        (
            ("claude", "plugin", "marketplace", "add", "{market_dir}"),
            ("claude", "plugin", "install", "cai@{marketplace}"),
        ),
    ),
    PlatformCheck(
        MARKETPLACES[1], "CODEX_HOME", "codex", "No plugin marketplaces in scope.",
        (
            ("codex", "plugin", "marketplace", "add", "{market_dir}"),
            ("codex", "plugin", "add", "cai-codex@{marketplace}"),
        ),
    ),
)


def _platform_cache_ok(cache_dir: Path, manifest_rel: str, version: str, expected_files: set) -> bool:
    manifest_path = cache_dir / manifest_rel
    if not manifest_path.is_file():
        return False
    try:
        manifest_version = product_version(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if manifest_version != version:
        return False
    for rel in expected_files:
        if not (cache_dir / rel).is_file():
            return False
    return True


@_reports_tool_missing
def verify(version: str, repo: Path = ROOT, temp_root: Path = None) -> int:
    if not VERSION_RE.match(version):
        print(f"FAIL version: not a version: {version!r}")
        return 2
    tag_name = f"v{version}"
    branch_name = f"release/{tag_name}"

    local_sha = _git(repo, "rev-parse", "-q", "--verify", tag_name)
    if local_sha.returncode != 0:
        print(f"FAIL local tag {tag_name} does not exist")
        return 2
    local_sha = local_sha.stdout.strip()

    remote = _git(repo, "ls-remote", "origin", f"refs/tags/{tag_name}", timeout=None)
    remote_sha = remote.stdout.split()[0] if remote.stdout.strip() else None
    if remote_sha != local_sha:
        print(f"FAIL remote {tag_name} does not match the local tag")
        return 2

    if _current_branch(repo) != branch_name:
        print(f"FAIL current branch is not {branch_name}")
        return 2

    ancestor = _git(repo, "merge-base", "--is-ancestor", tag_name, "HEAD")
    if ancestor.returncode != 0:
        print(f"FAIL {tag_name} is not HEAD or an ancestor of HEAD")
        return 2
    print(f"PASS {tag_name} is pushed, matches local, and is on {branch_name}")

    if temp_root is None:
        temp_root = Path(tempfile.gettempdir()) / "cai-check"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    market_dir = temp_root / "market"
    market_dir.mkdir(parents=True)
    for check in PLATFORM_CHECKS:
        (temp_root / check.home_dir).mkdir(parents=True)

    marketplace_names = {}
    for market in MARKETPLACES:
        text = _read_at_ref(repo, tag_name, market.file)
        dest = market_dir / market.file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="")
        marketplace_names[market.file] = json.loads(text)["name"]

    failures = []
    for check in PLATFORM_CHECKS:
        home_dir = temp_root / check.home_dir
        env = dict(os.environ)
        env[check.home_env] = str(home_dir)
        cli = check.commands[0][0]
        cli_path = _tool_path(cli)
        marketplace_name = marketplace_names[check.market.file]

        list_done = run([cli_path, "plugin", "marketplace", "list"], cwd=repo, env=env, timeout=None)
        if check.empty_marker not in (list_done.stdout or ""):
            print(f"FAIL {cli}: isolation did not take (CONFIG dir not empty)")
            _print_command_failure(list_done)
            print("nothing installed; your real plugin config was not touched")
            return 2

        platform_failed = False
        for template in check.commands:
            argv = [part.format(market_dir=str(market_dir), marketplace=marketplace_name)
                    for part in template]
            argv[0] = cli_path
            done = run(argv, cwd=repo, env=env, timeout=None)
            if done.returncode != 0:
                print(f"FAIL {' '.join(argv)}")
                _print_command_failure(done)
                platform_failed = True

        cache_dir = (home_dir / "plugins" / "cache" / marketplace_name
                     / check.market.plugin / version)
        ls_tree = _git(repo, "ls-tree", "-r", "--name-only", tag_name, "--", check.market.path,
                       timeout=None)
        expected_files = set()
        prefix = check.market.path + "/"
        for line in ls_tree.stdout.splitlines():
            if line.startswith(prefix):
                expected_files.add(line[len(prefix):])
        if platform_failed or not _platform_cache_ok(
                cache_dir, check.market.manifest, version, expected_files):
            print(f"FAIL {cli}: {tag_name} is not correctly installed at {cache_dir}")
            failures.append(check)
        else:
            print(f"PASS {cli}: {tag_name} installed and verified")

    if failures:
        print(f"kept for inspection: {temp_root}")
        print(f"{tag_name} is pushed but not served. If this was transient (network), "
              f"rerun `release.py verify {version}`; otherwise this number is burned "
              "-- fix the cause and `prepare` the next number.")
        return 1

    shutil.rmtree(temp_root)

    remote_branch = _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch_name}")
    if remote_branch.returncode != 0:
        push_done = _git(repo, "push", "-u", "origin", branch_name, timeout=None)
        if push_done.returncode != 0:
            print(f"FAIL git push -u origin {branch_name}")
            return 1
        print(f"PASS pushed {branch_name}")

    gh_path = _tool_path("gh")
    pr_view = run([gh_path, "pr", "view", branch_name, "--json", "number,url,state"],
                  cwd=repo, timeout=None)
    if pr_view.returncode != 0:
        changelog_text = _read_at_ref(repo, "HEAD", "CHANGELOG.md")
        body = extract_section(changelog_text, version) or ""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md", encoding="utf-8") as f:
            f.write(body)
            body_path = f.name
        try:
            pr_create = run([gh_path, "pr", "create", "--base", "main", "--head", branch_name,
                             "--title", f"chore(release): {tag_name}", "--body-file", body_path],
                            cwd=repo, timeout=None)
        finally:
            os.unlink(body_path)
        if pr_create.returncode != 0:
            print("FAIL gh pr create")
            _print_command_failure(pr_create)
            return 1
        print(pr_create.stdout.strip())
    else:
        info = json.loads(pr_view.stdout)
        print(info.get("url", ""))

    print(f"once CI is green, run `python scripts/release.py publish {version}`")
    return 0


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------

@_reports_tool_missing
def publish(version: str, repo: Path = ROOT) -> int:
    if not VERSION_RE.match(version):
        print(f"FAIL version: not a version: {version!r}")
        return 2
    tag_name = f"v{version}"
    branch_name = f"release/{tag_name}"

    gh_path = _tool_path("gh")
    pr_view = run([gh_path, "pr", "view", branch_name, "--json", "number,state,headRefOid,url"],
                  cwd=repo, timeout=None)
    if pr_view.returncode != 0:
        print(f"FAIL no PR found for {branch_name}")
        return 2
    info = json.loads(pr_view.stdout)
    if info.get("state") != "OPEN":
        print(f"FAIL PR for {branch_name} is not OPEN")
        return 2

    checks = run([gh_path, "pr", "checks", str(info["number"])], cwd=repo, timeout=None)
    if checks.returncode == 8:
        print("CI is still running, rerun later")
        return 1
    if checks.returncode != 0:
        print(f"FAIL CI failed for {branch_name}")
        _print_command_failure(checks)
        return 1
    print("PASS CI is green")

    release_view = run([gh_path, "release", "view", tag_name], cwd=repo, timeout=None)
    if release_view.returncode != 0:
        changelog_text = _read_at_ref(repo, tag_name, "CHANGELOG.md")
        notes = extract_section(changelog_text, version) or ""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md", encoding="utf-8") as f:
            f.write(notes)
            notes_path = f.name
        try:
            release_create = run([gh_path, "release", "create", tag_name, "--verify-tag",
                                  "--title", tag_name, "--notes-file", notes_path],
                                 cwd=repo, timeout=None)
        finally:
            os.unlink(notes_path)
        if release_create.returncode != 0:
            print("FAIL gh release create")
            _print_command_failure(release_create)
            return 1
        print(f"PASS created GitHub release {tag_name}")

    head_sha = info["headRefOid"]
    print(f"gh pr merge {info['number']} --merge --match-head-commit {head_sha}")
    print("do not use --squash")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    prepare_ap = sub.add_parser("prepare")
    prepare_ap.add_argument("version")
    prepare_ap.add_argument("--base", default="origin/main")

    for name in ("cut", "verify", "publish"):
        p = sub.add_parser(name)
        p.add_argument("version")

    args = ap.parse_args(argv)

    try:
        if args.command == "prepare":
            return prepare(args.version, base=args.base)
        if args.command == "cut":
            return cut(args.version)
        if args.command == "verify":
            return verify(args.version)
        if args.command == "publish":
            return publish(args.version)
    except ValueError as e:
        print(f"FAIL {e}")
        return 2
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
