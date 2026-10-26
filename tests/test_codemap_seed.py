"""`seed`: a new worktree starts from the main checkout's index instead of none.

`.cai/` is ignored, so a linked worktree never receives the main checkout's
index; `/cai:track` runs `seed` right after it enters one.
"""
import os

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import git, make_repo, same_mtimes, write

FILES = {"a.py": "def f():\n    pass\n", "b.py": "def g():\n    pass\n"}


def _main_and_worktree(tmp_path, build_main=True, files=FILES):
    main, wt = tmp_path / "main", tmp_path / "wt"
    main.mkdir()
    make_repo(main, files)
    if build_main:
        idx.build(str(main))
    git(main, "worktree", "add", "-q", str(wt), "-b", "feature")
    return str(main), str(wt)


def _state_bytes(top):
    with open(os.path.join(store.index_dir(top), store.STATE_NAME), "rb") as fh:
        return fh.read()


def test_seed_reuses_the_main_checkouts_records_and_leaves_its_index_alone(tmp_path):
    main, wt = _main_and_worktree(tmp_path)
    before = _state_bytes(main)

    result = idx.seed(wt, main)

    assert (result.word, result.reparsed, result.total) == ("fresh", 0, 2)
    assert idx.status(wt).word == "fresh"
    assert _state_bytes(main) == before


def test_seed_reparses_a_file_that_differs_from_the_main_checkout(tmp_path):
    main, wt = _main_and_worktree(tmp_path)
    write(wt, "a.py", "def renamed():\n    pass\n")

    result = idx.seed(wt, main)

    assert (result.reparsed, result.total) == (1, 2)
    assert idx.status(wt).word == "fresh"
    names = {s["name"] for s in store.load(wt).symbols}
    assert names == {"renamed", "g"}


def test_seed_hashes_a_file_even_when_its_size_and_mtime_match_the_main_record(tmp_path):
    # The main checkout's records describe its files, not these: trusting one
    # by size and mtime would keep a record for bytes this tree does not hold.
    main, wt = _main_and_worktree(tmp_path)
    write(wt, "a.py", "def h():\n    pass\n")     # same size as "def f()..."
    same_mtimes(main, wt)

    assert idx.seed(wt, main).reparsed == 1
    assert idx.status(wt).word == "fresh"


def test_seed_writes_an_index_even_when_nothing_differs_from_the_main_one(tmp_path):
    # Same HEAD, same bytes, same mtimes: update's "nothing changed" shortcut
    # would write nothing, and the worktree would still have no index.
    main, wt = _main_and_worktree(tmp_path)
    same_mtimes(main, wt)

    idx.seed(wt, main)

    assert os.path.isfile(os.path.join(store.index_dir(wt), store.STATE_NAME))
    assert idx.status(wt).word == "fresh"


def test_seed_returns_none_and_writes_nothing_when_the_main_checkout_has_no_index(tmp_path):
    main, wt = _main_and_worktree(tmp_path, build_main=False)
    assert idx.seed(wt, main) is None
    assert not os.path.exists(store.index_dir(wt))


def test_cli_seed_in_a_worktree_prints_the_result_line(tmp_path, capsys):
    _, wt = _main_and_worktree(tmp_path)
    assert codemap_cli.main(["seed", "--project-dir", wt]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "codemap: fresh (reparsed 0 of 2 files)"
    assert codemap_cli.main(["status", "--project-dir", wt]) == 0
    assert capsys.readouterr().out.startswith("codemap: fresh")


def test_cli_seed_with_no_index_anywhere_says_absent_and_writes_nothing(tmp_path, capsys):
    _, wt = _main_and_worktree(tmp_path, build_main=False)
    assert codemap_cli.main(["seed", "--project-dir", wt]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "codemap: absent", "run /cai:codemap build to create one"]
    assert not os.path.exists(store.index_dir(wt))


def test_cli_seed_in_a_worktree_with_its_own_index_is_an_update_of_that_index(tmp_path, capsys):
    main, wt = _main_and_worktree(tmp_path)
    write(wt, "a.py", "def own():\n    pass\n")
    idx.build(wt)
    write(main, "b.py", "def from_main():\n    pass\n")
    idx.update(main)

    assert codemap_cli.main(["seed", "--project-dir", wt]) == 0

    assert capsys.readouterr().out.startswith("codemap: fresh")
    assert {s["name"] for s in store.load(wt).symbols} == {"own", "g"}


def test_cli_seed_in_the_main_checkout_is_an_update(tmp_path, capsys):
    main, _ = _main_and_worktree(tmp_path)
    write(main, "a.py", "def changed():\n    pass\n")
    assert codemap_cli.main(["seed", "--project-dir", main]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "codemap: fresh (reparsed 1 of 2 files)"


def test_cli_seed_from_a_damaged_main_index_says_unsupported_and_writes_nothing(tmp_path, capsys):
    main, wt = _main_and_worktree(tmp_path)
    with open(os.path.join(store.index_dir(main), store.STATE_NAME), "w", encoding="utf-8") as fh:
        fh.write("{broken")

    assert codemap_cli.main(["seed", "--project-dir", wt]) == 2

    assert capsys.readouterr().out.startswith("codemap: unsupported (")
    assert not os.path.exists(os.path.join(store.index_dir(wt), store.STATE_NAME))
