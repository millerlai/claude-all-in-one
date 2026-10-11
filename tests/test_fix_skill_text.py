"""What /cai:fix may and may not say or do, read from its shipped files.

The scan covers whatever exists under skills/fix/ and every fix_*.py script,
found by glob, so a file a later unit adds is covered without touching this
file. The no-grant test runs validate.py against a copy of the repo, as
tests/test_validate.py does, because validate.py reads paths relative to the
current directory.
"""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "cai"
SKILL = PLUGIN / "skills" / "fix" / "SKILL.md"
SCRIPT_FILES = sorted((PLUGIN / "scripts").glob("fix_*.py"))
SHIPPED = sorted(p for p in (PLUGIN / "skills" / "fix").rglob("*") if p.is_file()) + SCRIPT_FILES

_spec = importlib.util.spec_from_file_location("gen_codex", REPO_ROOT / "scripts" / "gen-codex.py")
gen_codex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_codex)


def rel(path):
    return path.relative_to(REPO_ROOT).as_posix()


def frontmatter(text):
    end = text.index("\n---", 3)
    return text[3:end]


def test_there_is_something_to_scan():
    assert SKILL in SHIPPED
    assert PLUGIN / "scripts" / "fix_target.py" in SHIPPED


# A merge, a forced push, a refspec that starts with `+`: none may appear in
# anything this skill ships (AC4). A push is the only remote write besides the
# pull request and reply, and it is never forced.
FORBIDDEN = [
    ("a merge command", re.compile(r"gh\s+pr\s+merge")),
    ("a merge slash command", re.compile(r"(?<![\w.])/merge\b")),
    ("--force", re.compile(r"--force")),
    ("-f after push", re.compile(r"\bpush\b[^\n]*\s-f\b")),
    ("a + refspec after push", re.compile(r"\bpush\b[^\n]*\s\+\S")),
]


@pytest.mark.parametrize("path", SHIPPED, ids=rel)
def test_nothing_shipped_merges_or_forces(path):
    text = path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN:
        assert not pattern.search(text), f"{rel(path)} contains {label}"


SUBCOMMAND = re.compile(r"""["'](push|commit|merge)["']""")


@pytest.mark.parametrize("path", SCRIPT_FILES, ids=rel)
def test_scripts_never_name_a_write_subcommand(path):
    # The main session makes every push, commit and merge decision itself; a
    # script that could run one would make the guard's word the only check.
    assert not SUBCOMMAND.search(path.read_text(encoding="utf-8"))


def test_skill_is_flagged_so_only_a_person_starts_it():
    assert "disable-model-invocation: true" in SKILL.read_text(encoding="utf-8")


def test_skill_grants_no_tool():
    # The grant reached a dispatched implementer in the 2026-10-11 probe, so the
    # skill carries none: a push by an agent must still raise the platform's prompt.
    assert "allowed-tools" not in frontmatter(SKILL.read_text(encoding="utf-8"))


def test_skill_names_the_single_issue_procedure():
    text = SKILL.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/skills/fix/references/single-issue.md" in text
    assert (PLUGIN / "skills" / "fix" / "references" / "single-issue.md").is_file()


def test_skill_names_the_review_threads_procedure():
    text = SKILL.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/skills/fix/references/review-threads.md" in text
    assert (PLUGIN / "skills" / "fix" / "references" / "review-threads.md").is_file()


def test_skill_names_the_issue_list_procedure():
    text = SKILL.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/skills/fix/references/issue-list.md" in text
    assert (PLUGIN / "skills" / "fix" / "references" / "issue-list.md").is_file()


def test_skill_names_the_jira_procedure():
    text = SKILL.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/skills/fix/references/jira-ticket.md" in text
    assert (PLUGIN / "skills" / "fix" / "references" / "jira-ticket.md").is_file()
    assert PLUGIN / "scripts" / "fix_jira.py" in SCRIPT_FILES


def test_every_target_kind_has_a_reference_and_no_stand_in_sentence_is_left():
    text = SKILL.read_text(encoding="utf-8")
    for name in ("single-issue", "issue-list", "review-threads", "jira-ticket"):
        assert f"${{CLAUDE_PLUGIN_ROOT}}/skills/fix/references/{name}.md" in text
    assert "installed yet" not in text


def test_the_overridden_question_is_in_the_issue_list_reference_once():
    path = PLUGIN / "skills" / "fix" / "references" / "issue-list.md"
    anchor = next(o for o in gen_codex.load_overrides()
                  if o.target == "skills/fix/references/issue-list.md").anchor
    assert path.read_text(encoding="utf-8").count(anchor) == 1


def test_the_overridden_sentence_is_in_the_skill_once():
    text = SKILL.read_text(encoding="utf-8")
    anchor = next(o for o in gen_codex.load_overrides() if o.target == "skills/fix/SKILL.md").anchor
    assert text.count(anchor) == 1


REFERENCES = PLUGIN / "skills" / "fix" / "references"


def reference(name):
    # Whitespace folded: the files wrap their lines, and a phrase can straddle one.
    return " ".join((REFERENCES / f"{name}.md").read_text(encoding="utf-8").split())


@pytest.mark.parametrize("name", ["single-issue", "issue-list", "review-threads", "jira-ticket"])
def test_every_target_kind_stops_when_the_baseline_tests_fail(name):
    # AC3: a red base stops the run before any branch exists. issue-list.md and
    # review-threads.md say it themselves; the Jira procedure points at the
    # single-issue step, which holds the words.
    text = reference(name)
    assert "baseline" in text
    if name != "jira-ticket":
        assert "baseline tests fail on" in text


def test_review_threads_does_not_carry_on_past_a_red_baseline():
    assert "keep the result" not in reference("review-threads")


def test_the_report_step_says_how_the_results_are_written_and_checked():
    text = SKILL.read_text(encoding="utf-8")
    assert '"items"' in text and "--expect-file" in text
    for name in ("issue-list", "review-threads"):
        assert "--expect-file" in reference(name)


@pytest.mark.parametrize("name", ["single-issue", "issue-list", "review-threads", "jira-ticket"])
def test_references_leave_the_scratch_file_rule_to_the_skill(name):
    # Codex rewrites that rule in SKILL.md only; a second statement of it in a
    # reference would contradict the rewrite there.
    assert "system temp directory" not in reference(name)


@pytest.mark.parametrize("name", ["review-threads", "jira-ticket"])
def test_text_a_stranger_chose_is_single_quoted_on_a_command_line(name):
    assert "single-quote" in reference(name).lower()


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("codex") / "out"
    done = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "gen-codex.py"),
                           "--out", str(out)], capture_output=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    return out


def test_codex_skill_keeps_only_name_and_description(generated):
    text = (generated / "skills" / "fix" / "SKILL.md").read_text(encoding="utf-8")
    keys = re.findall(r"^([A-Za-z][\w-]*):", frontmatter(text), re.MULTILINE)
    assert keys == ["name", "description"]


def test_codex_skill_is_never_invoked_implicitly(generated):
    yaml = (generated / "skills" / "fix" / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in yaml


def test_codex_scratch_files_stay_where_codex_allows(generated):
    text = (generated / "skills" / "fix" / "SKILL.md").read_text(encoding="utf-8")
    assert "<scratch-dir>" in text
    assert "is deleted once the command has run" not in text
    assert "system temp directory" not in text


def test_codex_issue_list_asks_by_numbered_text(generated):
    text = (generated / "skills" / "fix" / "references" / "issue-list.md").read_text(
        encoding="utf-8")
    assert "as numbered text, say that a typed" in text
    assert "Ask one question with the question tool" not in text


def test_codex_implementer_is_told_about_fix_items(generated):
    text = (generated / "agents" / "cai_implementer.toml").read_text(encoding="utf-8")
    assert "one unit of `stage-build.md`, or one item of the `fix` skill" in text


def test_codex_gets_every_script_and_the_track_command_in_codex_form(generated):
    for path in SCRIPT_FILES:
        assert (generated / "scripts" / path.name).is_file()
    text = (generated / "scripts" / "fix_target.py").read_text(encoding="utf-8")
    assert "$track <url>" in text and "/cai:track" not in text


def test_validate_fails_when_the_skill_gains_a_grant(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, repo, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*", "node_modules"))

    def validate():
        return subprocess.run([sys.executable, "scripts/validate.py", "fix"], cwd=repo,
                              capture_output=True, encoding="utf-8")

    clean = validate()
    assert clean.returncode == 0, clean.stdout
    assert "FAIL" not in clean.stdout

    skill = repo / "plugins" / "cai" / "skills" / "fix" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert not re.search(r"^allowed-tools:", text, re.MULTILINE)
    skill.write_text(text.replace("disable-model-invocation: true\n",
                                  "disable-model-invocation: true\nallowed-tools: Bash(git push *)\n",
                                  1), encoding="utf-8")
    broken = validate()
    assert broken.returncode == 1
    assert re.search(r"^FAIL .*grants no tool", broken.stdout, re.MULTILINE)
