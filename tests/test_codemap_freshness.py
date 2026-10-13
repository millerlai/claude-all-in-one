"""AC8: status never says fresh when a tracked file differs from the index, and
names every file that differs."""
import os

import codemap_cli
import codemap_index as idx
from codemap_repo import git, make_repo, write

FILES = {"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"}


def _built(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path)


def test_absent_before_any_build(tmp_path):
    make_repo(tmp_path, FILES)
    st = idx.status(str(tmp_path))
    assert st.word == "absent"
    assert idx.state_line(st) == "codemap: absent"


def test_fresh_right_after_build(tmp_path):
    top = _built(tmp_path)
    st = idx.status(top)
    assert st.word == "fresh"
    assert idx.state_line(st).startswith("codemap: fresh (3 files, 0 with symbols, head ")


def test_fresh_line_says_no_commit_yet_on_unborn_head(tmp_path):
    make_repo(tmp_path, FILES, commit=False)
    idx.build(str(tmp_path))
    assert idx.state_line(idx.status(str(tmp_path))) == \
        "codemap: fresh (3 files, 0 with symbols, no commit yet)"


def test_changed_file_is_stale_and_named(tmp_path):
    top = _built(tmp_path)
    write(top, "a.py", "x = 99\n")
    st = idx.status(top)
    assert st.word == "stale"
    assert st.paths == ["a.py"]
    assert idx.state_line(st) == \
        "codemap: stale (1 file changed since the index was built: a.py)"


def test_added_file_is_stale_and_named(tmp_path):
    top = _built(tmp_path)
    write(top, "d.py", "w = 4\n")
    git(top, "add", "d.py")
    st = idx.status(top)
    assert st.word == "stale"
    assert st.paths == ["d.py"]


def test_deleted_file_is_stale_and_named(tmp_path):
    top = _built(tmp_path)
    git(top, "rm", "-q", "b.py")
    st = idx.status(top)
    assert st.word == "stale"
    assert st.paths == ["b.py"]


def test_cli_status_lists_every_changed_file_after_the_state_line(tmp_path, capsys):
    top = _built(tmp_path)
    write(top, "a.py", "x = 99\n")
    git(top, "rm", "-q", "b.py")
    assert codemap_cli.main(["status", "--project-dir", top]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("codemap: stale (2 files changed since the index was built: ")
    assert lines[1:] == ["  stale: a.py", "  stale: b.py"]


def test_state_line_caps_names_at_ten_with_a_count_of_the_rest(tmp_path):
    names = {"f%02d.py" % i: "v = %d\n" % i for i in range(13)}
    make_repo(tmp_path, names)
    idx.build(str(tmp_path))
    for name in names:
        write(tmp_path, name, "changed\n")
    st = idx.status(str(tmp_path))
    assert len(st.paths) == 13
    assert idx.state_line(st).endswith("f09.py and 3 more)")


def test_cli_status_on_absent_prints_the_build_hint(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    assert codemap_cli.main(["status", "--project-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "codemap: absent", "run /cai:codemap build to create one"]


def test_empty_repository_builds_and_is_fresh(tmp_path):
    git(tmp_path, "init", "-q")
    res = idx.build(str(tmp_path))
    assert (res.word, res.total) == ("fresh", 0)
    assert idx.state_line(idx.status(str(tmp_path))) == \
        "codemap: fresh (0 files, 0 with symbols, no commit yet)"
    assert os.path.exists(str(tmp_path / ".cai" / "codemap" / "files.jsonl"))


def test_fresh_counts_the_files_that_have_symbols(tmp_path):
    top = make_repo(tmp_path, {"a.py": "def f():\n    pass\n", "b.py": "def g():\n    pass\n",
                               "c.py": "x = 1\n", "README.md": "# r\n"})
    idx.build(top)
    assert idx.state_line(idx.status(top)).startswith(
        "codemap: fresh (4 files, 2 with symbols, head ")


def test_fresh_counts_files_and_not_the_symbols_in_them(tmp_path):
    top = make_repo(tmp_path, {"a.py": "def f():\n    pass\n\n\ndef g():\n    pass\n",
                               "b.py": "def h():\n    pass\n"})
    idx.build(top)
    assert idx.state_line(idx.status(top)).startswith(
        "codemap: fresh (2 files, 2 with symbols, head ")


def test_fresh_says_zero_with_symbols_when_no_language_is_supported(tmp_path):
    top = make_repo(tmp_path, {"Main.java": "class Main {}\n", "README.md": "# r\n"})
    idx.build(top)
    assert idx.state_line(idx.status(top)).startswith(
        "codemap: fresh (2 files, 0 with symbols, head ")


def test_status_asks_git_no_more_than_it_did(tmp_path, monkeypatch):
    top = _built(tmp_path)
    calls, real = [], idx.preflight.git

    def recording(where, *args, **kwargs):
        calls.append(args)
        return real(where, *args, **kwargs)
    monkeypatch.setattr(idx.preflight, "git", recording)

    assert idx.status(top).word == "fresh"

    assert calls == [("rev-parse", "--is-inside-work-tree"),
                     ("ls-files", "-z", "--stage"),
                     ("ls-files", "-z", "--", ".cai/codemap")]
