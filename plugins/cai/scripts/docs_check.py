#!/usr/bin/env python3
"""Finds where a project's Markdown has stopped matching its files, as far as
git can tell without anyone reading either for meaning. Zero deps.

A document goes stale in ways only a reader can judge, but two of them leave a
trace a program can follow:

  dead     the document names a path that is not there now and was committed
           once -- deleted or renamed since. A path that never existed is an
           illustration, or another repository's, and is left alone: that one
           rule is what keeps a page of examples from reading as a page of
           defects.
  review   the document names a file that changed after the document last
           did. The sentence may still be true; this is a list to read, not a
           verdict.

"There" means what git would check out, plus what is new and not ignored. A
file git ignores is on this machine only, so it never keeps a deleted path
alive: the same commit reads the same here and in a fresh checkout.

A path git's ignore rules now cover is not dead either: the project stopped
committing an output, it did not lose a file.

A path in running text or code is looked for beside the document first, then
in each directory above it up to the repository root, so `scripts/x.py`
written in a file three levels down means the nearest `scripts/x.py` above
it. A name with no directory (`x.py`) that is not found that way still counts
as there when any file carries it, and is called dead only when the file sat
beside the document: further up, the same name is as likely the reader's own
project's. A link is looked for where Markdown resolves it and nowhere else:
beside the document, or at the repository root when it begins with `/`.

Records are skipped unless named as PATH: a changelog, a dated file, a
decision record. They describe a moment, and a path that has gone since is
what they are supposed to say.

With --base, the question is what one change did: `dead` keeps the references
that still resolved before the change -- a path it removed, or one it put out
of reach by moving the document -- and the ones it wrote itself, and `review`
lists the sections naming a file the change touched. Without it,
`review` compares commit order across the whole history, a file at a time --
a document counts as updated when any line of it was -- and work not
committed yet counts as newer than every commit.

Usage:  docs_check.py [--project-dir DIR] [--base REF] [PATH ...]
        PATH is a Markdown file, or a directory of them, relative to the
        repository root.
Exit:   0 no dead reference, or nothing could be checked (the first line then
        reads `docs: unsupported (...)`); 2 at least one dead reference;
        1 usage error.
"""
import os
import posixpath
import re
import sys
from typing import NamedTuple
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemap_inventory  # noqa: E402
import preflight  # noqa: E402

DOC_EXTENSIONS = (".md", ".markdown", ".mdx")
# One walk over every commit. Past this the repository is too large for the
# walk to be worth waiting on, and the run says so instead of guessing.
HISTORY_TIMEOUT = 60
TOP = "(top)"   # the label of whatever a document says before its first heading
MOVED = "out of reach since this change moved the document"

RECORD_STEMS = {"changelog", "history", "news", "releases", "release-notes", "release_notes"}
RECORD_DIRS = {"adr", "adrs", "rfc", "rfcs", "decisions", "archive", "archived",
               "changelog", "changelogs", "postmortems"}
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}(?!\d)")

# A block opens on a run of backticks with no backtick after it on the line --
# "```x``` and so on" is inline code -- and closes on a run with nothing after
# it: "```bash" inside a block is part of what the block shows.
FENCE_OPEN = re.compile(r"^\s*(?:(`{3,})[^`]*|(~{3,}).*)$")
FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
# Not str.splitlines(), which also breaks on a form feed and on U+2028 and
# so counts lines no editor shows.
LINE_BREAK = re.compile(r"\r\n|\n|\r")
HEADING = re.compile(r"^#{1,6}[ \t]+(.*?)[ \t#]*$")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)")
# `[name]: target`, and not `[^1]: a footnote's first word`.
LINK_DEFINITION = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*<?([^\s>]+)")
WORD_BREAK = re.compile(r"[\s'\"()\[\],;=|]+")
# The two variables Claude Code defines as a directory this repository's own
# files sit under. Any other `$VAR/...` is a place on the reader's machine
# (`$HOME/.config/x.json`), and reading it as this repository's `x.json` calls
# a deleted file of ours dead on the strength of theirs.
ROOT_VARIABLE = re.compile(r"^\$\{?(?:CLAUDE_PLUGIN_ROOT|CLAUDE_PROJECT_DIR)\}?/")
# What follows a path to say where in the file: x.py:12, x.py:12-20,
# x.py:12:3, x.py::test_name, x.md#heading.
LOCATOR = re.compile(r"(?:(?::\d+(?:-\d+)?){1,2}|::.*|#.*)$")
# Anything outside this is a placeholder (`<name>`), a glob, a URL, a Windows
# path or another variable, none of which can be looked up.
PATH_CHARS = re.compile(r"^[\w.@+/-]+$")
BARE_FILE = re.compile(r"^[\w.@+-]*\.[A-Za-z]\w{0,15}$")


class Ref(NamedTuple):
    line: int
    heading: str
    token: str          # the path as the document wrote it, locator removed
    rooted: bool        # a link that began with `/`: the repository root and nowhere else
    section: int = 0    # the line of the heading it sits under, 0 before the first
    link: bool = False  # a link target, which Markdown resolves in exactly one place


class Tree(NamedTuple):
    files: frozenset     # what git would check out, plus what is new and not ignored
    dirs: frozenset      # every directory above one of `files`
    names: dict          # basename -> the `files` that carry it


class History(NamedTuple):
    order: dict     # path -> position of the newest commit touching it, 0 the newest
    gone: dict      # path -> (short hash, the path it was renamed to or None)
    dirs: frozenset


class Change(NamedTuple):
    base: str
    removed: dict        # path -> the path it was renamed to, or None
    modified: frozenset  # paths this change touched that are still there
    added: frozenset
    count: int
    renamed: dict        # the new path -> the path it was renamed from


class Dead(NamedTuple):
    doc: str
    ref: Ref
    path: str
    why: str
    mine: bool = True   # with --base: the reference was not dead before the change


def is_record(path):
    parts = path.casefold().split("/")
    stem = posixpath.splitext(parts[-1])[0]
    return (stem in RECORD_STEMS or DATED.match(parts[-1]) is not None
            or any(part in RECORD_DIRS for part in parts[:-1]))


def _names_a_record(path):
    """Whether a PATH the person gave is itself a record or a directory of
    them: naming `docs/adr` asks for what is in it, naming `docs` does not."""
    return is_record(path) or path.casefold().split("/")[-1] in RECORD_DIRS


def clean(word, link=False):
    """The path a word names, or None when it is not one this script can look
    up. A link target is taken as written; a word in running text or code has
    to look like a path -- a slash, or a file name with an extension -- since
    most words in backticks are not paths at all."""
    word = LOCATOR.sub("", ROOT_VARIABLE.sub("", word.strip())).rstrip(".,:;!?")
    if word.startswith("./"):
        word = word[2:]
    if not word or word.startswith("/") or "//" in word or not PATH_CHARS.match(word):
        return None
    if link or "/" in word or BARE_FILE.match(word):
        return word
    return None


def _label(text):
    text = "".join(ch for ch in " ".join(text.split()) if ch.isprintable())
    return (text[:77] + "...") if len(text) > 80 else text or TOP


def references(text):
    """Every Ref in a document, in order. Inside a fenced block each word is
    a candidate, since that is where commands live; outside one, only inline
    code and link targets are."""
    heading, section, fence = TOP, 0, None
    for number, line in enumerate(LINE_BREAK.split(text.lstrip("﻿")), 1):
        if fence is None:
            opened = FENCE_OPEN.match(line)
            if opened:
                fence = opened.group(1) or opened.group(2)
                continue
        else:
            # The same character, at least as many of them: a shorter run
            # inside a block is part of what the block is showing.
            closed = FENCE_CLOSE.match(line)
            if closed and closed.group(1)[0] == fence[0] and len(closed.group(1)) >= len(fence):
                fence = None
                continue
            for word in WORD_BREAK.split(line):
                token = clean(word)
                if token:
                    yield Ref(number, heading, token, False, section)
            continue
        title = HEADING.match(line)
        if title:
            heading, section = _label(title.group(1)), number
        for span in CODE_SPAN.finditer(line):
            for word in WORD_BREAK.split(span.group(1)):
                token = clean(word)
                if token:
                    yield Ref(number, heading, token, False, section)
        targets = [m.group(1) for m in LINK.finditer(line)]
        definition = LINK_DEFINITION.match(line)
        if definition:
            targets.append(definition.group(1))
        for target in targets:
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            token = clean(target.lstrip("/"), link=True)
            if token:
                yield Ref(number, heading, token, target.startswith("/"), section, True)


def candidates(doc, ref):
    """Where the reference could point, nearest first."""
    rel = ref.token.rstrip("/")
    base = posixpath.dirname(doc)
    bases = [""] if ref.rooted else [base]
    while base and not ref.rooted and not ref.link:
        base = posixpath.dirname(base)
        bases.append(base)
    seen = set()
    for base in bases:
        path = posixpath.normpath(posixpath.join(base, rel))
        if path in (".", "..") or path.startswith("../") or path in seen:
            continue
        seen.add(path)
        yield path


def _why(path, tree, history, change):
    if change is not None and path in change.removed:
        new = change.removed[path]
        return "renamed to %s in this change" % new if new else "deleted in this change"
    commit, new = history.gone.get(path, ("", None))
    # A file renamed twice is under its last name, or nowhere: the first
    # rename alone would send the reader to another path that is gone.
    seen = {path}
    while new is not None and new not in tree.files and new in history.gone and new not in seen:
        seen.add(new)
        commit, new = history.gone[new]
    if new is None:
        return "deleted in %s" % commit if commit else "no longer there"
    return "renamed to %s in %s" % (new, commit) if new in tree.files else "no longer there"


def _removed_by(change, path):
    return path in change.removed or any(r.startswith(path + "/") for r in change.removed)


def _resolved_before(doc, ref, bare, tree, change):
    """The path the reference resolved to before this change, or None when
    it resolved to nothing then either. Looked for the way `resolve` looks
    now, from where the document was, among what was there."""
    for path in candidates(change.renamed.get(doc, doc), ref):
        here = path in tree.files or path in tree.dirs
        if _removed_by(change, path) or (
                here and path not in change.added and path not in change.renamed):
            return path
    if bare:
        # Any file of that name answered for a bare one; the ones still here
        # would answer now, so only a removed one can have been the last.
        name = ref.token.rstrip("/")
        for path in sorted(change.removed):
            if posixpath.basename(path) == name:
                return path
    return None


def resolve(doc, ref, tree, history, change=None, base_tokens=None):
    """(the file the reference names or None, None) when it is there,
    (None, Dead) when it was there once, and (None, None) when it never was."""
    paths = list(candidates(doc, ref))
    for path in paths:
        if path in tree.files:
            return path, None
        if path in tree.dirs:
            return None, None
    name = ref.token.rstrip("/")
    bare = "/" not in name and not ref.link
    if bare and name in tree.names:
        same = tree.names[name]
        return (same[0] if len(same) == 1 else None), None
    # A bare name is looked for in history beside the document only: further
    # up it is as likely a file of the reader's own project (`config.json`)
    # as this repository's deleted one.
    gone = None
    for path in (paths[:1] if bare else paths):
        if path in history.order or path in history.dirs:
            gone = Dead(doc, ref, path, _why(path, tree, history, change))
            break
    if change is None:
        return None, gone
    before = (base_tokens or {}).get(doc)
    if doc in change.added or (before is not None and ref.token not in before):
        return None, gone       # a sentence this change wrote
    path = _resolved_before(doc, ref, bare, tree, change)
    if path is None:
        # Dead before the change and dead after it: not this change's doing.
        return None, gone._replace(mine=False) if gone is not None else None
    # Still there means the document went somewhere it cannot be seen from.
    there = path in tree.files or path in tree.dirs
    return None, Dead(doc, ref, path, MOVED if there else _why(path, tree, history, change))


def _name_status(text):
    """(letter, path, renamed-to or None) for each line of `--name-status`
    output; a line that is not one is skipped."""
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) >= 3 and fields[0][:1] in ("R", "C"):
            yield fields[0][0], fields[1], fields[2]
        elif len(fields) == 2 and fields[0][:1] in ("A", "M", "D", "T"):
            yield fields[0][0], fields[1], None


def read_history(log_text):
    order, gone, position, commit = {}, {}, -1, ""
    for block in log_text.split("\n@"):
        head, _, body = block.partition("\n")
        commit = head.lstrip("@").strip()
        position += 1
        for letter, path, new in _name_status(body):
            # Only when this is the newest thing that happened to the path:
            # one deleted and added back since did not go in that commit.
            last = path not in order
            order.setdefault(path, position)
            if new is not None:
                order.setdefault(new, position)
            if last and letter == "D":
                gone[path] = (commit, None)
            elif last and letter == "R":
                gone[path] = (commit, new)
    dirs = set()
    for path in order:
        parts = path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return History(order, gone, frozenset(dirs))


def read_change(base, diff_text):
    removed, renamed, modified, added, count = {}, {}, set(), set(), 0
    for letter, path, new in _name_status(diff_text):
        count += 1
        if letter == "D":
            removed[path] = None
        elif letter == "R":
            removed[path] = new
            renamed[new] = path
            modified.add(new)
        elif letter == "A" or letter == "C":
            added.add(new or path)
        else:
            modified.add(path)
    return Change(base, removed, frozenset(modified), frozenset(added), count, renamed)


def check(docs, tree, history, change=None, base_tokens=None):
    """(dead, review) over `docs`, a list of (path, text). `review` is a list
    of (doc, first line, heading, sorted files, note)."""
    dead, review = [], []
    for doc, text in docs:
        if change is not None and doc in change.added:
            sections = None     # written in this change, so there is nothing older to reread
        elif change is None and doc not in history.order:
            sections = None     # not committed yet: newer than everything
        else:
            sections = {}
        seen = set()
        for ref in references(text):
            path, gone = resolve(doc, ref, tree, history, change, base_tokens)
            # `[`x.py`](x.py)` names the path twice on one line and is one finding.
            if gone is not None and (ref.line, ref.token) not in seen:
                seen.add((ref.line, ref.token))
                dead.append(gone)
            if (path is None or sections is None or path == doc
                    or path.lower().endswith(DOC_EXTENSIONS)):
                continue
            if change is not None:
                newer = path in change.modified
            else:
                newer = history.order.get(path, len(history.order)) < history.order[doc]
            if newer:
                # By the heading's line, not its text: two sections may both
                # be called "Usage".
                first, heading, files = sections.setdefault(
                    ref.section, (ref.line, ref.heading, set()))
                files.add(path)
        note = "document also changed" if change is not None and doc in change.modified else ""
        for line, heading, files in (sections or {}).values():
            review.append((doc, line, heading, sorted(files), note))
    return dead, sorted(review)


def render(dead, review, counts, change=None, skipped=()):
    """The lines to print and the exit code."""
    before = 0
    if change is not None:
        before = sum(1 for d in dead if not d.mine)
        dead = [d for d in dead if d.mine]
    facts = ["%d documents" % counts["documents"]]
    if skipped:
        facts.append("%d records skipped" % len(skipped))
    if counts.get("ignored"):
        facts.append("%d now ignored" % counts["ignored"])
    if counts["unread"]:
        facts.append("%d unreadable" % counts["unread"])
    if change is not None:
        facts.insert(0, "%d changed files" % change.count)
        if before:
            facts.append("%d dead before this change" % before)
    against = " against %s" % change.base if change is not None else ""
    lines = ["docs: %d dead, %d to review%s (%s)" % (
        len(dead), len(review), against, ", ".join(facts))]
    for d in sorted(dead, key=lambda d: (d.doc, d.ref.line, d.ref.token)):
        lines.append("dead    %s:%d § %s: %s (%s)" % (
            d.doc, d.ref.line, d.ref.heading, d.ref.token, d.why))
    for doc, line, heading, files, note in review:
        lines.append("review  %s:%d § %s: %s%s" % (
            doc, line, heading, ", ".join(files), " (%s)" % note if note else ""))
    if skipped:
        more = " and %d more" % (len(skipped) - 5) if len(skipped) > 5 else ""
        lines.append("records skipped: %s%s" % (", ".join(skipped[:5]), more))
    # A file name is whatever the repository holds, control characters included.
    lines = ["".join(ch if ch.isprintable() else "?" for ch in line) for line in lines]
    return lines, (2 if dead else 0)


def _unsupported(reason):
    print("docs: unsupported (%s)" % reason)
    return 0


def _wanted(path, wanted):
    return any(path == w or path.startswith(w + "/") for w in wanted)


def _listed(top, *flags):
    """The paths `git ls-files -z <flags>` prints, or None when it failed."""
    done = preflight.git(top, "ls-files", "-z", *flags, timeout=codemap_inventory.LIST_TIMEOUT)
    if done is None or done.returncode != 0:
        return None
    return frozenset(path for path in done.stdout.split("\0") if path)


def _ignored(top, dead, history):
    """The dead paths git's ignore rules now cover. Asked of the rules, not
    of the disk, so a checkout that never built the file answers the same."""
    asked = {}
    for d in dead:
        # A directory is asked about as one, or a `build/` rule passes it by.
        asked[d.path if d.path in history.order else d.path + "/"] = d.path
    names, found = sorted(asked), set()
    for start in range(0, len(names), 100):
        done = preflight.git(top, "-c", "core.quotepath=off", "check-ignore", "--",
                             *names[start:start + 100], timeout=HISTORY_TIMEOUT)
        if done is not None and done.returncode == 0:
            found.update(asked[line] for line in done.stdout.splitlines() if line in asked)
    return found


def main(argv=None):
    # A `dead` line quotes a heading, in whatever alphabet the document uses;
    # a piped Windows stdout defaults to the ANSI codepage.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = preflight.ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--base")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args(argv)
    # The ref goes to git as an argument, so one shaped like an option would
    # be read as one.
    if args.base is not None and (not args.base or args.base.startswith("-")):
        ap.error("--base takes a ref, not %r" % args.base)

    done = preflight.git(args.project_dir, "rev-parse", "--show-toplevel",
                         "--is-shallow-repository", timeout=HISTORY_TIMEOUT)
    if done is None:
        return _unsupported("git did not answer")
    if done.returncode != 0:
        return _unsupported("not a git repository")
    top, _, shallow = done.stdout.strip().partition("\n")
    # Without the commits that deleted a path, every dead reference reads as
    # an example that never existed, and `0 dead` would be a guess.
    if shallow.strip() == "true":
        return _unsupported("shallow clone")
    try:
        listed = codemap_inventory.list_tracked(top)
    except (codemap_inventory.NotARepository, codemap_inventory.GitFailed):
        return _unsupported("git could not list the tracked files")
    deleted = _listed(top, "-d")
    untracked = _listed(top, "-o", "--exclude-standard")
    if deleted is None or untracked is None:
        return _unsupported("git could not list the tracked files")
    present = frozenset(path for mode, path, utf8 in listed) - deleted
    files = present | untracked
    dirs, names = set(), {}
    for path in sorted(files):
        parts = path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        names.setdefault(parts[-1], []).append(path)
    tree = Tree(files, frozenset(dirs), names)

    wanted = [posixpath.normpath(p.replace("\\", "/")) for p in args.paths]
    wanted = [w for w in wanted if w != "."]    # the root is every document
    records_wanted = [w for w in wanted if _names_a_record(w)]
    top_real = os.path.realpath(top)
    docs, skipped, unread = [], [], 0
    # A document not yet added is read like any other: the change under
    # review is often still sitting in the working tree.
    entries = [entry for entry in listed if entry[1] in present]
    entries += [("100644", path, True) for path in sorted(untracked)]
    for mode, path, utf8 in entries:
        if not path.lower().endswith(DOC_EXTENSIONS):
            continue
        if wanted and not _wanted(path, wanted):
            continue
        if is_record(path) and not _wanted(path, records_wanted):
            skipped.append(path)
            continue
        got = None
        if codemap_inventory.skip_reason(mode, utf8) is None:
            got = codemap_inventory.read_tracked(top_real, path,
                                                 limit=codemap_inventory.MAX_PARSE_BYTES)
        if (got is None or got.reason is not None
                or got.size > codemap_inventory.MAX_PARSE_BYTES):
            unread += 1
            continue
        docs.append((path, got.data.decode("utf-8", errors="replace")))
    if wanted and not docs and not skipped and not unread:
        print("docs_check.py: no Markdown under: %s" % ", ".join(args.paths),
              file=sys.stderr)
        return 1

    log = preflight.git(top, "-c", "core.quotepath=off", "log", "--name-status", "-M",
                        "--format=@%h", timeout=HISTORY_TIMEOUT)
    if log is None or log.returncode != 0:
        return _unsupported("git history could not be read")
    history = read_history(log.stdout)

    change, base_tokens = None, {}
    if args.base is None:
        # Work not committed yet is newer than every commit, on both sides:
        # an edited file puts its sections up, an edited document takes its
        # own down.
        dirty = preflight.git(top, "-c", "core.quotepath=off", "diff", "--name-only", "HEAD",
                              "--", timeout=HISTORY_TIMEOUT)
        if dirty is None or dirty.returncode != 0:
            return _unsupported("git could not list uncommitted work")
        order = dict(history.order)
        order.update((path, -1) for path in dirty.stdout.splitlines() if path)
        history = history._replace(order=order)
    else:
        point = preflight.git(top, "merge-base", "HEAD", args.base, timeout=HISTORY_TIMEOUT)
        if point is None:
            return _unsupported("git did not answer")
        if point.returncode != 0 or not point.stdout.strip():
            print("docs_check.py: no merge base between HEAD and %s" % args.base,
                  file=sys.stderr)
            return 1
        point = point.stdout.strip()
        diff = preflight.git(top, "-c", "core.quotepath=off", "diff", "--name-status", "-M",
                             point, "--", timeout=HISTORY_TIMEOUT)
        if diff is None or diff.returncode != 0:
            return _unsupported("git could not list the change")
        change = read_change(args.base, diff.stdout)
        # `git diff` does not list what was never added; it is new all the same.
        change = change._replace(added=change.added | untracked)
        # What each changed document named before the change: a path it
        # names only now is a sentence this change wrote.
        for doc, _ in docs:
            if doc in change.modified:
                shown = preflight.git(top, "show",
                                      "%s:%s" % (point, change.renamed.get(doc, doc)),
                                      timeout=HISTORY_TIMEOUT)
                if shown is not None and shown.returncode == 0:
                    base_tokens[doc] = {ref.token for ref in references(shown.stdout)}

    dead, review = check(docs, tree, history, change, base_tokens)
    ignored = _ignored(top, dead, history)
    dead = [d for d in dead if d.path not in ignored]
    counts = {"documents": len(docs), "unread": unread, "ignored": len(ignored)}
    lines, code = render(dead, review, counts, change, skipped)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
