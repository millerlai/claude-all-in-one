"""Text pins for the glossary steps of stage-build.md (#326, #411).

Build no longer asks anyone which glossary terms to write (#411): Step 6.2
picks them from the Detail design's `## Glossary`, checks them, records the
outcome in the notes and writes them. That is prose a model follows, so it is
pinned the way `test_human_in_the_loop_text.py` does it: whitespace folded, one
section at a time, in both trees (`plugins/cai` by hand, `plugins/cai-codex`
regenerated from it).
"""
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TREES = ["plugins/cai", "plugins/cai-codex"]

# How each tree tells the model to run the checker.
INVOKE = {
    "plugins/cai": "python ${CLAUDE_PLUGIN_ROOT}/scripts/glossary_check.py <that file>",
    "plugins/cai-codex": "<cai> glossary_check <that file>",
}
RAN = "the check ran only when its last line is `-- glossary: N entries checked, M flagged`"


def _flat(tree, name):
    path = os.path.join(ROOT, tree, "skills", "track", "references", name)
    with open(path, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def _step_0_5(tree):
    return _between(_flat(tree, "stage-build.md"), "## Step 0.5", "## Step 1 —")


def _step_6_2(tree):
    return _between(_flat(tree, "stage-build.md"),
                    "**Write the merged terms into", "**Review.**")


@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_asks_nothing_about_the_glossary(tree):
    assert "glossary" not in _step_0_5(tree).lower()
    build = _flat(tree, "stage-build.md")
    assert "Merge none" not in build
    assert "multiSelect" not in build


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_asks_nobody(tree):
    item = _step_6_2(tree)
    assert ("Nobody is asked which, under a track or standing alone: "
            "no menu, no pending question") in item
    assert "free text" not in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_picks_only_from_the_design_glossary(tree):
    item = _step_6_2(tree)
    assert ("pick the terms from that `## Glossary` only, never from another "
            "document, the conversation or the file's existing entries") in item
    assert "A project term is a concept specific to this project" in item
    assert "take decision ids and track-document paths out of its definition" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_checks_again_and_writes_nothing_unchecked(tree):
    item = _step_6_2(tree)
    assert INVOKE[tree] in item
    assert "A term it flags is not written" in item
    assert RAN in item
    # The check "did not run" is told by its summary line, not by its exit code:
    # a wrong script path or a usage error exits 2 with no FAIL line.
    assert "whatever the exit code, write nothing, record nothing" in item


ENSURE = {
    "plugins/cai": 'python ${CLAUDE_PLUGIN_ROOT}/scripts/cai_paths.py ensure --project-dir "<top>"',
    "plugins/cai-codex": '<cai> cai_paths ensure --project-dir "<top>"',
}


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_writes_into_cai_and_never_commits_it(tree):
    # The glossary went into git on every branch and conflicted with every
    # parallel one; it now lives in .cai/, which ignores itself.
    item = _step_6_2(tree)
    assert ENSURE[tree] in item
    assert "if `.cai/cai-context.md`" in item
    assert "Never `git add` or commit the file, whatever the commit answer" in item
    assert ".claude/cai-context.md" not in item
    assert "commit this write" not in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_places_a_new_term_beside_a_related_one_or_in_name_order(tree):
    item = _step_6_2(tree)
    assert "that it is most closely related to" in item
    assert "whose name sorts after the new term's" in item
    assert "after the last entry under its" not in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_records_before_it_writes_and_never_rejudges(tree):
    item = _step_6_2(tree)
    assert "A finished glossary record is never judged again" in item
    assert "before `.cai/cai-context.md` is touched" in item
    assert ("**Glossary record** for <the design document's path, relative to "
            "`<top>`> at <what git hash-object printed>") in item
    assert ("names the design document's path relative to `<top>`, written "
            "with `/`, and that hash") in item
    assert "quote git's first line in the report and skip the rest of this item" in item
    assert ("With no `- Write:` entry in the record, write nothing, create no "
            "file and skip the rest of this item") in item
    assert "or flagged by this run's check" in item
    assert "Run `git hash-object <the design document>` from `<top>`" in item
    assert ("or that names another hash because the design changed since, "
            "counts as never written") in item
    assert "- Complete: yes" in item
    assert "A finished record with no `- Line:` entry runs no check" in item
    assert "On a rerun from a finished record, the report is built from the record" in item
    # The record is looked up before anything is judged, the skip conditions included.
    assert (item.index("A finished glossary record is never judged again")
            < item.index("With no such record, skip entirely"))


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_says_nothing_when_there_is_no_design_document(tree):
    # A standing-alone build can have no design document at all; the record
    # lookup runs before the skip conditions, so without this sentence it would
    # hash a path that does not exist and report a git failure for a build that
    # had no glossary work.
    item = _step_6_2(tree)
    assert ("With no design document there is nothing to hash: skip this item "
            "entirely and say nothing about it in the report") in item
    assert (item.index("With no design document there is nothing to hash")
            < item.index("Run `git hash-object <the design document>`"))


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_writes_the_checked_line_and_keeps_to_project_terms(tree):
    # AC2: what reaches the file is what the check saw, and the exclusion list
    # and the rewrite rule travel with the pick.
    item = _step_6_2(tree)
    assert "write each `- Line:` exactly as it was checked, in the record's order" in item
    assert ("Build leaves out file names, functions, fields, status strings, "
            "agent names and everyday words") in item
    assert ("rewrite a definition that reads like a rule or a number into one "
            "or two sentences saying what the thing is") in item
    assert ("give it `## Domain` for something the project deals in and "
            "`## Process` for a step, stage or role, never another heading") in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_places_and_replaces_by_name_and_touches_nothing_else(tree):
    # AC3, K3: same name under any heading is replaced in place; a new line
    # goes under its own heading; nothing else in the file moves.
    item = _step_6_2(tree)
    assert "The first line in the file, under any heading, whose bold name is the same term" in item
    assert ("the new line goes after the entry under its `- Write:` heading that "
            "it is most closely related to") in item
    assert "and past any `_Avoid_` lines directly under that entry" in item
    assert "directly under that heading when it has none" in item
    assert ("a term left out or kept out never changes an existing entry, even "
            "one with its name") in item
    assert "A line that already reads as the recorded line is left as it is" in item
    # The hand-change guard fires only when the line is neither of the two the
    # record knows; weakened to "differs from the recorded line" it would
    # refuse every first-time replacement.
    assert ("is neither the recorded line nor the line the record says it "
            "replaces") in item
    assert "- Replaces: <the line it replaces, verbatim>, or nothing" in item
    # A replaced line stays under the heading it had, which may not be the one
    # build picked; the report must say where the line really is (K5).
    assert ("It stays under the heading it was under, and the report names "
            "that heading, on a rerun too, not the one its `- Write:` entry says") in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_adds_back_a_missing_domain_or_process_heading(tree):
    item = _step_6_2(tree)
    assert ("when the file lacks that `## Domain` or `## Process` heading, add "
            "it at the end of the file first; those two are the only headings "
            "build ever adds") in item
    assert "the heading is not re-created" not in item
    assert "a heading the menu named" not in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_matches_names_the_way_the_check_does(tree):
    item = _step_6_2(tree)
    assert ("the same once backticks are dropped, runs of whitespace are "
            "folded to one and case is ignored, the way the glossary check "
            "compares names") in item
    assert "is replaced in place" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_leaves_a_line_changed_by_hand(tree):
    item = _step_6_2(tree)
    assert ("it was changed by hand in between: write nothing for that term "
            "and quote what the file holds in the report") in item


@pytest.mark.parametrize("tree", TREES)
def test_report_lists_every_term_written_and_keeps_it_out_of_the_ceiling(tree):
    build = _flat(tree, "stage-build.md")
    step_6_4 = _between(build, "4. **Report.**", "Each deviation that changed an interface")
    assert "the name and heading of every glossary term written" in step_6_4
    assert "every free-text term" not in step_6_4
    report = build[build.index("## Report This is what you hand back"):]
    assert "the name and heading of every glossary term written" in report
    assert "that the glossary check did not run, when it did not" in report
    assert "The glossary item above is not counted toward the ceiling either" in report


@pytest.mark.parametrize("tree", TREES)
def test_report_names_what_was_replaced_kept_out_and_not_written(tree):
    # AC4, K5: the report is the only place a person sees the old text, the
    # reason a term was refused, and that the file will not reach the PR.
    build = _flat(tree, "stage-build.md")
    step_6_4 = _between(build, "4. **Report.**", "Each deviation that changed an interface")
    assert ("every glossary definition replaced with the old text quoted, every "
            "glossary term the check kept out with its reason, every glossary "
            "line Step 6.2 left alone because it was changed by hand, quoted") in step_6_4
    report = build[build.index("## Report This is what you hand back"):]
    assert ("every glossary definition replaced, old text quoted; every glossary "
            "term the check kept out, with its reason") in report
    assert "and git's first line, when `git hash-object` failed" in report
    item = _step_6_2(tree)
    assert "say in the report that it was written but will not reach the PR" in item
    assert "the report still names every term kept out" in item
    assert "the report names it with the reason the check printed" in item


@pytest.mark.parametrize("tree", TREES)
def test_verify_standing_alone_gets_the_glossary_record(tree):
    build = _flat(tree, "stage-build.md")
    assert "the glossary record Step 6.2 kept in `implementation-notes.md`" in build
    assert "Step 0.5's glossary answer" not in build


@pytest.mark.parametrize("tree", TREES)
def test_template_says_build_adds_only_domain_or_process(tree):
    path = os.path.join(ROOT, tree, "templates", "cai-context.md.tpl")
    with open(path, encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert ("Build adds new terms under these two headings only, puts either "
            "one back at the end of the file when it is missing, and never "
            "adds another") in text
    assert "only after a menu named it" not in text


@pytest.mark.parametrize("tree", TREES)
def test_ledger_note_carries_glossary_counts_only(tree):
    path = os.path.join(ROOT, tree, "skills", "track", "SKILL.md")
    with open(path, encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "goes into that note as three counts" in text
    # The reason for the counts: a list in the note pushes `Left open:` off the
    # end, where ledger.py cuts.
    assert "never as the list itself" in text


@pytest.mark.parametrize("tree", TREES)
def test_no_glossary_menu_left_in_gates_or_pending_questions(tree):
    assert "glossary menus" not in _flat(tree, "pending-questions.md")
    gates = _flat(tree, "approval-gates.md")
    assert "Step 0.5 glossary" not in gates
    assert "menus carry none either" not in gates
    assert "glossary menus being the other" not in gates


# --- #420: the minor findings left from #411's verify ------------------------

@pytest.mark.parametrize("tree", TREES)
def test_step_0_5_and_the_reference_run_keep_their_counts(tree):
    # Coverage m1: the counts the stop budget rests on.
    assert ("up to two answers standing alone and at most one under a track"
            in _step_0_5(tree))
    gates = _flat(tree, "approval-gates.md")
    assert "The table counts the stops from Step 0.5 to the merge, six at most" in gates


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_skip_conditions_and_template_are_pinned(tree):
    # Coverage m2.
    item = _step_6_2(tree)
    assert "when the document is not a Detail design" in item
    assert ("its `## Glossary` has no data row that is not the template's "
            "placeholder") in item
    assert "or none of its terms is a project term" in item
    assert "does not exist, create it verbatim from" in item
    assert "templates/cai-context.md.tpl" in item


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_says_a_deleted_line_comes_back(tree):
    # m2: a rerun cannot tell a line deleted by hand from one never written.
    assert ("A `- Write:` entry whose `- Replaces:` says nothing, and whose name "
            "no line in the file carries, is written again") in _step_6_2(tree)


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_quotes_the_replaced_line_when_the_check_did_not_run(tree):
    # m3
    assert ("quoting its `- Replaces:` line when it names one" in _step_6_2(tree))


@pytest.mark.parametrize("tree", TREES)
def test_step_6_2_keeps_an_avoid_line_with_its_entry(tree):
    # m5
    assert ("and past any `_Avoid_` lines directly under that entry"
            in _step_6_2(tree))


def test_glossary_check_names_no_maintainer_path():
    # Conformance m1: a shipped file names no path into this repo's tooling.
    path = os.path.join(ROOT, "plugins", "cai", "scripts", "glossary_check.py")
    with open(path, encoding="utf-8") as fh:
        assert "scripts/validate.py" not in fh.read()
