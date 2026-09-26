"""Unit: `## A menu that closes on its own` in
`references/approval-gates.md` -- what happens when a question the track
asked times out (the platform's own auto-continue, not the person answering).

Both trees carry this section -- `plugins/cai` by hand, `plugins/cai-codex`
regenerated from it by `scripts/gen-codex.py` -- so these tests run against
both, the same way `scripts/validate.py` checks both trees for other things.
"""
import os
import re

import pytest


def _reference(plugin_root, name):
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        plugin_root, "skills", "track", "references", name)


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(path):
    # Markdown soft-wraps a sentence across lines for width, same as every
    # other reference file -- collapsing that back to single spaces is what
    # lets a phrase-level assertion below match regardless of where the
    # editor happened to break the line.
    return " ".join(_text(path).split())


HEADING = "## A menu that closes on its own"


def _section(plugin_root):
    path = _reference(plugin_root, "approval-gates.md")
    text = _flat(path)
    return text[text.index(HEADING):]


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_has_the_heading(plugin_root):
    assert HEADING in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_unanswered_is_not_an_answer(plugin_root):
    assert "is not an answer" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_names_the_parallel_lane_and_sequential_fallback(plugin_root):
    section = _section(plugin_root)
    assert "parallel lane" in section
    assert "sequential" in section


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_names_the_directory_name_row(plugin_root):
    assert "directory name" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_no_round_of_pending_questions(plugin_root):
    assert "no round" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_asked_again_after_the_person_next_writes(plugin_root):
    assert "after the person next writes" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_recommended_is_backtick_quoted(plugin_root):
    assert "`(recommended)`" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_free_text_counts_as_nothing_selected(plugin_root):
    assert "free-text" in _section(plugin_root)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_no_bare_30_second_timeout_claim(plugin_root):
    assert not re.search(r"\b30\s?s\b", _section(plugin_root), re.IGNORECASE)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_gate_1_grants_nothing_on_timeout(plugin_root):
    section = _section(plugin_root)
    assert "Gate 1" in section
    assert "approved" in section
    assert "Nothing is written" in section
    assert "does not start" in section


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_gate_2_and_ship_items_grant_nothing_on_timeout(plugin_root):
    section = _section(plugin_root)
    assert "Gate 2" in section
    assert "the squash" in section
    assert "the ticket comment" in section
    assert "closing the ticket" in section
    assert "None of it runs" in section


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_step_0_5_commit_per_unit_and_glossary_fixed_fallbacks(plugin_root):
    section = _section(plugin_root)
    assert "Step 0.5 commit per unit" in section
    assert "Step 0.5 glossary" in section
    assert "left untouched" in section


def test_cai_names_the_setting_and_its_default():
    section = _section("plugins/cai")
    assert "askUserQuestionTimeout" in section
    assert "away from your keyboard" in section
    assert "60s" in section


def test_codex_calls_the_close_behavior_untested():
    section = _section("plugins/cai-codex")
    assert "untested" in section


def _between(path, start_marker, end_marker):
    # Unlike _flat above, blank-line boundaries matter here to find where an
    # inserted paragraph ends, so slice the raw text first and only flatten
    # the slice afterward for phrase-level matching.
    text = _text(path)
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return " ".join(text[start:end].split())


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_stage_build_step_0_5_menu_closes_on_its_own(plugin_root):
    path = _reference(plugin_root, "stage-build.md")
    text = _text(path)
    marker = "A Step 0.5 menu that closes on its own"
    start = text.index(marker)
    end = text.index("\n\n", start)
    para = " ".join(text[start:end].split())
    assert "commit per unit" in para
    assert "sequential" in para
    assert "merge none" in para


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_pending_questions_step_1_closes_on_its_own(plugin_root):
    path = _reference(plugin_root, "pending-questions.md")
    para = _between(
        path,
        "1. **Ask one decision per turn.**",
        "2. **Re-dispatch")
    assert "closes on its own" in para
    assert "no round" in para


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_ticket_mirror_step_3_closes_on_its_own(plugin_root):
    path = _reference(plugin_root, "ticket-mirror.md")
    para = _between(path, "3. **Ask", "4. **Create")
    assert "closes on its own" in para
