"""AC10: the index directory ignores itself before anything else is written, so
`git status` reads the same before and after, including after a crash (C18)."""
import os

import pytest

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import git, make_repo, write


def _porcelain(top):
    return git(top, "status", "--porcelain", "--untracked-files=all")


def test_status_is_the_same_before_and_after_build(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    before = _porcelain(tmp_path)
    idx.build(str(tmp_path))
    assert _porcelain(tmp_path) == before == ""
    gi = tmp_path / ".cai" / "codemap" / ".gitignore"
    assert gi.read_bytes() == b"*\n"


def test_interrupted_before_the_first_data_file_leaves_status_unchanged(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    before = _porcelain(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(store, "write_atomic", boom)
    with pytest.raises(OSError):
        idx.build(str(tmp_path))

    assert _porcelain(tmp_path) == before
    assert (tmp_path / ".cai" / "codemap" / ".gitignore").read_bytes() == b"*\n"
    assert idx.status(str(tmp_path)).word == "absent"


def _index_tmp(top):
    """Every `*.tmp` name under the index directory, `packages/` included."""
    found = []
    for dirpath, _, names in os.walk(str(top / ".cai" / "codemap")):
        found.extend(n for n in names if n.endswith(".tmp"))
    return found


def test_replace_failing_at_the_self_ignore_step_refuses_and_keeps_the_old_body(
        tmp_path, capsys, monkeypatch):
    # Rewritten for AC9: a wrong `.gitignore` is replaced through a temp file in
    # its own directory, and when that cannot be done nothing is written
    # directly and nothing is left under `.git` -- the build refuses instead.
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    gitignore = write(tmp_path, ".cai/codemap/.gitignore", "wrong\n")
    before = _porcelain(tmp_path)

    def boom(src, dst):
        raise OSError("cross-device")

    monkeypatch.setattr(os, "replace", boom)
    code = codemap_cli.main(["build", "--project-dir", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    monkeypatch.undo()

    assert (code, lines) == (2, ["codemap: unsupported (OSError: cross-device)"])
    with open(gitignore, "rb") as fh:
        assert fh.read() == b"wrong\n"
    assert [n for n in os.listdir(str(tmp_path / ".git"))
            if n.startswith("cai-codemap-gitignore.")] == []
    assert _index_tmp(tmp_path) == []
    assert _porcelain(tmp_path) == before


def test_a_tracked_symlink_at_dot_cai_cannot_redirect_the_index(tmp_path):
    # `.cai` itself is a tracked symlink to a directory outside the repository:
    # nothing may be written, or swept, through it.
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    make_repo(repo, {"a.py": "x = 1\n"})
    try:
        os.symlink(str(outside), str(repo / ".cai"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges here")
    git(repo, "add", ".cai")

    with pytest.raises(store.IndexUnreadable):
        idx.build(str(repo))

    assert os.listdir(str(outside)) == []


def _record_writes(monkeypatch):
    """(kind, absolute path, os.open flags) for every write or create the store
    does: `open` with a writing mode, `os.open` with a writing flag, the
    destination of `os.replace`, and `os.makedirs`."""
    seen = []
    real_open, real_os_open = open, os.open
    real_replace, real_makedirs = os.replace, os.makedirs

    def rec_open(file, mode="r", *args, **kwargs):
        if not isinstance(file, int) and set(mode) & set("wax+"):
            seen.append(("open", os.path.abspath(os.fsdecode(file)), 0))
        return real_open(file, mode, *args, **kwargs)

    def rec_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            seen.append(("os.open", os.path.abspath(os.fsdecode(path)), flags))
        return real_os_open(path, flags, *args, **kwargs)

    def rec_replace(src, dst, *args, **kwargs):
        seen.append(("replace", os.path.abspath(os.fsdecode(dst)), 0))
        return real_replace(src, dst, *args, **kwargs)

    def rec_makedirs(name, *args, **kwargs):
        seen.append(("makedirs", os.path.abspath(os.fsdecode(name)), 0))
        return real_makedirs(name, *args, **kwargs)

    monkeypatch.setattr(store, "open", rec_open, raising=False)
    monkeypatch.setattr(os, "open", rec_os_open)
    monkeypatch.setattr(os, "replace", rec_replace)
    monkeypatch.setattr(os, "makedirs", rec_makedirs)
    return seen


@pytest.mark.parametrize("variant", ["a_new_repo", "b_wrong_gitignore"])
def test_ac9_nothing_is_written_under_dot_git(tmp_path, monkeypatch, variant):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    if variant.startswith("b"):
        write(tmp_path, ".cai/codemap/.gitignore", "wrong\n")
    seen = _record_writes(monkeypatch)
    word = idx.build(str(tmp_path)).word
    monkeypatch.undo()

    top = os.path.normcase(str(tmp_path))
    index = os.path.join(top, ".cai", "codemap")
    git_dir = os.path.join(top, ".git") + os.sep
    paths = [os.path.normcase(p) for _, p, _ in seen]
    assert word == "fresh"
    assert [p for p in paths if p.startswith(git_dir)] == []
    # Each write is the index directory, something inside it, or `<top>/.cai`.
    assert [p for p in paths
            if not (p == index or p.startswith(index + os.sep)
                    or p == os.path.join(top, ".cai"))] == []
    # mkstemp opens through the os module, so the recorder did see its temp file.
    assert any(kind == "os.open" and p.endswith(".tmp") for kind, p, _ in seen)


@pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                    reason="needs POSIX permissions and a non-root user")
def test_ac9_a_read_only_git_dir(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    git_dir = tmp_path / ".git"
    mode = git_dir.stat().st_mode
    git_dir.chmod(0o555)
    try:
        word = idx.build(str(tmp_path)).word
        after = idx.status(str(tmp_path)).word
    finally:
        git_dir.chmod(mode)
    assert (word, after) == ("fresh", "fresh")


def test_ac9_a_new_repo_creates_the_self_ignore_file_exclusively(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    seen = _record_writes(monkeypatch)
    idx.build(str(tmp_path))
    monkeypatch.undo()

    target = os.path.normcase(str(tmp_path / ".cai" / "codemap" / ".gitignore"))
    opened = [flags for kind, p, flags in seen
              if kind == "os.open" and os.path.normcase(p) == target]
    replaced = [p for kind, p, _ in seen
                if kind == "replace" and os.path.normcase(p) == target]
    assert opened and opened[0] & os.O_EXCL
    assert replaced == []


def test_tracked_file_inside_the_index_directory_is_refused(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(tmp_path, ".cai/codemap/notes.txt", "mine\n")
    git(tmp_path, "add", "-f", ".cai/codemap/notes.txt")
    with pytest.raises(store.IndexUnreadable) as err:
        idx.build(str(tmp_path))
    assert err.value.args[0] == ".cai/codemap holds tracked files"
    assert not (tmp_path / ".cai" / "codemap" / "state.json").exists()
