"""#294: external tools are started by a full path found only in trusted PATH
entries -- never the current directory, the directory a call runs in, or an
empty or relative PATH entry.

tool_path.py is the shared lookup; statusline.py (copied to ~/.claude/) and
resolve_test_command.py (imports no sibling) carry their own copy, so every
case runs against all three.
"""
import os

import pytest

import resolve_test_command
import statusline
import tool_path

LOOKUPS = [tool_path.resolve, statusline._tool_path, resolve_test_command._tool_path]
IDS = ["tool_path", "statusline", "resolve_test_command"]


def plant(directory, name="faketool"):
    """An executable `name` in `directory`: a .bat on Windows (found through
    PATHEXT), a mode-0o755 file elsewhere."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = directory / (name + ".bat")
        path.write_bytes(b"@echo off\r\nexit /b 0\r\n")
    else:
        path = directory / name
        path.write_bytes(b"#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    return str(path)


def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """(trusted, here, project): a trusted bin directory, the process's current
    directory, and the directory a call runs in."""
    trusted, here, project = tmp_path / "trusted bin", tmp_path / "here", tmp_path / "project"
    for d in (trusted, here, project):
        d.mkdir()
    monkeypatch.chdir(here)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    return trusted, here, project


def path_of(*entries):
    return os.pathsep.join(str(e) for e in entries)


@pytest.mark.parametrize("lookup", LOOKUPS, ids=IDS)
def test_a_trusted_entry_is_found_even_with_a_space_in_it(dirs, monkeypatch, lookup):
    trusted, _, project = dirs
    real = plant(trusted)
    monkeypatch.setenv("PATH", path_of(trusted))
    assert same(lookup("faketool", str(project)), real)


@pytest.mark.parametrize("lookup", LOOKUPS, ids=IDS)
@pytest.mark.parametrize("bad", ["", ".", "rel", "here", "project", "above both"])
def test_untrusted_entries_are_skipped(dirs, monkeypatch, lookup, bad):
    # "above both" is the project root when the call runs in a subdirectory.
    trusted, here, project = dirs
    plant(here)
    plant(here / "rel")
    plant(project)
    plant(here.parent)
    real = plant(trusted)
    entry = {"": "", ".": ".", "rel": "rel", "here": here, "project": project,
             "above both": here.parent}[bad]
    monkeypatch.setenv("PATH", path_of(entry, trusted))
    assert same(lookup("faketool", str(project)), real)


@pytest.mark.parametrize("lookup", LOOKUPS, ids=IDS)
def test_a_tool_only_in_untrusted_places_is_not_found(dirs, monkeypatch, lookup):
    trusted, here, project = dirs
    plant(here)
    plant(project)
    monkeypatch.setenv("PATH", path_of("", ".", here, project, trusted))
    with pytest.raises(FileNotFoundError):
        lookup("faketool", str(project))


@pytest.mark.parametrize("lookup", LOOKUPS, ids=IDS)
def test_a_missing_tool_raises_file_not_found(dirs, monkeypatch, lookup):
    trusted, _, project = dirs
    monkeypatch.setenv("PATH", path_of(trusted))
    with pytest.raises(FileNotFoundError):
        lookup("faketool", str(project))


def test_argv_with_a_bare_name_gets_its_full_path(dirs, monkeypatch):
    trusted, _, project = dirs
    real = plant(trusted)
    monkeypatch.setenv("PATH", path_of(trusted))
    argv = tool_path.resolve_argv(["faketool", "--version"], str(project))
    assert same(argv[0], real) and argv[1:] == ["--version"]


def test_argv_naming_a_path_is_the_persons_choice_and_kept(dirs, monkeypatch):
    # An explicit override such as CAI_TICKET_CLI=C:/tools/gh.exe or ./bin/gh.
    trusted, here, project = dirs
    monkeypatch.setenv("PATH", path_of(trusted))
    for given in (os.path.join(str(here), "gh.exe"), "./bin/gh", "bin/gh"):
        assert tool_path.resolve_argv([given, "x"], str(project)) == [given, "x"]
