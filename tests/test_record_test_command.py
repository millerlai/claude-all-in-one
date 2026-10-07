"""Unit 3: record_test_command -- AC6 (other keys survive) and its failure exits."""
import json
import os
import subprocess
import sys

import pytest

import record_test_command as rec
import resolve_test_command as rtc


def cfg(tmp_path):
    return tmp_path / ".claude" / "cai.json"


def write_cfg(tmp_path, text):
    cfg(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    cfg(tmp_path).write_text(text, encoding="utf-8")


def load(tmp_path):
    return json.loads(cfg(tmp_path).read_text(encoding="utf-8"))


def test_write_config_is_atomic_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "sub" / "cai.json"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    rec.write_config(str(target), {"k": "值", "n": [1]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "值", "n": [1]}
    assert target.read_bytes().endswith(b"\n") and b"\r" not in target.read_bytes()
    assert os.listdir(str(target.parent)) == ["cai.json"]


def test_write_config_failure_keeps_the_old_file_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "cai.json"
    target.write_text("old", encoding="utf-8")

    def boom(src, dst):
        raise OSError("rename refused")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        rec.write_config(str(target), {"k": 1})
    assert target.read_text(encoding="utf-8") == "old"
    assert os.listdir(str(tmp_path)) == ["cai.json"]


def test_creates_the_file_and_the_directory(tmp_path):
    path = rec.record(str(tmp_path), ["make test", "npm test"])
    assert os.path.samefile(path, cfg(tmp_path))
    assert load(tmp_path) == {"test": {"commands": ["make test", "npm test"]}}
    assert cfg(tmp_path).read_text(encoding="utf-8").endswith("\n")


def test_keeps_the_ticket_key_and_other_test_subkeys(tmp_path):
    before = {"ticket": {"enabled": True, "backend": "github"},
              "test": {"other": [1, 2], "commands": ["old"]}, "zzz": "kept"}
    write_cfg(tmp_path, json.dumps(before))
    rec.record(str(tmp_path), ["python -m pytest"])
    after = load(tmp_path)
    assert after["ticket"] == before["ticket"]
    assert after["zzz"] == "kept"
    assert after["test"] == {"other": [1, 2], "commands": ["python -m pytest"]}


def test_existing_file_with_a_utf8_bom_is_merged(tmp_path):
    before = {"ticket": {"enabled": True, "backend": "github"}}
    cfg(tmp_path).parent.mkdir(parents=True)
    cfg(tmp_path).write_bytes(b"\xef\xbb\xbf" + json.dumps(before).encode("utf-8"))
    rec.record(str(tmp_path), ["make test"])
    raw = cfg(tmp_path).read_bytes()
    # Write-back is plain UTF-8: a file that arrived with a BOM leaves without one.
    assert raw[:3] != b"\xef\xbb\xbf"
    after = json.loads(raw.decode("utf-8"))
    assert after["ticket"] == before["ticket"]
    assert after["test"] == {"commands": ["make test"]}


def test_recorded_commands_resolve_as_declared_in_order(tmp_path):
    rec.record(str(tmp_path), ["npm test", "go test ./..."])
    result = rtc.resolve(str(tmp_path))
    assert result["source"] == "declared"
    assert [c["command"] for c in result["commands"]] == ["npm test", "go test"]


def test_non_ascii_is_written_as_is(tmp_path):
    rec.record(str(tmp_path), ["./測試.sh"])
    assert "測試" in cfg(tmp_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("commands", [[], [""], ["ok", "   "], ["a\nb"], ["a\rb"]])
def test_bad_commands_raise_and_write_nothing(tmp_path, commands):
    with pytest.raises(ValueError):
        rec.record(str(tmp_path), commands)
    assert not cfg(tmp_path).exists()


@pytest.mark.parametrize("text", ["{not json", "[]", json.dumps({"test": "x"}),
                                  json.dumps({"test": ["x"]})])
def test_unusable_existing_file_is_left_untouched(tmp_path, text):
    write_cfg(tmp_path, text)
    with pytest.raises(rec.ConfigProblem):
        rec.record(str(tmp_path), ["make test"])
    assert cfg(tmp_path).read_text(encoding="utf-8") == text


def test_main_exit_codes_and_messages(tmp_path, capsys):
    assert rec.main(["--project-dir", str(tmp_path), "make test"]) == 0
    out = capsys.readouterr()
    assert "make test" in out.out and out.err == ""
    assert rec.main(["--project-dir", str(tmp_path)]) == 2
    assert rec.main(["--project-dir", str(tmp_path), "  "]) == 2
    assert load(tmp_path) == {"test": {"commands": ["make test"]}}
    write_cfg(tmp_path, "{bad")
    capsys.readouterr()
    assert rec.main(["--project-dir", str(tmp_path), "x"]) == 5
    err = capsys.readouterr().err
    assert err.strip() and "bad" not in err


def test_write_failure_exits_5_and_leaves_no_temp_file(tmp_path, monkeypatch, capsys):
    write_cfg(tmp_path, json.dumps({"ticket": {}}))
    original = cfg(tmp_path).read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(rec.os, "replace", boom)
    assert rec.main(["--project-dir", str(tmp_path), "x"]) == 5
    assert cfg(tmp_path).read_text(encoding="utf-8") == original
    assert os.listdir(cfg(tmp_path).parent) == ["cai.json"]
    capsys.readouterr()


def test_main_finds_the_git_root_from_a_subdirectory(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sub = tmp_path / "pkg"
    sub.mkdir()
    assert rec.main(["--project-dir", str(sub), "make test"]) == 0
    assert cfg(tmp_path).exists() and not (sub / ".claude").exists()


def test_script_runs_from_the_command_line(tmp_path):
    proc = subprocess.run([sys.executable, rec.__file__, "--project-dir", str(tmp_path), "make test"],
                          capture_output=True)
    assert proc.returncode == 0
    assert "make test" in proc.stdout.decode("utf-8")
