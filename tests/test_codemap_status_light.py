"""#449: status no longer parses symbols.jsonl. Its fresh line's "M with
symbols" comes from state.json, written with the index; symbols.jsonl is still
checked against its sha256, so a changed file still makes status unsupported.
update and query keep the full load, which checks every symbol record."""
import json
import os

import pytest

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import make_repo

FILES = {"a.py": "def f():\n    pass\n\nclass C:\n    def m(self):\n        pass\n",
         "b.py": "def g():\n    pass\n", "r.md": "# r\n", "c.go": "package c\n"}


def _built(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path)


def _state(top):
    with open(os.path.join(top, ".cai", "codemap", "state.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_state_records_how_many_files_have_symbols(tmp_path):
    top = _built(tmp_path)
    expected = len({s["path"] for s in store.load(top).symbols})
    assert _state(top)["files_with_symbols"] == expected == 2
    assert _state(top)["schema_version"] == 4


def test_the_fresh_line_is_unchanged(tmp_path):
    top = _built(tmp_path)
    assert idx.status(top).detail.startswith("4 files, 2 with symbols, head ")


def test_status_parses_no_symbol_record(tmp_path, monkeypatch):
    top = _built(tmp_path)

    def refuse(record):
        raise AssertionError("status parsed a symbol record")

    monkeypatch.setattr(store, "_is_symbol_record", refuse)
    assert idx.status(top).word == "fresh"


def test_a_changed_symbols_file_is_still_unsupported(tmp_path):
    top = _built(tmp_path)
    path = os.path.join(top, ".cai", "codemap", "symbols.jsonl")
    with open(path, "ab") as fh:
        fh.write(b'{"path": "x"}\n')
    st = idx.status(top)
    assert st.word == "unsupported"
    assert "symbols.jsonl does not match state.json" in st.detail


@pytest.mark.parametrize("value", [None, "2", -1, True])
def test_a_bad_count_is_unreadable_and_rebuilt(tmp_path, capsys, value):
    top = _built(tmp_path)
    state = _state(top)
    if value is None:
        del state["files_with_symbols"]
    else:
        state["files_with_symbols"] = value
    with open(os.path.join(top, ".cai", "codemap", "state.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    assert idx.status(top).word == "unsupported"
    assert codemap_cli.main(["update", "--project-dir", top]) == 0
    assert "Traceback" not in capsys.readouterr().out
    assert idx.status(top).word == "fresh"


def test_query_still_loads_the_symbols(tmp_path, capsys):
    top = _built(tmp_path)
    assert codemap_cli.main(["query", "--project-dir", top, "--", "C.m"]) == 0
    assert "C.m" in capsys.readouterr().out
