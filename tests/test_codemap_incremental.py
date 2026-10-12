"""AC7: an incremental update lands on exactly the bytes a full build gives."""
import os

import codemap_cli
import codemap_index as idx
from codemap_repo import git, make_repo, write

BASE = {
    "a.py": "def a():\n    return 1\n",
    "pkg/b.py": "class B:\n    def m(self):\n        pass\n",
    "pkg/c.go": "package pkg\n\nfunc C() {}\n",
    "web/d.ts": "export function d() {}\n",
    "notes.md": "# notes\n",
}
DATA = ("files.jsonl", "symbols.jsonl", "repo-map.md")


def _data(top):
    root = os.path.join(str(top), ".cai", "codemap")
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            rel = os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/")
            if rel in DATA or rel.startswith("packages/"):
                with open(os.path.join(dirpath, n), "rb") as fh:
                    out[rel] = fh.read()
    return out


def test_update_after_one_change_reparses_one_and_equals_a_full_build(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    make_repo(one, BASE)
    idx.build(str(one))
    changed = "def a():\n    return 2\n\ndef extra(x):\n    return x\n"
    write(one, "a.py", changed)

    res = idx.update(str(one))

    assert (res.word, res.reparsed, res.total) == ("fresh", 1, 5)
    make_repo(two, {**BASE, "a.py": changed})
    idx.build(str(two))
    assert _data(one) == _data(two)
    assert "extra" in _data(one)["symbols.jsonl"].decode("utf-8")


def test_update_picks_up_added_and_deleted_files(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    make_repo(one, BASE)
    idx.build(str(one))
    write(one, "new.py", "def n():\n    pass\n")
    git(one, "add", "new.py")
    git(one, "rm", "-q", "-f", "pkg/c.go")

    res = idx.update(str(one))

    assert (res.reparsed, res.total) == (1, 5)
    expected = {k: v for k, v in BASE.items() if k != "pkg/c.go"}
    expected["new.py"] = "def n():\n    pass\n"
    make_repo(two, expected)
    idx.build(str(two))
    assert _data(one) == _data(two)
    assert idx.status(str(one)).word == "fresh"


def test_update_with_nothing_changed_reparses_nothing(tmp_path):
    make_repo(tmp_path, BASE)
    idx.build(str(tmp_path))
    before = _data(tmp_path)
    res = idx.update(str(tmp_path))
    assert (res.reparsed, res.total) == (0, 5)
    assert _data(tmp_path) == before


def test_update_without_an_index_writes_nothing(tmp_path):
    make_repo(tmp_path, BASE)
    assert idx.update(str(tmp_path)) is None
    assert not (tmp_path / ".cai").exists()


def test_update_rebuilds_in_full_when_the_index_is_damaged(tmp_path):
    make_repo(tmp_path, BASE)
    idx.build(str(tmp_path))
    (tmp_path / ".cai" / "codemap" / "state.json").write_text("garbage", encoding="utf-8")
    res = idx.update(str(tmp_path))
    assert (res.reparsed, res.total) == (5, 5)
    assert idx.status(str(tmp_path)).word == "fresh"


def test_build_records_symbols_and_facts_only_reasons(tmp_path):
    make_repo(tmp_path, {**BASE, "bad.py": "def (:\n"})
    idx.build(str(tmp_path))
    index = idx.store.load(str(tmp_path))
    assert index.files["bad.py"]["parse"] == "facts-only"
    assert index.files["bad.py"]["reason"] == "syntax-error at line 1"
    assert index.files["notes.md"]["reason"] == "unsupported-language"
    assert index.files["a.py"]["parse"] == "symbols"
    assert index.files["a.py"]["backend"] == "python-ast"
    assert [s["qualified_name"] for s in index.symbols if s["path"] == "pkg/b.py"] == \
        ["B", "B.m"]
    # a syntax error is not partial (T3-3)
    assert idx.status(str(tmp_path)).word == "fresh"


def test_oversized_file_is_facts_only_with_its_hash(tmp_path):
    big = "x = 1\n" * 200000          # 1,200,000 bytes, over the 1048576 cap
    make_repo(tmp_path, {"big.py": big, "a.py": "y = 2\n"})
    idx.build(str(tmp_path))
    rec = idx.store.load(str(tmp_path)).files["big.py"]
    assert rec["parse"] == "facts-only" and rec["reason"] == "too-large"
    assert rec["sha256"] and rec["bytes"] == len(big)


def _sharded_files():
    """Twenty modules in four packages: too long for one 1000-token map, each
    package alone short enough for its own shard."""
    return {"pkg%d/m%d.py" % (d, m): "".join(
                "def f%d_%d_%d(a, b):\n    return a\n\n" % (d, m, i) for i in range(8))
            for d in range(4) for m in range(5)}


def test_sharded_index_round_trips_updates_and_is_swept(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    files = _sharded_files()
    make_repo(one, files)
    idx.build(str(one))
    state = idx.store.load(str(one)).state
    shards = sorted(n for n in state["artifacts"] if n.startswith("packages/"))
    assert shards == ["packages/pkg%d.md" % d for d in range(4)]
    assert idx.status(str(one)).word == "fresh"

    changed = files["pkg2/m3.py"] + "def extra():\n    pass\n"
    write(one, "pkg2/m3.py", changed)
    assert idx.update(str(one)).reparsed == 1
    make_repo(two, {**files, "pkg2/m3.py": changed})
    idx.build(str(two))
    assert _data(one) == _data(two)
    assert idx.status(str(one)).word == "fresh"

    # the repository shrinks to one package: the shards must go, directory and all
    for d in (1, 2, 3):
        git(one, "rm", "-rq", "-f", "pkg%d" % d)
    idx.update(str(one))
    assert not (one / ".cai" / "codemap" / "packages").exists()
    assert idx.status(str(one)).word == "fresh"


def test_cli_update_prints_the_reparsed_count(tmp_path, capsys):
    make_repo(tmp_path, BASE)
    idx.build(str(tmp_path))
    write(tmp_path, "a.py", "def a():\n    return 3\n")
    assert codemap_cli.main(["update", "--project-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == \
        "codemap: fresh (reparsed 1 of 5 files)"


def test_cli_update_on_absent_prints_absent_and_writes_nothing(tmp_path, capsys):
    make_repo(tmp_path, BASE)
    assert codemap_cli.main(["update", "--project-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "codemap: absent"
    assert not (tmp_path / ".cai").exists()
