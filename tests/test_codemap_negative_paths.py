"""#406: the refusal and fallback branches of the codemap scripts, each run by a
test that fails when the guarded line is taken out (AC9: every failure is one
state line, never a traceback). Branches the earlier PRs already covered --
a data line that is not a record, the missing-file reason text, NUL bytes,
`path-not-utf8` -- are not repeated here.
"""
import importlib.util
import json
import os

import pytest

import codemap_cli
import codemap_index as idx
import codemap_inventory as inventory
import codemap_query
import codemap_repomap as rm
import codemap_store as store
import codemap_symbols as symbols
import preflight
from codemap_repo import git, make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.dirname(os.path.abspath(codemap_cli.__file__))
_spec = importlib.util.spec_from_file_location(
    "codemap_recall", os.path.join(REPO_ROOT, "scripts", "codemap_recall.py"))
recall = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recall)

FILES = {"a.py": "def alpha():\n    pass\n", "b.py": "y = 2\n"}


def _built(tmp_path):
    top = make_repo(tmp_path, FILES)
    idx.build(top)
    return top


def _state(top):
    return os.path.join(top, ".cai", "codemap", "state.json")


# --- load ------------------------------------------------------------------

def test_a_state_json_that_is_not_an_object_is_unsupported(tmp_path):
    top = _built(tmp_path)
    with open(_state(top), "w", encoding="utf-8") as fh:
        json.dump([], fh)
    st = idx.status(top)
    assert (st.word, st.detail) == (
        "unsupported", "index unreadable: state.json has the wrong shape or schema_version; "
        "run build")


def test_another_schema_version_is_unsupported(tmp_path):
    top = _built(tmp_path)
    with open(_state(top), encoding="utf-8") as fh:
        state = json.load(fh)
    state["schema_version"] = store.SCHEMA_VERSION + 1
    with open(_state(top), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    assert "wrong shape or schema_version" in idx.status(top).detail


def test_a_state_json_that_cannot_be_opened_names_the_error(tmp_path, monkeypatch):
    top = _built(tmp_path)
    real = store._read

    def locked(path):
        if os.path.basename(path) == store.STATE_NAME:
            raise PermissionError(13, "locked by another program", path)
        return real(path)

    monkeypatch.setattr(store, "_read", locked)
    assert idx.status(top).detail == (
        "index unreadable: state.json cannot be read (PermissionError); run build")


# --- status's unsupported branches ----------------------------------------

@pytest.mark.parametrize("where, raised, detail", [
    ("list_tracked", inventory.GitFailed("x"), "git did not answer"),
    ("list_tracked", PermissionError(13, "denied"), "PermissionError while reading the tree"),
    ("inventory", PermissionError(13, "denied"), "PermissionError while reading the tree"),
])
def test_status_when_the_inventory_fails(tmp_path, monkeypatch, where, raised, detail):
    top = _built(tmp_path)

    def fail(*args, **kwargs):
        raise raised

    monkeypatch.setattr(idx.inventory, where, fail)
    st = idx.status(top)
    assert (st.word, st.detail) == ("unsupported", detail)


def test_status_when_the_index_directory_is_tracked(tmp_path):
    top = _built(tmp_path)
    git(top, "add", "-f", ".cai/codemap/state.json")
    st = idx.status(top)
    assert (st.word, st.detail) == ("unsupported", store.TRACKED_REASON)


@pytest.mark.parametrize("where", ["tracked_inside", "load"])
def test_status_when_git_fails_while_the_index_is_read(tmp_path, monkeypatch, where):
    top = _built(tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("git did not answer")

    monkeypatch.setattr(idx.store, where, fail)
    st = idx.status(top)
    assert (st.word, st.detail) == ("unsupported", "git did not answer")


def test_tracked_inside_raises_when_git_does_not_answer(tmp_path, monkeypatch):
    top = _built(tmp_path)
    monkeypatch.setattr(store.preflight, "git", lambda *a, **k: None)
    with pytest.raises(OSError):
        store.tracked_inside(top)


# --- inventory ---------------------------------------------------------------

def test_list_tracked_when_git_does_not_answer(tmp_path, monkeypatch):
    top = make_repo(tmp_path, FILES)
    monkeypatch.setattr(inventory.preflight, "is_git_repo",
                        lambda _top: preflight.GIT_DID_NOT_ANSWER)
    with pytest.raises(inventory.GitFailed, match="git did not answer"):
        inventory.list_tracked(top)


def test_list_tracked_when_ls_files_fails(tmp_path, monkeypatch):
    top = make_repo(tmp_path, FILES)
    real = inventory.preflight.git

    def no_ls_files(cwd, *args, **kwargs):
        return None if "ls-files" in args else real(cwd, *args, **kwargs)

    monkeypatch.setattr(inventory.preflight, "git", no_ls_files)
    with pytest.raises(inventory.GitFailed, match="ls-files failed"):
        inventory.list_tracked(top)


def test_a_submodule_entry_is_facts_only(tmp_path):
    top = make_repo(tmp_path, FILES)
    sha = git(top, "rev-parse", "HEAD").strip()
    git(top, "update-index", "--add", "--cacheinfo", "160000,%s,vendored" % sha)
    by_path = {f.path: f for f in inventory.inventory(top)}
    assert (by_path["vendored"].reason, by_path["vendored"].sha256) == ("submodule", None)


# --- query -------------------------------------------------------------------

def test_the_text_scan_skips_what_the_inventory_never_opens(tmp_path, monkeypatch):
    top = _built(tmp_path)
    (tmp_path / "c.py").write_text("z = 3\n", encoding="utf-8")
    # Real files, so only the skip rule keeps the last two out.
    listed = [("100644", "a.py", True), ("160000", "b.py", True), ("100644", "c.py", False)]
    monkeypatch.setattr(codemap_query.inventory, "list_tracked", lambda _top: listed)
    assert [p for p, _ in codemap_query.tracked_texts(top)] == ["a.py"]


def test_a_query_with_no_terms_finds_nothing(tmp_path):
    top = _built(tmp_path)
    assert codemap_query.query(top, store.load(top), "!! ? --", 10) == []


# --- the CLI's own exits ------------------------------------------------------

@pytest.mark.parametrize("argv, code", [
    (["frobnicate"], 1),
    (["query", "--project-dir", "."], 1),
    ([], 1),
    (["--help"], 0),
])
def test_a_wrong_command_line_exits_1_and_help_exits_0(argv, code, capsys):
    assert codemap_cli.main(argv) == code
    out = capsys.readouterr().out
    assert "codemap: unsupported" not in out


@pytest.mark.parametrize("raised, line", [
    (inventory.GitFailed("x"), "codemap: unsupported (git did not answer)"),
    (store.IndexUnreadable("state.json is not valid JSON"),
     "codemap: unsupported (state.json is not valid JSON)"),
])
def test_build_failures_print_their_reason(tmp_path, monkeypatch, capsys, raised, line):
    top = make_repo(tmp_path, FILES)

    def fail(_top):
        raise raised

    monkeypatch.setattr(idx, "build", fail)
    assert codemap_cli.main(["build", "--project-dir", top]) == 2
    assert capsys.readouterr().out == line + "\n"


# --- the repo map's split --------------------------------------------------------

def test_a_directory_with_files_and_subdirectories_keeps_its_own_files():
    """`_split`'s direct branch: when a directory overflows and holds both its
    own files and subdirectories, its own files get a shard of their own."""
    files, syms = [], []
    for rel in ["pkg/top.py"] + ["pkg/sub%d/m%d.py" % (d, m) for d in range(2) for m in range(3)]:
        files.append({"path": rel, "language": "python", "confidence": "exact"})
        for i in range(12):
            syms.append({"path": rel, "kind": "function", "start_line": i + 1,
                         "end_line": i + 1, "qualified_name": "f%d_with_a_long_name" % i,
                         "signature": "(argument_one, argument_two)"})
    out = rm.render(files, syms, 300, 0)
    shards = {name: text for name, text in out.items() if name != "repo-map.md"}
    assert any("## pkg/top.py " in text for text in shards.values())
    assert "packages/pkg.md" in out


# --- the recall benchmark's input ----------------------------------------------

def _run_recall(tmp_path, text, capsys):
    path = tmp_path / "tasks.jsonl"
    path.write_text(text, encoding="utf-8")
    code = recall.main(["--project-dir", str(tmp_path), "--tasks", str(path)])
    return code, capsys.readouterr()


@pytest.mark.parametrize("text, message", [
    ("", "no tasks"),
    ("\n  \n", "no tasks"),
    ('{"query": "a", "expected_files": []}\n', "line 1"),
    ('{"expected_files": ["a.py"]}\n', "line 1"),
    ('{"query": "a", "expected_files": [7]}\n', "line 1"),
])
def test_recall_refuses_a_task_it_cannot_score(tmp_path, capsys, text, message):
    make_repo(tmp_path, FILES)
    code, out = _run_recall(tmp_path, text, capsys)
    assert code == 1
    assert message in out.err


def test_recall_refuses_a_tasks_file_that_is_not_there(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    code = recall.main(["--project-dir", str(tmp_path), "--tasks", str(tmp_path / "none")])
    assert code == 1
    assert "tasks file:" in capsys.readouterr().err


def test_recall_without_an_index_scores_the_baseline_only(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    code, out = _run_recall(
        tmp_path, '\n{"query": "alpha", "expected_files": ["a.py"]}\n', capsys)
    assert code == 0
    assert out.out.startswith("codemap: absent")


# --- symbols -------------------------------------------------------------------

def test_a_ts_file_that_is_not_utf8_is_undecodable():
    assert symbols.extract("m.ts", "typescript", b"export const x = '\xff';\n").reason == \
        "undecodable"


def test_a_multiline_ts_import_is_read_from_its_closing_line():
    data = b"import {\n  a,\n  b,\n} from './x';\nexport function f() {}\n"
    got = symbols.extract("m.ts", "typescript", data)
    assert got.imports == ["./x"]
    assert [s["name"] for s in got.symbols] == ["f"]


def test_a_go_file_with_a_bom_still_finds_its_first_declaration():
    data = "﻿func F() {}\n".encode("utf-8")
    assert [s["name"] for s in symbols.extract("m.go", "go", data).symbols] == ["F"]


# --- the import whitelist ---------------------------------------------------------

def test_every_codemap_script_is_in_the_import_whitelist():
    """A new codemap_*.py must be listed, or its imports are never checked."""
    import test_codemap_imports
    on_disk = {n for n in os.listdir(SCRIPTS) if n.startswith("codemap_") and n.endswith(".py")}
    assert set(test_codemap_imports.ALLOWED_SIBLINGS) == on_disk
