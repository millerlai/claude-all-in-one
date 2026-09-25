---
name: viewer
description: Open the local Agent Viewer web page, showing every running Claude Code and Codex session and which ones need you. Usage: /cai:viewer [stop]
model: haiku
disable-model-invocation: true
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/viewer.py` and relay its output.

- Default run: no arguments. Starts (or reports) the viewer and prints its URL.
- `stop`: closes the running viewer.
- Any other argument: explain the usage above and stop without running the script.

Relay the line that starts `Agent Viewer: http://127.0.0.1:` exactly as
printed — do not translate or reword it. Relay every other stdout line in the
user's own language.

If the script exits non-zero, quote its `error:` line and stop. Never retry
it and never try to kill any process yourself.
