"""Unit 2: resolve_test_command -- AC1-AC5 plus "this repo resolves to pytest".

Every fixture is a tmp_path with no `git init`, so the root falls back to the
directory itself (find_root's documented fallback).
"""
import json
import os
import subprocess
import sys

import pytest

import resolve_test_command as rtc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def on_path(monkeypatch, names):
    monkeypatch.setattr(rtc, "_on_path", lambda name: name in names)


@pytest.fixture(autouse=True)
def _python_on_path(monkeypatch):
    # The pytest launcher depends on PATH (#274); pin it so the rows below do
    # not change with the machine running them.
    on_path(monkeypatch, {"python", "python3", "py"})


def make(tmp_path, files):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return str(tmp_path)


def pairs(result):
    return [(c["command"], c["whole"], c["narrow"], c["origin"])
            for c in result["commands"] or result["candidates"]]


# --- AC1: every entry and marker file, command and source ------------------

TASKFILE_BODY = "version: '3'\ntasks:\n  build:\n    cmds: [x]\n  test:\n    cmds: [y]\n"

SINGLE = [
    ("Makefile", {"Makefile": "test:\n\tpytest\n"},
     ("make test", "", "none", "Makefile")),
    ("Makefile double colon", {"Makefile": "test::\n\tx\n"},
     ("make test", "", "none", "Makefile")),
    ("justfile", {"justfile": "test:\n  cargo t\n"},
     ("just test", "", "none", "justfile")),
    ("justfile with params", {"justfile": "test target:\n  x\n"},
     ("just test", "", "none", "justfile")),
    # #280: make's own names (GNUmakefile, makefile, Makefile) and just's
    # case-insensitive justfile/.justfile, each reported under its real name.
    ("GNUmakefile", {"GNUmakefile": "test:\n\tx\n"},
     ("make test", "", "none", "GNUmakefile")),
    ("makefile lowercase", {"makefile": "test:\n\tx\n"},
     ("make test", "", "none", "makefile")),
    ("GNUmakefile wins over Makefile", {"GNUmakefile": "test:\n\tx\n", "Makefile": "test:\n\tx\n"},
     ("make test", "", "none", "GNUmakefile")),
    ("Justfile capitalised", {"Justfile": "test:\n  x\n"},
     ("just test", "", "none", "Justfile")),
    ("hidden .justfile", {".justfile": "test:\n  x\n"},
     ("just test", "", "none", ".justfile")),
    ("Taskfile", {"Taskfile.yml": "version: '3'\ntasks:\n  build:\n    cmds: [x]\n  test:\n    cmds: [y]\n"},
     ("task test", "", "none", "Taskfile.yml")),
    *[("Taskfile as " + name, {name: TASKFILE_BODY}, ("task test", "", "none", name))
      for name in ("taskfile.yml", "Taskfile.yaml", "taskfile.yaml", "Taskfile.dist.yml",
                   "taskfile.dist.yml", "Taskfile.dist.yaml", "taskfile.dist.yaml")],
    ("Taskfile.yaml wins over Taskfile.dist.yml",
     {"Taskfile.yaml": TASKFILE_BODY, "Taskfile.dist.yml": TASKFILE_BODY},
     ("task test", "", "none", "Taskfile.yaml")),
    ("Taskfile.yml with a test task wins over a Taskfile.yaml without one",
     {"Taskfile.yml": TASKFILE_BODY, "Taskfile.yaml": "version: '3'\ntasks:\n  build:\n    cmds: [x]\n"},
     ("task test", "", "none", "Taskfile.yml")),
    ("a directory named Taskfile.yml is skipped",
     {"Taskfile.yml/keep": "", "Taskfile.yaml": TASKFILE_BODY},
     ("task test", "", "none", "Taskfile.yaml")),
    ("package.json no lockfile", {"package.json": '{"scripts": {"test": "jest"}}'},
     ("npm test", "", "none", "package.json")),
    ("package.json npm", {"package.json": '{"scripts": {"test": "jest"}}', "package-lock.json": "{}"},
     ("npm test", "", "none", "package.json")),
    ("package.json pnpm", {"package.json": '{"scripts": {"test": "jest"}}', "pnpm-lock.yaml": ""},
     ("pnpm test", "", "none", "package.json")),
    ("package.json yarn", {"package.json": '{"scripts": {"test": "jest"}}', "yarn.lock": ""},
     ("yarn test", "", "none", "package.json")),
    ("tox.ini", {"tox.ini": "[tox]\nenvlist = py\n"},
     ("tox", "", "none", "tox.ini")),
    ("noxfile", {"noxfile.py": "import nox\n"},
     ("nox", "", "none", "noxfile.py")),
    ("pyproject pytest", {"pyproject.toml": "[tool.pytest.ini_options]\naddopts = ''\n"},
     ("python -m pytest", "", "paths", "pyproject.toml")),
    ("pytest.ini", {"pytest.ini": "[pytest]\n"},
     ("python -m pytest", "", "paths", "pytest.ini")),
    ("setup.cfg", {"setup.cfg": "[tool:pytest]\nx = 1\n"},
     ("python -m pytest", "", "paths", "setup.cfg")),
    ("go.mod", {"go.mod": "module x\n"},
     ("go test", "./...", "packages", "go.mod")),
    ("Cargo.toml", {"Cargo.toml": '[package]\nname = "p"\n'},
     ("cargo test", "", "none", "Cargo.toml")),
    ("pom.xml", {"pom.xml": "<project/>"},
     ("mvn test", "", "none", "pom.xml")),
    ("gradle", {"build.gradle": "", "gradlew": ""},
     ("./gradlew test", "", "none", "build.gradle")),
    ("gradle kts", {"build.gradle.kts": "", "gradlew": ""},
     ("./gradlew test", "", "none", "build.gradle.kts")),
    ("sln", {"App.sln": ""},
     ("dotnet test", "", "none", "App.sln")),
    ("csproj", {"App.csproj": ""},
     ("dotnet test", "", "none", "App.csproj")),
]


@pytest.mark.parametrize("files,expected", [(f, e) for _, f, e in SINGLE],
                         ids=[n for n, _, _ in SINGLE])
def test_single_detected_command(tmp_path, files, expected):
    result = rtc.resolve(make(tmp_path, files))
    assert result["status"] == "resolved"
    assert result["source"] == "detected"
    assert pairs(result) == [expected]
    assert result["candidates"] == []


NOT_A_CANDIDATE = [
    ("npm placeholder", {"package.json": json.dumps({"scripts": {"test": rtc.NPM_PLACEHOLDER}})}),
    ("package.json without test", {"package.json": '{"scripts": {"build": "x"}}'}),
    ("makefile comment", {"Makefile": "# test:\nbuild:\n"}),
    ("makefile recipe line", {"Makefile": "build:\n\ttest: x\n"}),
    ("makefile variable", {"Makefile": "test := x\n"}),
    ("makefile simple variable", {"Makefile": "test ::= x\n"}),
    ("makefile immediate variable", {"Makefile": "test :::= x\n"}),
    # #280: a rule is `targets : prerequisites` on one line (GNU make, Rule Syntax).
    ("makefile colon on the next line", {"Makefile": "test\n: x\n"}),
    ("makefile colon after a blank line", {"Makefile": "test\n\n:\n"}),
    ("GNUmakefile without test hides a Makefile that has one",
     {"GNUmakefile": "build:\n\tx\n", "Makefile": "test:\n\tx\n"}),
    # #280: just refuses a directory holding several justfiles.
    ("justfile and .justfile together", {"justfile": "test:\n  x\n", ".justfile": "test:\n  x\n"}),
    ("justfile longer name", {"justfile": "test-x:\n  x\n"}),
    ("justfile variable", {"justfile": "test := 'x'\n"}),
    ("taskfile nested test", {"Taskfile.yml": "tasks:\n  build:\n    test:\n      x: 1\n"}),
    ("taskfile.yml without test hides a Taskfile.dist.yml that has one",
     {"Taskfile.yml": "tasks:\n  build:\n    cmds: [x]\n", "Taskfile.dist.yml": TASKFILE_BODY}),
    ("pyproject without pytest section", {"pyproject.toml": "[project]\nname = 'x'\n"}),
    ("gradle without wrapper", {"build.gradle": ""}),
]


@pytest.mark.parametrize("files", [f for _, f in NOT_A_CANDIDATE],
                         ids=[n for n, _ in NOT_A_CANDIDATE])
def test_not_a_candidate(tmp_path, files):
    result = rtc.resolve(make(tmp_path, files))
    assert result["status"] == "unknown"
    assert result["commands"] == [] and result["candidates"] == []


BOM_FILES = [
    ("Makefile", "Makefile", "test:\n\tx\n",
     ("make test", "", "none", "Makefile")),
    ("justfile", "justfile", "test:\n  x\n",
     ("just test", "", "none", "justfile")),
    ("Taskfile.yml", "Taskfile.yml", "tasks:\n  test:\n    cmds: [y]\n",
     ("task test", "", "none", "Taskfile.yml")),
    ("package.json", "package.json", '{"scripts": {"test": "jest"}}',
     ("npm test", "", "none", "package.json")),
    ("pyproject.toml", "pyproject.toml", "[tool.pytest.ini_options]\n",
     ("python -m pytest", "", "paths", "pyproject.toml")),
]


@pytest.mark.parametrize("name,body,expected", [(n, b, e) for _, n, b, e in BOM_FILES],
                         ids=[i for i, _, _, _ in BOM_FILES])
def test_a_utf8_bom_does_not_hide_an_entry(tmp_path, name, body, expected):
    # U+FEFF is not whitespace, so a BOM left in the text hides a line-1 entry.
    (tmp_path / name).write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "resolved"
    assert pairs(result) == [expected]


def test_several_justfiles_are_noted(tmp_path):
    result = rtc.resolve(make(tmp_path, {"justfile": "test:\n  x\n", ".justfile": "test:\n  x\n"}))
    assert any(".justfile" in n and "justfile" in n for n in result["notes"])


def case_sensitive(tmp_path):
    probe = tmp_path / "case-probe"
    probe.write_text("")
    sensitive = not (tmp_path / "CASE-PROBE").exists()
    probe.unlink()
    return sensitive


# Hard-coded rather than read from the code, so swapping two names there fails
# here (#280). Only a case-sensitive filesystem can hold both names of a pair.
PRIORITY_PAIRS = [("GNUmakefile", "makefile"), ("makefile", "Makefile"),
                  ("Taskfile.yml", "taskfile.yml"), ("taskfile.yml", "Taskfile.yaml"),
                  ("Taskfile.yaml", "taskfile.yaml"), ("taskfile.yaml", "Taskfile.dist.yml"),
                  ("Taskfile.dist.yml", "taskfile.dist.yml"),
                  ("taskfile.dist.yml", "Taskfile.dist.yaml"),
                  ("Taskfile.dist.yaml", "taskfile.dist.yaml")]


@pytest.mark.parametrize("first,second", PRIORITY_PAIRS, ids=["%s>%s" % p for p in PRIORITY_PAIRS])
def test_the_earlier_name_of_an_adjacent_pair_wins(tmp_path, first, second):
    if first.lower() == second.lower() and not case_sensitive(tmp_path):
        pytest.skip("this filesystem cannot hold both names")
    body = "test:\n\tx\n" if "akefile" in first else TASKFILE_BODY
    result = rtc.resolve(make(tmp_path, {first: body, second: body}))
    assert result["status"] == "resolved"
    assert pairs(result)[0][3] == first


def test_unparseable_package_json_is_noted_not_raised(tmp_path):
    result = rtc.resolve(make(tmp_path, {"package.json": "{nope", "go.mod": "module x\n"}))
    assert result["status"] == "resolved"
    assert pairs(result) == [("go test", "./...", "packages", "go.mod")]
    assert any("package.json" in n for n in result["notes"])
    assert "nope" not in " ".join(result["notes"])


# --- AC2: declaration wins, order kept, malformed never falls back ----------

def declare(tmp_path, body, extra=None):
    files = {os.path.join(".claude", "cai.json"): body}
    files.update(extra or {})
    return make(tmp_path, files)


def test_declaration_wins_over_detection_and_keeps_order(tmp_path):
    body = json.dumps({"test": {"commands": ["npm test", "python -m pytest"]}})
    result = rtc.resolve(declare(tmp_path, body, {"Makefile": "test:\n\tx\n"}))
    assert result["status"] == "resolved"
    assert result["source"] == "declared"
    assert [c["command"] for c in result["commands"]] == ["npm test", "python -m pytest"]
    assert all(c["origin"] == ".claude/cai.json" for c in result["commands"])


def test_declaration_with_a_utf8_bom_resolves(tmp_path):
    cfg = tmp_path / ".claude" / "cai.json"
    cfg.parent.mkdir()
    body = json.dumps({"test": {"commands": ["make test"]}})
    cfg.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "resolved" and result["source"] == "declared"
    assert pairs(result) == [("make test", "", "none", ".claude/cai.json")]
    # The BOM is stripped, never read as content: a bad body is still invalid.
    cfg.write_bytes(b"\xef\xbb\xbf{bad")
    assert rtc.resolve(str(tmp_path))["status"] == "invalid"


def test_declaration_in_utf16_is_invalid_for_every_reader(tmp_path):
    # #280: Windows PowerShell 5's Out-File writes UTF-16LE with a BOM. json.loads
    # on bytes accepted it while the recorder and ticket.py rejected it; all
    # three now read UTF-8 (with or without a BOM) only.
    import record_test_command
    import ticket
    cfg = tmp_path / ".claude" / "cai.json"
    cfg.parent.mkdir()
    body = json.dumps({"test": {"commands": ["make test"]}, "ticket": {"enabled": False, "backend": ""}})
    cfg.write_bytes(body.encode("utf-16"))
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "invalid"
    assert result["problem"] == ".claude/cai.json could not be read as JSON".replace("/", os.sep)
    assert ticket.read_config(str(tmp_path))["problem"] == result["problem"]
    with pytest.raises(record_test_command.ConfigProblem):
        record_test_command.record(str(tmp_path), ["make test"])


def test_declared_command_borrows_narrow_from_a_known_default(tmp_path):
    body = json.dumps({"test": {"commands": ["python -m pytest", "go test ./...", "go test", "make test"]}})
    result = rtc.resolve(declare(tmp_path, body))
    assert pairs(result) == [
        ("python -m pytest", "", "paths", ".claude/cai.json"),
        ("go test", "./...", "packages", ".claude/cai.json"),
        ("go test", "./...", "packages", ".claude/cai.json"),
        ("make test", "", "none", ".claude/cai.json"),
    ]


def test_declared_python3_and_py_launchers_borrow_paths(tmp_path):
    body = json.dumps({"test": {"commands": ["python3 -m pytest", "py -3 -m pytest"]}})
    assert pairs(rtc.resolve(declare(tmp_path, body))) == [
        ("python3 -m pytest", "", "paths", ".claude/cai.json"),
        ("py -3 -m pytest", "", "paths", ".claude/cai.json"),
    ]


def test_unknown_declared_command_is_whole_and_unnarrowed(tmp_path):
    result = rtc.resolve(declare(tmp_path, json.dumps({"test": {"commands": ["  ./run-tests.sh  "]}})))
    assert pairs(result) == [("./run-tests.sh", "", "none", ".claude/cai.json")]


def test_cai_json_without_test_key_falls_through_to_detection(tmp_path):
    result = rtc.resolve(declare(tmp_path, json.dumps({"ticket": {"enabled": False, "backend": ""}}),
                                 {"Cargo.toml": "[package]\n"}))
    assert result["status"] == "resolved" and result["source"] == "detected"


MALFORMED = [
    "{not json",
    "[]",
    json.dumps({"test": "make test"}),
    json.dumps({"test": {}}),
    json.dumps({"test": {"commands": "make test"}}),
    json.dumps({"test": {"commands": []}}),
    json.dumps({"test": {"commands": ["ok", ""]}}),
    json.dumps({"test": {"commands": ["ok", "   "]}}),
    json.dumps({"test": {"commands": ["ok", 3]}}),
    json.dumps({"test": {"commands": ["a\nb"]}}),
    json.dumps({"test": {"commands": ["a\rb"]}}),
]


@pytest.mark.parametrize("body", MALFORMED)
def test_malformed_declaration_is_invalid_and_does_not_fall_back(tmp_path, body):
    # A Makefile is present: falling back to detection would resolve it.
    result = rtc.resolve(declare(tmp_path, body, {"Makefile": "test:\n\tx\n"}))
    assert result["status"] == "invalid"
    assert result["source"] is None
    assert result["commands"] == [] and result["candidates"] == []
    assert result["problem"]
    assert "not json" not in result["problem"]


# --- AC3: several candidates ------------------------------------------------

def test_makefile_plus_pytest_is_several_with_no_commands(tmp_path):
    result = rtc.resolve(make(tmp_path, {"Makefile": "test:\n\tx\n",
                                         "pytest.ini": "[pytest]\n"}))
    assert result["status"] == "several"
    assert result["source"] is None
    assert result["commands"] == []
    assert [c["command"] for c in result["candidates"]] == ["make test", "python -m pytest"]


def test_two_lockfiles_are_two_candidates(tmp_path):
    result = rtc.resolve(make(tmp_path, {"package.json": '{"scripts": {"test": "x"}}',
                                         "package-lock.json": "{}", "yarn.lock": ""}))
    assert result["status"] == "several"
    assert [c["command"] for c in result["candidates"]] == ["npm test", "yarn test"]


@pytest.mark.parametrize("names,expected", [
    ({"python", "python3", "py"}, "python -m pytest"),
    ({"python3", "py"}, "python3 -m pytest"),
    ({"py"}, "py -3 -m pytest"),
    # Nothing found: the old default, which says what is missing when it fails.
    (set(), "python -m pytest"),
], ids=["python", "python3 only", "py only", "none"])
def test_pytest_launcher_is_the_first_name_on_path(tmp_path, monkeypatch, names, expected):
    # #274: a machine with only python3 cannot start `python -m pytest`.
    on_path(monkeypatch, names)
    result = rtc.resolve(make(tmp_path, {"pytest.ini": "[pytest]\n"}))
    assert pairs(result) == [(expected, "", "paths", "pytest.ini")]


def test_pytest_origin_is_the_first_configuring_file(tmp_path):
    # pyproject.toml and setup.cfg both say pytest: one candidate, the first file.
    result = rtc.resolve(make(tmp_path, {"pyproject.toml": "[tool.pytest.ini_options]\n",
                                         "setup.cfg": "[tool:pytest]\n"}))
    assert result["status"] == "resolved"
    assert pairs(result) == [("python -m pytest", "", "paths", "pyproject.toml")]


# --- AC4: nothing found -----------------------------------------------------

def test_empty_directory_is_unknown(tmp_path):
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "unknown"
    assert result["commands"] == [] and result["candidates"] == []


def test_exit_codes_differ_between_several_and_unknown(tmp_path, capsys):
    unknown = tmp_path / "u"
    several = tmp_path / "s"
    unknown.mkdir()
    several.mkdir()
    make(several, {"Makefile": "test:\n\tx\n", "go.mod": "module x\n"})
    assert rtc.main(["--project-dir", str(unknown)]) == rtc.EXIT_UNKNOWN == 4
    assert rtc.main(["--project-dir", str(several)]) == rtc.EXIT_SEVERAL == 3
    capsys.readouterr()


def test_main_prints_one_json_object_and_exit_codes(tmp_path, capsys):
    make(tmp_path, {"Cargo.toml": "[package]\n"})
    assert rtc.main(["--project-dir", str(tmp_path)]) == rtc.EXIT_RESOLVED == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["commands"][0]["command"] == "cargo test"
    assert out.err == ""
    make(tmp_path, {".claude/cai.json": "{bad"})
    assert rtc.main(["--project-dir", str(tmp_path)]) == rtc.EXIT_INVALID == 5


# --- AC5: read-only ---------------------------------------------------------

def snapshot(root):
    seen = {}
    for base, dirs, names in os.walk(root):
        for n in dirs + names:
            p = os.path.join(base, n)
            st = os.stat(p)
            seen[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns)
    return seen


def test_resolver_leaves_the_file_tree_unchanged(tmp_path):
    root = make(tmp_path, {"Makefile": "test:\n\tx\n", "go.mod": "module x\n",
                           "package.json": "{bad", ".claude/cai.json": '{"ticket": {}}'})
    before = snapshot(root)
    rtc.resolve(root)
    rtc.main(["--project-dir", root])
    assert snapshot(root) == before


# --- root, size limit, this repo -------------------------------------------

def test_find_root_falls_back_to_cwd_without_git(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no git on PATH
    assert rtc.find_root(str(tmp_path)) == str(tmp_path)


def test_find_root_uses_git_toplevel_from_a_subdirectory(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert os.path.samefile(rtc.find_root(str(sub)), str(tmp_path))


def test_main_resolves_from_the_git_root_when_pointed_at_a_subdirectory(tmp_path, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    make(tmp_path, {"Cargo.toml": ""})
    sub = tmp_path / "sub"
    sub.mkdir()
    assert rtc.main(["--project-dir", str(sub)]) == 0
    assert json.loads(capsys.readouterr().out)["commands"][0]["command"] == "cargo test"


def test_undecodable_detection_file_is_noted_not_raised(tmp_path):
    # cp950/cp1252 text is plausible on a Windows machine; it must not abort the run.
    (tmp_path / "Makefile").write_bytes(b"# \xe9\ntest:\n")
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "unknown"
    assert any("Makefile" in n for n in result["notes"])


def test_a_character_cut_by_the_read_limit_does_not_lose_the_file(tmp_path):
    # #280: the limit can fall inside a multibyte character; the entry on line 1
    # is well inside it and must still count.
    head = b"test:\n\tx\n"
    pad = b"y" * (rtc.READ_LIMIT - len(head) - 1)
    (tmp_path / "Makefile").write_bytes(head + pad + chr(0x6e2c).encode("utf-8"))
    result = rtc.resolve(str(tmp_path))
    assert result["status"] == "resolved"
    assert result["notes"] == []


def test_only_the_first_read_limit_bytes_of_a_file_are_judged(tmp_path):
    big = "x" * rtc.READ_LIMIT + "\ntest:\n"
    result = rtc.resolve(make(tmp_path, {"Makefile": big}))
    assert result["status"] == "unknown"


@pytest.mark.parametrize("doc", ["REFERENCE.md"])
def test_docs_name_every_entry_file_the_resolver_reads(doc):
    # The long-form doc restates TASKFILES, MAKEFILES and JUSTFILES; read the
    # code's own values so a name added to the code fails here until the docs follow.
    # The two READMEs are front doors and no longer list them.
    with open(os.path.join(REPO, doc), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    for name in rtc.TASKFILES + rtc.MAKEFILES + rtc.JUSTFILES:
        assert name in text, (doc, name)


def test_this_repo_resolves_to_pytest():
    result = rtc.resolve(REPO)
    assert result["status"] == "resolved"
    assert result["source"] == "detected"
    assert pairs(result) == [("python -m pytest", "", "paths", "pyproject.toml")]


def test_script_prints_non_ascii_under_an_ascii_stdout(tmp_path):
    # A piped Windows stdout is not UTF-8; the script's own reconfigure is what
    # lets a non-ASCII project path through. chr() keeps this file ASCII.
    root = tmp_path / chr(0x6e2c)
    root.mkdir()
    proc = subprocess.run([sys.executable, rtc.__file__, "--project-dir", str(root)],
                          capture_output=True, env=dict(os.environ, PYTHONIOENCODING="ascii:strict"))
    assert proc.returncode == rtc.EXIT_UNKNOWN == 4
    assert json.loads(proc.stdout.decode("utf-8"))["root"].endswith(chr(0x6e2c))


def test_script_runs_from_the_command_line(tmp_path):
    make(tmp_path, {"go.mod": "module x\n"})
    proc = subprocess.run([sys.executable, rtc.__file__, "--project-dir", str(tmp_path)],
                          capture_output=True)
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8"))["commands"][0]["whole"] == "./..."
