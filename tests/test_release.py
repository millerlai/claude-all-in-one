"""Tests for scripts/release.py.

`release.py` is a normal (non-hyphenated) module name, unlike gen-codex.py,
so it is imported directly rather than through importlib -- see
tests/test_gen_codex.py:11-16 for why gen-codex.py needs the importlib
dance and release.py does not.

Integration tests for `prepare`/`cut` build a real local `origin` with
`git init --bare` plus a working clone, per the design's Verification
section. `release.tool_versions`, `release.local_gate`, `release._which` and
`release._gh_auth_ok` are monkeypatched everywhere so no test ever shells out
to a real `gh`/`claude`/`codex`, or touches the network. `release._gen_codex`
is also stubbed for the same reason: making prepare()'s own logic pass
gen-codex.py for real would require a full plugins/cai fixture tree just to
satisfy its deny-list and models.json lookups, which is out of scope for
testing prepare()'s own preflight/action logic (noted in the spec as the
implementer's call to make).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release

# Captured before the autouse _stub_tools fixture below replaces
# release._gh_auth_ok with a lambda for every test in this file -- the one
# test that exercises _gh_auth_ok's own body needs the real function.
_REAL_GH_AUTH_OK = release._gh_auth_ok


# ---------------------------------------------------------------------------
# Fixture content -- read the real files, never hardcode a copy.
# ---------------------------------------------------------------------------

REAL_PLUGIN_JSON = (REPO_ROOT / "plugins/cai/.claude-plugin/plugin.json").read_text(encoding="utf-8")


def _legacy_form(marketplace_text):
    """The real marketplace file with every plugin entry's `source` set back
    to the relative-path string it had before the first release. The working
    tree's own form cannot be trusted as a fixture: `release.py prepare` pins
    it to git-subdir mid-release, and main stays pinned after the first
    release, so tests that need the legacy form build it here."""
    obj = json.loads(marketplace_text)
    for entry in obj["plugins"]:
        entry["source"] = f"./plugins/{entry['name']}"
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


LEGACY_CLAUDE_MARKETPLACE = _legacy_form(
    (REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
LEGACY_CODEX_MARKETPLACE = _legacy_form(
    (REPO_ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))

# Derived from the real manifest rather than hard-coded, so this file does not
# go stale every time scripts/release.py itself bumps the product version
# (implementation-notes.md, "Merge with main"). CURRENT_VERSION is today's
# real product version; NEXT_VERSION/HIGHER_VERSION/OTHER_VERSION are minors
# above it, used wherever a test needs a version prepare()/cut() will accept
# (or, for HIGHER_VERSION/OTHER_VERSION, one clearly higher still).
_CURRENT = json.loads(REAL_PLUGIN_JSON)["version"]
CURRENT_VERSION = _CURRENT
_MAJOR, _MINOR, _PATCH = (int(p) for p in _CURRENT.split("."))
NEXT_VERSION = f"{_MAJOR}.{_MINOR + 1}.0"
HIGHER_VERSION = f"{_MAJOR}.{_MINOR + 2}.0"
OTHER_VERSION = f"{_MAJOR}.{_MINOR + 3}.0"


def _run_git(args, cwd, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                            encoding="utf-8")
    if check and result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stdout}\n{result.stderr}")
    return result


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["0.0.0", "1.37.0", "12.3.400"])
def test_parse_version_accepts(text):
    assert release.parse_version(text) == tuple(int(p) for p in text.split("."))


@pytest.mark.parametrize("text", ["1.37", "v1.37.0", "1.37.0-rc1", "01.37.0", ""])
def test_parse_version_rejects(text):
    with pytest.raises(ValueError):
        release.parse_version(text)


# ---------------------------------------------------------------------------
# product_version / repository_git_url / set_version
# ---------------------------------------------------------------------------

def test_product_version_reads_real_manifest():
    assert release.product_version(REAL_PLUGIN_JSON) == CURRENT_VERSION


def test_set_version_only_changes_the_version_value():
    new_text = release.set_version(REAL_PLUGIN_JSON, NEXT_VERSION)

    assert release.product_version(new_text) == NEXT_VERSION
    # Every other byte is unchanged: replacing the new version back in
    # reproduces the original text exactly.
    assert new_text.replace(f'"version": "{NEXT_VERSION}"', f'"version": "{CURRENT_VERSION}"', 1) == REAL_PLUGIN_JSON


def test_set_version_rejects_zero_version_keys():
    text = '{"name": "x"}'
    with pytest.raises(ValueError):
        release.set_version(text, "1.0.0")


def test_set_version_rejects_two_version_keys():
    text = '{"version": "1.0.0", "nested": {"version": "2.0.0"}}'
    with pytest.raises(ValueError):
        release.set_version(text, "3.0.0")


def test_repository_git_url_appends_dot_git():
    assert release.repository_git_url(REAL_PLUGIN_JSON) == (
        "https://github.com/millerlai/claude-all-in-one.git")


# ---------------------------------------------------------------------------
# pin_marketplace / pinned_ref
# ---------------------------------------------------------------------------

def test_pinned_ref_is_none_for_legacy_string_form():
    market = release.MARKETPLACES[0]
    assert release.pinned_ref(LEGACY_CLAUDE_MARKETPLACE, market) is None


def test_pin_marketplace_replaces_only_the_target_source():
    market = release.MARKETPLACES[0]
    url = "https://github.com/millerlai/claude-all-in-one.git"
    new_text = release.pin_marketplace(LEGACY_CLAUDE_MARKETPLACE, market, url, "v1.37.0")

    assert new_text.endswith("\n") and not new_text.endswith("\n\n")
    obj = json.loads(new_text)
    entry = next(p for p in obj["plugins"] if p["name"] == "cai")
    assert entry["source"] == {
        "source": "git-subdir", "url": url, "path": "plugins/cai", "ref": "v1.37.0",
    }
    # Every other top-level key is untouched.
    assert entry["description"] == json.loads(LEGACY_CLAUDE_MARKETPLACE)["plugins"][0]["description"]
    assert list(obj.keys()) == list(json.loads(LEGACY_CLAUDE_MARKETPLACE).keys())

    assert release.pinned_ref(new_text, market) == "v1.37.0"


def test_pin_marketplace_codex_marketplace():
    market = release.MARKETPLACES[1]
    url = "https://github.com/millerlai/claude-all-in-one.git"
    new_text = release.pin_marketplace(LEGACY_CODEX_MARKETPLACE, market, url, "v1.37.0")

    assert release.pinned_ref(new_text, market) == "v1.37.0"


def test_shared_functions_handle_a_third_platform_with_no_special_casing(tmp_path):
    """UC5: adding a platform is one more release.Marketplace row, not a new
    code path -- scripts/validate.py's marketplace-pin checks read
    release.MARKETPLACES and call pinned_ref/repository_git_url/
    product_version on whatever rows are there. Prove those same shared
    functions handle a hypothetical third platform correctly, without
    mutating the real module-level release.MARKETPLACES tuple, by writing a
    temp git-subdir-pinned marketplace file for it (the same on-disk shape
    validate.py reads) and reading it back."""
    fake_platforms = release.MARKETPLACES + (
        release.Marketplace("fake/marketplace.json", "cai-fake", "plugins/cai-fake",
                            ".fake-plugin/plugin.json"),)
    fake_market = fake_platforms[-1]

    url = release.repository_git_url(REAL_PLUGIN_JSON)
    version = release.product_version(REAL_PLUGIN_JSON)
    ref = f"v{version}"

    fake_marketplace_path = tmp_path / fake_market.file
    fake_marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    fake_marketplace_path.write_text(json.dumps({
        "name": "fake-market",
        "owner": {"name": "x"},
        "plugins": [{
            "name": fake_market.plugin,
            "description": "fake",
            "source": release.git_subdir_source(url, fake_market.path, ref),
        }],
    }), encoding="utf-8")

    fake_marketplace_text = fake_marketplace_path.read_text(encoding="utf-8")
    assert release.pinned_ref(fake_marketplace_text, fake_market) == ref

    obj = json.loads(fake_marketplace_text)
    entry = next(p for p in obj["plugins"] if p["name"] == fake_market.plugin)
    source = entry["source"]
    assert source["source"] == "git-subdir"
    assert source["url"] == url
    assert source["path"] == fake_market.path
    assert source["ref"] == ref


def test_pin_marketplace_raises_when_plugin_missing():
    market = release.MARKETPLACES[1]  # "cai-codex" is not in the Claude marketplace
    with pytest.raises(ValueError):
        release.pin_marketplace(LEGACY_CLAUDE_MARKETPLACE, market, "https://x/y.git", "v1.0.0")


def test_pin_marketplace_raises_when_plugin_duplicated():
    obj = json.loads(LEGACY_CLAUDE_MARKETPLACE)
    obj["plugins"].append(dict(obj["plugins"][0]))
    text = json.dumps(obj)
    market = release.MARKETPLACES[0]
    with pytest.raises(ValueError):
        release.pin_marketplace(text, market, "https://x/y.git", "v1.0.0")


# ---------------------------------------------------------------------------
# draft_section
# ---------------------------------------------------------------------------

def test_draft_section_first_release_names_both_floors():
    section = release.draft_section("1.37.0", "2026-10-01", [], first=True,
                                    track_format_changed=False, skipped=[])

    assert section.startswith("## v1.37.0 — 2026-10-01")
    assert "2.1.283" in section
    assert "0.157.1" in section
    assert "### Added" not in section


def test_draft_section_groups_by_prefix_and_omits_empty_sections():
    subjects = ["feat(cai): add thing (#181)", "fix(cai): fix thing (#180)",
                "docs: write thing (#179)"]
    section = release.draft_section("1.38.0", "2026-10-15", subjects, first=False,
                                    track_format_changed=False, skipped=[])

    assert "### Added\n- feat(cai): add thing (#181)" in section
    assert "### Fixed\n- fix(cai): fix thing (#180)" in section
    assert "### Other\n- docs: write thing (#179)" in section


def test_draft_section_omits_empty_group():
    section = release.draft_section("1.38.0", "2026-10-15", ["feat(cai): x (#1)"],
                                    first=False, track_format_changed=False, skipped=[])

    assert "### Added" in section
    assert "### Fixed" not in section
    assert "### Other" not in section


def test_draft_section_track_format_and_skipped_lines():
    section = release.draft_section("1.38.0", "2026-10-15", ["fix(cai): x (#1)"],
                                    first=False, track_format_changed=True,
                                    skipped=["v1.37.1"])

    assert ("Finish any track in progress before updating: the track's "
            "state format changed in this release.") in section
    assert "Skipped: v1.37.1 (tagged, failed its check, never served)." in section


def test_pending_md_writer_counts_as_a_track_format_file():
    """An in-progress track's pending.md is read by the next version of
    pending.py, so a release that changes it carries the reminder."""
    assert "plugins/cai/scripts/pending.py" in release.TRACK_FORMAT_FILES


def test_draft_section_omits_reminder_and_skipped_when_not_asked():
    section = release.draft_section("1.38.0", "2026-10-15", ["fix(cai): x (#1)"],
                                    first=False, track_format_changed=False, skipped=[])

    assert "Finish any track" not in section
    assert "Skipped:" not in section


# ---------------------------------------------------------------------------
# _tool_path / _git / _gh_auth_ok -- external CLI calls resolve a full path
# ---------------------------------------------------------------------------

def test_git_uses_the_shutil_which_resolved_path(monkeypatch, tmp_path):
    """Design decision #22: an external CLI call must always resolve via
    shutil.which() into a list-form argv, never a bare name -- a bare "git"
    lets Windows' own argv[0] search find a same-named file in `cwd` (here,
    the repo being released) before it reaches PATH."""
    captured = {}

    def fake_which(name):
        return "C:/fake/git.exe" if name == "git" else None

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(release.shutil, "which", fake_which)
    monkeypatch.setattr(release, "run", fake_run)

    release._git(tmp_path, "status", "--porcelain")

    assert captured["argv"][0] == "C:/fake/git.exe"
    assert captured["argv"] != ["git", "status", "--porcelain"]


def test_gh_auth_ok_uses_the_shutil_which_resolved_path(monkeypatch, tmp_path):
    captured = {}

    def fake_which(name):
        return "C:/fake/gh.exe" if name == "gh" else None

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(release.shutil, "which", fake_which)
    monkeypatch.setattr(release, "run", fake_run)

    result = _REAL_GH_AUTH_OK(tmp_path)

    assert captured["argv"][0] == "C:/fake/gh.exe"
    assert result is True


def test_tool_path_raises_tool_missing_when_absent(monkeypatch):
    monkeypatch.setattr(release.shutil, "which", lambda name: None)

    with pytest.raises(release._ToolMissing):
        release._tool_path("git")


def test_tool_path_ignores_a_same_named_file_in_the_current_directory(monkeypatch, tmp_path):
    """Design decision #22 exists so a maintainer running `python
    scripts/release.py ...` from the repo root -- after checking out a
    branch/PR that plants a same-named `git.bat` there, which is exactly
    what `prepare()`'s own first step (`git fetch origin --tags`) makes
    routine -- gets the real git, not the planted one. shutil.which()
    alone does not do this: on stock Windows (no
    NoDefaultCurrentDirectoryInExePath set), it inserts the current
    directory ahead of every PATH entry regardless of a `path=` argument,
    so a bare shutil.which("git") call resolves the planted file first."""
    # shutil.which() finds `git.bat` through PATHEXT on Windows only; on
    # POSIX (the Linux CI) it wants a file named exactly `git` with the
    # executable bit, and it never searches cwd there, so the same assertion
    # holds on both.
    def write_tool(directory, body):
        if sys.platform == "win32":
            tool = directory / "git.bat"
            tool.write_text(f"@echo {body}\n")
        else:
            tool = directory / "git"
            tool.write_text(f"#!/bin/sh\necho {body}\n")
            tool.chmod(0o755)
        return tool

    real_tool_dir = tmp_path / "real_tools"
    real_tool_dir.mkdir()
    real_git = write_tool(real_tool_dir, "real")

    fake_cwd = tmp_path / "repo_root"
    fake_cwd.mkdir()
    write_tool(fake_cwd, "planted")

    monkeypatch.chdir(fake_cwd)
    monkeypatch.setenv("PATH", str(real_tool_dir))
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)

    resolved = release._tool_path("git")

    assert Path(resolved).resolve() == real_git.resolve()


def test_tool_path_refuses_a_resolved_path_that_sits_in_the_current_directory(monkeypatch, tmp_path):
    """Second, version-independent layer: the NoDefaultCurrentDirectoryInExePath
    guard above only stops shutil.which()'s cwd-search on CPython 3.12+
    (3.12 added _win_path_needs_curdir, which checks that variable; CPython
    3.11's shutil.which inserts cwd unconditionally -- Lib/shutil.py:1505-1510
    on the 3.11 branch, no environment check at all). A maintainer on 3.11
    running this script from a repo root with a planted git.bat would get it
    back from shutil.which() no matter what the first layer does, so this
    guard distrusts the result itself: whatever shutil.which() returns, if
    its directory is cwd, refuse it rather than ever returning that path."""
    planted = tmp_path / "git.bat"
    planted.write_text("@echo planted\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(release.shutil, "which", lambda name: str(planted))

    with pytest.raises(release._ToolMissing):
        release._tool_path("git")


def test_reports_tool_missing_turns_tool_missing_into_exit_1(monkeypatch, capsys):
    @release._reports_tool_missing
    def boom():
        raise release._ToolMissing("git")

    rc = boom()

    assert rc == 1
    assert "FAIL git not found on PATH" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# insert_section / extract_section
# ---------------------------------------------------------------------------

def test_insert_section_creates_file_when_none():
    result = release.insert_section(None, "## v1.0.0 — 2026-01-01\n\nbody")
    assert result == "# Changelog\n\n## v1.0.0 — 2026-01-01\n\nbody\n"


def test_insert_section_puts_newest_first():
    existing = "# Changelog\n\n## v1.0.0 — 2026-01-01\n\nold body\n"
    section = "## v1.1.0 — 2026-02-01\n\nnew body"

    result = release.insert_section(existing, section)

    assert result == (
        "# Changelog\n\n"
        "## v1.1.0 — 2026-02-01\n\nnew body\n\n"
        "## v1.0.0 — 2026-01-01\n\nold body\n"
    )


def test_insert_section_preserves_preamble_between_title_and_first_section():
    """Text between "# Changelog" and the first "## v" section (e.g. a
    Keep-a-Changelog-style intro line) belongs to neither `head`'s
    title-only slice nor `tail`'s section slice -- it must survive."""
    existing = (
        "# Changelog\n\n"
        "All notable changes to this project are documented here.\n\n"
        "## v1.0.0 — 2026-01-01\n\nold body\n"
    )
    section = "## v1.1.0 — 2026-02-01\n\nnew body"

    result = release.insert_section(existing, section)

    assert result == (
        "# Changelog\n\n"
        "All notable changes to this project are documented here.\n\n"
        "## v1.1.0 — 2026-02-01\n\nnew body\n\n"
        "## v1.0.0 — 2026-01-01\n\nold body\n"
    )


FAKE_CHANGELOG = (
    "# Changelog\n\n"
    "## v1.2.0 — 2026-03-01\n\n"
    "### Added\n- feat: newest\n\n"
    "## v1.1.0 — 2026-02-01\n\n"
    "### Fixed\n- fix: middle\n\n"
    "## v1.0.0 — 2026-01-01\n\n"
    "### Added\n- feat: oldest\n"
)


def test_extract_section_middle():
    assert release.extract_section(FAKE_CHANGELOG, "1.1.0") == "### Fixed\n- fix: middle"


def test_extract_section_last_section_reads_to_end():
    assert release.extract_section(FAKE_CHANGELOG, "1.0.0") == "### Added\n- feat: oldest"


def test_extract_section_missing_returns_none():
    assert release.extract_section(FAKE_CHANGELOG, "9.9.9") is None


def test_extract_section_does_not_match_a_version_that_is_only_a_prefix():
    """A bare startswith() match on "## v{version}" collides once a
    double-digit patch exists: wanting "1.2.1" must not return "1.2.10"'s
    section just because "1.2.10" starts with "1.2.1"."""
    changelog = (
        "# Changelog\n\n"
        "## v1.2.10 — 2026-04-01\n\n"
        "### Fixed\n- fix: later patch\n\n"
        "## v1.2.1 — 2026-03-01\n\n"
        "### Added\n- feat: the one actually wanted\n"
    )
    assert release.extract_section(changelog, "1.2.1") == "### Added\n- feat: the one actually wanted"


# ---------------------------------------------------------------------------
# _platform_cache_ok -- unit test, no shelling out
# ---------------------------------------------------------------------------

def test_platform_cache_ok_true_when_version_and_files_match(tmp_path):
    cache_dir = tmp_path / "cai" / "1.37.0"
    (cache_dir / ".claude-plugin").mkdir(parents=True)
    (cache_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "1.37.0"}), encoding="utf-8")
    (cache_dir / "skills").mkdir()
    (cache_dir / "skills" / "track.md").write_text("x", encoding="utf-8")

    ok = release._platform_cache_ok(
        cache_dir, ".claude-plugin/plugin.json", "1.37.0",
        {".claude-plugin/plugin.json", "skills/track.md"})

    assert ok is True


def test_platform_cache_ok_false_on_version_mismatch(tmp_path):
    cache_dir = tmp_path / "cai" / "1.37.0"
    (cache_dir / ".claude-plugin").mkdir(parents=True)
    (cache_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "1.36.1"}), encoding="utf-8")

    ok = release._platform_cache_ok(
        cache_dir, ".claude-plugin/plugin.json", "1.37.0", set())

    assert ok is False


def test_platform_cache_ok_false_on_missing_expected_file(tmp_path):
    cache_dir = tmp_path / "cai" / "1.37.0"
    (cache_dir / ".claude-plugin").mkdir(parents=True)
    (cache_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "1.37.0"}), encoding="utf-8")

    ok = release._platform_cache_ok(
        cache_dir, ".claude-plugin/plugin.json", "1.37.0", {"skills/missing.md"})

    assert ok is False


def test_platform_cache_ok_false_when_manifest_missing(tmp_path):
    cache_dir = tmp_path / "cai" / "1.37.0"
    cache_dir.mkdir(parents=True)

    ok = release._platform_cache_ok(cache_dir, ".claude-plugin/plugin.json", "1.37.0", set())

    assert ok is False


# ---------------------------------------------------------------------------
# local_gate -- which pytest command it runs
# ---------------------------------------------------------------------------

def test_local_gate_leaves_parallelism_to_pyproject(monkeypatch, tmp_path):
    """pyproject.toml's addopts already carries `-n auto`, so the gate adds
    none of its own -- whether xdist is installed or not."""
    seen = []

    def fake_run(argv, *, cwd, env=None, timeout=None):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(release, "run", fake_run)
    assert release.local_gate(tmp_path) == []

    assert [sys.executable, "-m", "pytest"] in seen


# ---------------------------------------------------------------------------
# prepare() -- real local origin (bare) + working clone
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_pair(tmp_path):
    """A bare `origin` and a working clone seeded with today's real manifest
    and the legacy-form marketplace fixtures on `main`, both on branch
    `main` -- the state `prepare` sees before a first release."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"

    init = subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                          capture_output=True, encoding="utf-8")
    assert init.returncode == 0, init.stderr

    _run_git(["clone", str(origin), str(work)], cwd=tmp_path)
    _run_git(["config", "user.email", "test@example.com"], cwd=work)
    _run_git(["config", "user.name", "Test"], cwd=work)

    plugin_json = work / "plugins" / "cai" / ".claude-plugin" / "plugin.json"
    plugin_json.parent.mkdir(parents=True)
    plugin_json.write_text(REAL_PLUGIN_JSON, encoding="utf-8")

    claude_market = work / ".claude-plugin" / "marketplace.json"
    claude_market.parent.mkdir(parents=True)
    claude_market.write_text(LEGACY_CLAUDE_MARKETPLACE, encoding="utf-8")

    codex_market = work / ".agents" / "plugins" / "marketplace.json"
    codex_market.parent.mkdir(parents=True)
    codex_market.write_text(LEGACY_CODEX_MARKETPLACE, encoding="utf-8")

    _run_git(["add", "-A"], cwd=work)
    _run_git(["commit", "-m", "seed"], cwd=work)
    _run_git(["push", "-u", "origin", "main"], cwd=work)

    return origin, work


@pytest.fixture(autouse=True)
def _stub_tools(monkeypatch):
    """No test in this file ever shells out to a real gh/claude/codex, or
    touches the network for auth -- the two named seams (tool_versions,
    local_gate) plus the two extra thin wrappers this build adds (_which,
    _gh_auth_ok) for the same reason (see module docstring)."""
    monkeypatch.setattr(release, "tool_versions", lambda: {
        "git": "2.40.0", "gh": "2.40.0", "claude": "2.1.283", "codex": "0.157.1"})
    monkeypatch.setattr(release, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(release, "_gh_auth_ok", lambda repo: True)
    monkeypatch.setattr(release, "_gen_codex", lambda repo: subprocess.CompletedProcess(
        args=["gen-codex"], returncode=0, stdout="", stderr=""))


def test_prepare_rejects_bad_version(repo_pair):
    origin, work = repo_pair
    before = _run_git(["status", "--porcelain"], cwd=work).stdout

    rc = release.prepare("not-a-version", base="origin/main", repo=work)

    assert rc == 2
    assert _run_git(["status", "--porcelain"], cwd=work).stdout == before
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == "main"


def test_prepare_rejects_dirty_working_tree(repo_pair):
    origin, work = repo_pair
    (work / "scratch.txt").write_text("uncommitted", encoding="utf-8")

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2


def test_prepare_rejects_non_increasing_version(repo_pair):
    origin, work = repo_pair

    rc = release.prepare(CURRENT_VERSION, base="origin/main", repo=work)  # equal to current

    assert rc == 2
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == "main"


def test_prepare_rejects_a_burned_tag_number(repo_pair):
    origin, work = repo_pair
    _run_git(["tag", "-a", f"v{HIGHER_VERSION}", "-m", "burned"], cwd=work)
    _run_git(["push", "origin", f"refs/tags/v{HIGHER_VERSION}"], cwd=work)

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)  # lower than the burned tag

    assert rc == 2


def test_prepare_rejects_existing_tag(repo_pair):
    origin, work = repo_pair
    _run_git(["tag", "-a", f"v{NEXT_VERSION}", "-m", "exists"], cwd=work)

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2


def test_prepare_rejects_existing_release_branch(repo_pair):
    origin, work = repo_pair
    _run_git(["branch", f"release/v{NEXT_VERSION}"], cwd=work)

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2


def test_prepare_rejects_when_a_release_is_already_in_flight(repo_pair):
    origin, work = repo_pair
    other = work.parent / "other_clone"
    _run_git(["clone", str(origin), str(other)], cwd=work.parent)
    _run_git(["config", "user.email", "test@example.com"], cwd=other)
    _run_git(["config", "user.name", "Test"], cwd=other)
    _run_git(["switch", "-c", f"release/v{OTHER_VERSION}"], cwd=other)
    (other / "marker.txt").write_text("x", encoding="utf-8")
    _run_git(["add", "-A"], cwd=other)
    _run_git(["commit", "-m", "in flight"], cwd=other)
    _run_git(["push", "-u", "origin", f"release/v{OTHER_VERSION}"], cwd=other)
    _run_git(["fetch", "origin"], cwd=work)

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2


def test_prepare_rejects_a_below_floor_codex_version(monkeypatch, repo_pair):
    """Coverage gap: no existing test overrode tool_versions()/_which()/
    _gh_auth_ok() to a failing value, so deleting prepare()'s whole
    tool-floor precondition block (step 7) would not fail any test."""
    origin, work = repo_pair
    monkeypatch.setattr(release, "tool_versions", lambda: {
        "git": "2.40.0", "gh": "2.40.0", "claude": "2.1.283", "codex": "0.157.0"})
    before = _run_git(["status", "--porcelain"], cwd=work).stdout

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2
    assert _run_git(["status", "--porcelain"], cwd=work).stdout == before
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == "main"


def test_prepare_rejects_a_missing_cli(monkeypatch, repo_pair):
    origin, work = repo_pair
    monkeypatch.setattr(release, "_which",
                        lambda name: None if name == "codex" else f"/usr/bin/{name}")
    before = _run_git(["status", "--porcelain"], cwd=work).stdout

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2
    assert _run_git(["status", "--porcelain"], cwd=work).stdout == before
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == "main"


def test_prepare_rejects_failed_gh_auth(monkeypatch, repo_pair):
    origin, work = repo_pair
    monkeypatch.setattr(release, "_gh_auth_ok", lambda repo: False)
    before = _run_git(["status", "--porcelain"], cwd=work).stdout

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 2
    assert _run_git(["status", "--porcelain"], cwd=work).stdout == before
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == "main"


def test_prepare_writes_all_four_kinds_of_files_and_detects_first_release(repo_pair):
    origin, work = repo_pair

    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)

    assert rc == 0
    assert _run_git(["branch", "--show-current"], cwd=work).stdout.strip() == f"release/v{NEXT_VERSION}"

    manifest_text = (work / "plugins/cai/.claude-plugin/plugin.json").read_text(encoding="utf-8")
    assert release.product_version(manifest_text) == NEXT_VERSION

    for market in release.MARKETPLACES:
        market_text = (work / market.file).read_text(encoding="utf-8")
        assert release.pinned_ref(market_text, market) == f"v{NEXT_VERSION}"

    changelog_text = (work / "CHANGELOG.md").read_text(encoding="utf-8")
    section = release.extract_section(changelog_text, NEXT_VERSION)
    assert section is not None
    assert "First unified version" in section  # detected as first release


# ---------------------------------------------------------------------------
# cut()
# ---------------------------------------------------------------------------

def _prepared_repo(repo_pair):
    origin, work = repo_pair
    rc = release.prepare(NEXT_VERSION, base="origin/main", repo=work)
    assert rc == 0
    return origin, work


def test_cut_rejects_changes_outside_the_allowed_set(repo_pair):
    origin, work = _prepared_repo(repo_pair)
    (work / "extra.txt").write_text("not allowed", encoding="utf-8")

    rc = release.cut(NEXT_VERSION, repo=work)

    assert rc == 2


def test_cut_does_not_commit_when_the_local_gate_fails(monkeypatch, repo_pair):
    origin, work = _prepared_repo(repo_pair)
    monkeypatch.setattr(release, "local_gate", lambda repo: ["FAIL validate.py: boom"])
    before_head = _run_git(["rev-parse", "HEAD"], cwd=work).stdout

    rc = release.cut(NEXT_VERSION, repo=work)

    assert rc == 1
    assert _run_git(["rev-parse", "HEAD"], cwd=work).stdout == before_head


def test_cut_exits_when_remote_already_has_the_tag(monkeypatch, repo_pair):
    origin, work = _prepared_repo(repo_pair)
    monkeypatch.setattr(release, "local_gate", lambda repo: [])

    # Simulate another clone having already pushed this tag.
    other = work.parent / "other_clone2"
    _run_git(["clone", str(origin), str(other)], cwd=work.parent)
    _run_git(["config", "user.email", "test@example.com"], cwd=other)
    _run_git(["config", "user.name", "Test"], cwd=other)
    _run_git(["tag", "-a", f"v{NEXT_VERSION}", "-m", f"cai v{NEXT_VERSION}"], cwd=other)
    _run_git(["push", "origin", f"refs/tags/v{NEXT_VERSION}"], cwd=other)

    rc = release.cut(NEXT_VERSION, repo=work)

    assert rc == 2


def test_cut_pushes_only_the_one_tag_ref(monkeypatch, repo_pair):
    origin, work = _prepared_repo(repo_pair)
    monkeypatch.setattr(release, "local_gate", lambda repo: [])
    pushed_refs = []
    real_git = release._git

    def spying_git(repo, *args, **kwargs):
        if args and args[0] == "push":
            pushed_refs.append(args)
        return real_git(repo, *args, **kwargs)

    monkeypatch.setattr(release, "_git", spying_git)
    monkeypatch.setattr(release, "verify", lambda version, repo=None, temp_root=None: 0)

    rc = release.cut(NEXT_VERSION, repo=work)

    assert rc == 0
    push_calls = [p for p in pushed_refs if p[0] == "push"]
    assert push_calls == [("push", "origin", f"refs/tags/v{NEXT_VERSION}")]


# ---------------------------------------------------------------------------
# verify() -- isolation-not-taken precondition
# ---------------------------------------------------------------------------

def _fake_git_for_verify(version, tag_sha="abc123"):
    """A release._git replacement that satisfies verify()'s preconditions
    (tag pushed, matches remote, on the release branch, tag is an ancestor
    of HEAD) with canned output, so the platform-check loop is reached
    without a real git repo/tag/push."""
    tag_name = f"v{version}"
    branch_name = f"release/{tag_name}"

    def fake(repo, *args, timeout=5):
        if args[:3] == ("rev-parse", "-q", "--verify") and args[-1] == tag_name:
            return subprocess.CompletedProcess(args, 0, f"{tag_sha}\n", "")
        if args[:1] == ("ls-remote",) and args[-1] == f"refs/tags/{tag_name}":
            return subprocess.CompletedProcess(args, 0, f"{tag_sha}\trefs/tags/{tag_name}\n", "")
        if args == ("branch", "--show-current"):
            return subprocess.CompletedProcess(args, 0, f"{branch_name}\n", "")
        if args[:1] == ("merge-base",):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:1] == ("show",):
            rel = args[1].split(":", 1)[1]
            if rel == release.MARKETPLACES[0].file:
                return subprocess.CompletedProcess(args, 0, LEGACY_CLAUDE_MARKETPLACE, "")
            if rel == release.MARKETPLACES[1].file:
                return subprocess.CompletedProcess(args, 0, LEGACY_CODEX_MARKETPLACE, "")
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:1] == ("ls-tree",):
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")
    return fake


def test_verify_returns_2_when_isolation_does_not_take(monkeypatch, tmp_path):
    """Design ("verify" step 3 / Failure modes table): isolation not taking
    (`marketplace list` isn't empty) must exit 2, not fall through to the
    generic exit-1 "this number may be burned" path -- nothing was
    installed and the maintainer's real config was never touched."""
    version = "1.99.0"

    monkeypatch.setattr(release, "_git", _fake_git_for_verify(version))
    monkeypatch.setattr(release, "_tool_path", lambda name: name)

    def fake_run(argv, cwd=None, env=None, timeout=None):
        if argv[1:4] == ["plugin", "marketplace", "list"]:
            return subprocess.CompletedProcess(argv, 0, "not empty", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(release, "run", fake_run)

    rc = release.verify(version, repo=tmp_path, temp_root=tmp_path / "cai-check")

    assert rc == 2


def test_cut_rerun_after_failed_push_does_not_duplicate_the_commit(monkeypatch, repo_pair):
    origin, work = _prepared_repo(repo_pair)
    monkeypatch.setattr(release, "local_gate", lambda repo: [])
    monkeypatch.setattr(release, "verify", lambda version, repo=None, temp_root=None: 0)

    # First attempt: make the push fail by pointing "origin" nowhere.
    real_git = release._git

    def failing_push(repo, *args, **kwargs):
        if args and args[0] == "push":
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="boom")
        return real_git(repo, *args, **kwargs)

    monkeypatch.setattr(release, "_git", failing_push)
    rc1 = release.cut(NEXT_VERSION, repo=work)
    assert rc1 == 1

    log_after_first = _run_git(["log", "--oneline"], cwd=work).stdout

    monkeypatch.setattr(release, "_git", real_git)
    rc2 = release.cut(NEXT_VERSION, repo=work)
    assert rc2 == 0

    log_after_second = _run_git(["log", "--oneline"], cwd=work).stdout
    assert log_after_first == log_after_second  # no duplicate commit was made
