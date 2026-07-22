#!/usr/bin/env python3
"""Validate marketplace/plugin manifests, component frontmatter, and guard
behavior. Zero deps."""
import glob
import json
import os
import re
import subprocess
import sys

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

GUARD = f"{PLUGIN}/scripts/bash_guard.py"
DISPATCHER = f"{PLUGIN}/hooks/run-guard.cmd"

CASES = [
    ("git push --force origin main", 2),
    ("git push -f origin main", 2),
    ("git push --force-with-lease origin main", 0),
    ("git reset --hard HEAD~1", 2),
    ("git commit --no-verify -m x", 2),
    ("rm -rf build/", 2),
    ("git status", 0),
]


def run(argv, cmd):
    return subprocess.run(
        argv, input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True, text=True,
    ).returncode


for cmd, expected in CASES:
    check(f"guard [{cmd}] -> {expected}", run([sys.executable, GUARD], cmd) == expected)

# The dispatcher is what hooks.json actually invokes. Exercise the branch this
# platform would take, so a broken interpreter lookup or a swallowed exit code
# fails here instead of silently disarming the guard.
dispatch = ["cmd", "/c", DISPATCHER.replace("/", "\\")] if os.name == "nt" else ["sh", DISPATCHER]
for cmd, expected in [("git reset --hard HEAD~1", 2), ("git status", 0)]:
    check(f"dispatcher [{cmd}] -> {expected}", run(dispatch, cmd) == expected)

sys.exit(FAIL)
