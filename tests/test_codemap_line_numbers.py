"""#404: a reported line is the line an editor shows, a file marked exact holds
every top-level declaration, and two tracked names that differ only in bytes
that are not UTF-8 are two entries.
"""
import os

import pytest

import codemap_index as idx
import codemap_inventory as inventory
import codemap_query
import codemap_store as store
import codemap_symbols as symbols
from codemap_repo import git, make_repo

# Each of these makes str.splitlines start a new line; none of them does in an
# editor, in git or in the Read tool.
SPLITTERS = ["\x0b", "\x0c", "\x1c", "\x85", " ", " "]


@pytest.mark.parametrize("ch", SPLITTERS)
def test_go_line_numbers_ignore_a_character_splitlines_breaks_on(ch):
    text = "package p\n\n// a%sb\nfunc F() {}\n" % ch
    got = symbols.extract("p.go", "go", text.encode("utf-8"))
    assert [(s["name"], s["start_line"]) for s in got.symbols] == [("F", 4)]


@pytest.mark.parametrize("ch", SPLITTERS)
def test_ts_line_numbers_ignore_a_character_splitlines_breaks_on(ch):
    text = "// a%sb\nexport function f() {}\n" % ch
    got = symbols.extract("p.ts", "typescript", text.encode("utf-8"))
    assert [(s["name"], s["start_line"]) for s in got.symbols] == [("f", 2)]


def test_editor_lines_splits_on_the_three_line_ends_only():
    assert symbols.editor_lines("a\r\nb\rc\nd\x0ce f") == ["a", "b", "c", "d\x0ce f"]


def test_a_text_hit_reports_the_editor_line(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n",
                               "notes.txt": "one\x0c \x85 still one\nneedle\n"})
    idx.build(top)
    hits = [h for h in codemap_query.query(top, store.load(top), "needle", 10)
            if h.kind == "text"]
    assert [(h.path, h.line) for h in hits] == [("notes.txt", 2)]


def test_declarations_under_top_level_if_try_and_with_are_symbols():
    text = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    class Hint:\n"
        "        def m(self): ...\n"
        "else:\n"
        "    def fallback(): ...\n"
        "try:\n"
        "    def fast(): ...\n"
        "except ImportError:\n"
        "    def slow(): ...\n"
        "finally:\n"
        "    def last(): ...\n"
        "with open(__file__) as fh:\n"
        "    def inside(): ...\n"
    )
    got = symbols.extract("m.py", "python", text.encode("utf-8"))
    assert got.confidence == "exact"
    assert [(s["qualified_name"], s["kind"], s["start_line"]) for s in got.symbols] == [
        ("Hint", "class", 3), ("Hint.m", "method", 4), ("fallback", "function", 6),
        ("fast", "function", 8), ("slow", "function", 10), ("last", "function", 12),
        ("inside", "function", 14)]


def _bytes_named(tmp_path, names):
    """A repo tracking files with these raw byte names, or a skip where the
    filesystem refuses them (Windows; macOS APFS rejects names that are not UTF-8)."""
    top = str(tmp_path)
    git(top, "init", "-q")
    for raw in names:
        try:
            with open(os.path.join(os.fsencode(top), raw), "wb") as fh:
                fh.write(b"x = 1\n")
        except (OSError, ValueError):
            pytest.skip("this filesystem refuses the name")
    git(top, "add", "-A")
    git(top, "commit", "-q", "-m", "init")
    return top


@pytest.mark.skipif(os.name == "nt", reason="Windows file names are Unicode")
def test_names_differing_only_in_non_utf8_bytes_are_two_entries(tmp_path):
    top = _bytes_named(tmp_path, [b"a\xff.py", b"a\xfe.py", b"ok.py"])

    listed = inventory.list_tracked(top)
    facts = inventory.inventory(top)

    assert listed == [("100644", "a\\xfe.py", False), ("100644", "a\\xff.py", False),
                      ("100644", "ok.py", True)]
    assert [(f.path, f.reason) for f in facts] == [
        ("a\\xfe.py", "path-not-utf8"), ("a\\xff.py", "path-not-utf8"), ("ok.py", None)]
    assert idx.build(top).total == 3


@pytest.mark.skipif(os.name == "nt", reason="Windows refuses a carriage return in a file name")
def test_a_carriage_return_in_a_name_stays_a_carriage_return(tmp_path):
    top = _bytes_named(tmp_path, [b"a\rb.py"])

    [f] = inventory.inventory(top)

    assert (f.path, f.reason, f.sha256 is not None) == ("a\rb.py", None, True)
