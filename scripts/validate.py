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


def agent_tools_line(path):
    """The raw value of an agent's `tools:` frontmatter line, or None when
    there is no frontmatter or no such line."""
    text = read_text(path)
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    m = re.search(r"^tools:[ \t]*(.+)$", text[3:end], re.MULTILINE)
    return m.group(1) if m else None


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


def frontmatter_description(path):
    """The `description` frontmatter value as the model actually sees it.

    Same trick frontmatter_keys() relies on: a YAML `>`/`>-` block scalar's
    continuation lines are indented, so `^[A-Za-z][\\w-]*:` never matches them
    as a new key -- here that lets a single regex capture the description
    line plus every indented line under it, stopping at the next top-level
    key. Folded lines are joined with spaces, which is what YAML folding does
    to them; a plain quoted value just has its quotes stripped.
    """
    text = read_text(path)
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    body = text[3:end]
    m = re.search(r"^description:[ \t]*(.*)$((?:\n[ \t]+.*)*)", body, re.MULTILINE)
    if not m:
        return ""
    first, continuation = m.group(1).strip(), m.group(2)
    cont_lines = [ln.strip() for ln in continuation.splitlines() if ln.strip()]
    if first in (">", ">-", ">+", "|", "|-", "|+"):
        return " ".join(cont_lines)
    if len(first) >= 2 and first[0] == first[-1] and first[0] in "\"'":
        return first[1:-1]
    return first


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

# goal.md routes rather than implements, so it is read start to finish every
# time someone reaches for it -- and prose that outgrows a screen is prose that
# gets skimmed past the branch it was carrying. The ceiling is the number the
# design settled on (docs/design/2026-08-25-goal-command-routing-detail.md,
# Budgets); this is what stops it being a number nobody ever checks again.
GOAL = f"{PLUGIN}/skills/goal/SKILL.md"
goal_text = read_text(GOAL)
# The ceiling is on the body a human reads, not the frontmatter the move to
# skills/ requires (a `name:` field commands never carried) -- counting the
# whole file would fail this check by exactly the one line that move added,
# for a reason unrelated to the prose the budget was set against.
goal_body_start = goal_text.find("\n---", 3) + 4 if goal_text.startswith("---") else 0
goal_lines = len(goal_text[goal_body_start:].splitlines())
check(f"{GOAL} is within its 120-line ceiling ({goal_lines})", goal_lines <= 120)

skills = sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
check("at least one skill ships", bool(skills))
for path in skills:
    keys = frontmatter_keys(path)
    check(f"{path} frontmatter has name+description", bool(keys) and {"name", "description"} <= keys)


# A skill body that tells the model to invoke /cai:x, or to read a file under
# the plugin, is only as good as x and that file still existing. This is the
# check that was missing when a restructure retired eight skills: goal.md went
# on naming three of them, every other check stayed green, and the command was
# broken for anyone who ran it. A body is instructions -- a name in it that
# resolves to nothing is a 404 handed to a model mid-task.
CMD_REF = re.compile(r"/cai:([a-z][a-z0-9-]*)")
PLUGIN_PATH_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.\w+)")
# Names that resolve to something other than a directory under skills/.
KNOWN_NON_SKILL = {"setup"}


def invocable_names():
    """Everything /cai:<name> can legitimately resolve to."""
    names = {os.path.basename(os.path.dirname(p)) for p in skills}
    names |= {os.path.basename(os.path.dirname(p))
              for p in glob.glob(f"{PLUGIN}/refactoring-catalog/*/SKILL.md")}
    return names | KNOWN_NON_SKILL


ALL_INVOCABLE = invocable_names()
for path in skills:
    body = read_text(path)
    dead_cmds = sorted({m for m in CMD_REF.findall(body) if m not in ALL_INVOCABLE})
    check(f"{path} names no command that does not exist "
          f"({len(dead_cmds)}{': ' + ', '.join(dead_cmds[:3]) if dead_cmds else ''})",
          not dead_cmds)
    dead_paths = sorted({rel for rel in PLUGIN_PATH_REF.findall(body)
                         if not os.path.isfile(os.path.join(PLUGIN, rel))})
    check(f"{path} names no plugin file that does not exist "
          f"({len(dead_paths)}{': ' + ', '.join(dead_paths[:2]) if dead_paths else ''})",
          not dead_paths)

# R1: the design's target is 14 skills -- it is 16 today for two separate
# reasons. `goal` stays until someone has actually run a track end to end,
# which has not happened yet (Unit 8 decision, 2026-08-27); once it retires
# this list drops to 15. `options` is an addition rather than a leftover: the
# always-on rule it backs (rules/option-explainer.md) has to fit in 45 lines,
# and the skeleton, dimension library and worked example do not
# (docs/design/2026-08-29-option-explainer-with-eli5-high-level.md,
# Decision 2). It carries `disable-model-invocation: true`, so it costs the
# always-on budget below nothing.
SKILL_NAMES = ["build", "chore", "debug", "design", "discover", "git", "goal",
               "intake", "options", "plan-review", "quiz", "refactor", "setup",
               "ship", "track", "verify"]
skill_dirs = sorted(os.path.basename(os.path.dirname(p)) for p in skills)
check(f"skills/ holds exactly the 16 names {SKILL_NAMES} ({skill_dirs})",
      skill_dirs == SKILL_NAMES)

# The 72 generated refactoring aliases moved out of the main line into their
# own directory (see .claude-plugin/plugin.json's additive "skills" key), so
# they get the same frontmatter check plus the one property that keeps their
# descriptions out of the always-on budget while leaving them user-invocable.
CATALOG = f"{PLUGIN}/refactoring-catalog"
catalog_skills = sorted(glob.glob(f"{CATALOG}/*/SKILL.md"))
check(f"refactoring-catalog holds exactly 72 skills ({len(catalog_skills)})", len(catalog_skills) == 72)
for path in catalog_skills:
    keys = frontmatter_keys(path)
    check(f"{path} frontmatter has name+description", bool(keys) and {"name", "description"} <= keys)
    check(f"{path} disables model invocation", "disable-model-invocation: true" in read_text(path))

# commands/ is retired: a file there and a same-named skill both create the
# same slash command, and that collision already shadowed a skill once. The
# 72 aliases must not have leaked back into the main skills/ line either.
check(f"{PLUGIN}/commands is gone", not os.path.isdir(f"{PLUGIN}/commands"))
alias_slugs = {os.path.basename(os.path.dirname(p)) for p in catalog_skills}
leaked_aliases = sorted(alias_slugs & {os.path.basename(os.path.dirname(p)) for p in skills})
check(f"skills/ holds no refactoring alias ({len(leaked_aliases)} found)", not leaked_aliases)

# The always-on budget: every description a model can match on without being
# asked is sent to it in every session, whether or not that component ever
# fires. Scanned by directory shape rather than by tag, on purpose -- the
# restructure moved files between directories, and a check keyed to a
# directory would have moved with them, changing the number without changing
# what it costs. Skips anything gated by `disable-model-invocation: true`
# (the 72 catalog aliases, plus any main-line skill given the same flag),
# since those never reach the model unbidden.
#
# This is a ratchet, not the design's target. UC4's target is 4,673
# characters; measured here, this repo is not there yet, and a ratchet is
# what stops the total drifting back up while that gap is still open. Two
# things are known to still be on the table for closing it: retiring `goal`
# once a track has actually been run end to end (see the SKILL_NAMES comment
# above), and shortening the longest descriptions -- which trades against
# those same descriptions still needing to be long enough to trigger, so it
# is not done here.
ALWAYS_ON_CEILING = 5468
always_on_paths = (sorted(glob.glob(f"{PLUGIN}/agents/*.md"))
                   + sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
                   + sorted(glob.glob(f"{CATALOG}/*/SKILL.md")))
always_on_total = sum(
    len(frontmatter_description(p)) for p in always_on_paths
    if "disable-model-invocation: true" not in read_text(p))
print(f"     always-on description budget: {always_on_total} chars "
      f"(design target: 4673)")
check(f"always-on description budget does not exceed {ALWAYS_ON_CEILING} chars "
      f"({always_on_total})", always_on_total <= ALWAYS_ON_CEILING)

# `options` has to keep that flag, and the budget above is the wrong thing to
# rely on for it: dropping the flag does trip the ceiling today, but only
# because the ratchet happens to leave 17 characters of headroom. Say it
# outright instead, the way the catalog aliases already do above.
OPTIONS_SKILL = f"{PLUGIN}/skills/options/SKILL.md"
check(f"{OPTIONS_SKILL} disables model invocation",
      "disable-model-invocation: true" in read_text(OPTIONS_SKILL))

# /cai:setup copies these out to ~/.claude/rules/; an empty dir would
# make setup a silent no-op.
rules = sorted(glob.glob(f"{PLUGIN}/rules/*.md"))
check("rules ship with the plugin", bool(rules))

# Every rules/*.md file is L1: loaded into every session whether or not it
# ever fires, unlike a skill body that is only read once invoked. There was
# no check on that cost until option-explainer.md's own design set 45 as the
# ceiling (its trailing comment carries the reasoning); this is what stops a
# future edit drifting past it unnoticed the way it could before this check
# existed. Same pattern as the goal.md line-ceiling check above.
RULES_LINE_CEILING = 45
for path in rules:
    n = len(read_text(path).splitlines())
    check(f"{path} is within its {RULES_LINE_CEILING}-line ceiling ({n})", n <= RULES_LINE_CEILING)

# The root CLAUDE.md's @-imports are what makes a rule file active for anyone
# working in this checkout; nothing compared that list to rules/*.md itself,
# so a new rule file could land with no import line and every check above
# would still be green. communication.md is the one deliberate exception --
# CLAUDE.md:15-17 explains why it is not imported (response language is
# per-user, set by /cai:setup into ~/.claude/rules/, not by this repo) -- so
# it is carved out here rather than failing on it every run.
ROOT_CLAUDE = "CLAUDE.md"
KNOWN_UNIMPORTED_RULES = {"communication"}
# Pinned, because the set is an escape hatch from the check right below it:
# adding a name here silences a genuinely missing import and nothing else
# would notice. Growing it should take deleting this line, so that whoever
# does has to say why in the same edit.
check(f"{ROOT_CLAUDE} import exceptions are exactly ['communication'] "
      f"({sorted(KNOWN_UNIMPORTED_RULES)})",
      KNOWN_UNIMPORTED_RULES == {"communication"})
imported_rules = set(re.findall(r"^@plugins/cai/rules/([\w-]+)\.md$", read_text(ROOT_CLAUDE), re.MULTILINE))
rule_names = {os.path.splitext(os.path.basename(p))[0] for p in rules}
missing_imports = sorted(rule_names - imported_rules - KNOWN_UNIMPORTED_RULES)
extra_imports = sorted(imported_rules - rule_names)
check(f"{ROOT_CLAUDE} imports match rules/*.md, exceptions {sorted(KNOWN_UNIMPORTED_RULES)} "
      f"({len(missing_imports)} missing, {len(extra_imports)} extra)",
      not missing_imports and not extra_imports)
for name in missing_imports[:5]:
    print("     rules/ has it but CLAUDE.md does not import it:", name)
for name in extra_imports[:5]:
    print("     CLAUDE.md imports it but rules/ does not have it:", name)

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


REFACTORING = f"{PLUGIN}/skills/refactor"


def referenced_paths(path):
    """Sub-file paths the refactoring SKILL.md points models at, e.g. the
    reference table and the smell lookup. A path named here that does not
    exist on disk is a model told to read something that was never shipped."""
    text = read_text(path)
    return {f"{PLUGIN}{m}" for m in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}([^`\s]+)", text)}


def index_slugs(path):
    """Slugs the catalog index declares as the single source of truth for
    what /cai:<slug> and procedure-apply.md can be called with."""
    text = read_text(path)
    return set(re.findall(r"^\|\s*\d+\s*\|[^|]*\|\s*`([a-z0-9-]+)`\s*\|", text, re.MULTILINE))


def card_slugs(paths):
    """Slugs actually defined by a '### N. Name `slug`' heading in the card
    files. If the index and this ever disagree, procedure-apply.md looks
    up a slug the index promised and the card never defines."""
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
# /cai:<slug> is invoked; the reverse means a card nobody can reach.
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

# The catalog count check above (72 dirs) only counts; it does not compare
# names, so renaming a directory keeps the total at 72 and nothing notices.
# alias_slugs is the catalog-generated directory names, computed above.
missing_dirs = sorted(idx_slugs - alias_slugs)
extra_dirs = sorted(alias_slugs - idx_slugs)
check(f"refactoring-catalog dirs match catalog-index slugs "
      f"({len(missing_dirs)} missing, {len(extra_dirs)} extra)",
      not missing_dirs and not extra_dirs)
for slug in missing_dirs[:5]:
    print("     index names but no catalog dir exists:", slug)
for slug in extra_dirs[:5]:
    print("     catalog dir exists but index omits:", slug)

# gen-commands.py is never invoked by this suite, so a hand-edit to a
# generated file, or a template drift from what is committed, is invisible.
# Run it against a scratch copy of just what it reads (its own script plus
# the single source-of-truth index) so the real refactoring-catalog/ is never
# touched -- exercising the generator must not leave the tree dirty.
GEN_COMMANDS = f"{PLUGIN}/scripts/gen-commands.py"
GEN_SCRATCH = tempfile.mkdtemp(prefix="cai-gen-commands-")
os.makedirs(os.path.join(GEN_SCRATCH, "scripts"), exist_ok=True)
shutil.copy(GEN_COMMANDS, os.path.join(GEN_SCRATCH, "scripts", "gen-commands.py"))
os.makedirs(os.path.join(GEN_SCRATCH, "skills", "refactor", "references"), exist_ok=True)
shutil.copy(INDEX, os.path.join(GEN_SCRATCH, "skills", "refactor", "references", "catalog-index.md"))
gen_done = subprocess.run([sys.executable, os.path.join(GEN_SCRATCH, "scripts", "gen-commands.py")],
                          capture_output=True, text=True)
check("gen-commands.py runs cleanly against a scratch copy of the index",
      gen_done.returncode == 0)

generated = sorted(glob.glob(os.path.join(GEN_SCRATCH, "refactoring-catalog", "*", "SKILL.md")))
gen_slugs = {os.path.basename(os.path.dirname(p)) for p in generated}
check(f"gen-commands.py produces the same slugs as committed ({len(gen_slugs)})",
      gen_slugs == alias_slugs)

regen_mismatches = []
for slug in sorted(gen_slugs & alias_slugs):
    gen_text = read_text(os.path.join(GEN_SCRATCH, "refactoring-catalog", slug, "SKILL.md"))
    committed_text = read_text(os.path.join(CATALOG, slug, "SKILL.md"))
    if gen_text != committed_text:
        regen_mismatches.append(slug)
check(f"gen-commands.py output matches committed refactoring-catalog/ "
      f"({len(regen_mismatches)} mismatched)", not regen_mismatches)
for slug in regen_mismatches[:5]:
    print("     regenerating differs from committed:", slug)

shutil.rmtree(GEN_SCRATCH, ignore_errors=True)

# Check 3: the safety protocol lives in the knowledge skill only (design
# decisions #3). A component that pastes a rule verbatim instead of pointing
# back here is exactly what goes stale the day the rule changes.
#
# refactoring-detector and refactoring-surgeon retired into this skill (Unit
# 6b), and refactor-scan/plan/apply/safety-net/auto are now reference files
# under skills/refactor/references/ rather than separate agents or skills --
# those reference files are what this check watches for a pasted copy now.
proto_lines = protocol_lines(SKILL)
for path in sorted(glob.glob(f"{REFACTORING}/references/procedure-*.md")):
    # Both sides must extract the same shapes, or widening one half silently
    # guards nothing: bullets() alone would miss a pasted numbered loop step.
    with open(path, encoding="utf-8") as fh:
        candidates = {ln.strip() for ln in fh
                      if ln.strip().startswith("- ") or re.match(r"^\d+\.\s", ln.strip())}
    restated = sorted(candidates & proto_lines)
    check(f"{path} does not restate the safety protocol ({len(restated)} duplicated)", not restated)
    for line in restated[:5]:
        print("     also in refactor/SKILL.md:", line[:90])

# Unit 6b: six refactoring skills collapsed into one (skills/refactor/), and
# two single-caller agents retired into it. The rename itself is worth its
# own check, separately from the drift check above -- a stray refactor-*/
# directory left behind after the merge is exactly the kind of thing nobody
# notices until someone opens the wrong one.
check(f"{REFACTORING} exists", os.path.isdir(REFACTORING))
stray_refactor_dirs = sorted(
    d for d in glob.glob(f"{PLUGIN}/skills/refactor-*") if os.path.isdir(d))
check(f"no skills/refactor-*/ directory remains ({len(stray_refactor_dirs)} found)",
      not stray_refactor_dirs)

# The heading itself, not just the bullet shapes protocol_lines() extracts --
# a second copy that paraphrases the loop instead of pasting it verbatim
# would slip past the restatement check above but still be a second place to
# keep the protocol in sync. Matched as an actual heading line, not the
# quoted citation procedure-apply.md and others make in prose when pointing
# back at it.
protocol_heading_files = sorted(
    p for p in glob.glob(f"{REFACTORING}/**/*.md", recursive=True)
    if re.search(r"^## Non-negotiable safety protocol$", read_text(p), re.MULTILINE))
check(f"the safety protocol appears in exactly one file under {REFACTORING} "
      f"({len(protocol_heading_files)} found)", len(protocol_heading_files) == 1)

# Six, not five. `refactoring-surgeon` merged into the refactor skill because
# it executes one refactoring on one target -- sequential work with nothing to
# parallelise. `refactoring-detector` did not: procedure-scan dispatches one
# per module group, in parallel, and merging it away silently turned a
# whole-project scan sequential. Caller count was the wrong test on its own.
AGENTS = sorted(glob.glob(f"{PLUGIN}/agents/*.md"))
check(f"agents/ holds exactly 9 files ({len(AGENTS)})", len(AGENTS) == 9)

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
SETUP = f"{PLUGIN}/skills/setup/SKILL.md"
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


# A component that tells the model to run `plugins/cai/scripts/...` works only
# inside this checkout. Anyone who installed from the marketplace has the plugin
# under ~/.claude/plugins/cache/, so the command silently stops working for
# every real user -- the failure this repo is least able to notice.
for path in sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md")
                   + glob.glob(f"{CATALOG}/*/SKILL.md")):
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


def write_preflight_state(artifact_cell, design_status="done"):
    # state.md is overwritten in place, never appended to -- each case
    # replaces the whole file rather than editing one cell.
    text = ("# preflight-fixture\n\nbranch: feat/preflight-fixture\n"
            "started: 2026-08-27\n\n| stage | status | artifact | note |\n"
            "|---|---|---|---|\n| intake | done | — | |\n"
            "| discover | done | — | |\n"
            "| design | %s | %s | |\n"
            "| build | | | |\n| verify | | | |\n| ship | | | |\n"
            % (design_status, artifact_cell))
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

# A design row that names nothing is the normal state before the stage runs --
# SKILL.md creates every row empty, and the document is what the stage writes.
# These two cases used to assert the opposite, which locked in a gate that
# could never open on a fresh track: `design` was unreachable and nobody knew
# until someone ran it. Both now assert the stage is allowed to start.
write_preflight_state("—")
done = run_preflight("design")
check("preflight design [no artifact named yet] -> 0", done.returncode == 0)
check("preflight design says the stage writes it",
      "PASS artifact_named (no design document yet" in done.stdout)

# ...but naming something that is not there is still a block: that is a design
# row pointing at a document somebody moved or misspelled, not a fresh track.
write_preflight_state("docs/design/never-written-detail.md")
done = run_preflight("design")
check("preflight design [named but missing] -> 2", done.returncode == 2)
check("preflight design names artifact_exists", "FAIL artifact_exists" in done.stdout)

PREFLIGHT_NO_STATE = tempfile.mkdtemp(prefix="cai-preflight-no-state-")
done = run_preflight("design", track_dir=PREFLIGHT_NO_STATE)
check("preflight design [no state.md] -> 2", done.returncode == 2)
check("preflight design names state_md", "FAIL state_md" in done.stdout)

# design's suffix routing for the other two kinds -- only -detail.md is
# exercised above, so mapping -high-level.md or -delta.md to the wrong kind
# would go unnoticed.
with open(os.path.join(PREFLIGHT_PROJECT, "docs", "design", "widget-high-level.md"),
          "w", encoding="utf-8") as fh:
    fh.write(HLD_OK)
with open(os.path.join(PREFLIGHT_PROJECT, "docs", "design", "widget-delta.md"),
          "w", encoding="utf-8") as fh:
    fh.write(DELTA_OK)

write_preflight_state("docs/design/widget-high-level.md")
done = run_preflight("design")
check("preflight design [-high-level.md routes to hld probe] -> 0", done.returncode == 0)

write_preflight_state("docs/design/widget-delta.md")
done = run_preflight("design")
check("preflight design [-delta.md routes to delta probe] -> 0", done.returncode == 0)

done = subprocess.run([sys.executable, PREFLIGHT, "no-such-stage",
                       "--track-dir", PREFLIGHT_TRACK],
                      capture_output=True, text=True)
check("preflight unknown stage id -> 1", done.returncode == 1)

# build reads the same design row as the design check above, but only cares
# whether the artifact names a work breakdown -- so its broken fixture is
# DETAIL_OK with that one heading (and everything after it) removed.
NO_BREAKDOWN = DETAIL_OK.split("## Work breakdown")[0].replace(
    "scripts/validate.py:41", "docs/design/hld.md:1")
with open(os.path.join(PREFLIGHT_PROJECT, "docs", "design", "no-breakdown-detail.md"),
          "w", encoding="utf-8") as fh:
    fh.write(NO_BREAKDOWN)

write_preflight_state("docs/design/billing-detail.md")
done = run_preflight("build")
check("preflight build [work breakdown present] -> 0", done.returncode == 0)

write_preflight_state("docs/design/no-breakdown-detail.md")
done = run_preflight("build")
check("preflight build [no work breakdown] -> 2", done.returncode == 2)
check("preflight build names work_breakdown", "FAIL work_breakdown" in done.stdout)

# `/cai:track skip design` is supported, and it lands on this check for the
# rest of the track's life. Blocking is right -- there is no design to build
# from -- but the reason has to say so, or it reads as a broken state.md and
# leaves the person guessing that `skip build` is the way on.
write_preflight_state("—", design_status="skipped")
done = run_preflight("build")
check("preflight build [design was skipped] -> 2", done.returncode == 2)
check("preflight build says the design was skipped",
      "design was skipped" in done.stdout and "skip build too" in done.stdout)

# build reads the same design row as design() -- same two block reasons apply
# before the artifact is even resolved to a work breakdown.
write_preflight_state("—")
done = run_preflight("build")
check("preflight build [no artifact named] -> 2", done.returncode == 2)
check("preflight build names artifact_named", "FAIL artifact_named" in done.stdout)

done = run_preflight("build", track_dir=PREFLIGHT_NO_STATE)
check("preflight build [no state.md] -> 2", done.returncode == 2)
check("preflight build names state_md", "FAIL state_md" in done.stdout)

# discover only needs the intake row's status; write_preflight_state's default
# (intake: done) is the passing fixture, an empty status is the blocking one.
write_preflight_state("docs/design/billing-detail.md")
done = run_preflight("discover")
check("preflight discover [intake done] -> 0", done.returncode == 0)

with open(os.path.join(PREFLIGHT_TRACK, "state.md"), "w", encoding="utf-8") as fh:
    fh.write("# preflight-fixture\n\nbranch: feat/preflight-fixture\n"
             "started: 2026-08-27\n\n| stage | status | artifact | note |\n"
             "|---|---|---|---|\n| intake | | — | |\n| discover | | — | |\n"
             "| design | | | |\n| build | | | |\n| verify | | | |\n| ship | | | |\n")
done = run_preflight("discover")
check("preflight discover [intake status empty] -> 2", done.returncode == 2)
check("preflight discover names intake_status", "FAIL intake_status" in done.stdout)


def run_preflight_at(stage, project_dir, track_dir):
    return subprocess.run(
        [sys.executable, PREFLIGHT, stage, "--track-dir", track_dir,
         "--project-dir", project_dir],
        capture_output=True, text=True)


# intake decides whether a track may even start, so its fixtures are plain
# repos with no state.md at all -- the checks it runs never look for one.
INTAKE_MAIN = temp_repo("main")
done = run_preflight_at("intake", INTAKE_MAIN, os.path.join(INTAKE_MAIN, "track", "feature-a"))
check("preflight intake [on main] -> 2", done.returncode == 2)
check("preflight intake names not_main_branch", "FAIL not_main_branch" in done.stdout)

INTAKE_FULL = temp_repo("work")
INTAKE_FULL_ROOT = os.path.join(INTAKE_FULL, "track")
for i in range(5):
    os.makedirs(os.path.join(INTAKE_FULL_ROOT, f"f{i}"))
done = run_preflight_at("intake", INTAKE_FULL, os.path.join(INTAKE_FULL_ROOT, "f-new"))
check("preflight intake [5 active tracks] -> 2", done.returncode == 2)
check("preflight intake names active_tracks", "FAIL active_tracks" in done.stdout)

INTAKE_RESERVED = temp_repo("work")
done = run_preflight_at("intake", INTAKE_RESERVED,
                        os.path.join(INTAKE_RESERVED, "track", "current"))
check("preflight intake [reserved feature name] -> 2", done.returncode == 2)
check("preflight intake names reserved_name", "FAIL reserved_name" in done.stdout)

# The passing fixture is the one that proves done/ is excluded: 4 active
# tracks plus a done/ archive holding its own subdirectory would block at the
# 5-track ceiling if the archive were counted.
INTAKE_OK = temp_repo("work")
INTAKE_OK_ROOT = os.path.join(INTAKE_OK, "track")
for i in range(4):
    os.makedirs(os.path.join(INTAKE_OK_ROOT, f"f{i}"))
os.makedirs(os.path.join(INTAKE_OK_ROOT, "done", "archived-1"))
done = run_preflight_at("intake", INTAKE_OK, os.path.join(INTAKE_OK_ROOT, "feature-new"))
check("preflight intake [4 active + done/ archive ignored] -> 0", done.returncode == 0)

# A track that git tracks makes the working tree dirty by existing, and the
# stage that then refuses is `ship`, whose clean_tree failure says nothing
# about why. intake says so while the fix is still one line -- and says it
# without blocking, because committing your track is a legitimate choice.
check("preflight intake warns when the track is not ignored",
      "track_ignored" in done.stdout and "NOT ignored" in done.stdout)
check("preflight intake does not block on it", done.returncode == 0)

with open(os.path.join(INTAKE_OK, ".gitignore"), "w", encoding="utf-8") as fh:
    fh.write("track/\n")
done = run_preflight_at("intake", INTAKE_OK, os.path.join(INTAKE_OK_ROOT, "feature-new"))
check("preflight intake is quiet once the track is ignored",
      "track_ignored" in done.stdout and "NOT ignored" not in done.stdout)

# Regression: a bare relative --track-dir (what a caller already sitting in
# .claude/track/ passes) used to derive an empty parent, count zero active
# tracks, and let a sixth one through. Exercised with cwd set to the track
# root itself, since that is what makes the value bare in the first place.
INTAKE_BARE = temp_repo("work")
INTAKE_BARE_ROOT = os.path.join(INTAKE_BARE, "track")
for i in range(5):
    os.makedirs(os.path.join(INTAKE_BARE_ROOT, f"f{i}"))
done = subprocess.run(
    [sys.executable, os.path.abspath(PREFLIGHT), "intake", "--track-dir", "f-new",
     "--project-dir", os.path.abspath(INTAKE_BARE)],
    capture_output=True, text=True, cwd=INTAKE_BARE_ROOT)
check("preflight intake [bare relative --track-dir, 5 active tracks] -> 2",
      done.returncode == 2)
check("preflight intake bare --track-dir names active_tracks",
      "FAIL active_tracks" in done.stdout)


# verify has nothing to read from state.md -- it only asks git whether there
# is a diff to review, so its fixtures are bare repos.
VERIFY_CLEAN = temp_repo("clean-branch")
done = run_preflight_at("verify", VERIFY_CLEAN, os.path.join(VERIFY_CLEAN, "track"))
check("preflight verify [clean tree, no base diff] -> 2", done.returncode == 2)
check("preflight verify names has_changes", "FAIL has_changes" in done.stdout)

VERIFY_DIRTY = temp_repo("dirty-branch")
with open(os.path.join(VERIFY_DIRTY, "note.txt"), "w", encoding="utf-8") as fh:
    fh.write("scratch\n")
done = run_preflight_at("verify", VERIFY_DIRTY, os.path.join(VERIFY_DIRTY, "track"))
check("preflight verify [uncommitted changes] -> 0", done.returncode == 0)


def write_ship_state(track_dir, verify_status):
    os.makedirs(track_dir, exist_ok=True)
    with open(os.path.join(track_dir, "state.md"), "w", encoding="utf-8") as fh:
        fh.write("# preflight-fixture\n\nbranch: feat/preflight-fixture\n"
                  "started: 2026-08-27\n\n| stage | status | artifact | note |\n"
                  "|---|---|---|---|\n| intake | done | — | |\n"
                  "| discover | done | — | |\n| design | done | — | |\n"
                  "| build | done | — | |\n| verify | %s | — | |\n"
                  "| ship | | | |\n" % verify_status)


# ship's own repo fixtures live outside the track directory it reads, so
# writing state.md never touches the git status this check is also reading.
SHIP_DIRTY = temp_repo("ship-dirty")
SHIP_DIRTY_TRACK = tempfile.mkdtemp(prefix="cai-ship-track-")
write_ship_state(SHIP_DIRTY_TRACK, "done")
with open(os.path.join(SHIP_DIRTY, "note.txt"), "w", encoding="utf-8") as fh:
    fh.write("scratch\n")
done = run_preflight_at("ship", SHIP_DIRTY, SHIP_DIRTY_TRACK)
check("preflight ship [dirty tree] -> 2", done.returncode == 2)
check("preflight ship names clean_tree", "FAIL clean_tree" in done.stdout)

SHIP_CLEAN = temp_repo("ship-clean")
SHIP_CLEAN_TRACK = tempfile.mkdtemp(prefix="cai-ship-track-")
write_ship_state(SHIP_CLEAN_TRACK, "done")
done = run_preflight_at("ship", SHIP_CLEAN, SHIP_CLEAN_TRACK)
check("preflight ship [clean tree, verify done, not main] -> 0", done.returncode == 0)

# ship's other two reasons: the fixtures above always fill verify's status and
# always run on a feature branch, so only clean_tree was ever exercised.
SHIP_NO_VERIFY = temp_repo("ship-no-verify")
SHIP_NO_VERIFY_TRACK = tempfile.mkdtemp(prefix="cai-ship-track-")
write_ship_state(SHIP_NO_VERIFY_TRACK, "")
done = run_preflight_at("ship", SHIP_NO_VERIFY, SHIP_NO_VERIFY_TRACK)
check("preflight ship [verify status empty] -> 2", done.returncode == 2)
check("preflight ship names verify_status", "FAIL verify_status" in done.stdout)

SHIP_ON_MAIN = temp_repo("main")
SHIP_ON_MAIN_TRACK = tempfile.mkdtemp(prefix="cai-ship-track-")
write_ship_state(SHIP_ON_MAIN_TRACK, "done")
done = run_preflight_at("ship", SHIP_ON_MAIN, SHIP_ON_MAIN_TRACK)
check("preflight ship [on main branch] -> 2", done.returncode == 2)
check("preflight ship names not_main_branch", "FAIL not_main_branch" in done.stdout)

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

    # The other direction from the orphan check below: a role assignment that
    # names a file nobody shipped (or already deleted, e.g. a retired agent)
    # is stale the moment it's written -- exactly the failure mode retiring
    # refactoring-detector/refactoring-surgeon into skills/refactor/ could
    # leave behind if their models.json rows were not removed with them.
    dangling = sorted(p for p in assigned if not os.path.isfile(f"{PLUGIN}/{p}"))
    check(f"models.json names no assignment whose file is missing ({len(dangling)} dangling)",
          not dangling)
    for p in dangling[:5]:
        print("     dangling assignment:", p)

    # Anything that declares a model must be in the table. Without this, a new
    # agent silently keeps whatever tier its author typed and re-tiering a role
    # quietly skips it.
    declaring = set()
    for path in (sorted(glob.glob(f"{PLUGIN}/agents/*.md"))
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
                 + sorted(glob.glob(f"{CATALOG}/*/SKILL.md"))):
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
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/SKILL.md"))
                 + sorted(glob.glob(f"{PLUGIN}/skills/*/references/*.md"))
                 + sorted(glob.glob(f"{CATALOG}/*/SKILL.md"))):
        for n, line in enumerate(read_text(path).splitlines(), 1):
            if line.startswith("model:"):
                continue
            if FAMILY.search(line):
                leaked.append(f"{path.replace(chr(92), '/')}:{n}: {line.strip()[:70]}")
    check(f"no component names a model family in prose ({len(leaked)} leak(s))",
          not leaked)
    for line in leaked[:8]:
        print(f"     {line}")

# What each stage's agent must be granted, checked against its `tools:`
# frontmatter rather than its name -- picking an agent by tier alone is
# exactly what pointed design at architect (can't Write) and ship at
# explorer (can't run git) before designer/verifier/shipper existed.
STAGE_TOOL_NEEDS = {
    "design": ("Write", lambda tools: re.search(r"\bWrite\b", tools) is not None),
    "verify": ("a test command", lambda tools: re.search(
        r"pytest|go test|npm test|unittest", tools, re.IGNORECASE) is not None),
    "ship": ("a git command", lambda tools: re.search(r"\bgit\b", tools, re.IGNORECASE) is not None),
}

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

    # Unit 6a: the six stage reference files and their thin wrapper skills.
    # A `reference` path that resolves to nothing leaves the subagent track
    # dispatches with a Read call that 404s mid-stage.
    for row in stages:
        ref = f"{PLUGIN}/skills/track/{row['reference']}"
        check(f"stage {row['id']} reference exists ({ref})", os.path.isfile(ref))

        wrapper = f"{PLUGIN}/skills/{row['id']}/SKILL.md"
        check(f"stage {row['id']} has a wrapper skill ({wrapper})", os.path.isfile(wrapper))
        if not os.path.isfile(wrapper):
            continue

        wrapper_text = read_text(wrapper)
        has_flag = "disable-model-invocation: true" in wrapper_text
        # auto_invoke says whether this skill may start the stage on its own;
        # a stage that writes things (auto_invoke: false) must carry the flag
        # or a matching description starts it unbidden, and a stage that only
        # reads (auto_invoke: true) must not carry it or the capability it
        # exists to keep -- firing on "review this diff" -- regresses silently.
        if row["auto_invoke"]:
            check(f"{wrapper} has no disable-model-invocation (auto_invoke: true)", not has_flag)
        else:
            check(f"{wrapper} disables model invocation (auto_invoke: false)", has_flag)

        wrapper_end = wrapper_text.find("\n---", 3) + 4 if wrapper_text.startswith("---") else 0
        wrapper_lines = len(wrapper_text[wrapper_end:].splitlines())
        check(f"{wrapper} body is under 25 lines ({wrapper_lines})", wrapper_lines < 25)

    # The original mis-assignment picked a stage's agent by tier alone --
    # design pointed at architect (Read-only), ship at explorer (no git) --
    # and both named agents that could not do the stage's job. Assert the
    # agent exists, is tiered, and is actually granted what the stage needs,
    # so a future re-assignment by tier alone fails here instead of at
    # someone's runtime.
    for row in stages:
        agent_name = row["agent"]
        agent_path = f"{PLUGIN}/agents/{agent_name}.md"
        check(f"stage {row['id']}'s agent ({agent_name}) exists", os.path.isfile(agent_path))

        rel_agent = f"agents/{agent_name}.md"
        check(f"stage {row['id']}'s agent ({agent_name}) has a models.json assignment",
              rel_agent in assigned)

        need = STAGE_TOOL_NEEDS.get(row["id"])
        if need is None or not os.path.isfile(agent_path):
            continue
        label, predicate = need
        tools_line = agent_tools_line(agent_path)
        check(f"stage {row['id']}'s agent ({agent_name}) is granted {label}",
              tools_line is not None and predicate(tools_line))

# track/SKILL.md routes rather than implements, so it is read start to finish
# every time someone reaches for it -- same reasoning and the same 120-line
# ceiling as goal.md above.
TRACK_SKILL = f"{PLUGIN}/skills/track/SKILL.md"
if os.path.isfile(TRACK_SKILL):
    track_text = read_text(TRACK_SKILL)
    track_body_start = track_text.find("\n---", 3) + 4 if track_text.startswith("---") else 0
    track_lines = len(track_text[track_body_start:].splitlines())
    check(f"{TRACK_SKILL} is within its 120-line ceiling ({track_lines})", track_lines <= 120)

# track_state.py resolves .claude/track/current -> state.md from files alone,
# with no model call -- UC1's acceptance test ("a fresh session resumes from
# files alone") is this loop. Every fixture lives under one temp_repo() (git
# is irrelevant to the script, but the helper is the repo's existing way to
# get a throwaway directory that gets cleaned up below).
TRACK_STATE = f"{PLUGIN}/scripts/track_state.py"
TRACK_FIXTURE_ROOT = temp_repo("track-state-fixture")

# Same six rows as the state.md example in the track spec: one stage done
# with an artifact, one done with a note, one skipped with a reason, one
# in-progress, two not started -- so "next" lands on the in-progress row
# rather than skating past it.
FULL_ROWS = [
    ("intake", "done", "docs/design/2026-08-27-billing-export-intake.md", ""),
    ("discover", "done", "—", "three unknowns closed"),
    ("design", "skipped", "—", "reusing the existing spec"),
    ("build", "in-progress", "—", "unit 3 of 5"),
    ("verify", "", "", ""),
    ("ship", "", "", ""),
]


def write_track_state(track_dir, rows):
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-27", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    os.makedirs(track_dir, exist_ok=True)
    with open(os.path.join(track_dir, "state.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def make_track_root(name):
    root = os.path.join(TRACK_FIXTURE_ROOT, name)
    os.makedirs(root, exist_ok=True)
    return root


def write_current(root, feature):
    with open(os.path.join(root, "current"), "w", encoding="utf-8") as fh:
        fh.write(feature)


def valid_track_root():
    root = make_track_root("valid")
    write_track_state(os.path.join(root, "billing-export"), FULL_ROWS)
    write_current(root, "billing-export")
    return root


def missing_dir_track_root():
    root = make_track_root("missing-dir")
    write_current(root, "ghost-feature")  # names a dir that is never created
    return root


def row_mismatch_track_root():
    root = make_track_root("row-mismatch")
    write_track_state(os.path.join(root, "short-track"), FULL_ROWS[:5])  # missing "ship"
    write_current(root, "short-track")
    return root


def no_current_track_root():
    return make_track_root("no-current")  # `current` is never written


TRACK_STATE_CASES = [
    # (label, root-builder, expected exit, substring the output must name)
    ("valid track resolves the next stage", valid_track_root, 0, "next: build"),
    ("current names a missing directory", missing_dir_track_root, 2, "ghost-feature"),
    ("state.md row count disagrees with stages.json", row_mismatch_track_root, 2, "5 stage row"),
    ("no current at all", no_current_track_root, 2, "no active track"),
]

for label, build_root, expected, needle in TRACK_STATE_CASES:
    done = subprocess.run(
        [sys.executable, TRACK_STATE, "status", "--track-root", build_root()],
        capture_output=True, text=True)
    check(f"track_state status [{label}] -> {expected}", done.returncode == expected)
    check(f"track_state status [{label}] names it", needle in done.stdout + done.stderr)

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


for path in (WORK, MAIN, NOT_A_REPO, DETACHED, UNBORN, PROBE_DIR, PREFLIGHT_PROJECT,
             TRACK_FIXTURE_ROOT):
    rmtree(path)

sys.exit(FAIL)
