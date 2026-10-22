"""cai_paths: `.cai/` ignores itself, and migrate moves what an earlier cai
left under `.claude/` without ever deleting a file git tracks."""
import os
import subprocess

import cai_paths
from codemap_repo import git, make_repo, write


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_ensure_dir_writes_a_self_ignore_git_honours(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    cai_paths.ensure_dir(top)
    write(top, ".cai/track/f/state.md", "state\n")
    assert _read(os.path.join(top, ".cai", ".gitignore")) == "*\n"
    assert git(top, "status", "--porcelain", "--untracked-files=all") == ""


def test_ensure_dir_leaves_an_existing_gitignore_alone(tmp_path):
    top = str(tmp_path)
    write(top, ".cai/.gitignore", "track/\n")
    cai_paths.ensure_dir(top)
    assert _read(os.path.join(top, ".cai", ".gitignore")) == "track/\n"


def test_untracked_legacy_items_are_moved(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/track/f/state.md", "state\n")
    write(top, ".claude/track/current", "f\n")
    write(top, ".claude/cai.json", "{}\n")
    write(top, ".claude/cai-context.md", "# Glossary\n")
    write(top, ".claude/cai-review.md", "# Review\n")

    lines = cai_paths.migrate(top)

    assert lines == ["moved .claude/track to .cai/track",
                     "moved .claude/cai.json to .cai/cai.json",
                     "moved .claude/cai-context.md to .cai/cai-context.md",
                     "moved .claude/cai-review.md to .cai/cai-review.md"]
    assert _read(os.path.join(top, ".cai", "track", "f", "state.md")) == "state\n"
    assert _read(os.path.join(top, ".cai", "track", "current")) == "f\n"
    assert not os.path.exists(os.path.join(top, ".claude", "track"))
    assert not os.path.exists(os.path.join(top, ".claude", "cai.json"))
    assert _read(os.path.join(top, ".cai", ".gitignore")) == "*\n"


def test_a_tracked_legacy_file_is_copied_and_the_tree_stays_clean(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n", ".claude/cai.json": '{"test": "x"}\n'})

    lines = cai_paths.migrate(top)

    assert lines == ["copied .claude/cai.json to .cai/cai.json; git tracks the original, "
                     "so it is left for you to remove"]
    assert _read(os.path.join(top, ".claude", "cai.json")) == '{"test": "x"}\n'
    assert _read(os.path.join(top, ".cai", "cai.json")) == '{"test": "x"}\n'
    assert git(top, "status", "--porcelain", "--untracked-files=all") == ""


def test_a_track_directory_with_one_tracked_file_is_copied_whole(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n", ".claude/track/f/state.md": "state\n"})
    write(top, ".claude/track/f/ledger.jsonl", "{}\n")

    lines = cai_paths.migrate(top)

    assert lines[0].startswith("copied .claude/track to .cai/track;")
    assert _read(os.path.join(top, ".cai", "track", "f", "ledger.jsonl")) == "{}\n"
    assert os.path.isfile(os.path.join(top, ".claude", "track", "f", "ledger.jsonl"))


def test_an_existing_new_place_wins_and_nothing_is_touched(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/cai.json", "old\n")
    write(top, ".cai/cai.json", "new\n")

    assert cai_paths.migrate(top) == []
    assert _read(os.path.join(top, ".claude", "cai.json")) == "old\n"
    assert _read(os.path.join(top, ".cai", "cai.json")) == "new\n"


def test_migrate_twice_does_nothing_the_second_time(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/track/current", "f\n")
    assert cai_paths.migrate(top) == ["moved .claude/track to .cai/track"]
    assert cai_paths.migrate(top) == []


def test_nothing_to_migrate_creates_nothing(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    assert cai_paths.migrate(top) == []
    assert not os.path.exists(os.path.join(top, ".cai"))


def test_outside_a_repository_nothing_is_tracked_so_it_moves(tmp_path, monkeypatch):
    # A Chinese locale must not turn "not a git repository" into a copy.
    monkeypatch.setenv("LANG", "zh_TW.UTF-8")
    monkeypatch.setenv("LANGUAGE", "zh_TW")
    top = str(tmp_path)
    write(top, ".claude/cai.json", "{}\n")
    assert cai_paths.migrate(top) == ["moved .claude/cai.json to .cai/cai.json"]
    assert not os.path.exists(os.path.join(top, ".claude", "cai.json"))


def test_a_failure_is_one_line_and_the_rest_still_runs(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/track/current", "f\n")
    write(top, ".claude/cai.json", "{}\n")
    real = os.replace

    def refuse_track(src, dst):
        if src.endswith("track"):
            raise PermissionError("in use")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", refuse_track)

    lines = cai_paths.migrate(top)

    assert lines[0].startswith("could not move .claude/track to .cai/track (PermissionError")
    assert lines[1] == "moved .claude/cai.json to .cai/cai.json"


def test_cli_ensure_prints_the_directory_and_migrate_prints_each_move(tmp_path, capsys):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/cai-review.md", "# Review\n")
    assert cai_paths.main(["migrate", "--project-dir", top]) == 0
    assert capsys.readouterr().out == "moved .claude/cai-review.md to .cai/cai-review.md\n"
    assert cai_paths.main(["ensure", "--project-dir", top]) == 0
    assert capsys.readouterr().out.strip() == os.path.join(top, ".cai")


def test_cli_ensure_exits_2_when_the_directory_cannot_be_made(tmp_path, capsys):
    write(str(tmp_path), ".cai", "a file where the directory should be\n")
    assert cai_paths.main(["ensure", "--project-dir", str(tmp_path)]) == 2
    assert capsys.readouterr().out.startswith("cai_paths: could not make ")


def test_git_not_answering_counts_as_tracked(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    write(top, ".claude/cai.json", "{}\n")

    def no_git(*args, **kwargs):
        raise OSError("no git")
    monkeypatch.setattr(subprocess, "run", no_git)

    assert cai_paths.migrate(top) == [
        "copied .claude/cai.json to .cai/cai.json; git could not say whether it "
        "tracks the original, so it is left for you to remove"]
    assert os.path.isfile(os.path.join(top, ".claude", "cai.json"))
