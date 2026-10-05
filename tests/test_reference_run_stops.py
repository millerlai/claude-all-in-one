"""approval-gates.md's table of the reference run's stops (AC12, R7).

The reference run is the one stops are counted on: ticket mirroring on, a
design with no gaps, all three Step 0.5 questions asked, one fix round, then
a merge. The table must stay at seven rows or fewer, and each row has to point
at a stop that really exists: the file it names must contain the quotation
printed beside the name. A row that cites a sentence nobody can find is a stop
the text no longer describes.
"""
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REFERENCES = os.path.join("skills", "track", "references")
HEADING = "### The reference run's stops"
MAX_STOPS = 7
ROW = re.compile(r"^\| (\d+) \| (?P<stop>[^|]+) \| `(?P<file>[\w.-]+\.md)` \"(?P<quote>[^\"]+)\" \| (?P<when>[^|]+) \|$")


def _flat(text):
    return " ".join(text.split())


def _read(plugin_root, name):
    with open(os.path.join(ROOT, plugin_root, REFERENCES, name), encoding="utf-8") as fh:
        return fh.read()


def _split_table(text):
    """(the table section, the text with that section taken out)."""
    start = text.index(HEADING)
    rest = text[start + len(HEADING):]
    end = re.search(r"\n#{1,3} ", rest)
    stop = start + len(HEADING) + (end.start() if end else len(rest))
    return text[start:stop], text[:start] + text[stop:]


def _table(plugin_root):
    section, _ = _split_table(_read(plugin_root, "approval-gates.md"))
    return [ln for ln in section.splitlines() if ln.startswith("| ")]


def _haystack(plugin_root, name):
    """The file a row cites, without the table itself: a row prints its own
    quotation, so searching the table too would let a deleted sentence pass."""
    text = _read(plugin_root, name)
    return _split_table(text)[1] if name == "approval-gates.md" else text


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_the_table_sits_at_the_end_of_the_other_stops(plugin_root):
    text = _read(plugin_root, "approval-gates.md")
    other = text.index("## The other stops")
    assert other < text.index(HEADING) < text.index("## A menu that closes on its own")


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_the_reference_run_has_at_most_seven_stops(plugin_root):
    lines = _table(plugin_root)
    # lines[0] is the header; the `|---|` separator does not start with `| `.
    assert lines[0].split("|")[1:-1] == [" # ", " Stop ", " Defined in ", " Asked when "]
    rows = lines[1:]
    assert 1 <= len(rows) <= MAX_STOPS, len(rows)


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_every_row_quotes_a_sentence_its_file_really_contains(plugin_root):
    rows = _table(plugin_root)[1:]
    assert rows
    for number, line in enumerate(rows, start=1):
        m = ROW.match(line)
        assert m, line
        assert int(line.split("|")[1]) == number, line
        assert _flat(m.group("quote")) in _flat(_haystack(plugin_root, m.group("file"))), line


@pytest.mark.parametrize("plugin_root", ["plugins/cai", "plugins/cai-codex"])
def test_the_table_covers_the_seven_stops_the_design_counted(plugin_root):
    stops = " ".join(ROW.match(ln).group("stop") for ln in _table(plugin_root)[1:]).lower()
    for word in ("commit", "parallel lane", "glossary", "push menu", "triage",
                 "fix round", "merge"):
        assert word in stops, word
