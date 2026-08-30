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
    args = ap.parse_args()

    price_table = load_price_table()
    if args.command == "track":
        print(track_report(args.track_dir, price_table))
    else:
        print(range_report(usage_collector.central_ledger_path(), args.days, price_table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
