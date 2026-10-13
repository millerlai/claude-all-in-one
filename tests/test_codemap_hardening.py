"""Found by the pre-merge review of the codemap PR: an index file is input like
any other. A state.json cannot name a file outside the index directory, every
name git allows round-trips through the index, no two directories share a shard
file, and one minified line does not become a megabyte of signature."""
import hashlib
import json
import os

import pytest

import codemap_index as idx
import codemap_repomap as rm
import codemap_store as store
import codemap_symbols as sym
from codemap_repo import git, make_repo, write


def _built(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    idx.build(str(tmp_path))
    return str(tmp_path)


def _name_a_file_outside_the_index(top, name):
    """Adds `name` to state.json's artifacts with the right digest of a file
    that sits outside the index directory."""
    body = b"outside the index directory\n"
    with open(os.path.join(top, "secret.txt"), "wb") as fh:
        fh.write(body)
    path = os.path.join(top, ".cai", "codemap", "state.json")
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    state["artifacts"][name] = hashlib.sha256(body).hexdigest()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


@pytest.mark.parametrize("name", ["../../secret.txt", "/etc/hostname", "C:/x.md",
                                  "packages/../../secret.txt", "a\\b.md"])
def test_an_artifact_name_that_leaves_the_index_directory_is_refused(tmp_path, name):
    top = _built(tmp_path)
    _name_a_file_outside_the_index(top, name)
    with pytest.raises(store.IndexUnreadable):
        store.load(top)
    assert idx.status(top).word == "unsupported"


def test_update_does_not_read_a_tracked_state_file(tmp_path, monkeypatch):
    # The refusal to work in a directory that holds tracked files has to come
    # before anything in that directory is parsed, not after.
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(tmp_path, ".cai/codemap/state.json", "{}\n")
    git(tmp_path, "add", "-f", ".cai/codemap/state.json")
    reads = []
    real = store._read
    monkeypatch.setattr(store, "_read", lambda p: reads.append(p) or real(p))
    with pytest.raises(store.IndexUnreadable):
        idx.update(str(tmp_path))
    assert reads == []


def test_a_data_file_over_the_size_cap_is_unreadable_not_read(tmp_path, monkeypatch):
    top = _built(tmp_path)
    monkeypatch.setattr(store, "MAX_ARTIFACT_BYTES", 10)
    with pytest.raises(store.IndexUnreadable):
        store.load(top)


def test_status_refuses_an_index_reached_through_a_symlinked_dot_cai(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    make_repo(repo, {"a.py": "x = 1\n"})
    idx.build(str(repo))
    os.rename(str(repo / ".cai"), str(outside / "payload"))
    try:
        os.symlink(str(outside / "payload"), str(repo / ".cai"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges here")
    git(repo, "add", ".cai")
    assert idx.status(str(repo)).word == "unsupported"


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\x85"])
def test_a_file_name_with_a_unicode_line_separator_round_trips(tmp_path, char):
    # json.dumps(ensure_ascii=False) leaves these raw; str.splitlines() splits
    # on them, which used to tear the record: build said fresh, status said
    # unsupported, and a rebuild did the same again.
    try:
        make_repo(tmp_path, {"a%sb.py" % char: "def f():\n    pass\n"})
    except OSError:
        pytest.skip("this file system cannot hold that name")
    res = idx.build(str(tmp_path))
    assert res.word == "fresh"
    st = idx.status(str(tmp_path))
    assert st.word == "fresh", st
    assert "a%sb.py" % char in store.load(str(tmp_path)).files


def _file(path):
    return {"path": path, "language": "python", "backend": "python-ast",
            "confidence": "exact", "parse": "symbols", "reason": None}


def _symbol(path, n):
    return {"path": path, "qualified_name": "func_%03d" % n, "kind": "function",
            "start_line": n * 3 + 1, "end_line": n * 3 + 2,
            "signature": "(a, b=%d)" % n, "name": "func_%03d" % n}


def _render(dirs, per_file=30, files_per_dir=2, budget=400, tolerance=40):
    files, symbols = [], []
    for d in dirs:
        for i in range(files_per_dir):
            path = "%s/mod%d.py" % (d, i)
            files.append(_file(path))
            symbols.extend(_symbol(path, n) for n in range(per_file))
    return rm.render(files, symbols, budget, tolerance)


def test_a_slash_directory_and_a_double_dash_directory_keep_separate_shards():
    # `a/b` and `a--b` both flatten to `a--b`: one shard used to overwrite the
    # other in the dict while every digest still verified.
    out = _render(["a/b", "a/c", "a--b"])
    text = "".join(out.values())
    for path in ("a/b/mod0.py", "a/c/mod0.py", "a--b/mod0.py"):
        assert "## %s " % path in text, path
    shards = [n for n in out if n != "repo-map.md"]
    assert len(shards) == 3
    assert all(len(t) <= 440 * rm.CHARS_PER_TOKEN for t in out.values())


def test_directories_that_differ_only_in_case_do_not_share_a_shard_file():
    out = _render(["Foo", "foo", "bar"])
    shards = [n for n in out if n != "repo-map.md"]
    assert len({n.lower() for n in shards}) == len(shards) == 3


def test_a_very_deep_or_long_directory_chain_gets_a_bounded_shard_name():
    long_a, long_b = "d" * 130, "e" * 130
    out = _render(["%s/%s" % (long_a, long_b), "%s/%s" % (long_a, "f" * 130), "x"])
    for name in out:
        assert len(os.path.basename(name)) <= 120, name
    text = "".join(out.values())
    assert "## %s/%s/mod0.py " % (long_a, long_b) in text


def test_a_declaration_line_as_long_as_a_bundle_gets_a_capped_signature():
    line = b"function f(){" + b"x=1;" * 50000 + b"}\n"
    ts = sym.extract("bundle.min.js", "javascript", line)
    go = sym.extract("big.go", "go", b"func F(" + b"a int, " * 50000 + b") {\n}\n")
    for ex in (ts, go):
        (only,) = ex.symbols
        assert len(only["signature"]) <= sym.MAX_SIGNATURE
        assert only["signature"].endswith("...")
