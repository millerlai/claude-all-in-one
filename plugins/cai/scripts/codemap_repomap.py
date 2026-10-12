"""Lays file and symbol records out as Markdown that fits a token budget.

A pure function: records in, texts out, nothing read or written. The same
input always gives the same text (no clock, no ordering left to a dict), which
is what lets an incremental update be compared byte for byte with a rebuild.

Only files that have symbols appear in the map; every file, symbol-less or
not, is in files.jsonl.
"""
CHARS_PER_TOKEN = 4
BUDGET_TOKENS = 1000     # a constant: no requirement varies it
TOLERANCE_TOKENS = 100

SYMBOLS_POINTER = ".cai/codemap/symbols.jsonl"
FILES_POINTER = ".cai/codemap/files.jsonl"
SHARD_DIR = ".cai/codemap/packages/"
ROOT = "(root)"


def estimate_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def _symbol_line(sym):
    start, end = sym["start_line"], sym.get("end_line")
    span = "L%d" % start if end in (None, start) else "L%d-%d" % (start, end)
    return "%s %s %s%s" % (span, sym["kind"], sym["qualified_name"], sym.get("signature") or "")


def _file_blocks(files, by_path):
    """[(header line, [symbol lines])] for each file, in path order."""
    blocks = []
    for f in files:
        lines = [_symbol_line(s) for s in by_path[f["path"]]]
        header = "## %s (%s, %s)" % (f["path"], f["language"], f.get("confidence"))
        blocks.append((header, lines))
    return blocks


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
    marker = "… %d more symbols: Grep %s\n" % (total, SYMBOLS_POINTER)
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
    return out + "… %d more symbols: Grep %s\n" % (total - included, SYMBOLS_POINTER)


def _dir_of(path, depth):
    parts = path.split("/")
    return parts[depth] if len(parts) > depth + 1 else None


def _split(files, prefix, by_path, limit, groups):
    """Appends (prefix, files, text) for each shard `files` (all under
    `prefix`) needs: the whole group when it fits, else its directly contained
    files and then each subdirectory, recursively."""
    label = "/".join(prefix) or ROOT
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
    total_symbols = sum(len(v) for v in by_path.values())
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
    for prefix, group_files, text in groups:
        name = "--".join(prefix) or ROOT
        out["packages/%s.md" % name] = text
        count = sum(len(by_path[f["path"]]) for f in group_files)
        rows.append("- %s: %d files, %d symbols -> %s%s.md"
                    % ("/".join(prefix) or ROOT, len(group_files), count, SHARD_DIR, name))
    index_head = "# codemap repo map\nbudget %d tokens, %d files, split into %d shards\n\n" % (
        budget, total_files, len(rows))
    index = index_head + "\n".join(rows) + "\n"
    if len(index) > limit:
        reserve = len("… %d more packages: Grep %s\n" % (len(rows), FILES_POINTER))
        kept, size = [], len(index_head) + reserve
        for row in rows:
            if size + len(row) + 1 > limit:
                break
            kept.append(row)
            size += len(row) + 1
        index = index_head + "\n".join(kept) + "\n" + \
            "… %d more packages: Grep %s\n" % (len(rows) - len(kept), FILES_POINTER)
    result = {"repo-map.md": index}
    result.update(out)
    return result
