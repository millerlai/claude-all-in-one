#!/usr/bin/env python3
"""Validate marketplace/plugin manifests and guard behavior. Zero deps."""
import json
import subprocess
import sys

FAIL = 0


def check(label, cond):
    global FAIL
    print(("PASS" if cond else "FAIL"), label)
    if not cond:
        FAIL = 1


mp = json.load(open(".claude-plugin/marketplace.json"))
check("marketplace has name/owner/plugins", all(k in mp for k in ("name", "owner", "plugins")))

for entry in mp["plugins"]:
    src = entry["source"]
    manifest = f"{src}/.claude-plugin/plugin.json"
    pl = json.load(open(manifest))
    check(f"{manifest} has name/version", "name" in pl and "version" in pl)
    check(f"names match ({entry['name']})", pl["name"] == entry["name"])

json.load(open("plugins/ml-workflow/hooks/hooks.json"))
print("PASS hooks.json is valid JSON")

CASES = [
    ("git push --force origin main", 2),
    ("git push -f origin main", 2),
    ("git push --force-with-lease origin main", 0),
    ("git reset --hard HEAD~1", 2),
    ("git commit --no-verify -m x", 2),
    ("rm -rf build/", 2),
    ("git status", 0),
]
for cmd, expected in CASES:
    r = subprocess.run(
        [sys.executable, "plugins/ml-workflow/scripts/bash_guard.py"],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True, text=True,
    )
    check(f"guard [{cmd}] -> {expected}", r.returncode == expected)

sys.exit(FAIL)
