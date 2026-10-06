"""Integration tests for scripts/validate.py's marketplace-pin and R4 checks
(docs/design/2026-09-26-release-versioning-detail.md).

Every test here shells out to validate.py as a subprocess, the same way
tests/test_release.py's `local_gate` and this repo's own CLAUDE.md ("Before
pushing") already treat it as a black box, against a copy of the repo (minus
.git and cache directories -- see _copy_repo) that the test then breaks on
purpose. validate.py reads every path relative to the current working
directory, so the copy is what it checks.

Each run names the one section these checks live in (#305). A whole run cost
about twenty seconds plain and twice that under `pytest --cov`, for some 380
child processes this file never reads.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_MANIFEST = "plugins/cai/.claude-plugin/plugin.json"
CAI_MARKETPLACE = ".claude-plugin/marketplace.json"
CODEX_MARKETPLACE = ".agents/plugins/marketplace.json"
CAI_CODEX_MANIFEST = "plugins/cai-codex/.codex-plugin/plugin.json"


def _copy_repo(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*"))
    return dest


def _run_validate(repo):
    # Built per call, not at import: conftest's autouse fixtures set this
    # test's CAI_USAGE_LEDGER in os.environ.
    return subprocess.run([sys.executable, "scripts/validate.py", "release-manifests"],
                          cwd=repo, capture_output=True, encoding="utf-8")


def _product_version(repo):
    manifest = json.loads((repo / PRODUCT_MANIFEST).read_text(encoding="utf-8"))
    return manifest["version"]


def _repository_url(repo):
    manifest = json.loads((repo / PRODUCT_MANIFEST).read_text(encoding="utf-8"))
    return manifest["repository"] + ".git"


def _set_legacy_form(repo):
    """Put both marketplace files in the copy back to the relative-path
    string form they had before the first release. A copy of the working
    tree is legacy only on main before that release -- `release.py prepare`
    pins it mid-release and main stays pinned afterwards -- so tests that
    need the legacy form set it here instead of assuming it."""
    for rel_path in (CAI_MARKETPLACE, CODEX_MARKETPLACE):
        path = repo / rel_path
        obj = json.loads(path.read_text(encoding="utf-8"))
        for entry in obj["plugins"]:
            entry["source"] = f"./plugins/{entry['name']}"
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _pin_marketplace(repo, rel_path, plugin_name, plugin_path, url, ref):
    """Rewrite one plugin entry's `source` in the given marketplace file to
    the git-subdir object form."""
    path = repo / rel_path
    obj = json.loads(path.read_text(encoding="utf-8"))
    entry = next(p for p in obj["plugins"] if p["name"] == plugin_name)
    entry["source"] = {"source": "git-subdir", "url": url, "path": plugin_path, "ref": ref}
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# R4 -- plugins/cai-codex/.codex-plugin/plugin.json version matches product
# ---------------------------------------------------------------------------

def test_r4_fails_when_codex_manifest_version_does_not_match_product(tmp_path):
    repo = _copy_repo(tmp_path)
    codex_manifest_path = repo / CAI_CODEX_MANIFEST
    codex_manifest = json.loads(codex_manifest_path.read_text(encoding="utf-8"))
    real_version = _product_version(repo)
    assert codex_manifest["version"] == real_version  # sanity: starts matching

    codex_manifest["version"] = "0.0.1-does-not-match"
    codex_manifest_path.write_text(json.dumps(codex_manifest, indent=2) + "\n", encoding="utf-8")

    result = _run_validate(repo)

    assert result.returncode != 0
    assert f"FAIL {CAI_CODEX_MANIFEST} version matches the product version (R4)" in result.stdout


def test_r4_passes_on_an_unmodified_copy(tmp_path):
    repo = _copy_repo(tmp_path)

    result = _run_validate(repo)

    assert f"PASS {CAI_CODEX_MANIFEST} version matches the product version (R4)" in result.stdout


# ---------------------------------------------------------------------------
# Legacy / pin-form matrix
# ---------------------------------------------------------------------------

FORM_LABEL = "every marketplace entry uses a git-subdir source"


def test_legacy_string_form_fails(tmp_path):
    """Stance I5: main holds git-subdir sources only. A PR that reverts both
    marketplace files to the legacy string must FAIL the form check, name
    each file's form, and never reach the pin checks."""
    repo = _copy_repo(tmp_path)
    _set_legacy_form(repo)

    result = _run_validate(repo)

    assert result.returncode != 0
    assert f"FAIL {FORM_LABEL}" in result.stdout
    assert f"{CAI_MARKETPLACE}: legacy" in result.stdout
    assert f"{CODEX_MARKETPLACE}: legacy" in result.stdout
    assert "pins cai" not in result.stdout  # the pin checks are gated on the form check


def test_consistent_git_subdir_form_passes(tmp_path):
    repo = _copy_repo(tmp_path)
    url = _repository_url(repo)
    version = _product_version(repo)
    ref = f"v{version}"

    _pin_marketplace(repo, CAI_MARKETPLACE, "cai", "plugins/cai", url, ref)
    _pin_marketplace(repo, CODEX_MARKETPLACE, "cai-codex", "plugins/cai-codex", url, ref)

    result = _run_validate(repo)

    assert f"PASS {FORM_LABEL}" in result.stdout
    assert f"PASS {CAI_MARKETPLACE} pins cai correctly (url/path/ref)" in result.stdout
    assert f"PASS {CODEX_MARKETPLACE} pins cai-codex correctly (url/path/ref)" in result.stdout
    assert result.returncode == 0, result.stdout[-4000:]


def test_mixed_form_fails_check_a(tmp_path):
    """One marketplace file pinned to git-subdir, the other left as the
    legacy string -- one entry is legacy, so Check A must FAIL."""
    repo = _copy_repo(tmp_path)
    _set_legacy_form(repo)
    url = _repository_url(repo)
    version = _product_version(repo)
    ref = f"v{version}"

    _pin_marketplace(repo, CAI_MARKETPLACE, "cai", "plugins/cai", url, ref)
    # .agents/plugins/marketplace.json stays in the legacy string form.

    result = _run_validate(repo)

    assert f"FAIL {FORM_LABEL}" in result.stdout
    assert result.returncode != 0


def test_uc5_validate_check_loop_reaches_a_third_marketplace_row(tmp_path):
    """UC5 (Verification table): "validate reads MARKETPLACES, checks a fake
    extra market file row too" -- adding a platform must be one more row in
    release.MARKETPLACES, not new code in validate.py. This is stronger than
    tests/test_release.py's test_shared_functions_handle_a_third_platform_
    with_no_special_casing, which only calls release.pinned_ref/
    repository_git_url/product_version directly on a synthetic row: it never
    proves validate.py's own check *loop* iterates whatever MARKETPLACES
    holds at runtime, so a validate.py hard-coded to two known platforms
    would still pass that test.

    Chosen variant (simpler than staging a fully consistent three-platform
    git-subdir scenario, per the finding's documented allowance): the third
    row points at a marketplace file that does not exist in the copy, so it
    lands in validate.py's own except-unreadable branch. The two real rows
    are git-subdir and the third is unreadable, so the git-subdir check FAILs
    only because of the third row -- proving the loop actually reached a row
    it was never specifically coded for.
    """
    repo = _copy_repo(tmp_path)
    release_py = repo / "scripts" / "release.py"
    text = release_py.read_text(encoding="utf-8")
    anchor = ")\nPRODUCT_MANIFEST"
    assert text.count(anchor) == 1  # sanity: matches the real tuple's close, once
    replacement = (
        '    Marketplace("fake/marketplace.json", "cai-fake", "plugins/cai-fake", '
        '".fake-plugin/plugin.json"),\n)\nPRODUCT_MANIFEST'
    )
    release_py.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

    result = _run_validate(repo)

    assert result.returncode != 0
    assert f"FAIL {FORM_LABEL}" in result.stdout
    assert "fake/marketplace.json: unreadable" in result.stdout


def test_wrong_ref_fails_check_b(tmp_path):
    """Both marketplace files consistently pinned to git-subdir, but one
    ref does not match "v" + the product version -- Check A passes (both
    entries are git-subdir) while Check B FAILs on the mismatched row."""
    repo = _copy_repo(tmp_path)
    url = _repository_url(repo)
    version = _product_version(repo)
    ref = f"v{version}"

    _pin_marketplace(repo, CAI_MARKETPLACE, "cai", "plugins/cai", url, "v0.0.1-wrong")
    _pin_marketplace(repo, CODEX_MARKETPLACE, "cai-codex", "plugins/cai-codex", url, ref)

    result = _run_validate(repo)

    assert f"PASS {FORM_LABEL}" in result.stdout
    assert f"FAIL {CAI_MARKETPLACE} pins cai correctly (url/path/ref)" in result.stdout
    assert result.returncode != 0
