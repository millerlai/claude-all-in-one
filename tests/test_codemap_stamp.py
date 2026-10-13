"""An index records which extractor and which Python wrote it, and is rebuilt
in full when either differs: a reused record would otherwise keep saying what
the old extractor said."""
import json
import os
import sys

import codemap_index as idx
import codemap_store as store
import codemap_symbols as symbols
from codemap_repo import make_repo

FILES = {"a.py": "def f(x):\n    return x\n", "b.py": "def g():\n    pass\n", "r.md": "# r\n"}
PARTS = ("files.jsonl", "symbols.jsonl", "repo-map.md")


def _built(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path)


def _state_path(top):
    return os.path.join(top, ".cai", "codemap", "state.json")


def _edit_state(top, change):
    with open(_state_path(top), encoding="utf-8") as fh:
        state = json.load(fh)
    change(state)
    with open(_state_path(top), "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def _parts(top):
    out = {}
    for name in PARTS:
        with open(os.path.join(top, ".cai", "codemap", name), "rb") as fh:
            out[name] = fh.read()
    return out


def _full_build_elsewhere(tmp_path_factory):
    other = tmp_path_factory.mktemp("full")
    make_repo(other, FILES)
    idx.build(str(other))
    return _parts(str(other))


def _rebuilt_in_full(top, tmp_path_factory):
    assert idx.status(top).word != "fresh"
    res = idx.update(top)
    assert res.reparsed == res.total
    assert idx.status(top).word == "fresh"
    assert _parts(top) == _full_build_elsewhere(tmp_path_factory)


def test_a_new_index_carries_the_stamp_and_schema_two(tmp_path):
    top = _built(tmp_path)
    with open(_state_path(top), encoding="utf-8") as fh:
        state = json.load(fh)
    assert state["schema_version"] == 2
    assert state["extractor_version"] == store.EXTRACTOR_VERSION
    assert state["python_version"] == "%d.%d" % sys.version_info[:2]
    assert store.extractor_stamp() == {"extractor_version": store.EXTRACTOR_VERSION,
                                       "python_version": state["python_version"]}


def test_a_changed_extractor_version_rebuilds_in_full(tmp_path, tmp_path_factory, monkeypatch):
    top = _built(tmp_path)
    real = symbols.extract

    def changed(path, language, data):
        got = real(path, language, data)
        return got._replace(symbols=[dict(s, signature="(changed)") for s in got.symbols])

    monkeypatch.setattr(symbols, "extract", changed)
    monkeypatch.setattr(store, "EXTRACTOR_VERSION", store.EXTRACTOR_VERSION + 1)
    _rebuilt_in_full(top, tmp_path_factory)


def test_another_python_version_rebuilds_in_full(tmp_path, tmp_path_factory):
    top = _built(tmp_path)
    _edit_state(top, lambda s: s.__setitem__("python_version", "2.7"))
    _rebuilt_in_full(top, tmp_path_factory)


def test_a_missing_stamp_rebuilds_in_full(tmp_path, tmp_path_factory):
    top = _built(tmp_path)

    def drop(state):
        del state["extractor_version"], state["python_version"]
    _edit_state(top, drop)
    _rebuilt_in_full(top, tmp_path_factory)


def test_an_index_written_by_v1_52_0_says_which_cai_wrote_it(tmp_path):
    top = _built(tmp_path)

    def as_v1_52_0(state):
        state["schema_version"] = 1
        del state["extractor_version"], state["python_version"]
    _edit_state(top, as_v1_52_0)
    assert idx.state_line(idx.status(top)) == (
        "codemap: unsupported (index unreadable: "
        "built by another codemap or Python version; run build)")
