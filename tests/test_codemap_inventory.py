"""AC4: the inventory lists exactly git's tracked files with facts about each."""
import hashlib
import os
import sys

import pytest

import codemap_index as idx
import codemap_inventory as inv
import codemap_store as store
from codemap_repo import git, make_repo, write


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_language_of_maps_the_documented_extensions():
    expected = {"a.py": "python", "b.go": "go", "c.ts": "typescript", "d.tsx": "typescript",
                "e.js": "javascript", "f.jsx": "javascript", "g.mjs": "javascript",
                "h.cjs": "javascript", "i.md": "other", "Makefile": "other"}
    assert {p: inv.language_of(p) for p in expected} == expected


def test_inventory_lists_only_tracked_files_with_facts(tmp_path):
    make_repo(tmp_path, {
        "a.py": "x = 1\n",
        "sub/b.go": "package b\n",
        "docs/說明.md": "# 說明\n",
        ".gitignore": "ignored.txt\n",
    })
    write(tmp_path, "untracked.py", "y = 2\n")
    write(tmp_path, "ignored.txt", "z\n")

    facts = inv.inventory(str(tmp_path))

    assert [f.path for f in facts] == [".gitignore", "a.py", "docs/說明.md", "sub/b.go"]
    by_path = {f.path: f for f in facts}
    assert by_path["a.py"].language == "python"
    assert by_path["a.py"].bytes == 6
    assert by_path["a.py"].sha256 == _sha("x = 1\n")
    assert by_path["a.py"].reason is None
    assert by_path["sub/b.go"].language == "go"
    assert by_path["docs/說明.md"].language == "other"
    assert by_path["docs/說明.md"].sha256 == _sha("# 說明\n")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlink_is_recorded_not_followed(tmp_path):
    make_repo(tmp_path, {"real.py": "x = 1\n"}, commit=False)
    os.symlink("real.py", str(tmp_path / "link.py"))
    git(tmp_path, "add", "-A")

    by_path = {f.path: f for f in inv.inventory(str(tmp_path))}

    assert by_path["link.py"].reason == "symlink"
    assert by_path["link.py"].sha256 is None
    assert by_path["link.py"].bytes is None


def test_file_deleted_but_not_removed_from_git_is_missing(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    os.remove(str(tmp_path / "b.py"))

    by_path = {f.path: f for f in inv.inventory(str(tmp_path))}

    assert by_path["b.py"].reason == "missing"
    assert by_path["b.py"].sha256 is None
    assert by_path["a.py"].reason is None


def test_a_deleted_tracked_file_is_missing_and_does_not_hold_the_index_at_partial(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    os.remove(os.path.join(top, "b.py"))      # tracked, deleted, not `git rm`ed

    idx.build(top)

    index = store.load(top)
    assert index.files["b.py"]["reason"] == "missing"
    assert index.state["partial"] == []
    assert idx.status(top).word == "fresh"


def _refuse_open_of(monkeypatch, name):
    real = os.open

    def refusing(path, *args, **kwargs):
        if os.path.basename(str(path)) == name:
            raise PermissionError("no")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", refusing)


def test_file_that_exists_but_cannot_be_opened_is_not_missing(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    _refuse_open_of(monkeypatch, "a.py")

    by_path = {f.path: f for f in inv.inventory(str(tmp_path))}

    assert by_path["a.py"].reason == "%s: PermissionError" % inv.CANNOT_OPEN
    assert by_path["a.py"].sha256 is None
    assert by_path["b.py"].reason is None


def test_an_unopenable_file_is_partial_and_read_again_next_update(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    with monkeypatch.context() as m:
        _refuse_open_of(m, "a.py")
        idx.build(top)
    state = store.load(top).state
    assert [e["path"] for e in state["partial"]] == ["a.py"]
    assert store.load(top).files["a.py"]["reason"] == "cannot-open: PermissionError"

    res = idx.update(top)

    assert res.reparsed >= 1
    assert idx.status(top).word == "fresh"
    assert store.load(top).files["a.py"]["parse"] == "symbols"


def test_a_file_that_cannot_be_opened_for_parsing_is_partial_not_stale(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    real, opened = os.open, []

    def second_open_fails(path, *args, **kwargs):
        if os.path.basename(str(path)) == "a.py":
            opened.append(path)
            if len(opened) == 2:     # the inventory read passed; the parse read is this one
                raise PermissionError("no")
        return real(path, *args, **kwargs)
    with monkeypatch.context() as m:
        m.setattr(os, "open", second_open_fails)
        idx.build(top)

    st = idx.status(top)
    assert st.word == "partial", st
    assert st.paths == ["a.py"]
    assert store.load(top).files["a.py"]["sha256"] == _sha("x = 1\n")
    assert idx.update(top).reparsed >= 1
    assert idx.status(top).word == "fresh"


def test_a_file_that_is_no_longer_a_regular_file_at_parse_time_is_recorded_as_such(tmp_path):
    os.mkdir(str(tmp_path / "d.py"))
    stale = inv.FileFacts("d.py", "python", 5, "0" * 64, None)

    record, symbols, crash = idx._parse(os.path.realpath(str(tmp_path)), stale)

    assert record["reason"] == "not-regular"
    assert (record["sha256"], record["bytes"]) == (None, None)
    assert (symbols, crash) == ([], None)     # what inventory records now: not partial


def test_non_git_directory_raises_not_a_repository(tmp_path):
    with pytest.raises(inv.NotARepository):
        inv.inventory(str(tmp_path))


def test_empty_repository_has_an_empty_inventory(tmp_path):
    git(tmp_path, "init", "-q")
    assert inv.inventory(str(tmp_path)) == []
