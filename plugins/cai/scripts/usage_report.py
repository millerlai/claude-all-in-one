#!/usr/bin/env python3
"""Turns ledger token counts into equivalent API spend.

The price-table half (unit 5 of the work breakdown) is `load_price_table()`
and `resolve_price()`. The three query functions -- `track_report()`,
`range_report()`, `data_start_date()` -- are unit 6, plus the CLI that
`/cai:usage` (unit 7) will shell out to.

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
`price table` and `usage_report.py` sections, and D9/D10/D11/D12.

Usage:  usage_report.py track --track-dir DIR
        usage_report.py range --days N
        usage_report.py metrics --track-dir DIR
        usage_report.py metrics --days N
Exit:   always 0 -- a query answering "no data" is not a failure (D9/D10).
"""
import argparse
import datetime
import json
import os
import sys

import ledger
import usage_collector

RATE_KEYS = usage_collector.TOKEN_KEYS

# UC6/D9: stated once in each report's header, next to the "spend" column's
# meaning -- a subscription does not bill per token, so a reader must not be
# able to see a dollar figure without knowing that. It is not repeated on
# every row: that buries the numbers it exists to explain (coordinator
# correction, 2026-08-30).
CAVEAT = "equivalent API spend (subscription, not billed)"

_SHIPPED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              os.pardir, "prices.json")


def _override_path():
    return os.path.join(usage_collector.config_root(), "cai", "prices.json")


def _valid_rates(rates):
    """A price entry must carry all five RATE_KEYS as non-negative numbers --
    a partial entry would let a lookup silently price only some of a
    model's token kinds."""
    if not isinstance(rates, dict):
        return False
    for key in RATE_KEYS:
        value = rates.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            return False
    return True


def _read_table_file(path):
    """(models dict, aliases dict, error string or None). A missing file is
    not an error -- there is simply nothing to merge; a present but broken
    file is, and is reported rather than silently ignored (D12: a bad
    override must not turn the whole table unpriced)."""
    if not path or not os.path.isfile(path):
        return {}, {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return {}, {}, "%s: cannot read or parse (%s)" % (path, exc)

    if not isinstance(data, dict):
        return {}, {}, "%s: expected a JSON object, got %s" % (path, type(data).__name__)

    models = data.get("models", {})
    if not isinstance(models, dict):
        return {}, {}, "%s: 'models' must be an object" % (path,)

    clean_models = {}
    for model_id, rates in models.items():
        if _valid_rates(rates):
            clean_models[model_id] = {key: rates[key] for key in RATE_KEYS}
        else:
            return {}, {}, ("%s: model %r has a malformed or incomplete price entry"
                            % (path, model_id))

    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}

    return clean_models, aliases, None


def load_price_table(path=None):
    """Shipped price table (D12), merged with the user's override at
    `<config root>/cai/prices.json` one model at a time -- an identifier the
    override does not name keeps its shipped rate; a broken override falls
    back to the shipped table entirely rather than pricing nothing.

    `path` overrides the shipped file's location; the override file's
    location is always `usage_collector.config_root()`-derived, never
    overridable by a caller (there is only ever one of it)."""
    shipped_path = path or _SHIPPED_PATH
    shipped_models, aliases, shipped_error = _read_table_file(shipped_path)
    shipped_version = None
    if shipped_error is None and os.path.isfile(shipped_path):
        try:
            with open(shipped_path, encoding="utf-8") as fh:
                shipped_version = json.load(fh).get("version")
        except (OSError, ValueError):
            shipped_version = None

    override_models, _override_aliases, override_error = _read_table_file(_override_path())

    models = dict(shipped_models)
    override_count = 0
    if override_error is None:
        for model_id, rates in override_models.items():
            models[model_id] = rates
            override_count += 1

    return {
        "version": shipped_version or "unknown",
        "models": models,
        "aliases": aliases,
        "override_count": override_count,
        "override_error": override_error,
        "shipped_error": shipped_error,
    }


def resolve_price(model_id, price_table):
    """The five-key rate dict for `model_id`, or `None` if it is not in the
    table -- unpriced, never a fabricated 0 (UC7). Alias resolution is a
    lookup against `price_table["aliases"]`, not a prefix match: which alias
    points at which full identifier is data, not a rule."""
    resolved_id = price_table.get("aliases", {}).get(model_id, model_id)
    rates = price_table.get("models", {}).get(resolved_id)
    return dict(rates) if rates is not None else None


NO_DATA = "—"  # em dash, matches ledger.py's NO_ARTIFACT sentinel style


# --- shared aggregation: one record at a time, into one running summary ----

def _money(amount):
    """`amount` in USD. The caveat (UC6/D9) is stated once in the report's
    header, not glued onto every number -- repeating it on every row buries
    the numbers it is supposed to help read (coordinator correction,
    2026-08-30)."""
    return "$%.4f" % amount


def _bucket_tokens(bucket, collapsed):
    """Total token count in one usage bucket. A collapsed bucket (D5's
    fourth `_fit` step) is already the five-key totals themselves, not
    per-model; an ordinary bucket is per-model, so it sums across models
    first."""
    if not bucket:
        return 0
    if collapsed:
        return sum(bucket.get(key, 0) for key in RATE_KEYS)
    return sum(sum(model_tokens.get(key, 0) for key in RATE_KEYS)
              for model_tokens in bucket.values())


def _bucket_models(bucket, collapsed):
    """The distinct model identifiers in one bucket -- empty for a collapsed
    bucket, because collapsing is exactly the step that threw the per-model
    identifiers away (Errors: 'this record only has a total')."""
    if collapsed or not bucket:
        return set()
    return set(bucket.keys())


def _price_bucket(bucket, price_table):
    """(spend, unpriced_tokens, unpriced_model_ids) for one per-model usage
    bucket. Priced tokens add to spend; a model `resolve_price()` cannot
    find adds to unpriced_tokens instead -- never both, and never folded
    into spend as a fabricated 0 (UC7). Collapsed buckets never reach this
    function -- see `_accumulate()`: a collapsed bucket has no model
    identifier left to look a price up by at all, which is a different fact
    from "the price table doesn't have this model" and gets its own counter
    (coordinator correction, 2026-08-30)."""
    spend = 0.0
    unpriced_tokens = 0
    unpriced_models = set()
    for model_id, tokens in bucket.items():
        rates = resolve_price(model_id, price_table)
        if rates is None:
            unpriced_tokens += sum(tokens.get(key, 0) for key in RATE_KEYS)
            unpriced_models.add(model_id)
        else:
            for key in RATE_KEYS:
                spend += tokens.get(key, 0) * rates.get(key, 0) / 1000000.0
    return spend, unpriced_tokens, unpriced_models


def _new_summary():
    return {"attempts": 0, "models": set(), "orchestration_tokens": 0,
            "agent_tokens": 0, "spend": 0.0, "unpriced_tokens": 0,
            "unpriced_models": set(), "uncovered": 0, "collapsed_records": 0,
            "collapsed_tokens": 0}


def _merge_into(total, summary):
    total["attempts"] += summary["attempts"]
    total["models"] |= summary["models"]
    total["orchestration_tokens"] += summary["orchestration_tokens"]
    total["agent_tokens"] += summary["agent_tokens"]
    total["spend"] += summary["spend"]
    total["unpriced_tokens"] += summary["unpriced_tokens"]
    total["unpriced_models"] |= summary["unpriced_models"]
    total["uncovered"] += summary["uncovered"]
    total["collapsed_records"] += summary["collapsed_records"]
    total["collapsed_tokens"] += summary["collapsed_tokens"]


def _accumulate(summary, record, price_table):
    """Folds one ledger record into `summary`. Every record counts as an
    attempt (UC5: retries -- `failed`/`blocked` -- are attempts too, and this
    is the same `ledger.records()` count the retry cap itself uses, not a
    second counting scheme). A record with neither `orchestration` nor
    `agents` present at all predates this feature (D11): it is marked
    uncovered and contributes no tokens, rather than the 0 a present-but-
    empty bucket would mean -- `track_report()`/`range_report()` read
    `summary["uncovered"]` to decide when a field must print `NO_DATA`
    instead of a real number."""
    summary["attempts"] += 1
    if "orchestration" not in record or "agents" not in record:
        summary["uncovered"] += 1
        return

    collapsed = bool(record.get("usage_collapsed"))
    orchestration = record.get("orchestration") or {}
    agents = record.get("agents") or {}
    orch_tokens = _bucket_tokens(orchestration, collapsed)
    agent_tokens = _bucket_tokens(agents, collapsed)
    summary["orchestration_tokens"] += orch_tokens
    summary["agent_tokens"] += agent_tokens

    if collapsed:
        # No model identifier survived the collapse (D5 step 4) -- there is
        # nothing left to look a price up by. That is not the same fact as
        # "the price table is missing this model" (unpriced), so it is its
        # own counter: one says "go fix the price table", the other says
        # "go raise MAX_RECORD or expect fewer models per record"
        # (coordinator correction, 2026-08-30).
        summary["collapsed_records"] += 1
        summary["collapsed_tokens"] += orch_tokens + agent_tokens
        return

    summary["models"] |= _bucket_models(orchestration, collapsed)
    summary["models"] |= _bucket_models(agents, collapsed)
    for bucket in (orchestration, agents):
        spend, unpriced_tokens, unpriced_models = _price_bucket(bucket, price_table)
        summary["spend"] += spend
        summary["unpriced_tokens"] += unpriced_tokens
        summary["unpriced_models"] |= unpriced_models


def _unpriced_str(summary):
    if not summary["unpriced_tokens"]:
        return "0"
    return "%d (%d model(s))" % (summary["unpriced_tokens"], len(summary["unpriced_models"]))


def _coverage(summary):
    """(covered_attempts, note) -- `note` is "" when every attempt that
    happened has usage data on file (including the trivial case of a stage
    with 0 attempts: there is nothing to be missing). Otherwise it names how
    much of the row's numbers actually cover, so a reader cannot mistake a
    partial figure for the whole thing."""
    attempts = summary["attempts"]
    covered = attempts - summary["uncovered"]
    if covered == attempts:
        return covered, ""
    if covered == 0:
        return covered, "  (no usage data on file for any attempt -- predates tracking, D11)"
    return covered, ("  (usage data for %d of %d attempts; the rest predate "
                     "tracking, D11)" % (covered, attempts))


def _row(name, summary, extra=""):
    covered, note = _coverage(summary)
    no_data = summary["attempts"] > 0 and covered == 0
    models = NO_DATA if no_data else str(len(summary["models"]))
    orch = NO_DATA if no_data else str(summary["orchestration_tokens"])
    agent = NO_DATA if no_data else str(summary["agent_tokens"])
    spend = NO_DATA if no_data else _money(summary["spend"])
    # UC6, user's tradeoff (2026-08-30): the field name itself carries the
    # marker, so a single row read on its own -- cut out of the report and
    # pasted elsewhere -- still shows this is not a real charge, without
    # repeating the full sentence CAVEAT already states once in the header.
    return ("%-10s  attempts=%d  models=%s%s  orchestration_tokens=%s  "
            "agent_tokens=%s  spend_equiv=%s  unpriced=%s  collapsed=%d%s"
            % (name, summary["attempts"], models, extra, orch, agent, spend,
               _unpriced_str(summary), summary["collapsed_tokens"], note))


def _price_header(price_table):
    parts = ["price table version %s" % price_table.get("version", "unknown"),
             "%d user override(s)" % price_table.get("override_count", 0)]
    if price_table.get("shipped_error"):
        parts.append("SHIPPED PRICE TABLE UNREADABLE (%s) -- every model is "
                     "unpriced until this is fixed" % price_table["shipped_error"])
    if price_table.get("override_error"):
        parts.append("user override ignored (%s)" % price_table["override_error"])
    return "; ".join(parts)


def _footnotes(total, malformed):
    lines = []
    if malformed:
        lines.append("%d malformed line(s) skipped." % malformed)
    if total["uncovered"]:
        lines.append("%d record(s) predate usage tracking and have no usage "
                     "data on file -- shown as %s, not as 0 (D11)."
                     % (total["uncovered"], NO_DATA))
    if total["collapsed_records"]:
        lines.append("%d record(s) (%d tokens, see 'collapsed' column) only "
                     "have collapsed per-source totals: per-model detail did "
                     "not fit the ledger and was summed away. That is a "
                     "different problem from 'unpriced' -- fix it by raising "
                     "MAX_RECORD or by having fewer distinct models per "
                     "attempt, not by editing the price table."
                     % (total["collapsed_records"], total["collapsed_tokens"]))
    return lines


# --- track_report: one track's own ledger, self-contained (UC9) ------------

def track_report(track_dir, price_table):
    """Every stage in this track, plus a total. Reads only this track's own
    `ledger.jsonl` -- never the central ledger -- so it still answers UC3
    even when the central ledger does not exist (UC9)."""
    stages = ledger.stage_ids()
    all_records = ledger.records(track_dir)
    malformed = sum(1 for record in all_records if record.get("malformed"))

    lines = ["Track usage report for %s" % track_dir,
             "Prices: %s" % _price_header(price_table),
             "Columns: spend_equiv is %s; unpriced is tokens with no rate on "
             "file, by model count; collapsed is tokens whose per-model "
             "detail was dropped to fit the ledger; %s means no attempt in "
             "this row has usage data on file." % (CAVEAT, NO_DATA), ""]

    total = _new_summary()
    for stage in stages:
        summary = _new_summary()
        for record in all_records:
            if record.get("malformed") or record.get("stage") != stage:
                continue
            _accumulate(summary, record, price_table)
        _merge_into(total, summary)
        lines.append(_row(stage, summary))

    lines.append("-" * 40)
    lines.append(_row("TOTAL", total))
    lines.extend([""] + _footnotes(total, malformed))
    return "\n".join(lines)


# --- range_report: the central ledger, grouped by stage, across projects ---

def _read_date_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            date = fh.read().strip()
    except OSError:
        return None
    return date or None


def _central_ledger_dir(config_root):
    """The directory the import-day marker lives next to (D14): the same
    rule `usage_collector.central_ledger_path()` uses, applied to a given
    `config_root` instead of re-reading `usage_collector.config_root()`.
    `CAI_USAGE_LEDGER`, when set, wins outright -- a caller-supplied
    `config_root` must not be able to make this function look somewhere the
    actual central ledger is not (coordinator correction, 2026-08-30: this
    function and `range_report()` used to disagree about where the marker
    is when the override was set)."""
    override = os.environ.get(usage_collector.CENTRAL_LEDGER_ENV)
    if override:
        return os.path.dirname(override)
    return os.path.join(config_root, "cai")


def data_start_date(config_root):
    """The import day (D10): the UTC date the central ledger was first
    created, or `None` when it has never been written -- which means
    "installed but never run", not "not installed"; an empty ledger cannot
    tell those apart any other way.

    `config_root` is the value `usage_collector.config_root()` returns, used
    when there is no `CAI_USAGE_LEDGER` override; `range_report()` calls
    this the same way rather than deriving the marker's location itself, so
    the two can no longer disagree."""
    return _read_date_file(os.path.join(_central_ledger_dir(config_root), "usage-start.txt"))


def _read_central_records(path):
    """(records, malformed_count) from the central ledger. Central records
    are never grouped by `ledger.stage_ids()` filtering the way per-track
    ones are -- there is no per-track `ledger.records()` for a
    cross-project file -- so this mirrors its tolerant-of-a-torn-last-line
    handling directly (ledger.py:350-377) rather than importing something
    that does not exist for this shape of file."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return [], 0

    out = []
    malformed = 0
    for number, text in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
            if not isinstance(record, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError):
            malformed += 1
            continue
        record["line"] = number
        out.append(record)
    return out, malformed


def _parse_ts(ts):
    try:
        return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def range_report(central_path, days, price_table):
    """Every stage across every project in the central ledger, for the last
    `days` days. A query window reaching back before the import date (D10)
    is marked "no data" for that stretch rather than folded in as 0 (UC8):
    the ledger genuinely does not go back that far, which is a different
    fact than "nothing happened".

    The import-day marker is read through `data_start_date()`, the same
    function a standalone caller uses, rather than re-deriving its location
    here -- the two must agree on where it is (coordinator correction,
    2026-08-30)."""
    import_date = data_start_date(usage_collector.config_root())

    if not os.path.isfile(central_path):
        lines = ["No cross-project data yet -- the central ledger does not "
                 "exist at %s." % central_path]
        lines.append("Data start date: %s."
                     % (import_date or "not recorded yet (installed but never run)."))
        return "\n".join(lines)

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    lines = ["Cross-project usage report -- last %d day(s)" % days,
             "Prices: %s" % _price_header(price_table),
             "Columns: spend_equiv is %s; unpriced is tokens with no rate on "
             "file, by model count; collapsed is tokens whose per-model "
             "detail was dropped to fit the ledger; %s means no attempt in "
             "this row has usage data on file." % (CAVEAT, NO_DATA)]

    if import_date:
        lines.append("Data start date: %s (nothing before this date is on "
                     "file -- the ledger was not installed yet, which is "
                     "different from nothing having happened)." % import_date)
        import_dt = datetime.datetime.strptime(import_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
        if cutoff < import_dt:
            no_data_days = (import_dt - cutoff).days
            lines.append("No data for the first %d of the requested %d "
                         "day(s) -- they are before the data start date, "
                         "shown as no data rather than as 0." % (no_data_days, days))
            cutoff = import_dt
    else:
        lines.append("Data start date: not recorded yet (installed but never run).")
    lines.append("")

    all_records, malformed = _read_central_records(central_path)
    in_range = []
    for record in all_records:
        ts = _parse_ts(record.get("ts"))
        if ts is not None and cutoff <= ts <= now:
            in_range.append(record)

    total = _new_summary()
    total_scopes = set()
    for stage in ledger.stage_ids():
        summary = _new_summary()
        scopes = set()
        for record in in_range:
            if record.get("stage") != stage:
                continue
            _accumulate(summary, record, price_table)
            scopes.add((record.get("project"), record.get("track")))
        _merge_into(total, summary)
        total_scopes |= scopes
        lines.append(_row(stage, summary, extra="  projects=%d" % len(scopes)))

    lines.append("-" * 40)
    lines.append(_row("TOTAL", total, extra="  projects=%d" % len(total_scopes)))
    lines.extend([""] + _footnotes(total, malformed))
    return "\n".join(lines)


# --- metrics: first-pass / cycle time / rework / human-signed (issue #85) --
#
# Answers a different question than track_report()/range_report() above --
# how the work went, not what it cost -- so it is its own pair of functions
# rather than a fifth column bolted onto _row()/_accumulate(). It reads the
# same two files (per-track ledger.jsonl, central usage.jsonl) and nothing
# else; no new data file, no OpenTelemetry (issue #85's "risk" section).

ATTEMPT_OUTCOMES = ("passed",) + ledger.COUNTS_AS_RETRY  # passed, failed, blocked
GATE_WALKED_STAGES = ("design", "ship")


def _stage_attempts(stage_records):
    """One list per attempt, in file order: consecutive `passed` records
    that share a sha256 collapse into the same attempt (design's auto row
    and a human sign-off of the same bytes; two separate passes of a stage
    never do). So does a person's sign-off (`gate: human`) of the artifact
    the pass before it named, whatever its sha: Gate 1's Approve writes
    `approved <date>` into a document with a `## Status` of its own -- a
    diagnosis, a legacy high-level design -- before its row is appended, so
    there the two shas differ and it is still one attempt (#140). The
    recorded string is what is compared, since this report reads only the
    ledger and has no project to resolve a path against.
    A null sha is not a shared one: stages that record no
    artifact (verify, intake) leave sha256 null on every row, and two such
    passes are two attempts, not one (verify, 2026-09-13). `stage_records`
    already excludes `skipped`/`unavailable`/malformed by the time an
    outcome check here would matter -- those are filtered out below because
    they are not in ATTEMPT_OUTCOMES."""
    groups = []
    for record in stage_records:
        if record.get("outcome") not in ATTEMPT_OUTCOMES:
            continue
        prev = groups[-1] if groups else None
        if (prev and record.get("outcome") == "passed"
                and prev[-1].get("outcome") == "passed"
                and ((record.get("sha256") is not None
                      and record.get("sha256") == prev[-1].get("sha256"))
                     or (record.get("gate") == "human" and record.get("artifact")
                         and record.get("artifact") == prev[-1].get("artifact")))):
            prev.append(record)
        else:
            groups.append([record])
    return groups


def stage_metrics(stage_records, stage):
    """The four issue-#85 numbers for one stage, from that stage's own
    non-malformed records (any outcome, file order). A stage with zero
    attempts (`rework` 0) carries no other number either -- callers print
    NO_DATA for the whole row rather than a fabricated 0 or 1."""
    groups = _stage_attempts(stage_records)
    if not groups:
        return {"first_pass": None, "rework": 0, "cycle_seconds": None,
                "human_num": 0, "human_den": 0, "gate_not_walked": False}

    first_pass = 1 if groups[0][0].get("outcome") == "passed" else 0
    human_den = len(groups)
    human_num = sum(1 for group in groups
                    if any(record.get("gate") == "human" for record in group))
    has_passed = any(group[0].get("outcome") == "passed" for group in groups)
    # #91's "how many times was the human gate bypassed": true only for the
    # two stages a human is meant to sign off on, and only once the stage
    # has actually passed -- a stage still failing has not been bypassed,
    # it just has not gotten there yet.
    gate_not_walked = has_passed and human_num == 0 and human_den > 0
    if stage == "design" and has_passed:
        # #128: "any human row" counted the #112 ledger -- stance approved,
        # finished design passed auto -- as walked, while preflight.py
        # refused build on it. Ask what preflight asks, as near as the
        # ledger alone gets: does a person's Approve carry the sha of
        # design's last pass?
        last = [r for r in stage_records if r.get("outcome") == "passed"][-1]
        gate_not_walked = not ledger.approved(stage_records, last.get("sha256"))

    first_ts = _parse_ts(stage_records[0].get("ts")) if stage_records else None
    last_passed_ts = None
    for record in stage_records:
        if record.get("outcome") == "passed":
            ts = _parse_ts(record.get("ts"))
            if ts is not None:
                last_passed_ts = ts
    cycle_seconds = None
    if first_ts is not None and last_passed_ts is not None:
        cycle_seconds = (last_passed_ts - first_ts).total_seconds()

    return {"first_pass": first_pass, "rework": human_den,
            "cycle_seconds": cycle_seconds, "human_num": human_num,
            "human_den": human_den, "gate_not_walked": gate_not_walked}


def _by_stage(records):
    """Non-malformed records, file order preserved, split by stage id."""
    by_stage = {stage: [] for stage in ledger.stage_ids()}
    for record in records:
        if record.get("malformed"):
            continue
        stage = record.get("stage")
        if stage in by_stage:
            by_stage[stage].append(record)
    return by_stage


def _track_cycle_seconds(by_stage):
    """ship's last `passed` ts minus intake's first record ts (any
    outcome) -- None when either end is missing."""
    intake = by_stage.get("intake") or []
    ship = by_stage.get("ship") or []
    if not intake or not ship:
        return None
    first_ts = _parse_ts(intake[0].get("ts"))
    last_passed_ts = None
    for record in ship:
        if record.get("outcome") == "passed":
            ts = _parse_ts(record.get("ts"))
            if ts is not None:
                last_passed_ts = ts
    if first_ts is None or last_passed_ts is None:
        return None
    return (last_passed_ts - first_ts).total_seconds()


def track_metrics(records):
    """(per-stage metrics dict keyed by stage id, track cycle in seconds or
    None) for one track's own records -- shared by metrics_report() (one
    track) and central_metrics_report() (one (project, track) group)."""
    by_stage = _by_stage(records)
    per_stage = {stage: stage_metrics(by_stage[stage], stage) for stage in ledger.stage_ids()}
    return per_stage, _track_cycle_seconds(by_stage)


def _fmt_hms(seconds):
    if seconds is None:
        return NO_DATA
    total = int(round(max(seconds, 0)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return "%d:%02d:%02d" % (hours, minutes, secs)


def _fmt_ratio(num, den):
    return "%d/%d" % (num, den) if den else NO_DATA


def metrics_report(track_dir):
    """One track's own ledger: first_pass/cycle/rework/human_signed per
    stage, a TOTAL line, and the track's own cycle time -- issue #85's
    `metrics --track-dir` form. Self-contained, like track_report(): reads
    only this track's ledger.jsonl, never the central one."""
    all_records = ledger.records(track_dir)
    malformed = sum(1 for record in all_records if record.get("malformed"))
    per_stage, track_cycle = track_metrics(all_records)

    lines = ["Stage metrics for %s" % track_dir,
             "Columns: first_pass is 1 if the stage's first attempt passed, "
             "else 0; cycle is h:mm:ss from the stage's first record to its "
             "last passed one; rework is the stage's attempt count "
             "(consecutive same-sha passed rows count once); human_signed "
             "is the share of attempts carrying a human gate record; %s "
             "means the stage had no attempt at all." % NO_DATA, ""]

    fp_passed = fp_attempted = 0
    total_rework = 0
    human_num_total = human_den_total = 0
    walked_notes = []
    for stage in ledger.stage_ids():
        metrics = per_stage[stage]
        if metrics["rework"] == 0:
            lines.append("%-10s  first_pass=%s  cycle=%s  rework=%s  human_signed=%s"
                        % (stage, NO_DATA, NO_DATA, NO_DATA, NO_DATA))
            continue
        fp_attempted += 1
        fp_passed += metrics["first_pass"]
        total_rework += metrics["rework"]
        human_num_total += metrics["human_num"]
        human_den_total += metrics["human_den"]
        if stage in GATE_WALKED_STAGES and metrics["gate_not_walked"]:
            walked_notes.append("gate not walked: %s" % stage)
        lines.append("%-10s  first_pass=%d  cycle=%s  rework=%d  human_signed=%s"
                    % (stage, metrics["first_pass"], _fmt_hms(metrics["cycle_seconds"]),
                       metrics["rework"], _fmt_ratio(metrics["human_num"], metrics["human_den"])))

    lines.append("-" * 40)
    lines.append("%-10s  first_pass=%s  cycle=%s  rework=%d  human_signed=%s"
                % ("TOTAL", _fmt_ratio(fp_passed, fp_attempted), NO_DATA,
                   total_rework, _fmt_ratio(human_num_total, human_den_total)))
    lines.append("track cycle: %s" % _fmt_hms(track_cycle))

    footnotes = []
    if malformed:
        footnotes.append("%d malformed line(s) skipped." % malformed)
    footnotes.extend(walked_notes)
    lines.extend([""] + footnotes)
    return "\n".join(lines)


def _central_window(days):
    """(header_lines, cutoff, now) for a --days query against the central
    ledger -- the same import-day floor range_report() applies (D10).
    Deliberately duplicated rather than shared: range_report()'s output is
    pinned verbatim by tests/test_report.py, so nothing here may become a
    line range_report() itself executes (coordinator instruction, issue
    #85)."""
    import_date = data_start_date(usage_collector.config_root())
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)
    lines = []
    if import_date:
        lines.append("Data start date: %s (nothing before this date is on "
                     "file -- the ledger was not installed yet, which is "
                     "different from nothing having happened)." % import_date)
        import_dt = datetime.datetime.strptime(import_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
        if cutoff < import_dt:
            no_data_days = (import_dt - cutoff).days
            lines.append("No data for the first %d of the requested %d "
                         "day(s) -- they are before the data start date, "
                         "shown as no data rather than as 0." % (no_data_days, days))
            cutoff = import_dt
    else:
        lines.append("Data start date: not recorded yet (installed but never run).")
    return lines, cutoff, now


def central_metrics_report(central_path, days):
    """Every stage across every (project, track) pair in the central
    ledger, for the last `days` days -- issue #85's `metrics --days` form.
    Computed per (project, track, stage) first, then aggregated per stage:
    first_pass and human_signed add numerators and denominators; rework and
    cycle time are averaged across the tracks that had an attempt."""
    header, cutoff, now = _central_window(days)
    lines = (["Cross-project stage metrics -- last %d day(s)" % days] + header
             + ["Columns: first_pass and human_signed add each track's own "
                "numerator and denominator; rework and cycle are averaged "
                "across tracks that had an attempt; %s means no track had "
                "an attempt in this stage." % NO_DATA, ""])

    if not os.path.isfile(central_path):
        lines.append("No cross-project data yet -- the central ledger does "
                     "not exist at %s." % central_path)
        return "\n".join(lines)

    all_records, malformed = _read_central_records(central_path)
    in_range = []
    for record in all_records:
        ts = _parse_ts(record.get("ts"))
        if ts is not None and cutoff <= ts <= now:
            in_range.append(record)

    by_track = {}
    for record in in_range:
        key = (record.get("project"), record.get("track"))
        by_track.setdefault(key, []).append(record)

    units = []
    track_cycles = []
    for track_records in by_track.values():
        per_stage, track_cycle = track_metrics(track_records)
        units.append(per_stage)
        if track_cycle is not None:
            track_cycles.append(track_cycle)

    walked_notes = []
    fp_num_total = fp_den_total = 0
    human_num_total = human_den_total = 0
    rework_avgs = []
    for stage in ledger.stage_ids():
        fp_num = fp_den = 0
        human_num = human_den = 0
        rework_vals = []
        cycle_vals = []
        walked = False
        for per_stage in units:
            metrics = per_stage[stage]
            if metrics["rework"] == 0:
                continue
            fp_den += 1
            fp_num += metrics["first_pass"]
            human_num += metrics["human_num"]
            human_den += metrics["human_den"]
            rework_vals.append(metrics["rework"])
            if metrics["cycle_seconds"] is not None:
                cycle_vals.append(metrics["cycle_seconds"])
            if stage in GATE_WALKED_STAGES and metrics["gate_not_walked"]:
                walked = True
        if walked:
            walked_notes.append("gate not walked: %s" % stage)
        if fp_den == 0:
            lines.append("%-10s  first_pass=%s  cycle=%s  rework=%s  human_signed=%s"
                        % (stage, NO_DATA, NO_DATA, NO_DATA, NO_DATA))
            continue
        rework_avg = sum(rework_vals) / len(rework_vals)
        cycle_avg = sum(cycle_vals) / len(cycle_vals) if cycle_vals else None
        fp_num_total += fp_num
        fp_den_total += fp_den
        human_num_total += human_num
        human_den_total += human_den
        rework_avgs.append(rework_avg)
        lines.append("%-10s  first_pass=%s  cycle=%s  rework=%.2f  human_signed=%s"
                    % (stage, _fmt_ratio(fp_num, fp_den), _fmt_hms(cycle_avg),
                       rework_avg, _fmt_ratio(human_num, human_den)))

    lines.append("-" * 40)
    total_rework_avg = (sum(rework_avgs) / len(rework_avgs)) if rework_avgs else None
    lines.append("%-10s  first_pass=%s  cycle=%s  rework=%s  human_signed=%s"
                % ("TOTAL", _fmt_ratio(fp_num_total, fp_den_total), NO_DATA,
                   ("%.2f" % total_rework_avg) if total_rework_avg is not None else NO_DATA,
                   _fmt_ratio(human_num_total, human_den_total)))
    overall_track_cycle = (sum(track_cycles) / len(track_cycles)) if track_cycles else None
    lines.append("track cycle (avg): %s" % _fmt_hms(overall_track_cycle))

    footnotes = []
    if malformed:
        footnotes.append("%d malformed line(s) skipped." % malformed)
    footnotes.extend(walked_notes)
    lines.extend([""] + footnotes)
    return "\n".join(lines)


# --- CLI: /cai:usage's unit-7 skill shells out to this ----------------------

class _ArgParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        sys.exit(1)


def main():
    # Same reasoning as ledger.py's main(): notes and reports carry whatever
    # alphabet the author used, and a piped Windows stdout defaults to a
    # codepage that cannot hold it (tests/test_cli_encoding.py).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = _ArgParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    track_ap = sub.add_parser("track")
    track_ap.add_argument("--track-dir", required=True)
    range_ap = sub.add_parser("range")
    range_ap.add_argument("--days", type=int, required=True)
    metrics_ap = sub.add_parser("metrics")
    metrics_group = metrics_ap.add_mutually_exclusive_group(required=True)
    metrics_group.add_argument("--track-dir")
    metrics_group.add_argument("--days", type=int)
    args = ap.parse_args()

    if args.command == "metrics":
        if args.track_dir:
            print(metrics_report(args.track_dir))
        else:
            print(central_metrics_report(usage_collector.central_ledger_path(), args.days))
        return 0

    price_table = load_price_table()
    if args.command == "track":
        print(track_report(args.track_dir, price_table))
    else:
        print(range_report(usage_collector.central_ledger_path(), args.days, price_table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
