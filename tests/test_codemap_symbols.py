"""AC5: symbol extraction per language, and a recorded reason for every file
that cannot be parsed."""
import codemap_symbols as sym

PY = b'''\
import os
import json as j
from . import sibling
from ..pkg import thing


class Outer(Base):
    def method(self, a, b=1) -> int:
        def inner():
            pass
        return a

    class Nested:
        pass


def top(x: int, *args, key=None) -> str:
    return str(x)


async def go():
    pass
'''


def _by_qualified(extraction):
    return {s["qualified_name"]: s for s in extraction.symbols}


def test_python_symbols_have_kind_lines_and_signature():
    ex = sym.extract("m.py", "python", PY)
    assert (ex.backend, ex.confidence, ex.reason) == ("python-ast", "exact", None)
    by = _by_qualified(ex)
    assert set(by) == {"Outer", "Outer.method", "Outer.Nested", "top", "go"}
    assert (by["Outer"]["kind"], by["Outer"]["start_line"], by["Outer"]["end_line"]) == \
        ("class", 7, 14)
    assert by["Outer.method"]["kind"] == "method"
    assert (by["Outer.method"]["start_line"], by["Outer.method"]["end_line"]) == (8, 11)
    assert by["Outer.method"]["signature"] == "(self, a, b=1) -> int"
    assert by["Outer.Nested"]["kind"] == "class"
    assert by["top"]["kind"] == "function"
    assert by["top"]["signature"] == "(x: int, *args, key=None) -> str"
    assert by["go"]["kind"] == "function"
    record = by["top"]
    assert record["id"] == "python:m.py:top"
    assert record["path"] == "m.py"
    assert record["backend"] == "python-ast" and record["confidence"] == "exact"


def test_python_imports_include_relative_levels():
    ex = sym.extract("m.py", "python", PY)
    assert sorted(ex.imports) == [".", "..pkg", "json", "os"]


GO = b'''\
package main

import "fmt"
import (
\talias "net/http"
\t"os"
)

type Server struct {
\tname string
}

var Version = "1"
const Max = 3

func main() {
\tfmt.Println("x")
}

func (s *Server) Handle(w int) error {
\treturn nil
}
'''


def test_go_top_level_declarations_are_heuristic():
    ex = sym.extract("main.go", "go", GO)
    assert (ex.backend, ex.confidence, ex.reason) == ("go-lines", "heuristic", None)
    by = _by_qualified(ex)
    assert set(by) == {"Server", "Version", "Max", "main", "Server.Handle"}
    assert by["Server"]["kind"] == "type"
    assert by["Version"]["kind"] == "variable"
    assert by["main"]["kind"] == "function" and by["main"]["start_line"] == 16
    assert by["Server.Handle"]["kind"] == "method"
    assert by["main"]["end_line"] is None
    assert by["main"]["backend"] == "go-lines" and by["main"]["confidence"] == "heuristic"
    assert sorted(ex.imports) == ["fmt", "net/http", "os"]


TS = b'''\
import { a } from './a';
import b from "b";
const c = require('c');

export function run(x: number): void {
  const inner = 1;
}

export default class Widget {
  method() {}
}

export interface Props { a: string }
type Id = string;
export const handler = (e) => e;
export async function load() {}
enum Color { Red }
'''


def test_typescript_top_level_declarations_are_heuristic():
    ex = sym.extract("w.ts", "typescript", TS)
    assert (ex.backend, ex.confidence, ex.reason) == ("ts-lines", "heuristic", None)
    by = _by_qualified(ex)
    assert set(by) == {"c", "run", "Widget", "Props", "Id", "handler", "load", "Color"}
    assert by["run"]["kind"] == "function"
    assert by["Widget"]["kind"] == "class"
    assert by["Props"]["kind"] == "interface"
    assert by["Id"]["kind"] == "type"
    assert by["handler"]["kind"] == "variable"
    assert by["Color"]["kind"] == "enum"
    assert sorted(ex.imports) == ["./a", "b", "c"]


def test_javascript_uses_the_same_adapter():
    ex = sym.extract("w.js", "javascript", b"function f() {}\n")
    assert (ex.backend, ex.confidence) == ("ts-lines", "heuristic")
    assert [s["name"] for s in ex.symbols] == ["f"]


def test_unsupported_language_records_reason_only():
    ex = sym.extract("README.md", "other", b"# hi\n")
    assert ex.reason == "unsupported-language"
    assert ex.symbols == [] and ex.backend is None and ex.confidence is None


def test_undecodable_python_records_reason():
    ex = sym.extract("m.py", "python", b'x = "\xff"\n')
    assert ex.reason == "undecodable"
    assert ex.symbols == []


def test_undecodable_go_records_reason():
    assert sym.extract("m.go", "go", b"package \xff\n").reason == "undecodable"


def test_python_syntax_error_records_line():
    ex = sym.extract("m.py", "python", b"x = 1\ndef (:\n")
    assert ex.reason == "syntax-error at line 2"
    assert ex.symbols == []


def test_empty_python_file_has_no_symbols_and_no_reason():
    ex = sym.extract("m.py", "python", b"")
    assert ex.symbols == [] and ex.reason is None


def test_go_signature_starts_after_the_matched_name():
    # `Read` is also the start of `Reader`, and `f` of `func`: the signature
    # must come from where the name matched, not from its first look-alike.
    data = (b"package p\n\n"
            b"func (r *Reader) Read(p []byte) (int, error) {\n}\n"
            b"type Foo struct {\n}\n"
            b"func f() {\n}\n")
    by = _by_qualified(sym.extract("p.go", "go", data))
    assert by["Reader.Read"]["signature"] == "(p []byte) (int, error)"
    assert by["Foo"]["signature"] == " struct"     # the space keeps `Foo struct` apart
    assert by["f"]["signature"] == "()"


def test_typescript_signature_starts_after_the_matched_name():
    data = (b"export function e(x: number): void {\n}\n"
            b"export const t = 1;\n"
            b"export class A extends B {\n}\n")
    by = _by_qualified(sym.extract("w.ts", "typescript", data))
    assert by["e"]["signature"] == "(x: number): void"
    assert by["t"]["signature"] == " = 1;"
    assert by["A"]["signature"] == " extends B"
