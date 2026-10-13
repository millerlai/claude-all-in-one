"""What /cai:fix may and may not say or do, read from its shipped files.

The scan covers whatever exists under skills/fix/ and every fix_*.py script,
found by glob, so a file a later unit adds is covered without touching this
file. The no-grant test runs validate.py against a copy of the repo, as
tests/test_validate.py does, because validate.py reads paths relative to the
current directory.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "cai"
SKILL = PLUGIN / "skills" / "fix" / "SKILL.md"
UNCLAIM_SKILL = PLUGIN / "skills" / "fix-unclaim" / "SKILL.md"
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


def test_fix_authorisation_is_unchanged_by_local_session_claims():
    text = SKILL.read_text(encoding="utf-8")
    section = text.split("## What typing this command authorises\n\n", 1)[1].split(
        "\n## Rules for the whole run", 1)[0]
    assert section == (
        "Typing `/cai:fix` authorises this one run, on the code in this checkout, for\n"
        "the origin it points at and the target the argument names: committing fixes to\n"
        "new local branches, pushing those branches to origin, opening pull requests\n"
        "from them, and replying to or resolving review threads. When the target is a\n"
        "list of issues, that authority covers only the issues the person selects from\n"
        "the list. It never merges anything, never pushes with force, and never pushes\n"
        "to the default branch.\n")


@pytest.mark.parametrize("disposition", ["fresh", "complete-push <branch>", "complete-pr <branch>"])
def test_work_dispositions_claim_before_any_work(disposition):
    assert (f'- `{disposition}`: Claim the item first, as "Claim the item" below says.'
            in reference("single-issue"))


def test_claim_uses_the_current_branch_and_preserves_the_blockers_identity():
    text = reference("single-issue")
    claim = text.split("### Claim the item ", 1)[1].split("## 2.", 1)[0]
    assert "fix_claims.py register --owner <owner> --repo <repo> --issue <N> --branch <branch>" in claim
    assert "`branch` line of step 1 or the branch in its `disposition`" in claim
    assert "Exit 3:" in claim and "`claimed-elsewhere`" in claim
    assert "`classify` printed" in claim and "issue's `url` in the list file" in claim
    assert "three words after `elsewhere`" in claim
    assert "Go to step 7 without releasing a claim" in claim


def test_claim_fallbacks_keep_working_and_only_remember_this_items_held_timestamp():
    claim = reference("single-issue").split("### Claim the item ", 1)[1].split("## 2.", 1)[0]
    assert "Exit 0:" in claim and "only for this item" in claim
    assert "`held` line's start time" in claim
    assert "every printed line other than `held`" in claim
    assert "Exit 1:" in claim and "retry once" in claim
    assert "without a claim" in claim and "add the error line" in claim


def test_session_claims_are_local_and_distinct_from_track_claims():
    text = reference("single-issue")
    assert ("A session claim is written only to this machine's user configuration directory: "
            "sessions see each other's claims only when they share that directory, and nothing "
            "is written to the issue or the ticket." in text)
    assert "track's claim on the issue, not a session claim" in text
    assert "Work on it anyway" in text
    for path in (PLUGIN / "skills" / "fix").rglob("*.md"):
        assert "fix_claims.py clear" not in path.read_text(encoding="utf-8")


def test_all_held_claim_endings_release_before_stopping_or_restoring_the_ref():
    text = reference("single-issue")
    baseline = text.split("## 3.", 1)[1].split("## 4.", 1)[0]
    changes = text.split("## 5.", 1)[1].split("## 6.", 1)[0]
    ending = text.split("## 7.", 1)[1]
    assert baseline.index("release") < baseline.index('"baseline tests fail on')
    assert "as step 7 says" in baseline
    assert "Exit 1 or 2: first release" in changes and "step 7's release command only" in changes
    assert changes.index("release") < changes.index("paste the output of `changes` and stop the run")
    assert "step 1 printed `held`" in ending
    assert "fix_claims.py release --owner <owner> --repo <repo> --issue <N> --started <started>" in ending
    assert "exact start time" in ending and "every printed line other than `released`" in ending
    assert ending.index("fix_claims.py release") < ending.index("Switch back")
    rules = " ".join(SKILL.read_text(encoding="utf-8").split())
    assert "however it ends or the whole run stops" in rules
    assert "`single-issue.md` step 7" in rules and "`jira-ticket.md`" in rules


def test_jira_maps_both_claim_commands_at_every_inherited_ending():
    text = reference("jira-ticket")
    mapping = text.split("For every", 1)[1].split("Jira is read", 1)[0]
    assert "`fix_claims.py` `register` or `release`" in mapping
    assert "--owner <owner> --repo <repo> --issue <N>" in mapping
    assert "--host '<host>' --key <KEY>" in mapping
    for ending in ("step 1", "baseline tests fail", "`changes` exits 1 or 2", "step 7"):
        assert ending in mapping
    assert "`classify` printed" in mapping and "ticket URL" in mapping
    assert "A ticket has no claims" not in text
    assert "no track claims" in text and "session claim in step 1 still applies" in text


def test_fix_unclaim_is_explicit_and_authorises_only_the_exact_claim():
    text = UNCLAIM_SKILL.read_text(encoding="utf-8")
    front = frontmatter(text)
    assert re.findall(r"^([A-Za-z][\w-]*):", front, re.MULTILINE) == [
        "name", "description", "argument-hint", "disable-model-invocation"]
    assert "name: fix-unclaim" in front
    assert ("Usage: /cai:fix-unclaim <issue or ticket URL> <platform> <session> <started>"
            in front)
    assert 'argument-hint: "<issue or ticket URL> <platform> <session> <started>"' in front
    assert "disable-model-invocation: true" in front
    assert re.findall(r"^## (.+)$", text, re.MULTILINE) == [
        "What typing this command authorises", "Steps", "No questions"]
    authority = " ".join(text.split("## Steps", 1)[0].split())
    assert "only the claim matching the URL, platform, session and start time" in authority
    assert "another session that is still active" in authority


def test_fix_unclaim_rejects_unsafe_input_before_one_exact_clear_command():
    text = " ".join(UNCLAIM_SKILL.read_text(encoding="utf-8").split())
    guard = text.split("## Steps", 1)[1].split("2. Run", 1)[0]
    assert "exactly four arguments" in guard
    assert "`detail:`" in guard and "single quote" in guard
    assert "do not call the script" in guard and "`rejected unrecognised:`" in guard
    assert ("fix_claims.py clear --project-dir <project root> --platform '<platform>' "
            "--session '<session>' --started '<started>' '<issue or ticket URL>'" in text)
    assert "three words from the blocked item's `detail`" in guard
    assert "Single-quote all four arguments" in text
    assert "paste its output as it is" in text
    assert "Exit 2 or 3" in text
    assert "Do not retry or change flags" in text
    assert "Ask no questions" in text


def test_validate_pins_fix_unclaim_frontmatter(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, repo, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*", "node_modules"))

    def validate():
        return subprocess.run([sys.executable, "scripts/validate.py", "fix-unclaim"], cwd=repo,
                              capture_output=True, encoding="utf-8")

    clean = validate()
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "FAIL" not in clean.stdout

    skill = repo / "plugins" / "cai" / "skills" / "fix-unclaim" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    mutations = [
        (text.replace("disable-model-invocation: true", "disable-model-invocation: false", 1),
         "disables model invocation"),
        (text.replace("disable-model-invocation: true\n", "", 1)
         + "\ndisable-model-invocation: true\n", "disables model invocation"),
        (text.replace("disable-model-invocation: true\n",
                      "disable-model-invocation: true\nmodel: sonnet\n", 1), "declares no model"),
        (text.replace("disable-model-invocation: true\n",
                      "disable-model-invocation: true\nallowed-tools: Bash\n", 1), "grants no tool"),
    ]
    for mutated, failure in mutations:
        assert mutated != text
        skill.write_text(mutated, encoding="utf-8")
        broken = validate()
        assert broken.returncode == 1, broken.stdout + broken.stderr
        assert re.search(r"^FAIL .*" + failure, broken.stdout, re.MULTILINE), broken.stdout


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


def test_codex_claim_script_uses_only_codex_identity_constants(generated):
    text = (generated / "scripts" / "fix_claims.py").read_text(encoding="utf-8")
    assert 'PLATFORM = "codex"' in text
    assert 'SESSION_ID_ENV = "CODEX_THREAD_ID"' in text
    assert "CLAUDE_CODE_" not in text


def run_claims(plugin, *args):
    return subprocess.run([sys.executable, str(plugin / "scripts" / "fix_claims.py"), *args],
                          capture_output=True, encoding="utf-8", env=os.environ.copy())


@pytest.mark.parametrize("session", ["codex-thread", None, "unknown"])
def test_codex_claim_records_runtime_identity_and_releases(generated, tmp_path, monkeypatch, session):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")
    if session is not None:
        monkeypatch.setenv("CODEX_THREAD_ID", session)
    path = tmp_path / "cai" / "fix-claims.json"
    register = ("register", "--owner", "Acme", "--repo", "APP", "--issue", "142",
                "--branch", "fix/142")
    held = run_claims(generated, *register)
    assert held.returncode == 0, held.stdout + held.stderr
    started = held.stdout.splitlines()[0].split()[3]
    assert held.stdout.splitlines()[0] == f"registry held acme/app#142 {started}"
    identity = session if session == "codex-thread" else None
    assert json.loads(path.read_text(encoding="utf-8")) == {"claims": {"acme/app#142": {
        "platform": "codex", "session_id": identity, "started": started,
        "status": "in-progress", "branch": "fix/142"}}}
    if identity is None:
        assert "registry note session unknown: CODEX_THREAD_ID is not set or not usable" in held.stdout
    else:
        # Resuming the same thread is treated as owning the claim, even in another process.
        resumed = run_claims(generated, *register)
        assert resumed.returncode == 0, resumed.stdout + resumed.stderr
        assert resumed.stdout.startswith("registry held acme/app#142 ")
        started = resumed.stdout.splitlines()[0].split()[3]
    released = run_claims(generated, "release", "--owner", "acme", "--repo", "app",
                          "--issue", "142", "--started", started)
    assert released.returncode == 0, released.stdout + released.stderr
    assert released.stdout == "registry released acme/app#142\n"
    assert json.loads(path.read_text(encoding="utf-8")) == {"claims": {}}


@pytest.mark.parametrize("first_platform", ["claude", "codex"])
def test_codex_and_claude_claims_share_one_registry(generated, tmp_path, monkeypatch, first_platform):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "shared-session")
    monkeypatch.setenv("CODEX_THREAD_ID", "shared-session")
    plugins = {"claude": PLUGIN, "codex": generated}
    first = plugins[first_platform]
    second = plugins["codex" if first_platform == "claude" else "claude"]
    register = ("register", "--owner", "acme", "--repo", "app", "--issue", "142",
                "--branch", "fix/142")
    held = run_claims(first, *register)
    assert held.returncode == 0, held.stdout + held.stderr
    started = held.stdout.splitlines()[0].split()[3]
    path = tmp_path / "cai" / "fix-claims.json"
    before = path.read_bytes()
    blocked = run_claims(second, *register)
    assert blocked.returncode == 3, blocked.stdout + blocked.stderr
    assert blocked.stdout == f"registry elsewhere {first_platform} shared-session {started}\n"
    assert path.read_bytes() == before
    released = run_claims(first, "release", "--owner", "acme", "--repo", "app",
                          "--issue", "142", "--started", started)
    assert released.returncode == 0, released.stdout + released.stderr
    assert released.stdout == "registry released acme/app#142\n"
    assert json.loads(path.read_text(encoding="utf-8")) == {"claims": {}}
    claimed = run_claims(second, *register)
    assert claimed.returncode == 0, claimed.stdout + claimed.stderr
    assert claimed.stdout.startswith("registry held acme/app#142 ")


def test_codex_fix_unclaim_keeps_only_name_description_and_explicit_invocation(generated):
    skill = generated / "skills" / "fix-unclaim"
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert re.findall(r"^([A-Za-z][\w-]*):", frontmatter(text), re.MULTILINE) == [
        "name", "description"]
    assert "Usage: $fix-unclaim <issue or ticket URL> <platform> <session> <started>" in text
    yaml = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert yaml == "policy:\n  allow_implicit_invocation: false\n"


def test_codex_readme_explains_local_claim_limits_and_unverified_permissions():
    text = (REPO_ROOT / "plugins" / "cai-codex" / "README.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `/cai:fix` "))
    for phrase in ("Claims are local only", "`config_root()/cai/`", "`CLAUDE_CONFIG_DIR`",
                   "`~/.claude`", "same `config_root()`", "no claim writes to an issue or ticket",
                   "same session ID do not block each other", "sandbox permission",
                   "has not been confirmed in a real Codex session"):
        assert phrase in row


def test_codex_readme_explains_explicit_four_argument_unclaim():
    text = (REPO_ROOT / "plugins" / "cai-codex" / "README.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `/cai:fix-unclaim` "))
    for phrase in ("$fix-unclaim <issue or ticket URL> <platform> <session> <started>",
                   "explicitly typed", "exactly four arguments", "URL, platform, session and start time",
                   "all match", "mismatch deletes nothing", "still active"):
        assert phrase in row


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
