"""AC10: the index directory ignores itself before anything else is written, so
`git status` reads the same before and after, including after a crash (C18)."""
import os

import pytest

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


def test_replace_failing_at_the_self_ignore_step_leaves_temp_in_git_dir(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    before = _porcelain(tmp_path)

    def boom(src, dst):
        raise OSError("cross-device")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        idx.build(str(tmp_path))
    monkeypatch.undo()

    leftovers = [n for n in os.listdir(str(tmp_path / ".git"))
                 if n.startswith("cai-codemap-gitignore.") and n.endswith(".tmp")]
    assert leftovers, "temp file should stay in the git dir"
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


def test_tracked_file_inside_the_index_directory_is_refused(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(tmp_path, ".cai/codemap/notes.txt", "mine\n")
    git(tmp_path, "add", "-f", ".cai/codemap/notes.txt")
    with pytest.raises(store.IndexUnreadable) as err:
        idx.build(str(tmp_path))
    assert err.value.args[0] == ".cai/codemap holds tracked files"
    assert not (tmp_path / ".cai" / "codemap" / "state.json").exists()
