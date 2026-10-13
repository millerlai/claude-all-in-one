"""Pulls top-level declarations and imports out of one file's bytes.

A pure function of its arguments: no file, no git, no shared state. Python goes
through `ast` (exact); Go and TypeScript/JavaScript go through line patterns on
unindented lines only (heuristic, and labelled so).

Failures that are expected for a file in the wild (a syntax error, bytes that
are not text) come back as an empty extraction with a `reason`. Anything else
is not caught here: the caller records that file as partial.
"""
import ast
import re
from typing import NamedTuple, Optional


class Extraction(NamedTuple):
    symbols: list            # symbol records (dict)
    imports: list            # list of str
    backend: Optional[str]   # "python-ast" | "go-lines" | "ts-lines" | None
    confidence: Optional[str]  # "exact" | "heuristic" | None
    reason: Optional[str]    # None, or "unsupported-language" | "undecodable" | "syntax-error at line N"


def _failed(reason):
    return Extraction([], [], None, None, reason)


# The map shows a signature for orientation. Without a cap one minified line
# becomes a signature as long as the file, and every later symbol in that
# shard falls off the end of the map behind it.
MAX_SIGNATURE = 200


def _record(language, path, qualified, kind, start, end, signature, backend, confidence):
    if len(signature) > MAX_SIGNATURE:
        signature = signature[:MAX_SIGNATURE - 3] + "..."
    return {"id": "%s:%s:%s" % (language, path, qualified),
            "name": qualified.rsplit(".", 1)[-1], "qualified_name": qualified,
            "kind": kind, "path": path, "start_line": start, "end_line": end,
            "signature": signature, "backend": backend, "confidence": confidence}


# --- Python ---------------------------------------------------------------

def _py_signature(node):
    if isinstance(node, ast.ClassDef):
        if not node.bases or not hasattr(ast, "unparse"):
            return ""
        return "(%s)" % ", ".join(ast.unparse(b) for b in node.bases)
    if not hasattr(ast, "unparse"):
        return ""      # Python before 3.9: the name alone is the signature
    text = "(%s)" % ast.unparse(node.args)
    if node.returns is not None:
        text += " -> %s" % ast.unparse(node.returns)
    return text


# ast.TryStar is `try`/`except*`, Python 3.11+.
_TRY_NODES = (ast.Try,) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())


def _py_walk(body, prefix, in_class, path, out):
    for node in body:
        if isinstance(node, ast.ClassDef):
            qualified = prefix + node.name
            out.append(_record("python", path, qualified, "class", node.lineno,
                               node.end_lineno, _py_signature(node), "python-ast", "exact"))
            _py_walk(node.body, qualified + ".", True, path, out)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "method" if in_class else "function"
            out.append(_record("python", path, prefix + node.name, kind, node.lineno,
                               node.end_lineno, _py_signature(node), "python-ast", "exact"))
        elif isinstance(node, (ast.If, ast.With, ast.AsyncWith)):
            # `if TYPE_CHECKING:`, a version check, a `with` around definitions:
            # their declarations are still top-level names, and a file marked
            # exact must not leave them out.
            _py_walk(node.body, prefix, in_class, path, out)
            _py_walk(getattr(node, "orelse", []), prefix, in_class, path, out)
        elif isinstance(node, _TRY_NODES):
            for block in (node.body, *(h.body for h in node.handlers), node.orelse,
                          node.finalbody):
                _py_walk(block, prefix, in_class, path, out)


def _python(path, data):
    try:
        tree = ast.parse(data)
    except SyntaxError as exc:
        if str(exc.msg).startswith("(unicode error)") or "null bytes" in str(exc.msg):
            return _failed("undecodable")
        return _failed("syntax-error at line %d" % (exc.lineno or 0))
    except ValueError:      # Python before 3.12 raises this for a null byte
        return _failed("undecodable")
    symbols = []
    _py_walk(tree.body, "", False, path, symbols)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add("." * node.level + (node.module or ""))
    return Extraction(symbols, sorted(imports), "python-ast", "exact", None)


# --- line-pattern adapters -------------------------------------------------

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def editor_lines(text):
    """`text` split where an editor, git and the Read tool start a new line.
    `str.splitlines` also splits at \\x0b, \\x0c, \\x1c-\\x1e, \\x85, U+2028 and
    U+2029, and every one of those before a match would push the reported
    line number past the one an agent opens."""
    return _LINE_BREAK.split(text)


def _decode(data):
    try:
        return data.decode("utf-8").lstrip("﻿")
    except UnicodeDecodeError:
        return None


GO_METHOD = re.compile(r"^func\s*\(\s*(?:\w+\s+)?\*?(\w+)(?:\[[^\]]*\])?\s*\)\s*(\w+)")
GO_FUNC = re.compile(r"^func\s+(\w+)")
GO_TYPE = re.compile(r"^type\s+(\w+)")
GO_VAR = re.compile(r"^(?:var|const)\s+(\w+)")
GO_IMPORT_ONE = re.compile(r'^import\s+(?:[\w.]+\s+)?"([^"]+)"')
GO_IMPORT_ITEM = re.compile(r'^\s*(?:[\w.]+\s+)?"([^"]+)"')


def _tail(line, end):
    """What follows the name on the declaration line, without a trailing `{`.
    `end` is where the regex matched the name: searching the line for the name
    again finds a look-alike first (`Read` in `Reader`, `f` in `func`). A space
    after the name stays, so `Foo` and ` struct` do not fuse in the map."""
    return line[end:].rstrip().rstrip("{").rstrip()


def _go(path, data):
    text = _decode(data)
    if text is None:
        return _failed("undecodable")
    symbols, imports, in_block = [], [], False
    for number, line in enumerate(editor_lines(text), start=1):
        if in_block:
            if line.startswith(")"):
                in_block = False
                continue
            item = GO_IMPORT_ITEM.match(line)
            if item:
                imports.append(item.group(1))
            continue
        if line.startswith("import ("):
            in_block = True
            continue
        one = GO_IMPORT_ONE.match(line)
        if one:
            imports.append(one.group(1))
            continue
        for pattern, kind in ((GO_METHOD, "method"), (GO_FUNC, "function"),
                              (GO_TYPE, "type"), (GO_VAR, "variable")):
            hit = pattern.match(line)
            if not hit:
                continue
            if kind == "method":
                qualified, group = "%s.%s" % (hit.group(1), hit.group(2)), 2
            else:
                qualified, group = hit.group(1), 1
            symbols.append(_record("go", path, qualified, kind, number, None,
                                   _tail(line, hit.end(group)), "go-lines", "heuristic"))
            break
    return Extraction(symbols, sorted(set(imports)), "go-lines", "heuristic", None)


TS_DECL = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:const\s+)?(function|class|interface|type|enum)\*?\s+(\w+)")
TS_VAR = re.compile(r"^(?:export\s+)?(?:declare\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=")
TS_FROM = re.compile(r"""^(?:import\b|\}).*?\bfrom\s+['"]([^'"]+)['"]""")
TS_BARE = re.compile(r"""^import\s+['"]([^'"]+)['"]""")
TS_REQUIRE = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")


def _ts(path, language, data):
    text = _decode(data)
    if text is None:
        return _failed("undecodable")
    symbols, imports = [], []
    for number, line in enumerate(editor_lines(text), start=1):
        for pattern in (TS_FROM, TS_BARE):
            hit = pattern.match(line)
            if hit:
                imports.append(hit.group(1))
        imports.extend(TS_REQUIRE.findall(line))
        if line[:1].isspace() or not line:
            continue
        decl = TS_DECL.match(line)
        if decl:
            word, name = decl.groups()
            symbols.append(_record(language, path, name, word, number, None,
                                   _tail(line, decl.end(2)), "ts-lines", "heuristic"))
            continue
        var = TS_VAR.match(line)
        if var:
            symbols.append(_record(language, path, var.group(1), "variable", number, None,
                                   _tail(line, var.end(1)), "ts-lines", "heuristic"))
    return Extraction(symbols, sorted(set(imports)), "ts-lines", "heuristic", None)


def extract(path: str, language: str, data: bytes) -> Extraction:
    if language == "python":
        return _python(path, data)
    if language == "go":
        return _go(path, data)
    if language in ("typescript", "javascript"):
        return _ts(path, language, data)
    return _failed("unsupported-language")
