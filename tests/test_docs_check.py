"""docs_check.py: which Markdown references git can show have gone stale.

The tests that matter most are the ones about what is *not* reported: a path
that never existed, a record, a bare name, a path under somebody's home
directory. A check that calls an example a defect is one nobody runs twice.
"""
import os
import subprocess
import sys

import pytest

import codemap_inventory
import docs_check
import preflight
from codemap_repo import GIT_IDENTITY, git, make_repo, write

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "plugins", "cai", "scripts", "docs_check.py")


def repo(tmp_path, files):
    top = make_repo(tmp_path, files)
    # The script's own git calls read the repository's config, not the
    # helper's per-command -c flags.
    git(top, "config", "core.autocrlf", "false")
    git(top, "branch", "-M", "main")
    return top


def commit(top, message="next"):
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", message)
    return git(top, "rev-parse", "--short", "HEAD").strip()


def run(capsys, top, *args):
    code = docs_check.main(["--project-dir", str(top), *args])
    return code, capsys.readouterr().out.splitlines()


def remove(top, rel):
    os.remove(os.path.join(top, *rel.split("/")))


# --- the pure parts -----------------------------------------------------

@pytest.mark.parametrize("path", [
    "CHANGELOG.md", "docs/Release-Notes.md", "docs/adr/0001-use-git.md",
    "docs/design/2026-01-02-topic-design.md", "Archive/old-guide.md"])
def test_a_record_is_recognised_by_its_name_or_its_directory(path):
    assert docs_check.is_record(path)


@pytest.mark.parametrize("path", [
    "README.md", "docs/design/architecture.md", "docs/2026-roadmap.md", "docs/changes.md"])
def test_a_living_document_is_not_a_record(path):
    assert not docs_check.is_record(path)


@pytest.mark.parametrize("word, want", [
    ("scripts/x.py", "scripts/x.py"),
    ("scripts/x.py:12", "scripts/x.py"),
    ("scripts/x.py:12-20", "scripts/x.py"),
    ("scripts/x.py:12:3", "scripts/x.py"),
    ("tests/test_x.py::test_name", "tests/test_x.py"),
    ("docs/a.md#heading", "docs/a.md"),
    ("${CLAUDE_PLUGIN_ROOT}/scripts/x.py", "scripts/x.py"),
    ("$CLAUDE_PROJECT_DIR/scripts/x.py", "scripts/x.py"),
    ("./scripts/x.py", "scripts/x.py"),
    ("scripts/x.py.", "scripts/x.py"),
    ("docs/", "docs/"),
    ("x.py", "x.py"),
    (".gitignore", ".gitignore"),
])
def test_clean_keeps_the_path_and_drops_what_points_inside_it(word, want):
    assert docs_check.clean(word) == want


@pytest.mark.parametrize("word", [
    "word", "LICENSE", "v2.2.0", "1.5x", "<name>/x.md", "src/*.py", "{a,b}/x.py",
    "https://example.com/a/b", "/usr/bin/python", "~/.config/x.toml",
    "plugins\\cai\\x.py", "a//b", "", "...",
    # Somewhere under a directory only the reader's machine has.
    "$HOME/.claude/settings.json", "${CODEX_HOME}/hooks.json", "$ROOT/scripts/x.py"])
def test_clean_refuses_what_cannot_be_looked_up(word):
    assert docs_check.clean(word) is None


def test_a_link_target_needs_no_extension():
    assert docs_check.clean("LICENSE", link=True) == "LICENSE"


def test_references_come_from_inline_code_links_and_fenced_blocks():
    text = "\n".join([
        "Intro names `scripts/a.py` and plain scripts/ignored.py.",      # 1
        "# Usage ##",                                                    # 2
        "See [the guide](docs/guide.md#top) and [root](/LICENSE).",      # 3
        "[ref]: docs/ref.md",                                            # 4
        "```bash",                                                       # 5
        "python scripts/run.py --out=build/out.json",                    # 6
        "~~~",                                                           # 7
        "```",                                                           # 8
        "## `tools/b.py`",                                               # 9
        "Not a path: `some words`, `<x>/y.md`.",                         # 10
        "[^1]: scripts/were/removed long ago.",                          # 11
    ])
    assert list(docs_check.references(text)) == [
        docs_check.Ref(1, "(top)", "scripts/a.py", False, 0, False),
        docs_check.Ref(3, "Usage", "docs/guide.md", False, 2, True),
        docs_check.Ref(3, "Usage", "LICENSE", True, 2, True),
        docs_check.Ref(4, "Usage", "docs/ref.md", False, 2, True),
        docs_check.Ref(6, "Usage", "scripts/run.py", False, 2, False),
        docs_check.Ref(6, "Usage", "build/out.json", False, 2, False),
        docs_check.Ref(9, "`tools/b.py`", "tools/b.py", False, 9, False),
    ]


def test_inline_code_in_three_backticks_does_not_open_a_block():
    text = ("```foo``` is inline code\n# Real heading\n`a/b.py` here\n```bash\n"
            "python scripts/run.py\n```\nplain prose/path.py and `c/d.py`\n")
    refs = list(docs_check.references(text))
    assert [ref.token for ref in refs] == ["a/b.py", "scripts/run.py", "c/d.py"]
    assert refs[0].heading == "Real heading"


def test_a_fence_with_a_language_after_it_does_not_close_a_block():
    text = "```\n```bash\npython x/y.py\n```\n"
    assert [ref.token for ref in docs_check.references(text)] == ["x/y.py"]


def test_line_numbers_are_the_ones_an_editor_shows():
    (ref,) = docs_check.references("a\x0cb c\r\n`x/y.py`\n")
    assert ref.line == 2


def test_a_link_is_looked_for_beside_its_document_only():
    link = docs_check.Ref(1, "(top)", "README.md", False, 0, True)
    assert list(docs_check.candidates("a/b/doc.md", link)) == ["a/b/README.md"]
    assert list(docs_check.candidates("a/b/doc.md", link._replace(rooted=True))) == ["README.md"]


def test_a_shorter_fence_inside_a_longer_one_does_not_close_it():
    text = "````md\n```bash\npython scripts/in.py\n```\npython scripts/still_in.py\n````\n"
    assert [ref.token for ref in docs_check.references(text)] == [
        "scripts/in.py", "scripts/still_in.py"]
    assert not list(docs_check.references("````\n```\n````\nplain scripts/out.py\n"))


def test_a_long_heading_is_cut_and_keeps_no_control_character():
    (ref,) = docs_check.references("# %s\x1b[31m\n`a/b.py`\n" % ("h" * 100))
    assert ref.heading == "h" * 77 + "..."


def test_candidates_start_beside_the_document_and_end_at_the_root():
    ref = docs_check.Ref(1, "(top)", "scripts/x.py", False)
    assert list(docs_check.candidates("a/b/doc.md", ref)) == [
        "a/b/scripts/x.py", "a/scripts/x.py", "scripts/x.py"]
    assert list(docs_check.candidates("a/b/doc.md", ref._replace(rooted=True))) == [
        "scripts/x.py"]


def test_candidates_never_leave_the_repository():
    ref = docs_check.Ref(1, "(top)", "../x.md", False)
    assert list(docs_check.candidates("a/b/doc.md", ref)) == ["a/x.md", "x.md"]
    assert list(docs_check.candidates("doc.md", ref)) == []


def test_read_history_keeps_the_newest_touch_and_how_a_path_went():
    log = ("@ccc\n\nR100\tsrc/a.py\tsrc/b.py\n"
           "@bbb\n\nD\tsrc/old.py\nM\tsrc/a.py\n"
           "@aaa\n\nA\tsrc/a.py\nA\tsrc/old.py\nnot a status line\n")
    history = docs_check.read_history(log)
    assert history.order == {"src/a.py": 0, "src/b.py": 0, "src/old.py": 1}
    assert history.gone == {"src/a.py": ("ccc", "src/b.py"), "src/old.py": ("bbb", None)}
    assert history.dirs == {"src"}


def test_read_history_forgets_a_deletion_the_path_came_back_from():
    history = docs_check.read_history("@c2\n\nA\tx.py\n@c1\n\nD\tx.py\n@c0\n\nA\tx.py\n")
    assert history.gone == {}


def test_read_change_sorts_a_diff_into_removed_modified_and_added():
    change = docs_check.read_change(
        "main", "M\ta.py\nD\tb.py\nR090\tc.py\td.py\nA\te.py\nT\tf.py\n")
    assert change.removed == {"b.py": None, "c.py": "d.py"}
    assert change.modified == {"a.py", "d.py", "f.py"}
    assert change.added == {"e.py"}
    assert change.renamed == {"d.py": "c.py"}
    assert change.count == 5


def test_a_control_character_in_a_file_name_never_reaches_the_terminal():
    ref = docs_check.Ref(1, "(top)", "a/b.py", False)
    dead = [docs_check.Dead("README.md", ref, "a/b.py", "renamed to a/\x1b[31mc.py in abc")]
    lines, code = docs_check.render(dead, [], {"documents": 1, "unread": 0})
    assert lines[1] == "dead    README.md:1 § (top): a/b.py (renamed to a/?[31mc.py in abc)"
    assert code == 2


# --- dead references ----------------------------------------------------

def test_a_deleted_path_is_dead_and_names_the_commit(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "# Usage\n\nRun `scripts/old.py` first.\n",
                          "scripts/old.py": "x = 1\n"})
    remove(top, "scripts/old.py")
    gone = commit(top)
    code, out = run(capsys, top)
    assert code == 2
    assert out == ["docs: 1 dead, 0 to review (1 documents)",
                   "dead    README.md:3 § Usage: scripts/old.py (deleted in %s)" % gone]


def test_a_renamed_path_is_dead_and_names_where_it_went(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "See [old](scripts/old.py).\n",
                          "scripts/old.py": "x = 1\ny = 2\nz = 3\n"})
    git(top, "mv", "scripts/old.py", "scripts/new.py")
    moved = commit(top)
    code, out = run(capsys, top)
    assert code == 2
    assert out[1] == ("dead    README.md:1 § (top): scripts/old.py "
                      "(renamed to scripts/new.py in %s)" % moved)


def test_a_path_renamed_twice_names_where_it_is_now(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`scripts/a.py` and `scripts/k.py`\n",
                          "scripts/a.py": "x = 1\ny = 2\nz = 3\n",
                          "scripts/k.py": "k = 1\nl = 2\nm = 3\n"})
    git(top, "mv", "scripts/a.py", "scripts/b.py")
    git(top, "mv", "scripts/k.py", "scripts/l.py")
    commit(top)
    git(top, "mv", "scripts/b.py", "scripts/c.py")
    remove(top, "scripts/l.py")
    last = commit(top)
    code, out = run(capsys, top)
    assert out[1:] == [
        "dead    README.md:1 § (top): scripts/a.py (renamed to scripts/c.py in %s)" % last,
        "dead    README.md:1 § (top): scripts/k.py (deleted in %s)" % last]


def test_a_path_named_twice_on_one_line_is_one_finding(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "[`scripts/a.py`](scripts/a.py) and `scripts/a.py`\n",
                          "scripts/a.py": "x = 1\n"})
    remove(top, "scripts/a.py")
    commit(top)
    code, out = run(capsys, top)
    assert out[0] == "docs: 1 dead, 0 to review (1 documents)"
    assert len(out) == 2


def test_a_path_deleted_added_back_and_removed_again_names_no_old_commit(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`scripts/a.py`\n", "scripts/a.py": "x = 1\n"})
    remove(top, "scripts/a.py")
    commit(top)
    write(top, "scripts/a.py", "x = 2\n")
    commit(top)
    remove(top, "scripts/a.py")
    assert run(capsys, top)[1][1] == "dead    README.md:1 § (top): scripts/a.py (no longer there)"


def test_a_link_is_dead_where_markdown_would_look_for_it(tmp_path, capsys):
    # A README at the root and an index somewhere else do not mend a link
    # that pointed at the ones beside the document.
    top = repo(tmp_path, {
        "docs/a.md": "[next](README.md) [idx](index.md) [lic](/LICENSE)\n",
        "docs/README.md": "# d\n", "docs/index.md": "# i\n", "LICENSE": "l\n",
        "README.md": "# root\n", "site/index.md": "# s\n", "vendor/LICENSE": "v\n"})
    for rel in ("docs/README.md", "docs/index.md", "LICENSE"):
        remove(top, rel)
    gone = commit(top)
    assert run(capsys, top, "docs") == (2, [
        "docs: 3 dead, 0 to review (1 documents)",
        "dead    docs/a.md:1 § (top): LICENSE (deleted in %s)" % gone,
        "dead    docs/a.md:1 § (top): README.md (deleted in %s)" % gone,
        "dead    docs/a.md:1 § (top): index.md (deleted in %s)" % gone])


def test_a_path_git_now_ignores_is_an_output_not_a_dead_reference(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "Results land in `build/out.json`, under `build/`.\n",
                          "build/out.json": "{}\n"})
    write(top, ".gitignore", "build/\n")
    git(top, "rm", "-r", "-q", "--cached", "build")
    commit(top)
    want = (0, ["docs: 0 dead, 0 to review (1 documents, 2 now ignored)"])
    assert run(capsys, top) == want
    remove(top, "build/out.json")       # and the same in a checkout that never built
    os.rmdir(os.path.join(top, "build"))
    assert run(capsys, top) == want


def test_a_removed_directory_is_dead(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "Everything under `legacy/` is old.\n",
                          "legacy/a.py": "x = 1\n"})
    remove(top, "legacy/a.py")      # by hand: the empty directory stays on disk
    commit(top)
    code, out = run(capsys, top)
    assert code == 2
    assert out[1] == "dead    README.md:1 § (top): legacy/ (no longer there)"


def test_what_git_ignores_does_not_keep_a_removed_directory_alive(tmp_path, capsys):
    # The same commit must read the same here and in a fresh checkout.
    top = repo(tmp_path, {"README.md": "Everything under `legacy/` is old.\n",
                          ".gitignore": "__pycache__/\n", "legacy/a.py": "x = 1\n"})
    remove(top, "legacy/a.py")
    write(top, "legacy/__pycache__/a.cpython-313.pyc", "bytes")
    commit(top)
    code, out = run(capsys, top)
    assert code == 2
    assert out[1] == "dead    README.md:1 § (top): legacy/ (no longer there)"


def test_a_file_removed_but_not_committed_is_dead(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`scripts/a.py`\n", "scripts/a.py": "x = 1\n"})
    remove(top, "scripts/a.py")
    code, out = run(capsys, top)
    assert code == 2
    assert out[1] == "dead    README.md:1 § (top): scripts/a.py (no longer there)"


def test_a_path_that_never_existed_is_left_alone(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "Put it in `src/your_module.py`, like `a/b`.\n"})
    assert run(capsys, top) == (0, ["docs: 0 dead, 0 to review (1 documents)"])


def test_a_path_under_the_readers_home_is_not_this_repositorys(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "Edit `$HOME/.claude/settings.json`.\n",
                          ".claude/settings.json": "{}\n"})
    remove(top, ".claude/settings.json")
    commit(top)
    assert run(capsys, top) == (0, ["docs: 0 dead, 0 to review (1 documents)"])


def test_a_bare_name_is_dead_only_beside_its_document(tmp_path, capsys):
    # In docs/guide.md, `config.json` is whatever the reader's project calls
    # its file; in the root README, `setup.py` is the file that sat next to it.
    top = repo(tmp_path, {"docs/guide.md": "Edit `config.json`.\n", "config.json": "{}\n",
                          "README.md": "Run `setup.py`.\n", "setup.py": "x = 1\n",
                          ".cfg/settings.json": "{}\n", "NOTES.md": "`settings.json`\n"})
    for rel in ("config.json", "setup.py", ".cfg/settings.json"):
        remove(top, rel)
    gone = commit(top)
    assert run(capsys, top) == (2, [
        "docs: 1 dead, 0 to review (3 documents)",
        "dead    README.md:1 § (top): setup.py (deleted in %s)" % gone])


def test_a_new_file_not_yet_added_is_there(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`scripts/new.py`\n", "scripts/new.py": "x = 1\n"})
    # Committed once, gone from the index since, and still on disk.
    git(top, "rm", "-q", "--cached", "scripts/new.py")
    git(top, "commit", "-q", "-m", "untrack")
    assert run(capsys, top)[0] == 0


def test_a_record_is_skipped_unless_it_is_named(tmp_path, capsys):
    top = repo(tmp_path, {"CHANGELOG.md": "Removed `scripts/old.py`.\n",
                          "README.md": "# Hello\n", "scripts/old.py": "x = 1\n"})
    remove(top, "scripts/old.py")
    commit(top)
    assert run(capsys, top) == (0, ["docs: 0 dead, 0 to review (1 documents, 1 records skipped)",
                                    "records skipped: CHANGELOG.md"])
    code, out = run(capsys, top, "CHANGELOG.md")
    assert code == 2
    assert out[0] == "docs: 1 dead, 0 to review (1 documents)"


def test_a_directory_of_records_is_read_when_it_is_the_one_named(tmp_path, capsys):
    top = repo(tmp_path, {"docs/adr/0001.md": "Uses `scripts/old.py`.\n",
                          "docs/guide.md": "# Guide\n", "scripts/old.py": "x = 1\n"})
    remove(top, "scripts/old.py")
    commit(top)
    assert run(capsys, top, "docs")[1] == [
        "docs: 0 dead, 0 to review (1 documents, 1 records skipped)",
        "records skipped: docs/adr/0001.md"]
    code, out = run(capsys, top, "docs/adr")
    assert code == 2
    assert out[0] == "docs: 1 dead, 0 to review (1 documents)"


def test_only_the_first_five_records_are_named(tmp_path, capsys):
    files = {"docs/adr/%d.md" % n: "# n\n" for n in range(7)}
    top = repo(tmp_path, dict(files, **{"README.md": "# Hello\n"}))
    code, out = run(capsys, top)
    assert out[-1] == ("records skipped: docs/adr/0.md, docs/adr/1.md, docs/adr/2.md, "
                       "docs/adr/3.md, docs/adr/4.md and 2 more")


# --- sections to review -------------------------------------------------

def test_a_file_changed_after_its_document_puts_the_section_up_for_review(tmp_path, capsys):
    top = repo(tmp_path, {
        "README.md": "# Build\n\n`scripts/a.py` builds.\n\n# Test\n\n`scripts/b.py` and\n"
                     "`scripts/a.py` test.\n\n# Docs\n\n[more](docs/more.md)\n",
        "docs/more.md": "# More\n", "scripts/a.py": "x = 1\n", "scripts/b.py": "x = 1\n"})
    write(top, "scripts/a.py", "x = 2\n")
    write(top, "docs/more.md", "# More, later\n")     # a document is not code to check against
    commit(top)
    assert run(capsys, top) == (0, [
        "docs: 0 dead, 2 to review (2 documents)",
        "review  README.md:3 § Build: scripts/a.py",
        "review  README.md:8 § Test: scripts/a.py"])
    write(top, "README.md", "# Build\n\n`scripts/a.py` builds, differently now.\n")
    commit(top)
    assert run(capsys, top)[1] == ["docs: 0 dead, 0 to review (2 documents)"]


def test_two_sections_under_the_same_heading_stay_two(tmp_path, capsys):
    top = repo(tmp_path, {
        "README.md": "# A\n\n## Usage\n\n`scripts/a.py`\n\n# B\n\n## Usage\n\n`scripts/b.py`\n",
        "scripts/a.py": "x = 1\n", "scripts/b.py": "x = 1\n"})
    write(top, "scripts/a.py", "x = 2\n")
    write(top, "scripts/b.py", "x = 2\n")
    commit(top)
    assert run(capsys, top)[1][1:] == ["review  README.md:5 § Usage: scripts/a.py",
                                       "review  README.md:11 § Usage: scripts/b.py"]


def test_work_not_committed_yet_counts_on_both_sides(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`scripts/a.py`\n", "scripts/a.py": "x = 1\n"})
    write(top, "scripts/a.py", "x = 2\n")
    assert run(capsys, top)[1] == ["docs: 0 dead, 1 to review (1 documents)",
                                   "review  README.md:1 § (top): scripts/a.py"]
    write(top, "README.md", "`scripts/a.py`, as it is now.\n")
    assert run(capsys, top)[1] == ["docs: 0 dead, 0 to review (1 documents)"]


def test_a_document_is_one_whatever_the_case_of_its_extension(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "[n](NOTES.MD)\n", "NOTES.MD": "# n\n"})
    write(top, "NOTES.MD", "# n, later\n")
    commit(top)
    assert run(capsys, top)[1] == ["docs: 0 dead, 0 to review (2 documents)"]


def test_a_byte_order_mark_does_not_hide_the_first_heading(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "﻿# Title\n\n`scripts/a.py`\n",
                          "scripts/a.py": "x = 1\n"})
    write(top, "scripts/a.py", "x = 2\n")
    commit(top)
    assert run(capsys, top)[1][1] == "review  README.md:3 § Title: scripts/a.py"


def test_a_new_document_not_yet_added_is_read(tmp_path, capsys):
    top = branch_repo(tmp_path)
    older = git(top, "rev-parse", "--short", "HEAD").strip()
    write(top, "DRAFT.md", "# Draft\n\n`scripts/older.py`\n")
    assert run(capsys, top)[1][0] == "docs: 2 dead, 0 to review (3 documents)"
    assert run(capsys, top, "--base", "main") == (2, [
        "docs: 1 dead, 0 to review against main "
        "(0 changed files, 3 documents, 1 dead before this change)",
        "dead    DRAFT.md:3 § Draft: scripts/older.py (deleted in %s)" % older])


def test_a_path_resolves_to_the_nearest_one_above_the_document(tmp_path, capsys):
    top = repo(tmp_path, {"pkg/docs/guide.md": "`scripts/x.py` and `tool.py`\n",
                          "pkg/scripts/x.py": "x = 1\n", "scripts/x.py": "x = 1\n",
                          "lib/tool.py": "x = 1\n"})
    write(top, "pkg/scripts/x.py", "x = 2\n")
    write(top, "lib/tool.py", "x = 2\n")     # the only file of that name anywhere
    commit(top)
    assert run(capsys, top)[1][1] == ("review  pkg/docs/guide.md:1 § (top): "
                                      "lib/tool.py, pkg/scripts/x.py")


def test_a_bare_name_several_files_carry_maps_to_none_of_them(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "`tool.py`\n", "a/tool.py": "x = 1\n",
                          "b/tool.py": "x = 1\n"})
    write(top, "a/tool.py", "x = 2\n")
    commit(top)
    assert run(capsys, top) == (0, ["docs: 0 dead, 0 to review (1 documents)"])


def test_a_document_not_committed_yet_has_nothing_to_review(tmp_path, capsys):
    top = repo(tmp_path, {"scripts/a.py": "x = 1\n"})
    write(top, "NEW.md", "`scripts/a.py`\n")
    git(top, "add", "NEW.md")
    assert run(capsys, top) == (0, ["docs: 0 dead, 0 to review (1 documents)"])


def test_paths_narrow_the_documents_read(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "# r\n", "docs/a.md": "# a\n", "docs/sub/b.md": "# b\n",
                          "other/c.md": "# c\n"})
    assert run(capsys, top, "docs\\", "README.md")[1] == ["docs: 0 dead, 0 to review (3 documents)"]
    assert run(capsys, top, ".")[1] == ["docs: 0 dead, 0 to review (4 documents)"]


def test_a_path_holding_no_markdown_is_a_usage_error(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "# r\n"})
    assert docs_check.main(["--project-dir", top, "nowhere"]) == 1
    assert "no Markdown under: nowhere" in capsys.readouterr().err


def test_a_document_too_large_to_read_is_counted(tmp_path, capsys):
    top = repo(tmp_path, {"README.md": "# r\n",
                          "BIG.md": "x" * (codemap_inventory.MAX_PARSE_BYTES + 1)})
    assert run(capsys, top)[1] == ["docs: 0 dead, 0 to review (1 documents, 1 unreadable)"]


# --- one change, with --base --------------------------------------------

def branch_repo(tmp_path):
    """`main` already carries one dead reference; `work` is checked out on it."""
    top = repo(tmp_path, {
        "README.md": "# Use\n\nRun `scripts/a.py`, then `scripts/b.py`. See `scripts/old.py`.\n",
        "NOTES.md": "# Notes\n\n`scripts/older.py`\n",
        "scripts/a.py": "a = 1\n", "scripts/b.py": "b = 1\nc = 2\nd = 3\n",
        "scripts/old.py": "old = 1\n", "scripts/older.py": "older = 1\n"})
    remove(top, "scripts/older.py")
    commit(top)
    git(top, "checkout", "-q", "-b", "work")
    return top


def test_base_keeps_only_what_this_change_broke(tmp_path, capsys):
    top = branch_repo(tmp_path)
    remove(top, "scripts/old.py")
    write(top, "scripts/a.py", "a = 2\n")
    commit(top)
    assert run(capsys, top, "--base", "main") == (2, [
        "docs: 1 dead, 1 to review against main "
        "(2 changed files, 2 documents, 1 dead before this change)",
        "dead    README.md:3 § Use: scripts/old.py (deleted in this change)",
        "review  README.md:3 § Use: scripts/a.py"])


def test_base_passes_when_the_only_dead_reference_is_older_than_the_change(tmp_path, capsys):
    top = branch_repo(tmp_path)
    write(top, "scripts/b.py", "b = 2\nc = 2\nd = 3\n")
    write(top, "NOTES.md", "# Notes, retitled\n\n`scripts/older.py`\n")     # the old sentence stays
    code, out = run(capsys, top, "--base", "main")      # not committed: still part of the change
    assert code == 0
    assert out == ["docs: 0 dead, 1 to review against main "
                   "(2 changed files, 2 documents, 1 dead before this change)",
                   "review  README.md:3 § Use: scripts/b.py"]


def test_base_counts_a_sentence_this_change_wrote_about_a_path_long_gone(tmp_path, capsys):
    top = branch_repo(tmp_path)
    older = git(top, "rev-parse", "--short", "HEAD").strip()
    write(top, "README.md", "# Use\n\nRun `scripts/a.py`, and `scripts/older.py` too.\n")
    write(top, "NEW.md", "# New\n\nAlso `scripts/older.py`.\n")
    commit(top)
    code, out = run(capsys, top, "--base", "main")
    assert code == 2
    assert out[1:] == [
        "dead    NEW.md:3 § New: scripts/older.py (deleted in %s)" % older,
        "dead    README.md:3 § Use: scripts/older.py (deleted in %s)" % older]


def test_base_counts_a_path_that_resolved_further_up_until_this_change(tmp_path, capsys):
    top = repo(tmp_path, {"pkg/docs/guide.md": "`scripts/x.py`\n",
                          "pkg/scripts/x.py": "x = 1\n", "scripts/x.py": "y = 1\n"})
    remove(top, "pkg/scripts/x.py")     # long ago: the root one answers from here on
    commit(top)
    git(top, "checkout", "-q", "-b", "work")
    assert run(capsys, top, "--base", "main")[0] == 0
    remove(top, "scripts/x.py")
    commit(top)
    assert run(capsys, top, "--base", "main") == (2, [
        "docs: 1 dead, 0 to review against main (1 changed files, 1 documents)",
        "dead    pkg/docs/guide.md:1 § (top): scripts/x.py (deleted in this change)"])


def test_base_counts_a_bare_name_whose_last_file_this_change_removed(tmp_path, capsys):
    top = repo(tmp_path, {"docs/guide.md": "`tool.py`\n", "docs/tool.py": "x = 1\n",
                          "lib/tool.py": "y = 1\n"})
    remove(top, "docs/tool.py")     # long ago: lib/tool.py is the only one of that name since
    commit(top)
    git(top, "checkout", "-q", "-b", "work")
    assert run(capsys, top, "--base", "main")[0] == 0
    remove(top, "lib/tool.py")
    commit(top)
    assert run(capsys, top, "--base", "main") == (2, [
        "docs: 1 dead, 0 to review against main (1 changed files, 1 documents)",
        "dead    docs/guide.md:1 § (top): tool.py (deleted in this change)"])


def test_base_counts_what_moving_a_document_put_out_of_reach(tmp_path, capsys):
    top = repo(tmp_path, {"docs/guide.md": "[img](img/a.png) and `scripts/x.py`\n",
                          "docs/img/a.png": "png\n", "docs/scripts/x.py": "x = 1\n"})
    git(top, "checkout", "-q", "-b", "work")
    os.makedirs(os.path.join(top, "manual", "deep"))
    git(top, "mv", "docs/guide.md", "manual/deep/guide.md")
    commit(top)
    moved = "out of reach since this change moved the document"
    assert run(capsys, top, "--base", "main") == (2, [
        "docs: 2 dead, 0 to review against main (1 changed files, 1 documents)",
        "dead    manual/deep/guide.md:1 § (top): img/a.png (%s)" % moved,
        "dead    manual/deep/guide.md:1 § (top): scripts/x.py (%s)" % moved])


def test_base_sees_a_rename_that_is_not_committed(tmp_path, capsys):
    top = branch_repo(tmp_path)
    git(top, "mv", "scripts/b.py", "scripts/c.py")
    code, out = run(capsys, top, "--base", "main")
    assert code == 2
    assert out[1] == ("dead    README.md:3 § Use: scripts/b.py "
                      "(renamed to scripts/c.py in this change)")


def test_base_counts_a_removed_directory_as_this_changes_doing(tmp_path, capsys):
    top = branch_repo(tmp_path)
    write(top, "README.md", "# Use\n\nEverything in `scripts/` runs.\n")
    for name in ("a.py", "b.py", "old.py"):
        remove(top, "scripts/" + name)
    commit(top)
    code, out = run(capsys, top, "--base", "main")
    assert code == 2
    assert out[1] == "dead    README.md:3 § Use: scripts/ (no longer there)"


def test_base_says_when_the_document_changed_too_and_skips_a_new_one(tmp_path, capsys):
    top = branch_repo(tmp_path)
    write(top, "scripts/a.py", "a = 2\n")
    write(top, "README.md", "# Use\n\nRun `scripts/a.py` twice.\n")
    write(top, "NEW.md", "# New\n\n`scripts/a.py`\n")
    commit(top)
    code, out = run(capsys, top, "--base", "main")
    assert out[1:] == ["review  README.md:3 § Use: scripts/a.py (document also changed)"]


def test_base_reads_a_renamed_document_under_its_old_name(tmp_path, capsys):
    top = branch_repo(tmp_path)
    git(top, "mv", "NOTES.md", "MEMO.md")
    commit(top)
    code, out = run(capsys, top, "--base", "main")
    assert code == 0
    assert out == ["docs: 0 dead, 0 to review against main "
                   "(1 changed files, 2 documents, 1 dead before this change)"]


def test_base_refuses_a_ref_shaped_like_an_option(tmp_path, capsys):
    top = branch_repo(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        docs_check.main(["--project-dir", top, "--base=--output=x"])
    assert stopped.value.code == 1


def test_base_that_names_no_ref_is_a_usage_error(tmp_path, capsys):
    top = branch_repo(tmp_path)
    assert docs_check.main(["--project-dir", top, "--base", "no-such-ref"]) == 1
    assert "no merge base between HEAD and no-such-ref" in capsys.readouterr().err


# --- when nothing can be checked ----------------------------------------

def without(monkeypatch, word):
    """Makes every git call carrying `word` fail the way a timeout does."""
    real = preflight.git

    def fake(cwd, *args, **kwargs):
        return None if word in args else real(cwd, *args, **kwargs)
    monkeypatch.setattr(preflight, "git", fake)


def test_outside_a_repository_nothing_is_checked(tmp_path, capsys):
    assert run(capsys, tmp_path) == (0, ["docs: unsupported (not a git repository)"])


def test_a_repository_with_no_commit_has_no_history_to_read(tmp_path, capsys):
    top = make_repo(tmp_path, {"README.md": "# r\n"}, commit=False)
    assert run(capsys, top) == (0, ["docs: unsupported (git history could not be read)"])


def test_a_shallow_clone_has_too_little_history_to_say_anything(tmp_path, capsys):
    # Without the commits that deleted a path, every dead reference reads as
    # an example that never existed: `0 dead` here would be a guess.
    (tmp_path / "source").mkdir()
    source = repo(tmp_path / "source", {"README.md": "`scripts/a.py`\n", "scripts/a.py": "x\n"})
    remove(source, "scripts/a.py")
    commit(source)
    clone = str(tmp_path / "clone")
    done = subprocess.run(
        ["git", *GIT_IDENTITY, "clone", "-q", "--depth", "1",
         "file:///" + source.replace("\\", "/").lstrip("/"), clone],
        capture_output=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, done.stderr
    assert run(capsys, clone) == (0, ["docs: unsupported (shallow clone)"])


@pytest.mark.parametrize("word, reason", [
    ("rev-parse", "git did not answer"),
    ("--stage", "git could not list the tracked files"),
    ("-d", "git could not list the tracked files"),
    ("-o", "git could not list the tracked files"),
    ("log", "git history could not be read"),
    ("merge-base", "git did not answer"),
    ("diff", "git could not list the change"),
])
def test_a_git_call_that_does_not_answer_is_said_not_guessed(tmp_path, capsys, monkeypatch,
                                                             word, reason):
    top = branch_repo(tmp_path)
    without(monkeypatch, word)
    assert run(capsys, top, "--base", "main") == (0, ["docs: unsupported (%s)" % reason])


def test_uncommitted_work_that_cannot_be_listed_is_said_too(tmp_path, capsys, monkeypatch):
    top = branch_repo(tmp_path)
    without(monkeypatch, "diff")
    assert run(capsys, top) == (0, ["docs: unsupported (git could not list uncommitted work)"])


def test_a_base_document_that_cannot_be_shown_falls_back_to_what_was_removed(
        tmp_path, capsys, monkeypatch):
    top = branch_repo(tmp_path)
    write(top, "README.md", "# Use\n\nRun `scripts/a.py`, and `scripts/older.py` too.\n")
    without(monkeypatch, "show")
    code, out = run(capsys, top, "--base", "main")
    assert code == 0
    assert out[0].endswith("2 dead before this change)")


def test_the_script_runs_as_a_program(tmp_path):
    top = repo(tmp_path, {"README.md": "`scripts/old.py`\n", "scripts/old.py": "x = 1\n"})
    remove(top, "scripts/old.py")
    commit(top)
    done = subprocess.run([sys.executable, SCRIPT, "--project-dir", top],
                          capture_output=True, encoding="utf-8")
    assert done.returncode == 2
    assert done.stdout.startswith("docs: 1 dead, 0 to review (1 documents)\ndead    README.md:1")
