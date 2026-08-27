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


def read_text(path):
    """Every file this script reads is UTF-8. Naming the encoding once is what
    stops the next check being written without it -- on Windows the default is
    the OEM codepage, so an omission reads the em dashes in rules/*.md as
    mojibake and only fails on someone else's machine."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter_keys(path):
    """Return the top-level keys of a markdown file's YAML frontmatter.

    Deliberately not a YAML parser — we only need key presence, and the repo
    must stay dependency-free so CI runs on a bare Python.
    """
    text = read_text(path)
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

# goal.md routes rather than implements, so it is read start to finish every
# time someone reaches for it -- and prose that outgrows a screen is prose that
# gets skimmed past the branch it was carrying. The ceiling is the number the
# design settled on (docs/design/2026-08-25-goal-command-routing-detail.md,
# Budgets); this is what stops it being a number nobody ever checks again.
GOAL = f"{PLUGIN}/commands/goal.md"
goal_lines = len(read_text(GOAL).splitlines())
check(f"{GOAL} is within its 120-line ceiling ({goal_lines})", goal_lines <= 120)

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


REFACTORING = f"{PLUGIN}/skills/refactoring"


def referenced_paths(path):
    """Sub-file paths the refactoring SKILL.md points models at, e.g. the
    reference table and the smell lookup. A path named here that does not
    exist on disk is a model told to read something that was never shipped."""
    text = read_text(path)
    return {f"{PLUGIN}{m}" for m in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}([^`\s]+)", text)}


def index_slugs(path):
    """Slugs the catalog index declares as the single source of truth for
    what /refactor-apply <slug> can be called with."""
    text = read_text(path)
    return set(re.findall(r"^\|\s*\d+\s*\|[^|]*\|\s*`([a-z0-9-]+)`\s*\|", text, re.MULTILINE))


def card_slugs(paths):
    """Slugs actually defined by a '### N. Name `slug`' heading in the card
    files. If the index and this ever disagree, refactor-apply looks up a
    slug the index promised and the card never defines."""
    slugs = set()
    for path in paths:
        text = read_text(path)
        slugs |= set(re.findall(r"^### \d+\.\s.*`([a-z0-9-]+)`\s*$", text, re.MULTILINE))
    return slugs


def protocol_lines(path):
    """Entries of the safety protocol: the numbered loop steps and the hard-rule
    bullets. Both halves count -- the numbered loop is the half a process skill
    is most likely to paste, since it reads like a procedure. Like bullets()
    above, this compares first lines only, so a wrapped entry is matched on the
    line that carries its opening words."""
    text = read_text(path)
    section = text.split("## Non-negotiable safety protocol", 1)[1]
    section = section.split("\n## ", 1)[0]
    return {line.strip() for line in section.splitlines()
            if line.strip().startswith("- ") or re.match(r"^\d+\.\s", line.strip())}


# Check 1: a body that points at a card the refactor never shipped leaves a
# model to improvise the mechanics instead of reading them.
SKILL = f"{REFACTORING}/SKILL.md"
refs = referenced_paths(SKILL)
missing_refs = sorted(p for p in refs if not os.path.isfile(p))
check(f"{SKILL} sub-files all exist ({len(missing_refs)} missing)", not missing_refs)
for p in missing_refs[:5]:
    print("     missing:", p)

# Check 2: the index is the single source of truth for slugs (see design
# decisions #4). A slug it declares but no card defines is a 404 the moment
# /refactor-apply is called with it; the reverse means a card nobody can reach.
INDEX = f"{REFACTORING}/references/catalog-index.md"
CARDS = sorted(glob.glob(f"{REFACTORING}/references/cat-*.md"))
idx_slugs = index_slugs(INDEX)
crd_slugs = card_slugs(CARDS)
missing_cards = sorted(idx_slugs - crd_slugs)
extra_cards = sorted(crd_slugs - idx_slugs)
check(f"catalog-index slugs match card files ({len(missing_cards)} missing, {len(extra_cards)} extra)",
      not missing_cards and not extra_cards)
for slug in missing_cards[:5]:
    print("     index names but no card defines:", slug)
for slug in extra_cards[:5]:
    print("     card defines but index omits:", slug)

# Check 3: the safety protocol lives in the knowledge skill only (design
# decisions #3). A component that pastes a rule verbatim instead of pointing
# back here is exactly what goes stale the day the rule changes.
#
# The agents are covered as well as the process skills, because the design's
# own failure mode counts three copies of the protocol -- the knowledge skill,
# refactor-apply, and refactoring-surgeon -- and a check that watched only two
# of the three would leave the copy inside the agent free to drift.
proto_lines = protocol_lines(SKILL)
for path in sorted(glob.glob(f"{PLUGIN}/skills/refactor-*/SKILL.md")
                   + glob.glob(f"{PLUGIN}/agents/refactoring-*.md")):
    # Both sides must extract the same shapes, or widening one half silently
    # guards nothing: bullets() alone would miss a pasted numbered loop step.
    with open(path, encoding="utf-8") as fh:
        candidates = {ln.strip() for ln in fh
                      if ln.strip().startswith("- ") or re.match(r"^\d+\.\s", ln.strip())}
    restated = sorted(candidates & proto_lines)
    check(f"{path} does not restate the safety protocol ({len(restated)} duplicated)", not restated)
    for line in restated[:5]:
        print("     also in refactoring/SKILL.md:", line[:90])

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

# /cai:setup step 5 runs the dispatcher through cmd, and the Bash tool on
# Windows is Git Bash, which rewrites a lone /c into C:/. cmd then never sees
# the switch and exits 0 -- the exact code step 5 reads as "the guard is inert".
# A healthy guard reported as broken is worse than no check at all.
SETUP = f"{PLUGIN}/commands/setup.md"
setup_text = read_text(SETUP)
check("setup.md invokes cmd as //c (MSYS would eat a lone /c)",
      "cmd //c" in setup_text and not re.search(r"cmd\s+/(?!/)c\b", setup_text))

GUARD = f"{PLUGIN}/scripts/bash_guard.py"
DISPATCHER = f"{PLUGIN}/hooks/run-guard.cmd"

# CMD.exe reads batch files through the OEM codepage, so one multi-byte
# character desyncs its parser and every later line runs mangled ('cho' for
# 'echo'). The sh branch is unaffected, so this breaks on Windows only.
for path in sorted(glob.glob("**/*.cmd", recursive=True)):
    with open(path, "rb") as fh:
        non_ascii = [b for b in fh.read() if b > 127]
    check(f"{path} is pure ASCII ({len(non_ascii)} byte(s) over 127)", not non_ascii)

# A UTF-8 BOM is invisible in an editor and breaks readers that expect the file
# to start with content: mermaid-cli refuses the diagram outright ("Parse error
# on line 1"), and CMD.exe prints the three bytes before the first line runs.
# On Windows PowerShell's `>`, `>>` and `Out-File` write one by default, which
# is how it gets in -- so this catches a redirect that should have been an edit.
BOM = b"\xef\xbb\xbf"
TEXT = (".md", ".json", ".py", ".cmd", ".sh", ".tpl", ".yml", ".yaml", ".mmd")
bom_files = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d != ".git"]
    for name in sorted(files):
        if not name.endswith(TEXT):
            continue
        path = os.path.join(root, name)
        with open(path, "rb") as fh:
            if fh.read(3) == BOM:
                bom_files.append(os.path.relpath(path).replace(os.sep, "/"))
check(f"no text file carries a UTF-8 BOM ({len(bom_files)} found)", not bom_files)
for path in bom_files[:5]:
    print("     BOM:", path)


# The evidence and decision rules are copied verbatim into both design commands
# on purpose: a command's text is only loaded when that command runs, so a
# cross-reference would point at something the model cannot see. Duplication
# nothing checks is duplication that drifts, and the drift is silent.
def rule_block(path):
    body = read_text(path).split("## The two rules everything below obeys", 1)[-1]
    return body.split("These two rules appear", 1)[0].strip()


DESIGN_CMDS = [f"{PLUGIN}/commands/design-high-level-doc.md",
               f"{PLUGIN}/commands/design-implementation-detail-doc.md"]
# Guarding on existence without checking it lets the drift check disappear the
# day a file is renamed -- which is exactly the drift it exists to catch.
for path in DESIGN_CMDS:
    check(f"design command ships ({path})", os.path.isfile(path))
if all(os.path.isfile(p) for p in DESIGN_CMDS):
    one, two = (rule_block(p) for p in DESIGN_CMDS)
    check("design commands carry one identical rule block", bool(one) and one == two)


# A component that tells the model to run `plugins/cai/scripts/...` works only
# inside this checkout. Anyone who installed from the marketplace has the plugin
# under ~/.claude/plugins/cache/, so the command silently stops working for
# every real user -- the failure this repo is least able to notice.
for path in sorted(glob.glob(f"{PLUGIN}/commands/*.md")
                   + glob.glob(f"{PLUGIN}/skills/*/SKILL.md")):
    check(f"{path} runs scripts via <plugin-root>",
          f"{PLUGIN}/scripts/" not in read_text(path))


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


# design_probe.py holds the two design commands' absolutes -- every capability
# cites evidence, every use case reaches a component, every glossary term points
# at a line that exists. Prose cannot hold those, so the probe has to actually
# work: one clean document per kind, then one deliberate defect per probe. A
# case asserts the exit code *and* which probe reported it, because a probe that
# fails for the wrong reason is a probe nobody can act on.
PROBE = f"{PLUGIN}/scripts/design_probe.py"
PROBE_DIR = tempfile.mkdtemp(prefix="cai-design-probe-")
FENCE = "```mermaid\nflowchart LR\n  A --> B\n```\n\n"
SEQ = "```mermaid\nsequenceDiagram\n  A->>B: go\n```\n\n"

HLD_OK = """## Status
approved 2026-08-25

## Use cases / Issues
- UC1 - an operator needs to see which runs failed overnight.

## Feasibility
| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | read the session log | verified | scripts/validate.py:41 |

## High-level design
The collector reads the logs and the reporter renders them; nothing is stateful.

## Architecture decisions
- Option A (recommended) - poll the log. Rests on C1, and adds no runtime dep.

## Open questions
- Whether "overnight" is measured in UTC or in the operator's local time.

## Out of scope
Cross-repo runs, and anything at all that would require a database.
"""

DETAIL_OK = """## Reference
High Level Design doc: hld.md (Status: approved 2026-08-25).

## Requirement
UC1 from the referenced high-level design is what this document satisfies.

## Glossary
| Term | Definition | Where it lives |
|---|---|---|
| Collector | reads the session log, one record per run | scripts/validate.py:41 |

## Budgets
| What | Number | Where it comes from |
|---|---|---|
| runs per night | up to 400 | the operator's own estimate, 2026-08-25 |
| render latency | under 2s at 400 runs | UC1 is read interactively |

## Design decisions
Polling beat interception because UC1 never needs to block a live call.

## Diagrams
Architecture, component, flow, and one sequence per use case follow below.

""" + FENCE * 3 + SEQ + """## Implementation spec
The Collector exposes read_runs(path) -> list[Record]; errors surface to caller.

## Naming
Every file this produces gets a spelled-out name; no abbreviation is invented.

## Change points
- scripts/validate.py - gains one case for the collector. No new dependency.

## Failure modes
- The log file is missing: the collector emits nothing and reports that.

## Rollout
- Ships in one piece; rollback is reverting the commit, no data is written.

## Verification
- UC1: unit test over a fixture log, asserting one record per run.

## Work breakdown
| Unit | Depends on | Done when |
|---|---|---|
| 1 collector | nothing | its unit test is green |
| 2 reporter | unit 1's record shape | UC1's test is green end to end |
"""

# One decision row cites evidence and the other is UNVERIFIED, so the clean
# fixture walks both paths decisions_evidence accepts. A fixture where every
# row cites something would leave the UNVERIFIED branch untested, and that
# branch is the one carrying the command's promise not to guess.
DELTA_OK = """## Scope
Base ref origin/main, range a3f21bc..HEAD, four files changed.

## Problem
The overnight run reported failures nobody saw until the next morning.

## Before / After
The collector wrote to stdout before; it writes to the session log now.

""" + FENCE * 2 + """## Decisions
| Decision | Why | Evidence |
|---|---|---|
| write to the session log | stdout is not captured by the runner | scripts/validate.py:41 |
| drop the retry loop | UNVERIFIED | nothing in the branch says why |

## Impact
| What it touches | The assumption | What breaks if it is wrong |
|---|---|---|
| the runner's log path | it is writable at start up | the collector emits nothing and says so |

## Limits
Cross-repo runs stay out of scope; this reads the local session log only.
"""

# The detail fixtures name this in ## Reference, and the probe looks for it
# beside the document it is checking.
with open(os.path.join(PROBE_DIR, "hld.md"), "w", encoding="utf-8") as fh:
    fh.write(HLD_OK)

PROBE_CASES = [
    # (kind, fixture text, expected exit, the probe that must be the one to fail)
    ("hld", HLD_OK, 0, ""),
    ("hld", HLD_OK.replace(" Rests on C1,", ""), 2, "pairs_covered"),
    ("hld", HLD_OK.replace("| verified |", "| UNVERIFIED |"), 2, "recommendation_is_verified"),
    ("hld", HLD_OK.replace("scripts/validate.py:41", "the session log"), 2, "feasibility_evidence"),
    ("hld", HLD_OK.replace("## Out of scope", "## Elsewhere"), 2, "headings_complete"),
    ("detail", DETAIL_OK, 0, ""),
    ("detail", DETAIL_OK.replace("UC1", "the use case"), 2, "traceability"),
    ("detail", DETAIL_OK.replace("validate.py:41", "validate.py:99999"), 2, "glossary_citations"),
    ("hld", HLD_OK.replace("approved 2026-08-25", "signed off, looks good"), 2, "status_is_well_formed"),
    ("hld", re.sub(r"\n\| C1 .*", "", HLD_OK), 2, "feasibility_has_rows"),
    ("hld", HLD_OK.replace("| C1 |", "| the log |"), 2, "feasibility_ids"),
    ("detail", DETAIL_OK.replace(FENCE * 3 + SEQ, FENCE * 2 + SEQ), 2, "diagrams_present"),
    ("detail", DETAIL_OK.replace(SEQ, FENCE), 2, "sequence_diagram_present"),
    ("detail", DETAIL_OK.replace("up to 400", "as many as we get"), 2, "budgets_are_numeric"),
    ("detail", DETAIL_OK.replace("## Rollout", "## Shipping"), 2, "headings_complete"),
    ("detail", DETAIL_OK.replace("hld.md", "no-such-design.md"), 2, "reference_resolves"),
    ("delta", DELTA_OK, 0, ""),
    ("delta", DELTA_OK.replace("a3f21bc..HEAD", "the tip of the branch"), 2, "scope_names_a_range"),
    ("delta", DELTA_OK.replace(FENCE * 2, FENCE), 2, "before_after_diagrams"),
    ("delta", re.sub(r"\n\| (?:write|drop) .*", "", DELTA_OK), 2, "decisions_have_rows"),
    ("delta", DELTA_OK.replace("scripts/validate.py:41", "it seemed better"), 2, "decisions_evidence"),
    ("delta", re.sub(r"\n\| the runner's log path .*", "", DELTA_OK), 2, "impact_has_rows"),
    ("delta", DELTA_OK.replace("## Limits", "## Caveats"), 2, "headings_complete"),
]

for i, (kind, fixture_text, expected, probe) in enumerate(PROBE_CASES):
    fixture = os.path.join(PROBE_DIR, f"case{i}.md")
    with open(fixture, "w", encoding="utf-8") as fh:
        fh.write(fixture_text)
    done = subprocess.run([sys.executable, PROBE, "--kind", kind, fixture],
                          capture_output=True, text=True)
    check(f"design_probe {kind} [{probe or 'clean document'}] -> {expected}",
          done.returncode == expected)
    if probe:
        check(f"design_probe {kind} names {probe}", f"FAIL {probe}" in done.stdout)

# The templates are the shape both commands write to, so they and the probe have
# to agree on the headings -- if they drift, every real document fails a check
# whose source nobody can find. And an untouched template must FAIL its own
# probe: its guidance lives in HTML comments, and the day those start counting
# as content is the day a blank template passes everything.
sys.path.insert(0, f"{PLUGIN}/scripts")
import design_probe  # noqa: E402

for kind, want in (("hld", design_probe.HLD_HEADINGS),
                   ("detail", design_probe.DETAIL_HEADINGS),
                   ("delta", design_probe.DELTA_HEADINGS)):
    tpl = f"{PLUGIN}/templates/{design_probe.TEMPLATES[kind]}"
    check(f"{kind} design template ships", os.path.isfile(tpl))
    if not os.path.isfile(tpl):
        continue
    got = list(design_probe.sections(read_text(tpl)))
    check(f"{kind} template headings match the probe", got == want)
    if got != want:
        print("     template:", got)
        print("     probe   :", want)
    blank = subprocess.run([sys.executable, PROBE, "--kind", kind, tpl],
                           capture_output=True, text=True)
    check(f"{kind} template does not pass its own probe", blank.returncode == 2)

# preflight.py's design check reads state.md's design row and hands the
# artifact to design_probe.py, so its fixture needs a real track state next
# to a real (or deliberately broken) design document -- same shape as the
# PROBE_CASES above, one level up the stack.
PREFLIGHT = f"{PLUGIN}/scripts/preflight.py"
PREFLIGHT_PROJECT = temp_repo("preflight-fixture")
PREFLIGHT_TRACK = os.path.join(PREFLIGHT_PROJECT, "track")
os.makedirs(os.path.join(PREFLIGHT_PROJECT, "docs", "design"), exist_ok=True)
os.makedirs(PREFLIGHT_TRACK, exist_ok=True)

with open(os.path.join(PREFLIGHT_PROJECT, "docs", "design", "hld.md"), "w", encoding="utf-8") as fh:
    fh.write(HLD_OK)
with open(os.path.join(PREFLIGHT_PROJECT, "docs", "design", "billing-detail.md"),
          "w", encoding="utf-8") as fh:
    # DETAIL_OK's glossary cites scripts/validate.py:41, which does not exist
    # inside this throwaway project root; point it at the sibling hld.md
    # written above instead, which does.
    fh.write(DETAIL_OK.replace("scripts/validate.py:41", "docs/design/hld.md:1"))


def write_preflight_state(artifact_cell):
    # state.md is overwritten in place, never appended to -- each case
    # replaces the whole file rather than editing one cell.
    text = ("# preflight-fixture\n\nbranch: feat/preflight-fixture\n"
            "started: 2026-08-27\n\n| stage | status | artifact | note |\n"
            "|---|---|---|---|\n| intake | done | — | |\n"
            "| discover | done | — | |\n"
            "| design | done | %s | |\n"
            "| build | | | |\n| verify | | | |\n| ship | | | |\n" % artifact_cell)
    with open(os.path.join(PREFLIGHT_TRACK, "state.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


def run_preflight(stage, track_dir=PREFLIGHT_TRACK):
    return subprocess.run(
        [sys.executable, PREFLIGHT, stage, "--track-dir", track_dir,
         "--project-dir", PREFLIGHT_PROJECT],
        capture_output=True, text=True)


write_preflight_state("docs/design/billing-detail.md")
done = run_preflight("design")
check("preflight design [clean detail doc] -> 0", done.returncode == 0)

write_preflight_state("docs/design/does-not-exist-detail.md")
done = run_preflight("design")
check("preflight design [artifact missing] -> 2", done.returncode == 2)
check("preflight design names artifact_exists", "FAIL artifact_exists" in done.stdout)

write_preflight_state("docs/design/billing-export.txt")
done = run_preflight("design")
check("preflight design [unrecognized suffix] -> 2", done.returncode == 2)
check("preflight design names artifact_kind", "FAIL artifact_kind" in done.stdout)

done = subprocess.run([sys.executable, PREFLIGHT, "no-such-stage",
                       "--track-dir", PREFLIGHT_TRACK],
                      capture_output=True, text=True)
check("preflight unknown stage id -> 1", done.returncode == 1)

done = run_preflight("intake")
check("preflight stub stage [intake] -> 2", done.returncode == 2)
check("preflight stub stage names not_implemented", "FAIL not_implemented" in done.stdout)

# Model tiers live in models.json, not in eighteen frontmatters. Three checks,
# because the failure modes are different: drift (someone edited a frontmatter
# by hand), escape (a new component nobody assigned a role), and regression
# (someone pinned a concrete version again, which is what models.json exists to
# stop -- an alias tracks its family, `claude-haiku-4-5-20251001` does not).
GEN_MODELS = f"{PLUGIN}/scripts/gen-models.py"
MODELS_JSON = f"{PLUGIN}/models.json"
check(f"models.json ships ({MODELS_JSON})", os.path.isfile(MODELS_JSON))
check(f"gen-models.py ships ({GEN_MODELS})", os.path.isfile(GEN_MODELS))

if os.path.isfile(MODELS_JSON) and os.path.isfile(GEN_MODELS):
    drifted = subprocess.run([sys.executable, GEN_MODELS, "--check"],
                             capture_output=True, text=True)
    check("every component's model matches its role in models.json",
          drifted.returncode == 0)
    if drifted.returncode != 0:
        print("    ", drifted.stdout.strip().replace("\n", "\n     "))

    spec = json.load(open(MODELS_JSON, encoding="utf-8"))
    aliases = {r["alias"] for r in spec["roles"].values()}
    assigned = set(spec["assignments"])

    # Anything that declares a model must be in the table. Without this, a new
    # agent silently keeps whatever tier its author typed and re-tiering a role
    # quietly skips it.
    declaring = set()
    for path in (sorted(glob.glob(f"{PLUGIN}/agents/*.md"))
                 + sorted(glob.glob(f"{PLUGIN}/commands/*.md"))
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))):
        body = read_text(path)
        end = body.find("\n---", 3) if body.startswith("---") else -1
        if end == -1:
            continue
        m = re.search(r"^model:[ \t]*(\S+)", body[3:end], re.MULTILINE)
        if not m:
            continue
        rel = path.replace("\\", "/")[len(PLUGIN) + 1:]
        declaring.add(rel)
        check(f"{rel} uses a family alias, not a pinned version ({m.group(1)})",
              m.group(1) in aliases)

    orphans = sorted(declaring - assigned)
    check(f"every component declaring a model is in models.json "
          f"({len(orphans)} unassigned)", not orphans)
    for rel in orphans:
        print(f"     unassigned: {rel}")

    # Frontmatter is only half of it. The bigger drift was in prose -- a file
    # that said "dispatch `explorer` (Haiku)" carried a second copy of a fact
    # agents/explorer.md already owned, and the two diverge the moment a tier
    # moves. Components name TIERS (chore/build/think); only models.json and
    # rules/model-selection.md name families. rules/ is excluded because
    # defining the tiers is exactly its job.
    FAMILY = re.compile(r"\b(haiku|sonnet|opus|fable)\b", re.IGNORECASE)
    leaked = []
    for path in (sorted(glob.glob(f"{PLUGIN}/agents/*.md"))
                 + sorted(glob.glob(f"{PLUGIN}/commands/*.md"))
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/references/*.md"))):
        for n, line in enumerate(read_text(path).splitlines(), 1):
            if line.startswith("model:"):
                continue
            if FAMILY.search(line):
                leaked.append(f"{path.replace(chr(92), '/')}:{n}: {line.strip()[:70]}")
    check(f"no component names a model family in prose ({len(leaked)} leak(s))",
          not leaked)
    for line in leaked[:8]:
        print(f"     {line}")

# The track skill's stage table. Shape checks only -- the six stage prose
# files and their wrapper skills are later units and do not exist yet.
STAGES_JSON = f"{PLUGIN}/skills/track/stages.json"
STAGE_ORDER = ["intake", "discover", "design", "build", "verify", "ship"]
check(f"stages.json ships ({STAGES_JSON})", os.path.isfile(STAGES_JSON))
if os.path.isfile(STAGES_JSON):
    stages_text = read_text(STAGES_JSON)
    stages = json.loads(stages_text)["stages"]
    check(f"stages.json has {len(STAGE_ORDER)} rows ({len(stages)})",
          len(stages) == len(STAGE_ORDER))
    keys_ok = all(set(row) == {"id", "agent", "reference", "auto_invoke"} for row in stages)
    check("every stage row has exactly id/agent/reference/auto_invoke", keys_ok)
    ids = [row.get("id") for row in stages]
    check(f"stage ids are {STAGE_ORDER} in order ({ids})", ids == STAGE_ORDER)

    # Model tier lives only in models.json; a second copy here would drift
    # the moment a role is re-tiered. "build" is also a legitimate stage id
    # and names its reference file, so only flag it elsewhere.
    BUILD_LEGIT = re.compile(r'"id"\s*:\s*"build"|stage-build\.md')
    tier_leaks = []
    for ln in stages_text.splitlines():
        if re.search(r"\btier\b|\b(chore|think)\b", ln, re.IGNORECASE):
            tier_leaks.append(ln)
        elif re.search(r"\bbuild\b", ln, re.IGNORECASE) and not BUILD_LEGIT.search(ln):
            tier_leaks.append(ln)
    check(f"stages.json names no model tier ({len(tier_leaks)} leak(s))", not tier_leaks)

# plan-review restates both skeletons so the skill stays self-contained when it
# is handed a document the commands did not write. Restating is fine; restating
# with nothing checking it is how a skill starts telling people to write a shape
# the probe rejects.
PLAN_REVIEW = f"{PLUGIN}/skills/plan-review/SKILL.md"
check(f"plan-review ships ({PLAN_REVIEW})", os.path.isfile(PLAN_REVIEW))
if os.path.isfile(PLAN_REVIEW):
    blocks = re.findall(r"```md\n(.*?)```", read_text(PLAN_REVIEW), re.S)
    listed = [[re.split(r"\s{2,}", line[3:].strip(), maxsplit=1)[0]
               for line in b.splitlines() if line.startswith("## ")]
              for b in blocks]
    for kind, want in (("hld", design_probe.HLD_HEADINGS),
                       ("detail", design_probe.DETAIL_HEADINGS)):
        check(f"plan-review's {kind} skeleton matches the probe", want in listed)


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


for path in (WORK, MAIN, NOT_A_REPO, DETACHED, UNBORN, PROBE_DIR, PREFLIGHT_PROJECT):
    rmtree(path)

sys.exit(FAIL)
