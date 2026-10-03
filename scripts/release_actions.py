#!/usr/bin/env python3
"""GitHub Actions adapter for a maintainer-reviewed release commit.

Run from a checkout of main; the candidate may only change release files.
The existing release.py remains the implementation of cut/verify/publish.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import release


def git(repo: Path, *args) -> str:
    done = release._git(repo, *args, timeout=None)
    if done.returncode:
        raise RuntimeError(f"git {args[0]} failed")
    return done.stdout.strip()


def gh(repo: Path, *args) -> str:
    done = release.run([release._tool_path("gh"), *args], cwd=repo, timeout=None)
    if done.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed")
    return done.stdout.strip()


def candidate(version: str, head: str, repo: Path, allow_merged: bool = False) -> str:
    release.parse_version(version)
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("head must be a full lowercase 40-character commit SHA")
    if git(repo, "status", "--porcelain"):
        raise ValueError("working tree is not clean")
    git(repo, "fetch", "--prune", "origin", "--tags")
    branch = f"release/v{version}"
    remote = release._git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch}")
    if remote.returncode and allow_merged:
        # GitHub can delete the branch after merge. Its immutable tag and
        # matching MERGED PR retain everything needed to finish the CI check.
        if pr_info(repo, version, head)["state"] != "MERGED":
            raise ValueError("missing release branch is only allowed after merge")
    elif remote.returncode or remote.stdout.strip() != head:
        raise ValueError("release branch no longer matches the approved head")
    parents = git(repo, "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 2:
        raise ValueError("candidate must be one non-merge release commit")
    parent = parents[1]
    git(repo, "merge-base", "--is-ancestor", parent, "origin/main")
    if git(repo, "log", "-1", "--format=%s", head) != f"chore(release): v{version}":
        raise ValueError("candidate must have the chore(release) subject")
    paths = git(repo, "diff", "--name-only", "--no-renames", parent, head).splitlines()
    if not paths or any(not release._path_is_allowed(p, release._allowed_cut_paths())
                        for p in paths):
        raise ValueError("candidate changes files outside the release set")
    manifest = git(repo, "show", f"{head}:{release.PRODUCT_MANIFEST}")
    if release.product_version(manifest) != version:
        raise ValueError("candidate manifest version does not match")
    for market in release.MARKETPLACES:
        text = git(repo, "show", f"{head}:{market.file}")
        if release.pinned_ref(text, market) != f"v{version}":
            raise ValueError("candidate marketplace is not pinned to this tag")
    notes = release.extract_section(git(repo, "show", f"{head}:CHANGELOG.md"), version)
    if not notes:
        raise ValueError("candidate has no release notes")
    if f"v{version}" in release._local_tags(repo):
        if git(repo, "rev-parse", f"v{version}^{{commit}}") != head:
            raise ValueError("existing tag does not match the approved head")
    else:
        current = release.product_version(git(repo, "show", f"origin/main:{release.PRODUCT_MANIFEST}"))
        versions = release._all_version_tags(repo) | {current}
        if any(release.parse_version(version) <= release.parse_version(v) for v in versions):
            raise ValueError("version must exceed every existing version/tag")
        if parent != git(repo, "rev-parse", "origin/main"):
            raise ValueError("main advanced; prepare a new candidate before tagging")
        served = release.pinned_ref(git(repo, "show", f"{parent}:{release.MARKETPLACES[0].file}"),
                                   release.MARKETPLACES[0])
        if served and not git(repo, "diff", "--name-only", served, parent, "--", "plugins/"):
            raise ValueError("no unreleased plugin changes")
    print(f"PASS candidate {branch} at {head}")
    print(notes)
    return parent


def wait_ci(repo: Path, head: str, branch: str, event: str, *, seconds: int = 2400):
    # A PR or merge push can reach Actions after its API call returns. Poll for
    # this exact commit, never accept the previous green run on the branch.
    deadline = time.monotonic() + seconds
    while True:
        runs = json.loads(gh(repo, "run", "list", "--workflow", "validate.yml",
                             "--commit", head, "--branch", branch, "--event", event,
                             "--limit", "1", "--json", "headSha,status,conclusion"))
        if runs and runs[0]["headSha"] == head and runs[0]["status"] == "completed":
            if runs[0]["conclusion"] != "success":
                raise RuntimeError(f"validate CI failed for {head}")
            print(f"PASS validate CI for {head}")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for validate CI for {head}")
        time.sleep(10)


def pr_info(repo: Path, version: str, head: str) -> dict:
    info = json.loads(gh(repo, "pr", "view", f"release/v{version}", "--json",
                         "number,state,headRefOid,baseRefName,mergeCommit"))
    if info["headRefOid"] != head or info["baseRefName"] != "main":
        raise ValueError("release PR does not match the approved head/base")
    if git(repo, "rev-parse", f"v{version}^{{commit}}") != head:
        raise ValueError("release tag does not match the approved head")
    return info


def execute(command: str, version: str, head: str, repo: Path) -> int:
    parent = candidate(version, head, repo, command == "merge")
    branch = f"release/v{version}"
    if command == "check":
        wait_ci(repo, parent, "main", "push")
        return 0
    if command == "gate":
        wait_ci(repo, parent, "main", "push")
        git(repo, "switch", "--create", branch, head)
        failures = release.local_gate(repo)
        if failures:
            raise RuntimeError("\n".join(failures))
        if git(repo, "status", "--porcelain"):
            raise RuntimeError("working tree changed during validation")
        print("PASS validate.py and pytest")
        return 0
    if command == "cut":
        # gate ran before minting the write token; recheck the remote head here.
        if release._current_branch(repo) != branch or git(repo, "rev-parse", "HEAD") != head:
            raise ValueError("cut must follow gate in the same checkout")
        if f"v{version}" in release._remote_tags(repo):
            return release.verify(version, repo=repo)
        return release.cut(version, repo=repo)
    info = pr_info(repo, version, head)
    if command == "publish":
        if info["state"] != "OPEN":
            raise ValueError("release PR must be OPEN before publishing")
        wait_ci(repo, head, branch, "pull_request")
        gh(repo, "pr", "checks", str(info["number"]), "--watch", "--interval", "10")
        pr_info(repo, version, head)
        result = release.publish(version, repo=repo)
        if result:
            return result
    published = json.loads(gh(repo, "release", "view", f"v{version}", "--json", "isDraft,publishedAt"))
    if published["isDraft"] or not published["publishedAt"]:
        raise ValueError("GitHub Release must be published before merging")
    if command == "publish":
        return 0
    if info["state"] == "OPEN":
        gh(repo, "pr", "checks", str(info["number"]), "--watch", "--interval", "10")
        gh(repo, "pr", "merge", str(info["number"]), "--merge", "--match-head-commit", head)
        info = pr_info(repo, version, head)
    if info["state"] != "MERGED":
        raise ValueError("release PR was not merged")
    git(repo, "fetch", "origin", "main")
    git(repo, "merge-base", "--is-ancestor", f"v{version}", "origin/main")
    wait_ci(repo, info["mergeCommit"]["oid"], "main", "push")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "gate", "cut", "publish", "merge"))
    parser.add_argument("version")
    parser.add_argument("head")
    args = parser.parse_args(argv)
    try:
        return execute(args.command, args.version, args.head, release.ROOT)
    except (ValueError, RuntimeError) as e:
        print(f"FAIL {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
