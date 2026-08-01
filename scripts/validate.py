#!/usr/bin/env python3
"""Validate marketplace/plugin manifests, component frontmatter, and guard
behavior. Zero deps."""
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

FAIL = 0
PLUGIN = "plugins/cai"


def check(label, cond):
    global FAIL
    print(("PASS" if cond else "FAIL"), label)
    if not cond:
        FAIL = 1


def frontmatter_keys(path):
    """Return the top-level keys of a markdown file's YAML frontmatter.

    Deliberately not a YAML parser — we only need key presence, and the repo
    must stay dependency-free so CI runs on a bare Python.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return set(re.findall(r"^([A-Za-z][\w-]*):", text[3:end], re.MULTILINE))


mp = json.load(open(".claude-plugin/marketplace.json"))
check("marketplace has name/owner/plugins", all(k in mp for k in ("name", "owner", "plugins")))

for entry in mp["plugins"]:
    src = entry["source"]
    manifest = f"{src}/.claude-plugin/plugin.json"
    pl = json.load(open(manifest))
    check(f"{manifest} has name/version", "name" in pl and "version" in pl)
    check(f"names match ({entry['name']})", pl["name"] == entry["name"])

# Component frontmatter. A missing key means Claude Code silently skips the
# component, so catch it here rather than at someone else's runtime.
for path in sorted(glob.glob(f"{PLUGIN}/agents/*.md")):
    keys = frontmatter_keys(path)
    check(f"{path} frontmatter has name+description", bool(keys) and {"name", "description"} <= keys)

for path in sorted(glob.glob(f"{PLUGIN}/commands/*.md")):
    keys = frontmatter_keys(path)
    check(f"{path} frontmatter has description", bool(keys) and "description" in keys)

skills = sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
check("at least one skill ships", bool(skills))
for path in skills:
    keys = frontmatter_keys(path)
    check(f"{path} frontmatter has name+description", bool(keys) and {"name", "description"} <= keys)

# /cai:setup copies these out to ~/.claude/rules/; an empty dir would
# make setup a silent no-op.
rules = sorted(glob.glob(f"{PLUGIN}/rules/*.md"))
check("rules ship with the plugin", bool(rules))

TEMPLATE = f"{PLUGIN}/templates/CLAUDE.md.tpl"
check("user CLAUDE.md template ships", os.path.isfile(TEMPLATE))


def bullets(path):
    with open(path, encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip().startswith("- ")}


# The template seeds ~/.claude/CLAUDE.md, which loads alongside ~/.claude/rules/.
# Anything restated in both is sent to the model twice in every session, and the
# copies drift the moment one is edited. Keep them disjoint.
if os.path.isfile(TEMPLATE) and rules:
    ruleset = set().union(*(bullets(p) for p in rules))
    clashes = sorted(bullets(TEMPLATE) & ruleset)
    check(f"template does not restate rules ({len(clashes)} duplicated)", not clashes)
    for line in clashes[:5]:
        print("     also in rules/:", line[:90])

hooks = json.load(open(f"{PLUGIN}/hooks/hooks.json"))
print("PASS hooks.json is valid JSON")

for event in hooks.get("hooks", {}).values():
    for matcher in event:
        for hook in matcher.get("hooks", []):
            for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}([^\"]*)", hook.get("command", "")):
                target = f"{PLUGIN}{ref.strip()}"
                check(f"hook target exists ({target})", os.path.isfile(target))

# .claude/settings.json points at a repo-local hook the same way hooks.json
# points at a shipped one. A rename should fail here, not at someone's runtime.
SETTINGS = ".claude/settings.json"
if os.path.isfile(SETTINGS):
    for event in json.load(open(SETTINGS)).get("hooks", {}).values():
        for matcher in event:
            for hook in matcher.get("hooks", []):
                for ref in re.findall(r"\$\{CLAUDE_PROJECT_DIR\}([^\"]*)", hook.get("command", "")):
                    target = ref.strip().lstrip("/")
                    check(f"project hook target exists ({target})", os.path.isfile(target))

GUARD = f"{PLUGIN}/scripts/bash_guard.py"
DISPATCHER = f"{PLUGIN}/hooks/run-guard.cmd"

# CMD.exe reads batch files through the OEM codepage, so one multi-byte
# character desyncs its parser and every later line runs mangled ('cho' for
# 'echo'). The sh branch is unaffected, so this breaks on Windows only.
for path in sorted(glob.glob("**/*.cmd", recursive=True)):
    with open(path, "rb") as fh:
        non_ascii = [b for b in fh.read() if b > 127]
    check(f"{path} is pure ASCII ({len(non_ascii)} byte(s) over 127)", not non_ascii)

def temp_repo(branch, commit=True):
    """A throwaway repo on a known branch. The guard asks git which branch it
    is on, so every `git commit` case needs a cwd of its own — otherwise the
    result depends on whoever runs validate.py being on the right branch.

    `commit=False` leaves HEAD unborn, which the guard treats as unprotected."""
    path = tempfile.mkdtemp(prefix=f"cai-guard-{branch}-")
    subprocess.run(["git", "init", "-b", branch, path], capture_output=True, text=True)
    if commit:
        subprocess.run(["git", "-C", path, "-c", "user.email=t@example.com",
                        "-c", "user.name=t", "commit", "--allow-empty", "-m", "root"],
                       capture_output=True, text=True)
    return path


def detached_repo():
    """A repo on no branch at all. symbolic-ref fails here for a different
    reason than 'not a repo', and the guard has to fail open for both."""
    path = temp_repo("main")
    subprocess.run(["git", "-C", path, "checkout", "--detach"], capture_output=True, text=True)
    return path


WORK = temp_repo("work")
MAIN = temp_repo("main")
NOT_A_REPO = tempfile.mkdtemp(prefix="cai-guard-bare-")
DETACHED = detached_repo()
UNBORN = temp_repo("main", commit=False)

CASES = [
    # (tool_name, command, expected, cwd)
    ("Bash", "git push --force origin main", 2, WORK),
    ("Bash", "git push -f origin main", 2, WORK),
    ("Bash", "git push --force-with-lease origin main", 0, WORK),
    ("Bash", "git reset --hard HEAD~1", 2, WORK),
    ("Bash", "git commit --no-verify -m x", 2, WORK),
    ("Bash", "rm -rf build/", 2, WORK),
    ("Bash", "git status", 0, WORK),
    # git global options before the verb: one flag used to defeat every rule.
    ("Bash", "git -C /repo push --force origin main", 2, WORK),
    ("Bash", "git -c user.name=x reset --hard HEAD~1", 2, WORK),
    ("Bash", "git --no-pager clean -fd", 2, WORK),
    # Split and long delete flags reach the same files as -rf.
    ("Bash", "rm -r -f build/", 2, WORK),
    ("Bash", "rm --recursive --force build/", 2, WORK),
    ("Bash", "rm -f notes.txt", 0, WORK),
    # ...but the match must not run past the command it belongs to.
    ("Bash", "git status && npm publish --no-verify", 0, WORK),
    # A here-string is a typo in Bash and correct in PowerShell, so the verdict
    # depends on tool_name alone. Both directions matter: blocking the second
    # would be a false positive on valid PowerShell.
    ("Bash", "git commit -m @'\nfeat: x\n'@", 2, WORK),
    ("PowerShell", "git commit -m @'\nfeat: x\n'@", 0, WORK),
    # The pattern backreferences the opening quote, so the double-quoted form
    # has to be caught too or the character class is decoration.
    ('Bash', 'git commit -m @"\nfeat: x\n"@', 2, WORK),
    ("Bash", "git commit -F - <<'EOF'\nfeat: x\nEOF", 0, WORK),
    ("Bash", "grep '@\"' README.md", 0, WORK),
    ("Bash", 'curl -o x "https://user:tok@"', 0, WORK),  # opener shape, no terminator
    ("Bash", "git log --grep='git commit' --oneline", 0, MAIN),  # not a commit
    # rm -rf spelled the PowerShell way; the shared patterns never see it.
    ("PowerShell", "Remove-Item -Recurse -Force build", 2, WORK),
    ("PowerShell", "Remove-Item -Force build.txt", 0, WORK),
    # The spellings a PowerShell user actually types: aliases, lower case, and
    # any unambiguous parameter prefix.
    ("PowerShell", "rm -Recurse -Force build", 2, WORK),
    ("PowerShell", "remove-item -recurse -force build", 2, WORK),
    ("PowerShell", "ri -Recurse -Force build", 2, WORK),
    ("PowerShell", "Remove-Item -Rec -Fo build", 2, WORK),
    # rules/workflow.md says never work directly on main. This is the half of
    # that absolute a hook can actually decide.
    ("Bash", "git commit -m 'feat: x'", 2, MAIN),
    ("Bash", "git commit -m 'feat: x'", 0, WORK),
    # The whole point of anchoring to a command boundary rather than matching
    # `git commit` anywhere. Drop the anchor back to ^ and only these two fail.
    ("Bash", "echo hi && git commit -m 'feat: x'", 2, MAIN),
    ("Bash", "echo hi; git commit -m 'feat: x'", 2, MAIN),
    # The shapes a commit really arrives in. Each one walked past the old anchor.
    ("Bash", "GIT_EDITOR=true git commit -m x", 2, MAIN),
    ("Bash", "(git commit -m x)", 2, MAIN),
    ("Bash", "echo $(git commit -m x)", 2, MAIN),
    ("Bash", "git -c user.name=x commit -m y", 2, MAIN),
    # Git cannot name a branch with no repo, and names none when HEAD is
    # detached. Fail open for both: a guard that blocks every commit the moment
    # git can't answer is worse than the rule it enforces.
    ("Bash", "git commit -m 'feat: x'", 0, NOT_A_REPO),
    ("Bash", "git commit -m 'feat: x'", 0, DETACHED),
    # A repo with no commits yet reports branch `main`, but blocking its first
    # commit is unescapable: you cannot branch off a history that isn't there.
    ("Bash", "git commit -m 'chore: initial commit'", 0, UNBORN),
    # Heredoc bodies are data. Writing a PR body or release note that mentions
    # a git command is not running that command.
    ("Bash", "cat > notes.md <<'EOF'\ngit commit -m x rewrites nothing\nEOF", 0, MAIN),
    ("Bash", "cat > s.ps1 <<'EOF'\n$m = @'\nhello\n'@\nEOF", 0, WORK),
    # ...but the heredoc feeding a real commit must not hide the commit itself.
    ("Bash", "git commit -F - <<'EOF'\nfeat: x\nEOF", 2, MAIN),
]


def run(argv, cmd, tool="Bash", cwd=""):
    return subprocess.run(
        argv,
        input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": cwd}),
        capture_output=True, text=True,
    ).returncode


for tool, cmd, expected, cwd in CASES:
    label = cmd.replace("\n", "\\n")
    check(f"guard {tool} [{label}] -> {expected}", run([sys.executable, GUARD], cmd, tool, cwd) == expected)

# The dispatcher is what hooks.json actually invokes. Exercise the branch this
# platform would take, so a broken interpreter lookup or a swallowed exit code
# fails here instead of silently disarming the guard.
dispatch = ["cmd", "/c", DISPATCHER.replace("/", "\\")] if os.name == "nt" else ["sh", DISPATCHER]
for cmd, expected in [("git reset --hard HEAD~1", 2), ("git status", 0)]:
    check(f"dispatcher [{cmd}] -> {expected}", run(dispatch, cmd, "Bash", WORK) == expected)


# The PostToolUse hook re-runs this script, so exercising it re-enters this
# block. validate_hook.py sets the flag on the run it spawns, which stops the
# chain one level down and keeps a real edit paying for one validate, not five.
def run_hook(payload_text, argv=None):
    return subprocess.run(
        argv or [sys.executable, "scripts/validate_hook.py"], input=payload_text,
        capture_output=True, text=True,
    )


def hook_payload(path):
    return json.dumps({"tool_name": "Edit", "tool_input": {"file_path": os.path.abspath(path)}})


if os.environ.get("CAI_VALIDATE_NESTED") != "1":
    # Bail-out paths. A hook that is slow or noisy on unrelated files is a hook
    # someone turns off, so these must return before spawning anything.
    for text, label in [
        (hook_payload("README.md"), "file outside the plugin tree"),
        (json.dumps({"tool_input": {}}), "no file_path"),
        ("not json at all", "malformed payload"),
    ]:
        check(f"validate_hook [{label}] -> 0", run_hook(text).returncode == 0)

    # The reason the hook exists. Both verdicts have to be exercised, or the
    # only tested behaviour is the part that does nothing.
    check("validate_hook [watched edit, repo valid] -> 0",
          run_hook(hook_payload(f"{PLUGIN}/rules/coding.md")).returncode == 0)

    probe = f"{PLUGIN}/skills/_validate_hook_probe"
    try:
        os.makedirs(probe, exist_ok=True)
        with open(f"{probe}/SKILL.md", "w", encoding="utf-8") as fh:
            fh.write("no frontmatter, so validate.py fails\n")
        broke = run_hook(hook_payload(f"{probe}/SKILL.md"))
        check("validate_hook [watched edit, repo broken] -> 2", broke.returncode == 2)
        check("validate_hook names the failing check", "FAIL" in broke.stderr)
    finally:
        shutil.rmtree(probe, ignore_errors=True)

    # .claude/settings.json invokes the dispatcher, not the script. Same reason
    # the guard's dispatcher is exercised above: a broken interpreter lookup or
    # a swallowed exit code should fail here, not silently do nothing forever.
    hook_dispatch = (["cmd", "/c", r"scripts\run-validate-hook.cmd"] if os.name == "nt"
                     else ["sh", "scripts/run-validate-hook.cmd"])
    check("validate_hook dispatcher [file outside the plugin tree] -> 0",
          run_hook(hook_payload("README.md"), hook_dispatch).returncode == 0)
else:
    # A green run must always say what it did not check. Otherwise a stray
    # CAI_VALIDATE_NESTED in the environment reports success for a run that
    # skipped six checks.
    print("SKIP hook self-tests (CAI_VALIDATE_NESTED=1)")

def rmtree(path):
    """git marks loose objects read-only and Windows refuses to delete those,
    so ignore_errors would silently leave a temp repo behind on every run — and
    the PostToolUse hook runs this script on every edit under plugins/cai/."""
    def retry(func, target, _):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


for path in (WORK, MAIN, NOT_A_REPO, DETACHED, UNBORN):
    rmtree(path)

sys.exit(FAIL)
