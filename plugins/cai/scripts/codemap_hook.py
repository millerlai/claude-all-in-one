#!/usr/bin/env python3
"""SubagentStart hook: hands a read-side agent the codemap state line when the
index is fresh, so a dispatch outside the track starts from the index too.

Reads one hook JSON on stdin. Prints the additionalContext JSON only when the
agent is one whose definition reads the line and `status` says `fresh`;
otherwise prints nothing. Always exits 0: no line only means the agent reads
the code as it would without an index.

Runs `status` alone, never `update`: a model starts most of these dispatches,
and only a person's command or a track's dispatch writes the index
(codemap-brief.md). After an edit the index is `stale` and nothing is added."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_cli  # noqa: E402
import codemap_index  # noqa: E402

# The plugin-scoped form only: SubagentStart carries the resolved agent_type,
# and a bare `explorer` is some other plugin's or the project's own agent.
READERS = frozenset({"cai:explorer", "cai:architect"})


def context_line(payload):
    """The state line to add for this SubagentStart payload, or None."""
    if not isinstance(payload, dict) or payload.get("agent_type") not in READERS:
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    status = codemap_index.status(codemap_cli._top(cwd))
    if status.word != "fresh":
        return None
    return codemap_index.state_line(status)


def main():
    try:
        # Bytes, so the console code page never decides what a path says.
        line = context_line(json.loads(sys.stdin.buffer.read()))
    except Exception:  # noqa: BLE001 -- a hook that fails must not touch the dispatch
        return 0
    if line:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": line,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
