"""`load` vouches for the shape of what it hands the readers, not only for its
bytes: a record the readers cannot use, or an artifacts table that leaves out a
file they open, is an unreadable index and `update` rebuilds it."""
import hashlib
import json
import os

import pytest

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import make_repo

FILES = {"a.py": "def f():\n    pass\n", "b.py": "def g():\n    pass\n", "r.md": "# r\n"}


def _built(tmp_path, files=FILES):
    make_repo(tmp_path, files)
    idx.build(str(tmp_path))
    return str(tmp_path)


def _state_path(top):
    return os.path.join(top, ".cai", "codemap", "state.json")


def _read_state(top):
    with open(_state_path(top), encoding="utf-8") as fh:
        return json.load(fh)


def _write_state(top, state):
    with open(_state_path(top), "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def _rewrite(top, name, edit):
    """Lets `edit` change the records of one data file, writes them back and
    repairs the digest state.json holds, so only the shape is wrong."""
    path = os.path.join(top, ".cai", "codemap", name)
    with open(path, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh.read().split("\n") if line]
    records = edit(records)
    body = "".join(json.dumps(r) + "\n" for r in records).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(body)
    state = _read_state(top)
    state["artifacts"][name] = hashlib.sha256(body).hexdigest()
    _write_state(top, state)


def _set(key, value):
    def edit(state):
        state[key] = value
    return edit


def _state_edit(change):
    def damage(top):
        state = _read_state(top)
        change(state)
        _write_state(top, state)
    return damage


def _records_edit(name, change):
    def damage(top):
        def edit(records):
            change(records)
            return records
        _rewrite(top, name, edit)
    return damage


def _del(key):
    def change(records):
        del records[0][key]
    return change


def _put(key, value):
    def change(records):
        records[0][key] = value
    return change


BAD_SHAPES = {
    "partial-null": _state_edit(_set("partial", None)),
    "partial-element-string": _state_edit(_set("partial", ["a.py"])),
    "partial-element-without-path": _state_edit(_set("partial", [{"reason": "x"}])),
    "symbol-is-a-string": _records_edit("symbols.jsonl", lambda r: r.__setitem__(0, "a.py")),
    "symbol-without-path": _records_edit("symbols.jsonl", _del("path")),
    "start-line-is-a-string": _records_edit("symbols.jsonl", _put("start_line", "3")),
    "start-line-is-a-bool": _records_edit("symbols.jsonl", _put("start_line", True)),
    "file-path-is-an-integer": _records_edit("files.jsonl", _put("path", 7)),
    "head-is-an-integer": _state_edit(_set("head", 7)),
    # The fields the readers sort or format by: each is one check `load` makes.
    "partial-path-is-an-integer": _state_edit(_set("partial", [{"path": 7}])),
    "file-record-is-a-string": _records_edit("files.jsonl", lambda r: r.__setitem__(0, "a.py")),
    "symbol-path-is-an-integer": _records_edit("symbols.jsonl", _put("path", 7)),
    "symbol-qualified-name-is-an-integer": _records_edit("symbols.jsonl", _put("qualified_name", 7)),
    "symbol-name-is-null": _records_edit("symbols.jsonl", _put("name", None)),
    "symbol-kind-is-an-integer": _records_edit("symbols.jsonl", _put("kind", 7)),
    "end-line-is-a-string": _records_edit("symbols.jsonl", _put("end_line", "9")),
}


@pytest.mark.parametrize("shape", sorted(BAD_SHAPES))
def test_a_record_the_readers_cannot_use_is_unreadable_and_rebuilt(tmp_path, capsys, shape):
    top = _built(tmp_path)
    BAD_SHAPES[shape](top)

    with pytest.raises(store.IndexUnreadable):
        store.load(top)
    assert idx.status(top).word == "unsupported"
    assert codemap_cli.main(["status", "--project-dir", top]) == 0
    assert codemap_cli.main(["update", "--project-dir", top]) == 0
    out = capsys.readouterr()
    assert "Traceback" not in out.out + out.err
    assert idx.status(top).word == "fresh"


@pytest.mark.parametrize("name", [store.FILES_NAME, store.SYMBOLS_NAME, "repo-map.md"])
def test_an_artifacts_table_that_omits_a_required_file_is_unreadable(tmp_path, tmp_path_factory,
                                                                      capsys, name):
    top = _built(tmp_path)
    state = _read_state(top)
    del state["artifacts"][name]
    _write_state(top, state)

    with pytest.raises(store.IndexUnreadable) as caught:
        store.load(top)
    assert "%s is missing" % name in caught.value.args[0]
    assert idx.status(top).word == "unsupported"
    assert codemap_cli.main(["update", "--project-dir", top]) == 0
    assert "Traceback" not in capsys.readouterr().out
    assert idx.status(top).word == "fresh"

    other = tmp_path_factory.mktemp("full")
    reference = _built(other)
    with open(os.path.join(top, ".cai", "codemap", "symbols.jsonl"), "rb") as fh, \
            open(os.path.join(reference, ".cai", "codemap", "symbols.jsonl"), "rb") as ref:
        assert fh.read() == ref.read()


def test_fields_that_are_null_by_design_are_still_accepted(tmp_path):
    top = _built(tmp_path, {"m.go": "package m\n\nfunc F() {}\n", "README.md": "# r\n"})
    index = store.load(top)
    assert index is not None
    assert any(s["end_line"] is None for s in index.symbols)      # Go writes null
    assert index.files["README.md"]["confidence"] is None
