"""Lays file and symbol records out as Markdown that fits a token budget.

A pure function: records in, texts out, nothing read or written. The same
input always gives the same text (no clock, no ordering left to a dict), which
is what lets an incremental update be compared byte for byte with a rebuild.

Only files that have symbols appear in the map; every file, symbol-less or
not, is in files.jsonl.
"""
import hashlib
import re

import codemap_store as store
import preflight

CHARS_PER_TOKEN = 4
BUDGET_TOKENS = 1000     # a constant: no requirement varies it
TOLERANCE_TOKENS = 100

# The map names files the store writes; built from the store's own names so a
# rename there cannot leave the map pointing at a path that does not exist.
_BASE = "/".join(store.INDEX_PARTS)
SYMBOLS_POINTER = "%s/%s" % (_BASE, store.SYMBOLS_NAME)
FILES_POINTER = "%s/%s" % (_BASE, store.FILES_NAME)
SHARD_DIR = "%s/packages/" % _BASE
ROOT = "(root)"


def _shown(text):
    """Paths, names and signatures come from the repository's own files, and an
    agent reads this map to choose what to open next; escaped, none of them can
    add a heading or a `-> <path>` row of its own."""
    return preflight.escape_control_chars(text)


def _symbol_line(sym):
    start, end = sym["start_line"], sym.get("end_line")
    span = "L%d" % start if end in (None, start) else "L%d-%d" % (start, end)
    return "%s %s %s%s" % (span, sym["kind"], _shown(sym["qualified_name"]),
                           _shown(sym.get("signature") or ""))


def _file_blocks(files, by_path):
    """[(header line, [symbol lines])] for each file, in path order."""
    blocks = []
    for f in files:
        lines = [_symbol_line(s) for s in by_path[f["path"]]]
        header = "## %s (%s, %s)" % (_shown(f["path"]), f["language"], f.get("confidence"))
        blocks.append((header, lines))
    return blocks


def _more_symbols(n):
    """The truncation line of a group, the same text whether it is measured
    for the space it needs or written."""
    return "… %d more symbols: Grep %s\n" % (n, SYMBOLS_POINTER)


def _more_packages(n):
    return "… %d more packages: Grep %s\n" % (n, FILES_POINTER)


def _group_text(title, files, by_path, limit=None, n_files=None):
    """The Markdown for `files`. With `limit` (characters), stops adding
    symbol lines when the next one would not fit alongside the pointer line."""
    blocks = _file_blocks(files, by_path)
    total = sum(len(lines) for _, lines in blocks)
    head = "%s\n%d files, %d symbols\n" % (
        title, len(files) if n_files is None else n_files, total)
    full = head + "".join("\n%s\n%s\n" % (h, "\n".join(ls)) for h, ls in blocks)
    if limit is None or len(full) <= limit:
        return full
    marker = _more_symbols(total)
    out, included = head, 0
    for header, lines in blocks:
        opened = False
        for line in lines:
            add = ("" if opened else "\n%s\n" % header) + line + "\n"
            if len(out) + len(add) + len(marker) > limit:
                break
            out += add
            opened = True
            included += 1
        else:
            continue
        break
    return out + _more_symbols(total - included)


def _dir_of(path, depth):
    parts = path.split("/")
    return parts[depth] if len(parts) > depth + 1 else None


def _split(files, prefix, by_path, limit, groups):
    """Appends (prefix, files, text) for each shard `files` (all under
    `prefix`) needs: the whole group when it fits, else its directly contained
    files and then each subdirectory, recursively."""
    label = _shown("/".join(prefix)) or ROOT
    title = "# codemap shard: %s" % label
    text = _group_text(title, files, by_path)
    if len(text) <= limit:
        groups.append((prefix, files, text))
        return
    depth = len(prefix)
    direct = [f for f in files if _dir_of(f["path"], depth) is None]
    subdirs = sorted({_dir_of(f["path"], depth) for f in files} - {None})
    if not subdirs:
        groups.append((prefix, files, _group_text(title, files, by_path, limit)))
        return
    if direct:
        groups.append((prefix, direct, _group_text(title, direct, by_path, limit)))
    for name in subdirs:
        inside = [f for f in files if _dir_of(f["path"], depth) == name]
        _split(inside, prefix + [name], by_path, limit, groups)


_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_SHARD_NAME = 100


def _shard_names(groups):
    """One file name per group, in group order. The readable `a--b` when it is
    safe and no other group flattens to the same name (ignoring case, as
    Windows and macOS file systems do); otherwise a bounded slug plus a hash of
    the real path, so `a/b` and `a--b`, `Foo` and `foo`, or a chain of long
    directory names never share a file or overflow a name limit."""
    plain = ["--".join(prefix) or ROOT for prefix, _, _ in groups]
    seen = {}
    for name in plain:
        seen[name.lower()] = seen.get(name.lower(), 0) + 1
    names = []
    for (prefix, _, _), name in zip(groups, plain):
        if (seen[name.lower()] > 1 or len(name) > MAX_SHARD_NAME
                or _UNSAFE_NAME.search(name) or name.endswith((".", " "))):
            digest = hashlib.sha256("/".join(prefix).encode("utf-8", "replace")).hexdigest()[:8]
            name = "%s~%s" % (_UNSAFE_NAME.sub("_", name)[:60], digest)
        names.append(name)
    return names


def render(files: list, symbols: list, budget: int, tolerance: int) -> dict:
    """{"repo-map.md": text} when everything fits budget + tolerance, else
    {"repo-map.md": index, "packages/<dir>.md": shard, ...}."""
    limit = (budget + tolerance) * CHARS_PER_TOKEN
    by_path = {}
    for s in symbols:
        by_path.setdefault(s["path"], []).append(s)
    for items in by_path.values():
        items.sort(key=lambda s: (s["start_line"], s["qualified_name"]))
    with_symbols = sorted((f for f in files if f["path"] in by_path), key=lambda f: f["path"])
    total_files = len(files)
    # The header counts every file, not only the ones that have symbols.
    full = _group_text("# codemap repo map", with_symbols, by_path, n_files=total_files)
    if len(full) <= limit:
        return {"repo-map.md": full}

    groups = []
    root_direct = [f for f in with_symbols if _dir_of(f["path"], 0) is None]
    if root_direct:
        _split(root_direct, [], by_path, limit, groups)
    for name in sorted({_dir_of(f["path"], 0) for f in with_symbols} - {None}):
        _split([f for f in with_symbols if _dir_of(f["path"], 0) == name], [name],
               by_path, limit, groups)

    out, rows = {}, []
    for (prefix, group_files, text), name in zip(groups, _shard_names(groups)):
        out["packages/%s.md" % name] = text
        count = sum(len(by_path[f["path"]]) for f in group_files)
        rows.append("- %s: %d files, %d symbols -> %s%s.md"
                    % (_shown("/".join(prefix)) or ROOT, len(group_files), count, SHARD_DIR, name))
    index_head = "# codemap repo map\nbudget %d tokens, %d files, split into %d shards\n\n" % (
        budget, total_files, len(rows))
    index = index_head + "\n".join(rows) + "\n"
    if len(index) > limit:
        reserve = len(_more_packages(len(rows)))
        kept, size = [], len(index_head) + reserve
        for row in rows:
            if size + len(row) + 1 > limit:
                break
            kept.append(row)
            size += len(row) + 1
        index = index_head + "\n".join(kept) + "\n" + \
            _more_packages(len(rows) - len(kept))
    result = {"repo-map.md": index}
    result.update(out)
    return result
