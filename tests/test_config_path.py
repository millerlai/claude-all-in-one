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
    path, notes = cai_paths.config_path(str(wt))
    assert same(path, main / ".cai" / "cai.json")
    assert load(main) == {"test": {"commands": ["make test"]},
                          "ticket": {"enabled": True, "backend": "github"},
                          "run": {"start": ["x"], "ready": READY}}
    assert len(notes) == 1
    assert notes[0].startswith("cai_paths: merged run, ticket from ")
    assert " into " in notes[0] and notes[0].endswith("cai.json")
    assert cai_paths.config_path(str(wt))[1] == []   # nothing left to merge


def test_a_worktree_only_file_is_merged_into_a_main_with_none(repo):
    main, wt = repo
    put(wt, {"test": {"commands": ["make test"]}})
    cai_paths.config_path(str(wt))
    assert load(main) == {"test": {"commands": ["make test"]}}
    assert (main / ".cai" / ".gitignore").read_text() == "*\n"


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '"s"'])
def test_a_worktree_file_that_is_not_a_json_object_is_not_merged(repo, text):
    main, wt = repo
    put(main, {"a": 1})
    put(wt, text)
    path, notes = cai_paths.config_path(str(wt))
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


def test_resolvers_in_a_new_worktree_see_what_the_main_checkout_recorded(repo):
    main, wt = repo
    put(main, {"test": {"commands": ["make test"]}, "run": {"start": ["npm", "start"],
                                                           "ready": READY}})
    assert resolve_test_command.resolve(str(wt))["commands"][0]["command"] == "make test"
    assert resolve_start_command.resolve(str(wt))["status"] == "declared"


def test_resolvers_report_the_merge_in_their_notes(repo):
    main, wt = repo
    put(wt, {"test": {"commands": ["make test"]}})
    result = resolve_test_command.resolve(str(wt))
    assert result["status"] == "resolved"
    assert any(n.startswith("cai_paths: merged test from ") for n in result["notes"])
    put(wt, {"run": {"start": ["npm", "start"], "ready": READY}})
    result = resolve_start_command.resolve(str(wt))
    assert result["status"] == "declared"
    assert any(n.startswith("cai_paths: merged run from ") for n in result["notes"])


def test_a_worktree_only_config_is_still_read_by_ticket_after_the_merge(repo, capsys):
    main, wt = repo
    put(wt, {"ticket": {"enabled": True, "backend": "github"}})
    got = ticket.read_config(str(wt))
    assert got == {"enabled": True, "backend": "github", "problem": None}
    assert "cai_paths: merged ticket from " in capsys.readouterr().err
    assert load(main)["ticket"]["enabled"] is True


def test_a_main_checkout_ticket_setting_reaches_a_new_worktree(repo):
    main, wt = repo
    put(main, {"ticket": {"enabled": True, "backend": "github"}})
    assert ticket.read_config(str(wt))["enabled"] is True
