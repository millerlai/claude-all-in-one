"""#455: setup decides by hash, not by a model's reading, whether it may
overwrite a rule it installed, and keeps a timestamped copy of anything it
changes. Every test writes into tmp_path only."""
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

import setup_files

SCRIPT = Path(setup_files.__file__)
LANG = "- Respond in English; keep technical terms in their original form.\n"
NOW = datetime.datetime(2026, 10, 14, 15, 30, 42)


def tree(tmp_path, shipped):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    for name, text in shipped.items():
        (src / name).write_text(text, encoding="utf-8")
    return src, dest


def cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, encoding="utf-8")


def bak(dest):
    return sorted(p.name for p in dest.iterdir() if p.name.endswith(".bak"))


def test_the_four_states(tmp_path):
    src, dest = tree(tmp_path, {"a.md": "A\n", "b.md": "B\n", "c.md": "C2\n", "d.md": "D2\n"})
    (dest / "b.md").write_text("B\r\n", encoding="utf-8")
    (dest / "c.md").write_text("C1\n", encoding="utf-8")
    (dest / "d.md").write_text("D1 mine\n", encoding="utf-8")
    setup_files.save_manifest(dest, {"c.md": setup_files.digest("C1\n"),
                                     "d.md": setup_files.digest("D1\n")})
    out = cli("status", "--src", src, "--dest", dest).stdout.splitlines()
    assert out == ["absent a.md", "identical b.md", "stale-unmodified c.md",
                   "user-modified d.md"]


def test_install_backs_up_what_it_changes_and_skips_user_edits(tmp_path):
    src, dest = tree(tmp_path, {"a.md": "A\n", "b.md": "B\n", "c.md": "C2\n", "d.md": "D2\n"})
    (dest / "b.md").write_text("B\n", encoding="utf-8")
    (dest / "c.md").write_text("C1\n", encoding="utf-8")
    (dest / "d.md").write_text("D1 mine\n", encoding="utf-8")
    setup_files.save_manifest(dest, {"c.md": setup_files.digest("C1\n")})
    result = cli("install", "--src", src, "--dest", dest)
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert "wrote a.md" in lines and "unchanged b.md" in lines
    assert "skipped d.md (user-modified)" in lines
    backups = [ln.split(" ", 1)[1] for ln in lines if ln.startswith("backup ")]
    assert len(backups) == 1 and Path(backups[0]).is_absolute()
    assert Path(backups[0]).read_text(encoding="utf-8") == "C1\n"
    assert (dest / "c.md").read_text(encoding="utf-8") == "C2\n"
    assert (dest / "d.md").read_text(encoding="utf-8") == "D1 mine\n"
    assert [n.split(".")[0] for n in bak(dest)] == ["c"]
    # Only the identical and written files are vouched for; d stays unknown.
    assert set(setup_files.load_manifest(dest)) == {"a.md", "b.md", "c.md"}


def test_overwrite_replaces_a_user_edit_after_a_backup(tmp_path):
    src, dest = tree(tmp_path, {"d.md": "D2\n"})
    (dest / "d.md").write_text("D1 mine\n", encoding="utf-8")
    assert cli("install", "--src", src, "--dest", dest, "--overwrite", "d.md").returncode == 0
    assert (dest / "d.md").read_text(encoding="utf-8") == "D2\n"
    (only,) = bak(dest)
    assert (dest / only).read_text(encoding="utf-8") == "D1 mine\n"
    assert cli("status", "--src", src, "--dest", dest).stdout == "identical d.md\n"


def test_an_install_without_a_manifest_counts_as_user_modified(tmp_path):
    src, dest = tree(tmp_path, {"a.md": "new\n", "b.md": "same\n"})
    (dest / "a.md").write_text("old\n", encoding="utf-8")
    (dest / "b.md").write_text("same\n", encoding="utf-8")
    (dest / setup_files.MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert cli("status", "--src", src, "--dest", dest).stdout.splitlines() == [
        "user-modified a.md", "identical b.md"]


def test_identical_files_are_neither_rewritten_nor_backed_up(tmp_path):
    src, dest = tree(tmp_path, {"a.md": "A\n"})
    assert cli("install", "--src", src, "--dest", dest).returncode == 0
    before = (dest / "a.md").stat().st_mtime_ns
    assert cli("install", "--src", src, "--dest", dest).stdout == "unchanged a.md\n"
    assert (dest / "a.md").stat().st_mtime_ns == before and bak(dest) == []


def test_the_chosen_language_survives_and_is_not_an_edit(tmp_path):
    src, dest = tree(tmp_path, {"communication.md": "# C\n" + LANG})
    assert cli("install", "--src", src, "--dest", dest).returncode == 0
    chosen = (dest / "communication.md").read_text(encoding="utf-8").replace(
        "English", "Traditional Chinese (繁體中文)")
    (dest / "communication.md").write_text(chosen, encoding="utf-8")
    assert cli("status", "--src", src, "--dest", dest).stdout == "identical communication.md\n"
    (src / "communication.md").write_text("# C v2\n" + LANG, encoding="utf-8")
    assert cli("status", "--src", src, "--dest", dest).stdout == (
        "stale-unmodified communication.md\n")
    assert cli("install", "--src", src, "--dest", dest).returncode == 0
    assert (dest / "communication.md").read_text(encoding="utf-8") == (
        "# C v2\n" + LANG.replace("English", "Traditional Chinese (繁體中文)"))


def test_diff_shows_the_user_edit(tmp_path):
    src, dest = tree(tmp_path, {"d.md": "D2\n"})
    (dest / "d.md").write_text("D1 mine\n", encoding="utf-8")
    out = cli("status", "--src", src, "--dest", dest, "--diff").stdout
    assert "-D1 mine" in out and "+D2" in out


def test_backups_within_one_second_never_overwrite_each_other(tmp_path):
    f = tmp_path / "CLAUDE.md"
    names = []
    for text in ("one", "two", "three"):
        f.write_text(text, encoding="utf-8")
        names.append(setup_files.backup(f, NOW))
    assert [p.name for p in names] == ["CLAUDE.md.2026-10-14-153042.bak",
                                       "CLAUDE.md.2026-10-14-153042-1.bak",
                                       "CLAUDE.md.2026-10-14-153042-2.bak"]
    assert [p.read_text(encoding="utf-8") for p in names] == ["one", "two", "three"]
    assert all(p.parent == tmp_path for p in names)


def test_backup_command_prints_the_full_path(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("mine\n", encoding="utf-8")
    result = cli("backup", f)
    assert result.returncode == 0
    path = Path(result.stdout.strip().split(" ", 1)[1])
    assert path.is_absolute() and path.parent == f.resolve().parent
    assert path.read_text(encoding="utf-8") == "mine\n"
    assert cli("backup", tmp_path / "missing.md").returncode == 1


def test_manifest_is_not_a_rule_file(tmp_path):
    src, dest = tree(tmp_path, {"a.md": "A\n"})
    cli("install", "--src", src, "--dest", dest)
    data = json.loads((dest / setup_files.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert data["format"] == 1 and set(data["files"]) == {"a.md"}
    assert not setup_files.MANIFEST_NAME.endswith(".md")


@pytest.mark.parametrize("bad", ['{"format": 2, "files": {}}', '{"format": 1, "files": []}',
                                 '[]', '{"format": 1}'])
def test_an_odd_manifest_vouches_for_nothing(tmp_path, bad):
    (tmp_path / setup_files.MANIFEST_NAME).write_text(bad, encoding="utf-8")
    assert setup_files.load_manifest(tmp_path) == {}
