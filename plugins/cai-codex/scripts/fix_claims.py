#!/usr/bin/env python3
"""Register, release and clear local session claims for fix items."""
import contextlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fix_target  # noqa: E402
import ledger  # noqa: E402
import preflight  # noqa: E402
import usage_collector  # noqa: E402

PLATFORM = "codex"
SESSION_ID_ENV = "CODEX_THREAD_ID"
REGISTRY_NAME = "fix-claims.json"
EXPIRY_SECONDS = 1800
LOCK_WAIT_SECONDS = 2.0
LOCK_RETRY_SECONDS = 0.05

_SESSION = re.compile(r"[A-Za-z0-9._:-]+")
_PLATFORM = re.compile(r"[a-z][a-z0-9-]*")
_STARTED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
_escape = preflight._escape_control_chars


def item_key(owner: str, repo: str, number: int) -> str:
    return f"{owner}/{repo}#{number}".lower()


def jira_key(host: str, key: str) -> str:
    return f"{host}/{key}".lower()


def current_session() -> Optional[str]:
    value = os.environ.get(SESSION_ID_ENV)
    # The printed marker must identify only null claims when copied to clear.
    return value if value and value != "unknown" and _SESSION.fullmatch(value) else None


def registry_path() -> str:
    return os.path.join(usage_collector.config_root(), "cai", REGISTRY_NAME)


def is_expired(started: object, now: datetime) -> Optional[bool]:
    if not isinstance(started, str) or not _STARTED.fullmatch(started):
        return None
    try:
        beginning = datetime.strptime(started, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (now - beginning).total_seconds() >= EXPIRY_SECONDS


def load(path: str, repair: bool) -> Tuple[Optional[dict], List[str]]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("claims"), dict):
            return data, []
    except FileNotFoundError:
        return {"claims": {}}, []
    except ValueError:
        pass
    if not repair:
        return None, []
    backup = path + ".bak"
    os.replace(path, backup)
    return {"claims": {}}, ["the registry could not be parsed and was moved to %s" % _escape(backup)]


def save(path: str, data: dict) -> None:
    temporary = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(temporary, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


@contextlib.contextmanager
def hold_lock(create: bool, readonly: bool = False,
              attempts: Optional[int] = None) -> Iterator[bool]:
    flags = os.O_RDONLY if readonly else os.O_RDWR
    if create:
        flags |= os.O_CREAT
    fd = os.open(registry_path() + ".lock", flags, 0o644)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            def acquire():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            def unlock():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlock():
                fcntl.flock(fd, fcntl.LOCK_UN)
        start = time.monotonic()
        count = 0
        while True:
            try:
                acquire()
                locked = True
                break
            except OSError:
                count += 1
                if attempts is not None:
                    if count >= attempts:
                        break
                remaining = LOCK_WAIT_SECONDS - (time.monotonic() - start)
                if remaining <= 0:
                    break
                time.sleep(min(LOCK_RETRY_SECONDS, remaining))
        yield locked
    finally:
        try:
            if locked:
                unlock()
        finally:
            os.close(fd)


def _readable(row, now):
    if not isinstance(row, dict):
        return False
    platform, session = row.get("platform"), row.get("session_id")
    return (isinstance(platform, str) and _PLATFORM.fullmatch(platform) is not None
            and "session_id" in row
            and (session is None or isinstance(session, str) and session != "unknown"
                 and _SESSION.fullmatch(session) is not None)
            and is_expired(row.get("started"), now) is not None)


def _own(row, session):
    return session is not None and row["platform"] == PLATFORM and row["session_id"] == session


def _detail(row):
    return "%s %s %s" % (row["platform"], row["session_id"] or "unknown", row["started"])


def others_by_key(keys: Iterable[str]) -> Optional[Dict[str, List[dict]]]:
    result = {key: [] for key in keys}
    try:
        with hold_lock(create=False, readonly=True, attempts=1) as held:
            if not held:
                return None
            data, _ = load(registry_path(), repair=False)
            if data is None:
                return None
            now, session = datetime.now(timezone.utc), current_session()
            for key in result:
                row = data["claims"].get(key)
                if (_readable(row, now) and not _own(row, session)
                        and not is_expired(row["started"], now)):
                    result[key] = [{field: row[field] for field in ("platform", "session_id", "started")}]
    except FileNotFoundError as exc:
        return result if exc.filename == registry_path() + ".lock" else None
    except OSError:
        return None
    return result


def _output(outcome, notes=()):
    print("registry " + outcome)
    for note in notes:
        print("registry note " + note)


def _unavailable(exc, notes=()):
    _output("unavailable %s: %s" % (type(exc).__name__, _escape(str(exc)[:200])), notes)


def _register(args, key):
    session, notes = current_session(), []
    if session is None:
        notes.append("session unknown: %s is not set or not usable, so this claim names no session"
                     % _escape(SESSION_ID_ENV))
    try:
        os.makedirs(os.path.dirname(registry_path()), exist_ok=True)
        with hold_lock(create=True) as held:
            if not held:
                _output("unavailable lock-busy", notes)
                return 0
            data, repairs = load(registry_path(), repair=True)
            notes.extend(repairs)
            row = data["claims"].get(key)
            now = datetime.now(timezone.utc)
            readable = _readable(row, now)
            own = readable and _own(row, session)
            if readable and not own:
                if not is_expired(row["started"], now):
                    _output("elsewhere " + _detail(row), notes)
                    return 3
                notes.append("took over an expired claim by %s session %s started %s" % (
                    _escape(row["platform"]), _escape(row["session_id"] or "unknown"), _escape(row["started"])))
            elif key in data["claims"] and not readable:
                notes.append("replaced an unreadable entry for this item")
            started = ledger._now_ms()
            new = dict(row) if isinstance(row, dict) else {}
            new.update(platform=PLATFORM, session_id=session, started=started,
                       status="in-progress", branch=args.branch)
            data["claims"][key] = new
            save(registry_path(), data)
            _output("held %s %s" % (_escape(key), started), notes)
            return 0
    except OSError as exc:
        _unavailable(exc, notes)
        return 0


def _remove(key, platform, session, started, manual):
    absent = "not-found" if manual else "not-held"
    try:
        with hold_lock(create=False) as held:
            if not held:
                _output("unavailable lock-busy")
                return 3 if manual else 0
            data, notes = load(registry_path(), repair=True)
            row = data["claims"].get(key)
            readable = _readable(row, datetime.now(timezone.utc))
            if readable and (row["platform"], row["session_id"], row["started"]) == (platform, session, started):
                del data["claims"][key]
                save(registry_path(), data)
                _output("%s %s" % ("cleared" if manual else "released", _escape(key)), notes)
                return 0
            _output("%s %s" % (absent, _escape(key)), notes)
            if manual and readable:
                _output("entry " + _detail(row))
    except FileNotFoundError as exc:
        if exc.filename == registry_path() + ".lock":
            _output("%s %s" % (absent, _escape(key)))
        else:
            _unavailable(exc)
    except OSError as exc:
        _unavailable(exc)
    return 3 if manual else 0


def main(argv=None):
    parser = preflight.ArgParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("register", "release"):
        sub = commands.add_parser(command)
        for name in ("owner", "repo", "host", "key"):
            sub.add_argument("--" + name)
        sub.add_argument("--issue", type=int)
        sub.add_argument("--branch" if command == "register" else "--started", required=True)
    sub = commands.add_parser("clear")
    for name in ("project-dir", "platform", "session", "started"):
        sub.add_argument("--" + name, required=True)
    sub.add_argument("url")
    args = parser.parse_args(argv)
    if args.command == "clear":
        row = {"platform": args.platform, "session_id": None if args.session == "unknown" else args.session,
               "started": args.started}
        if not _readable(row, datetime.now(timezone.utc)):
            return fix_target.stop("unrecognised", "The platform, session or start time is not in the shape "
                                   "a blocked item's detail prints; copy the three words from that detail.",
                                   word="rejected")
        target = fix_target.classify(args.url, fix_target.origin_remote(args.project_dir))
        if isinstance(target, fix_target.Rejection):
            return fix_target.stop(target.reason, target.message, word="rejected")
        if target.kind == "issue":
            key = item_key(target.owner, target.repo, target.number)
        elif target.kind == "jira-ticket":
            key = jira_key(target.host, target.key)
        else:
            return fix_target.stop("unrecognised", "Give the issue or Jira ticket URL on the blocked item's report line.",
                                   word="rejected")
        return _remove(key, args.platform, row["session_id"], args.started, manual=True)
    github = args.owner is not None or args.repo is not None or args.issue is not None
    jira = args.host is not None or args.key is not None
    if github == jira or (github and not (args.owner and args.repo and args.issue is not None)) or (
            jira and not (args.host and args.key)):
        parser.error("give either --owner, --repo and --issue, or --host and --key")
    key = item_key(args.owner, args.repo, args.issue) if github else jira_key(args.host, args.key)
    if args.command == "register":
        return _register(args, key)
    return _remove(key, PLATFORM, current_session(), args.started, manual=False)


if __name__ == "__main__":
    sys.exit(main())
