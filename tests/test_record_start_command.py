"""Unit 3: record_start_command -- AC2 (d) other keys survive, plus its failure exits."""
import json
import os
import subprocess
import sys

import pytest

import record_start_command as rec
import resolve_start_command as rsc

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "plugins", "cai", "scripts", "record_start_command.py")
READY = "http://127.0.0.1:3000/"


def cfg(tmp_path):
    return tmp_path / ".claude" / "cai.json"


def write_cfg(tmp_path, text):
    cfg(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    cfg(tmp_path).write_text(text, encoding="utf-8")


def load(tmp_path):
    return json.loads(cfg(tmp_path).read_text(encoding="utf-8"))


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, SCRIPT, "--project-dir", str(tmp_path), *args],
                          capture_output=True, timeout=60)


def test_creates_file_and_resolves_as_declared(tmp_path):
    path = rec.record(str(tmp_path), ["npm", "run", "dev"], READY)
    assert os.path.samefile(path, cfg(tmp_path))
    assert load(tmp_path) == {"run": {"start": ["npm", "run", "dev"], "ready": READY}}
    assert cfg(tmp_path).read_text(encoding="utf-8").endswith("\n")
    assert rsc.resolve(str(tmp_path))["status"] == "declared"


def test_keeps_test_ticket_and_other_keys(tmp_path):
    """AC2 (d)."""
    before = {"ticket": {"enabled": True, "backend": "github"},
              "test": {"commands": ["make test"], "other": [1]}, "zzz": "kept"}
    write_cfg(tmp_path, json.dumps(before))
    rec.record(str(tmp_path), ["npm", "run", "dev"], READY)
    after = load(tmp_path)
    for key, value in before.items():
        assert after[key] == value
    assert after["run"] == {"start": ["npm", "run", "dev"], "ready": READY}


def test_replaces_start_and_ready_but_keeps_existing_e2e(tmp_path):
    e2e = {"smoke": ["npx", "playwright", "test"]}
    write_cfg(tmp_path, json.dumps({"run": {"start": ["old"], "ready": READY, "e2e": e2e}}))
    rec.record(str(tmp_path), ["node", "s.js"], "http://localhost:9/up")
    assert load(tmp_path)["run"] == {"start": ["node", "s.js"],
                                     "ready": "http://localhost:9/up", "e2e": e2e}


def test_existing_e2e_port_needs_start_port(tmp_path):
    write_cfg(tmp_path, json.dumps({"run": {"e2e": {"a": ["t", "{port}"]}}}))
    before = cfg(tmp_path).read_bytes()
    with pytest.raises(ValueError):
        rec.record(str(tmp_path), ["node", "s.js"], READY)
    assert cfg(tmp_path).read_bytes() == before


@pytest.mark.parametrize("start,ready", [
    ([], READY), (["x"], "https://127.0.0.1/"), (["x"], "http://example.com/"),
    (["x\ny"], READY), (["x"], "http://127.0.0.1:{port}/")])
def test_invalid_arguments_raise_and_write_nothing(tmp_path, start, ready):
    with pytest.raises(ValueError):
        rec.record(str(tmp_path), start, ready)
    assert not cfg(tmp_path).exists()


@pytest.mark.parametrize("text", ["{bad", "[1]", json.dumps({"run": 3}),
                                  json.dumps({"test": 3})])
def test_unmergeable_file_is_left_alone(tmp_path, text):
    write_cfg(tmp_path, text)
    before = cfg(tmp_path).read_bytes()
    with pytest.raises(rec.ConfigProblem):
        rec.record(str(tmp_path), ["x"], READY)
    assert cfg(tmp_path).read_bytes() == before


# ---- CLI ----

def test_cli_success_line_and_file(tmp_path):
    proc = cli(tmp_path, "--ready", READY, "--", "npm", "run", "dev")
    assert proc.returncode == 0
    line = proc.stdout.decode("utf-8").strip()
    assert line == '%s: run.start=["npm", "run", "dev"] run.ready=%s' % (
        os.path.join(str(tmp_path), ".claude", "cai.json"), READY)
    assert load(tmp_path)["run"]["start"] == ["npm", "run", "dev"]


def test_cli_second_double_dash_inside_the_words_is_preserved(tmp_path):
    proc = cli(tmp_path, "--ready", "http://127.0.0.1:{port}/", "--",
               "npm", "run", "dev", "--", "--port", "{port}")
    assert proc.returncode == 0, proc.stderr
    assert load(tmp_path)["run"]["start"] == ["npm", "run", "dev", "--", "--port", "{port}"]


def test_main_splits_on_the_first_double_dash_only(tmp_path):
    rc = rec.main(["--project-dir", str(tmp_path), "--ready", READY, "--",
                   "--", "a", "--", "b"])
    assert rc == 0
    assert load(tmp_path)["run"]["start"] == ["--", "a", "--", "b"]


@pytest.mark.parametrize("args", [
    ["--ready", READY],                       # no words, no --
    ["--ready", READY, "--"],                 # empty words
    ["--", "npm", "run", "dev"],              # no --ready
    ["--ready", "http://example.com/", "--", "x"],
])
def test_cli_bad_arguments_exit_2_and_write_nothing(tmp_path, args):
    proc = cli(tmp_path, *args)
    assert proc.returncode == 2
    assert proc.stderr
    assert not cfg(tmp_path).exists()


def test_cli_unmergeable_file_exits_5_and_leaves_it(tmp_path):
    write_cfg(tmp_path, "{bad")
    proc = cli(tmp_path, "--ready", READY, "--", "x")
    assert proc.returncode == 5
    assert cfg(tmp_path).read_text(encoding="utf-8") == "{bad"


def test_write_failure_exits_5(tmp_path, monkeypatch, capsys):
    def boom(path, data):
        raise OSError("disk")
    monkeypatch.setattr(rec.record_test_command, "write_config", boom)
    assert rec.main(["--project-dir", str(tmp_path), "--ready", READY, "--", "x"]) == 5
    assert "nothing changed" in capsys.readouterr().err
