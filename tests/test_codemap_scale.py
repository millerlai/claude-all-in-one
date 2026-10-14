"""#403: what the codemap does at scale, checked at small scale -- an update
that finds nothing changed writes nothing, a status with no index never reads
a file's content, the path list after a state line is capped, and the git
call that lists a large tree gets more than five seconds.
"""
import os

import codemap_cli
import codemap_index as idx
import codemap_inventory as inventory
import codemap_store as store
import preflight
from codemap_repo import git, make_repo, write

FILES = {"a.py": "def alpha():\n    pass\n", "pkg/b.py": "def beta():\n    pass\n"}


def _index_files(top):
    root = store.index_dir(top)
    out = {}
    for base, _, names in os.walk(root):
        for name in names:
            path = os.path.join(base, name)
            out[os.path.relpath(path, root)] = os.stat(path).st_mtime_ns
    return out


def test_an_update_with_nothing_changed_writes_nothing(tmp_path):
    # AC2
    top = make_repo(tmp_path, FILES)
    idx.build(top)
    before = _index_files(top)

    result = idx.update(top)

    assert (result.word, result.reparsed, result.total) == ("fresh", 0, 2)
    assert _index_files(top) == before
    assert idx.status(top).word == "fresh"


def test_an_update_after_a_new_commit_still_writes_the_new_head(tmp_path):
    # Nothing in the tree changed, but the line names HEAD, so it is rewritten.
    top = make_repo(tmp_path, FILES)
    idx.build(top)
    git(top, "commit", "-q", "--allow-empty", "-m", "empty")
    head = git(top, "rev-parse", "HEAD").strip()

    idx.update(top)

    assert "head %s" % head[:7] in idx.state_line(idx.status(top))


def test_an_update_after_a_change_still_writes(tmp_path):
    top = make_repo(tmp_path, FILES)
    idx.build(top)
    write(tmp_path, "a.py", "def gamma():\n    pass\n")

    result = idx.update(top)

    assert result.reparsed == 1
    assert idx.status(top).word == "fresh"


def test_status_without_an_index_reads_no_file(tmp_path, monkeypatch):
    # AC3
    top = make_repo(tmp_path, FILES)

    def no_reads(*_args, **_kwargs):
        raise AssertionError("a file was read")

    monkeypatch.setattr(inventory, "read_tracked", no_reads)
    assert idx.status(top).word == "absent"


def test_status_without_an_index_still_says_when_there_is_no_repository(tmp_path):
    assert idx.status(str(tmp_path)).detail == "not a git repository"


def test_the_path_list_after_a_state_line_is_capped(tmp_path, capsys):
    files = {"m%02d.py" % i: "x = %d\n" % i for i in range(15)}
    top = make_repo(tmp_path, files)
    idx.build(top)
    for name in files:
        write(tmp_path, name, "y = 1\n")

    assert codemap_cli.main(["status", "--project-dir", top]) == 0
    lines = capsys.readouterr().out.splitlines()

    listed = [line for line in lines if line.startswith("  stale: ")]
    assert len(listed) == preflight.MAX_CONFLICTS_SHOWN
    assert lines[-1] == "  … and 5 more"


def test_listing_the_tree_waits_longer_than_other_git_calls(tmp_path, monkeypatch):
    # Item 8: a large repository's ls-files may take more than five seconds.
    top = make_repo(tmp_path, FILES)
    seen, real = [], preflight.git

    def recording(cwd, *args, **kwargs):
        if "ls-files" in args:
            seen.append(kwargs.get("timeout"))
        return real(cwd, *args, **kwargs)

    monkeypatch.setattr(inventory.preflight, "git", recording)
    inventory.list_tracked(top)
    assert seen == [inventory.LIST_TIMEOUT] and inventory.LIST_TIMEOUT > 5


def test_the_partial_list_after_build_is_capped(tmp_path, capsys, monkeypatch):
    files = {"m%02d.py" % i: "x = %d\n" % i for i in range(13)}
    top = make_repo(tmp_path, files)

    def crash(path, language, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(idx.symbols, "extract", crash)
    assert codemap_cli.main(["build", "--project-dir", top]) == 0
    lines = capsys.readouterr().out.splitlines()

    assert len([line for line in lines if line.startswith("  partial: ")]) == \
        preflight.MAX_CONFLICTS_SHOWN
    assert lines[-1] == "  … and 3 more"
