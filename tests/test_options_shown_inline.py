"""Unit: Step 0 of `references/pending-questions.md` (and its Codex mirror)
sends the linted options text itself as the message that asks, rather than
only naming the file it was written to.

Both trees carry this wording -- `plugins/cai` by hand, `plugins/cai-codex`
regenerated from it by `scripts/gen-codex.py` -- so these tests run against
both, the same way `scripts/validate.py` checks both trees for other things.
"""
import os

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


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_step0_says_the_linted_text_is_sent_in_full(plugin_root):
    path = _reference(plugin_root, "pending-questions.md")
    text = _flat(path)
    start = text.index("0. **Lay the options out before asking")
    end = text.index("1. **Ask one decision per turn.**")
    step0 = text[start:end]
    assert "send the linted text itself, in full" in step0


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_step0_names_path_plus_summaries_as_the_failure(plugin_root):
    path = _reference(plugin_root, "pending-questions.md")
    text = _flat(path)
    start = text.index("0. **Lay the options out before asking")
    end = text.index("1. **Ask one decision per turn.**")
    step0 = text[start:end]
    assert "A file path plus a one-line summary per option" in step0


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_approval_gates_puts_reasoning_in_the_same_message(plugin_root):
    path = _reference(plugin_root, "approval-gates.md")
    text = _flat(path)
    assert "in full in the same message, before the options" in text
