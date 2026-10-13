"""#405: the codemap scripts say their rules themselves, keep one copy of each
constant and string, and carry no raw invisible character.
"""
import glob
import os
import re

import pytest

import codemap_cli
import codemap_index as idx
import codemap_inventory as inventory
import codemap_query
import codemap_repomap as rm
import codemap_store as store
import codemap_symbols as symbols
import preflight

SCRIPTS = os.path.dirname(os.path.abspath(codemap_cli.__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPTS)))
SOURCES = sorted(glob.glob(os.path.join(SCRIPTS, "codemap_*.py"))) + [
    os.path.join(REPO, "scripts", "codemap_recall.py")]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("path", SOURCES, ids=os.path.basename)
def test_no_raw_invisible_character_in_the_source(path):
    # Item 9: written as escapes, so an editor or a code page cannot drop them.
    text = _read(path)
    assert not [hex(ord(c)) for c in text if ord(c) in (0xFEFF, 0xFFFD, 0x200B)]


@pytest.mark.parametrize("path", SOURCES[:-1], ids=os.path.basename)
def test_no_design_section_numbers_in_shipped_scripts(path):
    # Item 1: the design document is not in an installed copy.
    assert not re.search(r"\bT\d+-\d+\b", _read(path))


def test_the_one_mib_cap_is_written_once():
    # Item 4
    count = sum(_read(p).count("1048576") + _read(p).count("1 << 20") for p in SOURCES)
    assert count == 1
    assert idx.MAX_PARSE_BYTES == codemap_query.MAX_TEXT_BYTES == inventory.MAX_PARSE_BYTES


def test_the_map_points_at_the_store_names():
    # Item 5
    base = "/".join(store.INDEX_PARTS)
    assert rm.SYMBOLS_POINTER == "%s/%s" % (base, store.SYMBOLS_NAME)
    assert rm.FILES_POINTER == "%s/%s" % (base, store.FILES_NAME)
    assert rm.SHARD_DIR == "%s/packages/" % base


def test_no_production_function_is_only_for_tests():
    # Items 2 and 3
    assert not hasattr(rm, "estimate_tokens")
    assert "total_symbols" not in _read(rm.__file__)


def test_the_tracked_files_reason_is_one_string():
    # Item 7
    for path in (idx.__file__, store.__file__):
        assert _read(path).count('".cai/codemap holds tracked files"') <= 1
    assert store.TRACKED_REASON == ".cai/codemap holds tracked files"


def test_query_and_inventory_share_the_skip_rule():
    # Item 8
    assert inventory.skip_reason("120000", True) == "symlink"
    assert inventory.skip_reason("160000", True) == "submodule"
    assert inventory.skip_reason("100644", False) == "path-not-utf8"
    assert inventory.skip_reason("100644", True) is None
    assert "120000" not in _read(codemap_query.__file__)


def test_recall_and_query_share_the_line_match():
    # Item 8: the baseline and the index count matching lines the same way,
    # editor lines included (#404).
    assert codemap_query.matching_lines("a needle\x0cb\nNeedle c\nx", ["needle"]) == [
        (1, "a needle\x0cb"), (2, "Needle c")]
    recall = _read(SOURCES[-1])
    assert "splitlines" not in recall
    assert 'in ("absent", "unsupported")' not in recall
    assert 'in ("absent", "unsupported")' not in _read(codemap_cli.__file__)


def test_codemap_calls_no_private_preflight_name():
    # Item 10
    for path in SOURCES[:-1]:
        assert not re.search(r"preflight\._\w", _read(path)), path
    assert preflight.escape_control_chars("a\nb") == "a\\x0ab"
    assert preflight.named_paths(["a"], "file changed") == "1 file changed: a"


@pytest.mark.parametrize("data, reason", [
    (b"x = 1\0\n", "undecodable"),
    (b"x = '\xff'\n", "undecodable"),
    (b'x = "\\N{NO SUCH NAME}"\n', "syntax-error at line 1"),
])
def test_python_failures_do_not_depend_on_cpython_message_text(data, reason):
    # Item 12: NUL and a bad encoding are found before parsing.
    assert symbols.extract("m.py", "python", data).reason == reason


def test_a_declared_encoding_still_parses():
    data = "# -*- coding: latin-1 -*-\ndef f(): return '\xe9'\n".encode("latin-1")
    assert [s["name"] for s in symbols.extract("m.py", "python", data).symbols] == ["f"]


def test_a_bom_is_still_dropped_before_line_patterns():
    data = "﻿export function f() {}\n".encode("utf-8")
    assert [s["name"] for s in symbols.extract("m.ts", "typescript", data).symbols] == ["f"]
