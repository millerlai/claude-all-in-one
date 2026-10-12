"""AC4: the inventory lists exactly git's tracked files with facts about each."""
import hashlib
import os
import sys

import pytest

import codemap_inventory as inv
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


def test_non_git_directory_raises_not_a_repository(tmp_path):
    with pytest.raises(inv.NotARepository):
        inv.inventory(str(tmp_path))


def test_empty_repository_has_an_empty_inventory(tmp_path):
    git(tmp_path, "init", "-q")
    assert inv.inventory(str(tmp_path)) == []
