"""Regression checks for the September open-issue batch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import ledger
import usage_collector
import usage_report


def test_bad_transcript_lines_are_bounded_per_file(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("bad\n" * 45 + '{"type":"assistant"}\n' * 30,
                          encoding="utf-8")
    for since, until in [(0, 2000), (2000, 6000)]:
        problems = []
        assert usage_collector.read_window(transcript, since, until, problems) == []
        assert len(problems) == 2
        assert "45 unparseable lines" in problems[0]
        assert "first: line 1" in problems[0]
        assert "30 missing or unparseable timestamps" in problems[1]
        assert "first: line 46" in problems[1]


def test_crlf_records_have_no_malformed_rows(tmp_path):
    rows = [{"stage": "build", "note": "one"}, {"stage": "verify", "note": "two"}]
    (tmp_path / "ledger.jsonl").write_bytes(
        ("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    assert ledger.records(str(tmp_path)) == [dict(row, line=i) for i, row in enumerate(rows, 1)]


def test_crlf_central_records_have_no_malformed_rows(tmp_path):
    path = tmp_path / "usage.jsonl"
    rows = [{"note": "one"}, {"note": "two"}]
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    records, malformed = usage_report._read_central_records(str(path))
    assert malformed == 0
    assert records == [dict(row, line=i) for i, row in enumerate(rows, 1)]


def test_crlf_window_reads_both_records(tmp_path, monkeypatch):
    path = tmp_path / "usage.jsonl"
    rows = [{"session_id": "crlf", "window_end": value} for value in
            ["2026-09-30T00:00:02.000Z", "2026-09-30T00:00:01.000Z"]]
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    monkeypatch.setattr(usage_collector, "central_ledger_path", lambda: str(path))
    monkeypatch.setattr(ledger, "_data_start_floor", lambda: None)
    assert ledger._window_since("crlf") == rows[0]["window_end"]
    rows.reverse()
    path.write_bytes(("\r\n".join(json.dumps(row) for row in rows) + "\r\n").encode())
    assert ledger._window_since("crlf") == rows[1]["window_end"]


def test_read_only_lenses_have_no_shell():
    for name in ["reviewer", "security-reviewer", "explorer"]:
        text = Path("plugins/cai/agents", name + ".md").read_text(encoding="utf-8")
        tools = next(line for line in text.splitlines() if line.startswith("tools:"))
        assert tools == "tools: Read, Grep, Glob"


def test_no_detail_design_has_explicit_brief_and_traceability():
    build = Path("plugins/cai/skills/track/references/stage-build.md").read_text(encoding="utf-8")
    intake = Path("plugins/cai/skills/track/references/stage-intake.md").read_text(encoding="utf-8")
    assert "## Invariants preserved" in build
    assert "no `UC`/`R` ids and is not a diagnosis" in build
    assert "AC1, AC2" in intake


def test_designer_hook_blocks_out_of_scope_commands():
    guard = Path("plugins/cai/scripts/designer_guard.py")
    for command, expected in [
        ("git status", 2), ("git stash -u", 2), ("python -c 'print(1)'", 2),
        ("python scripts/validate.py", 2),
        ("python plugins/cai/scripts/design_probe.py --kind detail doc.md", 0),
        ("python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail doc.md", 0),
        ('python "${CLAUDE_PLUGIN_ROOT}/scripts/options_lint.py" options.md', 0),
        ("mmdc -i diagram.mmd -o diagram.svg", 0),
        ("mmdc -i diagram.mmd > code.py", 2),
        ("python plugins/cai/scripts/design_probe.py doc.md; git stash", 2),
        ("python plugins/cai/scripts/design_probe.py $(git stash)", 2),
        ("mmdc -i (Start-Process calc)", 2),
    ]:
        result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
            "tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True, text=True)
        assert result.returncode == expected, (command, result.stderr)


def test_designer_is_held_by_the_global_hook_through_agent_type():
    # The platform ignores `hooks:` in a plugin agent's frontmatter, so the
    # boundary lives in the one global hook and is chosen by `agent_type`.
    agent = Path("plugins/cai/agents/designer.md").read_text(encoding="utf-8")
    assert "hooks:" not in agent.split("\n---", 1)[0]
    wrapper = Path("plugins/cai/hooks/run-guard.cmd").resolve()
    for command, agent_type, expected in [
            ("git stash -u", "cai:designer", 2),
            ("python ${CLAUDE_PLUGIN_ROOT}/scripts/design_probe.py --kind detail doc.md",
             "cai:designer", 0),
            ("git stash -u", None, 0)]:  # the main session has no agent_type
        argv = ["cmd", "/c", str(wrapper)] if os.name == "nt" else ["sh", str(wrapper)]
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        result = subprocess.run(argv, input=json.dumps(payload),
                                capture_output=True, text=True)
        assert result.returncode == expected, result.stderr


def _wrapper_without_python(tmp_path):
    """argv and env that run run-guard.cmd with no interpreter on PATH.

    Windows: PATH is System32 alone, where neither `py` nor `python` lives
    (checked, and the test skips if a machine puts one there). POSIX: a
    directory holding links to only the three programs the sh branch calls."""
    wrapper = str(Path("plugins/cai/hooks/run-guard.cmd").resolve())
    if os.name == "nt":
        bin_dir = os.path.join(os.environ["SystemRoot"], "System32")
        argv = [os.environ["COMSPEC"], "/c", wrapper]
    else:
        bin_dir = str(tmp_path / "bin")
        os.mkdir(bin_dir)
        for name in ("sh", "grep", "dirname"):
            os.symlink(shutil.which(name), os.path.join(bin_dir, name))
        argv = [os.path.join(bin_dir, "sh"), wrapper]
    for name in ("py", "python", "python3"):
        if shutil.which(name, path=bin_dir):
            pytest.skip("%s is on the reduced PATH" % name)
    return argv, dict(os.environ, PATH=bin_dir)


@pytest.mark.parametrize("compact", [True, False])
def test_wrapper_without_python_blocks_only_the_scoped_agents(tmp_path, compact):
    argv, env = _wrapper_without_python(tmp_path)
    separators = (",", ":") if compact else None  # the platform sends compact JSON
    for agent_type, expected in [("cai:test-runner", 2), ("cai:verifier", 2),
                                 ("cai:designer", 2), ("cai:explorer", 0), (None, 0)]:
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        if agent_type:
            payload["agent_type"] = agent_type
        result = subprocess.run(argv, input=json.dumps(payload, separators=separators),
                                capture_output=True, text=True, env=env)
        assert result.returncode == expected, (agent_type, result.stderr)


def test_designer_guard_uses_its_installed_path_with_spaces(tmp_path):
    scripts = tmp_path / "plugin with spaces" / "scripts"
    scripts.mkdir(parents=True)
    guard = scripts / "designer_guard.py"
    guard.write_bytes(Path("plugins/cai/scripts/designer_guard.py").read_bytes())
    for script in ("design_probe.py", "options_lint.py"):
        command = 'python "%s" doc.md' % (scripts / script)
        result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
            "cwd": str(tmp_path), "tool_input": {"command": command}}),
            capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    other = tmp_path / "design_probe.py"
    result = subprocess.run([sys.executable, str(guard)], input=json.dumps({
        "cwd": str(tmp_path), "tool_input": {"command": 'python "%s" doc.md' % other}}),
        capture_output=True, text=True)
    assert result.returncode == 2


def test_bad_line_summaries_preserve_note_and_usage_on_append(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cwd = str(tmp_path)
    root = tmp_path / "projects"
    project = root / usage_collector.encoded_project_dir(cwd)
    project.mkdir(parents=True)
    transcript = project / "summary.jsonl"
    row = {"type": "assistant", "timestamp": "2026-09-30T00:00:01.000Z",
           "requestId": "one", "message": {"model": "test-model", "usage": {
               "input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 0}}}
    transcript.write_text("bad\n" * 545 + json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(usage_collector, "_projects_root", lambda: str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "summary")
    monkeypatch.setattr(ledger, "_window_since", lambda _: None)
    monkeypatch.setattr(ledger, "_now_ms", lambda: "2026-09-30T00:00:02.000Z")
    artifact = tmp_path / "design.md"
    artifact.write_text("design", encoding="utf-8")
    track = tmp_path / "track"
    track.mkdir()
    note = "important failure detail " * 26
    result = ledger.append(str(track), "build", "failed", artifact=str(artifact), note=note)
    assert result["note"] == note
    assert result["artifact"] == str(artifact)
    assert len(result["usage_problems"]) == 1
    assert "545 unparseable lines" in result["usage_problems"][0]
    assert result["orchestration"]["test-model"]["input_tokens"] == 100
    assert len((track / "ledger.jsonl").read_bytes()) <= ledger.MAX_RECORD
