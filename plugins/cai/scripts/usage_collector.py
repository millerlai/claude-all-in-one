#!/usr/bin/env python3
"""Reads a session's transcripts, dedupes by requestId, aggregates token
usage per model. Zero deps.

`ledger.append()` calls `collect()` once per attempt to answer "which
models, how many tokens, in this session since the last record". The two
things that make this correct rather than merely plausible:

  - requestId dedup. One API response can land on several transcript lines,
    each carrying its own copy of `message.usage`. Not deduping inflates the
    count with no error to notice it by (measured 5x on a real subagent
    transcript) -- so a request without a requestId is dropped and noted in
    `problems`, never guessed at.
  - the two output columns are always dict, never anything else. A source
    this cannot read becomes an empty dict plus a reason in `problems`, not
    a zero -- zero would claim "no usage happened", which is a fact this
    module is not in a position to assert.

It imports nothing from this repo, on purpose, matching ledger.py:15-19: it
is a leaf, only ledger.py imports it.

Bad-line tolerance and UTF-8 reading are copied from ledger.py:216-231
(Claude Code may still be appending to the transcript this module is
reading).
"""
import datetime
import json
import os
import re

# Token keys (N2a). Three are verbatim `message.usage` fields; the two
# ephemeral_* keys are not -- they are the split of message.usage's
# combined `cache_creation_input_tokens`, read from the nested
# message.usage.cache_creation.{ephemeral_1h,ephemeral_5m}_input_tokens
# instead. The combined field is not carried: cache writes have two
# different rates (1.25x for a 5-minute TTL write, 2x for a 1-hour TTL
# write, per https://platform.claude.com/docs/en/about-claude/pricing), so a
# merged total cannot be priced correctly and recording it too would just be
# a redundant 4096-byte-budget cost -- see _resolve_ephemeral().
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
             "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens")

CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
CENTRAL_LEDGER_ENV = "CAI_USAGE_LEDGER"
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"


def config_root():
    return os.environ.get(CONFIG_DIR_ENV) or os.path.expanduser("~/.claude")


def central_ledger_path():
    override = os.environ.get(CENTRAL_LEDGER_ENV)
    if override:
        return override
    return os.path.join(config_root(), "cai", "usage.jsonl")


def data_start_path():
    """Always the same-directory sibling of central_ledger_path() (D14), so
    one env var moves both files together."""
    return os.path.join(os.path.dirname(central_ledger_path()), "usage-start.txt")


def session_id_from_env():
    """`CLAUDE_CODE_SESSION_ID` is undocumented (C21) -- absent means the
    caller gets None and decides what that means, not an exception."""
    return os.environ.get(SESSION_ID_ENV) or None


def encoded_project_dir(cwd):
    """`~/.claude/projects/` directory name for `cwd`: every non-alphanumeric
    character becomes `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def _projects_root():
    return os.path.join(config_root(), "projects")


def session_transcript(projects_root, cwd, session_id):
    path = os.path.join(projects_root, encoded_project_dir(cwd), session_id + ".jsonl")
    return path if os.path.isfile(path) else None


def _subagents_dir(projects_root, cwd, session_id):
    return os.path.join(projects_root, encoded_project_dir(cwd), session_id, "subagents")


def subagent_transcripts(projects_root, cwd, session_id, since):
    """Subagent transcript files new in the window, by file mtime -- a cheap
    pre-filter so a long-lived session does not reopen every subagent it
    ever ran. `_read_window()` still filters each line by its own
    `timestamp` for the millisecond precision the window boundary needs
    (D4); this is only which files are worth opening at all.

    Only `since` gates here, not `until` (Major-1): a file's mtime is when
    it was last written, and content is never dated before that, so
    `mtime <= since` safely means "nothing in here can be new enough".
    `mtime > until` is not safe the same way -- disk flush, antivirus, or a
    synced home directory can all leave a file's mtime after a line whose
    own `timestamp` is still inside the window, and excluding the file here
    would drop that line with no future window ever able to see it again.
    `_read_window()`'s per-line `timestamp` check is what enforces `until`."""
    directory = _subagents_dir(projects_root, cwd, session_id)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []

    since_ms = _safe_parse_ms(since) if since else None
    out = []
    for name in names:
        if not (name.startswith("agent-") and name.endswith(".jsonl")):
            continue
        path = os.path.join(directory, name)
        try:
            mtime_ms = int(os.path.getmtime(path) * 1000)
        except OSError:
            continue
        if since_ms is not None and mtime_ms <= since_ms:
            continue
        out.append(path)
    return out


def _parse_ms(text):
    """Millisecond-precision UTC ISO 8601 string (`...Z`) to epoch ms."""
    value = text[:-1] if text.endswith("Z") else text
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def _safe_parse_ms(text):
    try:
        return _parse_ms(text)
    except (ValueError, TypeError):
        return None


def _valid_usage(usage):
    """`usage` has the three flat token keys, each a non-negative int. `bool`
    is excluded even though it is technically an int subclass -- a token
    count is never actually a bool. The two ephemeral_* keys are not flat
    `usage` fields (see TOKEN_KEYS) -- _resolve_ephemeral() validates those,
    reading the nested cache_creation object instead."""
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
        value = usage.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    return True


def _resolve_ephemeral(usage):
    """message.usage.cache_creation.{ephemeral_1h,ephemeral_5m}_input_tokens
    -> (ephemeral_1h, ephemeral_5m, problem). `problem` is None unless the
    split cannot be trusted, in which case both counts are None and the
    caller must not guess a TTL for the untracked tokens: measured lossless
    (ephemeral_1h + ephemeral_5m == cache_creation_input_tokens, every time)
    across 9,013 real usage objects in 40 session transcripts, but that is
    an observation, not a guarantee -- this project already relearned that
    once (Major-1)."""
    creation = usage.get("cache_creation")
    if isinstance(creation, dict):
        h1 = creation.get("ephemeral_1h_input_tokens")
        m5 = creation.get("ephemeral_5m_input_tokens")
        if (isinstance(h1, int) and not isinstance(h1, bool) and h1 >= 0
                and isinstance(m5, int) and not isinstance(m5, bool) and m5 >= 0):
            return h1, m5, None

    # cache_creation is missing or malformed. If the combined total the old
    # schema used is zero (or absent), there is nothing to lose by treating
    # both TTL buckets as zero rather than flagging a problem over nothing.
    combined = usage.get("cache_creation_input_tokens")
    if isinstance(combined, int) and not isinstance(combined, bool) and combined > 0:
        return None, None, (
            "%d cache_creation_input_tokens cannot be split into TTL buckets: "
            "message.usage.cache_creation is missing or malformed" % combined)
    return 0, 0, None


def _read_window(path, since_ms, until_ms, problems):
    """Raw JSON-line strings from `path` whose top-level `timestamp` falls in
    (since_ms, until_ms] -- window is left-open, right-closed (glossary:
    window). OSError and unparseable lines are swallowed, per
    ledger.py:216-231: reading tolerates a file Claude Code may still be
    appending to, and notes why in `problems` rather than raising."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        problems.append("cannot read %s: %s" % (path, exc))
        return []

    out = []
    for number, text in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        text = text.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except ValueError:
            problems.append("unparseable line %d in %s" % (number, path))
            continue
        if not isinstance(row, dict) or row.get("type") != "assistant":
            continue
        timestamp = row.get("timestamp")
        ts_ms = _safe_parse_ms(timestamp) if timestamp else None
        if ts_ms is None:
            problems.append("missing or unparseable timestamp in %s line %d" % (path, number))
            continue
        if since_ms is not None and ts_ms <= since_ms:
            continue
        if ts_ms > until_ms:
            continue
        out.append(text)
    return out


def _aggregate_with_problems(line_iter, source, problems):
    """Dedup by requestId, sum the five token keys per model. Every anomaly
    (bad JSON, missing requestId, missing/malformed message.usage, an
    unsplittable cache_creation) is skipped and named in `problems`, tagged
    with `source` and a line number -- R1's "each one names which
    column"."""
    seen = set()
    totals = {}
    for number, text in enumerate(line_iter, 1):
        text = text.strip() if isinstance(text, str) else text
        if not text:
            continue
        try:
            row = json.loads(text)
        except ValueError:
            problems.append("unparseable line %d in %s" % (number, source))
            continue
        if not isinstance(row, dict) or row.get("type") != "assistant":
            continue

        request_id = row.get("requestId")
        if not request_id:
            problems.append("missing requestId in %s line %d" % (source, number))
            continue
        if request_id in seen:
            continue

        message = row.get("message")
        message = message if isinstance(message, dict) else {}
        model = message.get("model")
        usage = message.get("usage")
        if not model or not isinstance(usage, dict) or not _valid_usage(usage):
            problems.append("missing or malformed message.model/message.usage "
                            "in %s line %d" % (source, number))
            continue

        ephemeral_1h, ephemeral_5m, ephemeral_problem = _resolve_ephemeral(usage)
        if ephemeral_problem:
            problems.append("%s in %s line %d" % (ephemeral_problem, source, number))
            continue

        seen.add(request_id)
        bucket = totals.setdefault(model, {key: 0 for key in TOKEN_KEYS})
        bucket["input_tokens"] += usage["input_tokens"]
        bucket["output_tokens"] += usage["output_tokens"]
        bucket["cache_read_input_tokens"] += usage["cache_read_input_tokens"]
        bucket["ephemeral_1h_input_tokens"] += ephemeral_1h
        bucket["ephemeral_5m_input_tokens"] += ephemeral_5m
    return totals


def aggregate(line_iter):
    """Same job as `_aggregate_with_problems()`, for a caller that only
    wants the totals -- `collect()` is the one that keeps the reasons."""
    return _aggregate_with_problems(list(line_iter), "<stream>", [])


def collect(session_id, cwd, since, until, projects_root=None):
    """Per-model token totals for `cwd`'s session `session_id`, windowed to
    (since, until]. Returns (orchestration, agents, problems): the first two
    are always dict -- empty means "nothing to report", which is either
    "genuinely no usage" (problems empty) or "could not tell" (problems
    non-empty), never a fabricated zero (R1)."""
    problems = []
    root = projects_root or _projects_root()
    since_ms = _safe_parse_ms(since) if since else None
    until_ms = _safe_parse_ms(until)
    if until_ms is None:
        problems.append("cannot parse until=%r" % (until,))
        return {}, {}, problems

    path = session_transcript(root, cwd, session_id)
    if path is None:
        problems.append("no session transcript for session %s under %s"
                        % (session_id, root))
        orchestration = {}
    else:
        lines = _read_window(path, since_ms, until_ms, problems)
        orchestration = _aggregate_with_problems(lines, path, problems)

    sub_paths = subagent_transcripts(root, cwd, session_id, since)
    agent_lines = []
    for sub_path in sub_paths:
        agent_lines.extend(_read_window(sub_path, since_ms, until_ms, problems))
    agents = _aggregate_with_problems(agent_lines, "subagents", problems)

    return orchestration, agents, problems
