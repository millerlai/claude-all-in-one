"""#448: a tracked file whose size and mtime still match its record, and whose
mtime is safely older than the scan that recorded it, is not opened again.

The record says what the file held when the last write scanned it. A write to
the file after that scan moves its mtime past the scan, so equal (size, mtime)
means equal content -- unless the mtime fell so close to the scan that a second
write could land in the same timestamp tick (a "racy" file, as git calls it).
Those are always read and hashed again.
"""
import json
import os

import pytest

import codemap_index as idx
import codemap_inventory as inv
import codemap_store as store
from codemap_repo import make_repo, write

FILES = {"a.py": "def a():\n    return 1\n", "b.py": "def b():\n    return 2\n",
         "notes.md": "# notes\n"}
OLD = 1_600_000_000 * 10**9          # 2020-09-13, far older than any scan


def _age(top, rel, ns=OLD):
    os.utime(os.path.join(str(top), *rel.split("/")), ns=(ns, ns))


def _aged_repo(tmp_path, files=FILES):
    make_repo(tmp_path, files)
    for rel in files:
        _age(tmp_path, rel)
    return str(tmp_path)


def _opens(monkeypatch):
    """Paths read_tracked opens for hashing, as POSIX names."""
    opened = []
    real = os.open

    def counting(path, flags, *args, **kwargs):
        if ".cai" not in str(path).replace(os.sep, "/").split("/"):
            opened.append(os.path.basename(str(path)))
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", counting)
    return opened


def _state(top):
    with open(os.path.join(top, ".cai", "codemap", "state.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _files(top):
    return store.load(top).files


# ---- the records -------------------------------------------------------------

def test_records_carry_mtime_and_the_state_its_scan_time(tmp_path):
    top = _aged_repo(tmp_path)
    idx.build(top)
    assert {p: r["mtime_ns"] for p, r in _files(top).items()} == {p: OLD for p in FILES}
    assert isinstance(_state(top)["scanned_at_ns"], int)
    assert _state(top)["schema_version"] == 3


# ---- the short-cut -----------------------------------------------------------

def test_status_and_update_open_no_unchanged_file(tmp_path, monkeypatch):
    top = _aged_repo(tmp_path)
    idx.build(top)
    opened = _opens(monkeypatch)
    assert idx.status(top).word == "fresh"
    assert idx.update(top).reparsed == 0
    assert opened == []


def test_a_changed_file_is_still_read(tmp_path, monkeypatch):
    top = _aged_repo(tmp_path)
    idx.build(top)
    write(tmp_path, "a.py", "def a():\n    return 10\n")
    opened = _opens(monkeypatch)
    assert idx.status(top).word == "stale"
    assert opened == ["a.py"]


def test_same_mtime_but_another_size_is_stale(tmp_path):
    top = _aged_repo(tmp_path)
    idx.build(top)
    write(tmp_path, "a.py", "def a():\n    return 1234\n")
    _age(tmp_path, "a.py")
    assert idx.status(top).word == "stale"


def test_a_racy_file_is_hashed_again(tmp_path):
    """Written within the racy window of the scan, rewritten to the same size
    with its mtime put back: the short-cut must not trust it."""
    make_repo(tmp_path, FILES)
    top = str(tmp_path)
    idx.build(top)
    recorded = _files(top)["a.py"]["mtime_ns"]
    assert recorded + inv.RACY_NS > _state(top)["scanned_at_ns"]   # it is racy
    write(tmp_path, "a.py", "def a():\n    return 9\n")              # same size
    _age(tmp_path, "a.py", recorded)
    assert idx.status(top).word == "stale"
    res = idx.update(top)
    assert res.reparsed == 1 and idx.status(top).word == "fresh"


def test_a_touched_file_is_rehashed_once_then_trusted(tmp_path, monkeypatch):
    """Same bytes, new mtime: fresh, and update writes the new mtime so the
    next run need not read the file again."""
    top = _aged_repo(tmp_path)
    idx.build(top)
    _age(tmp_path, "a.py", OLD + 10**9)
    assert idx.status(top).word == "fresh"
    assert idx.update(top).reparsed == 0
    assert _files(top)["a.py"]["mtime_ns"] == OLD + 10**9
    opened = _opens(monkeypatch)
    assert idx.update(top).reparsed == 0
    assert opened == []


def test_an_update_with_nothing_touched_writes_nothing(tmp_path):
    top = _aged_repo(tmp_path)
    idx.build(top)
    state = os.path.join(top, ".cai", "codemap", "state.json")
    before = os.stat(state).st_mtime_ns
    idx.update(top)
    assert os.stat(state).st_mtime_ns == before


def test_a_file_replaced_by_a_symlink_is_not_trusted(tmp_path):
    """The short-cut still lstat-checks the kind: a link at the name is
    reported, not mistaken for the regular file the record describes."""
    top = _aged_repo(tmp_path)
    idx.build(top)
    os.remove(os.path.join(top, "a.py"))
    try:
        os.symlink("b.py", os.path.join(top, "a.py"))
    except (OSError, NotImplementedError):
        if os.name == "nt":
            pytest.skip("symlinks need privileges here")
        raise
    assert idx.status(top).word == "stale"


# ---- the format --------------------------------------------------------------

def test_a_schema_2_index_is_rebuilt(tmp_path):
    top = _aged_repo(tmp_path)
    idx.build(top)
    path = os.path.join(top, ".cai", "codemap", "state.json")
    state = _state(top)
    state["schema_version"] = 2
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    assert idx.status(top).word == "unsupported"
    assert idx.update(top).reparsed == len(FILES)
    assert idx.status(top).word == "fresh"
