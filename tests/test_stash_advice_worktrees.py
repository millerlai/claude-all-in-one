"""Shipped advice must not send a linked worktree to `git stash` (#230).

Every worktree of a repo shares one refs/stash, and track's parallel lanes
each run in their own `git worktree` (stage-build.md, Step 4) -- so a lane
that stashes can pop another lane's work into its own tree. Each text that
used to say "commit or stash" now prefers a commit and allows a stash only
where `git worktree list` shows a single worktree.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAI = os.path.join(ROOT, "plugins", "cai")
sys.path.insert(0, os.path.join(CAI, "scripts"))

import bash_guard  # noqa: E402


def read(*parts):
    with open(os.path.join(CAI, *parts), encoding="utf-8") as fh:
        return fh.read()


def paragraphs_mentioning_stash(text):
    return [p for p in re.split(r"\n\s*\n", text) if re.search(r"\bstash", p, re.I)]


def test_guard_advice_prefers_a_commit_and_names_the_shared_stash():
    advice = bash_guard.COMMIT_FIRST
    assert "WIP commit" in advice
    assert "worktree" in advice


def test_preflight_clean_tree_message_qualifies_stash():
    source = read("scripts", "preflight.py")
    line = next(l for l in source.splitlines() if "clean_tree (%s" in l and "--" in l)
    assert "commit or stash them" not in line
    assert "worktree" in source[source.index(line):source.index(line) + 300]


def test_git_skill_qualifies_every_stash_mention():
    text = read("skills", "git", "SKILL.md")
    body = text.split("---", 2)[2]  # the frontmatter description only lists stash as a verb
    # One rule per bullet line, so judge each line rather than the whole list.
    for line in body.splitlines():
        if re.search(r"\bstash", line, re.I):
            assert "worktree" in line, line


def test_stage_ship_qualifies_every_stash_mention():
    for para in paragraphs_mentioning_stash(read("skills", "track", "references", "stage-ship.md")):
        assert "worktree" in para, para


def test_parallel_lane_brief_forbids_stash():
    text = read("skills", "track", "references", "stage-build.md")
    step4 = text[text.index("## Step 4"):]
    step4 = step4[:step4.index("\n## ", 1)] if "\n## " in step4[1:] else step4
    assert "git stash" in step4
    assert "WIP commit" in step4
