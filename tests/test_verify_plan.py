"""Unit 2: verify_plan levels -- AC1's five fixtures, the `\\|` escape and the CLI.

Fixtures are intake text in a string or a tmp_path file; nothing is run.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

import verify_plan as vp

TABLE = """## Verification levels

| AC | level | check |
|---|---|---|
| AC1 | test | tests/test_x.py |
| AC2 | local-run | GET /health 200 |
| AC3 | deployed | open the preview URL and look |
| AC4 | manual | read the README section |
"""


def intake(body="", table=TABLE):
    return ("# Intake\n\n## Acceptance criteria\n\n" + body + "\n" + table)


BODY = ("- AC1: a test\n- **AC2** a run\n**AC3 deployed**\n"
        "- **AC4（manual）** — text\n")


def test_ok_table_reads_every_row_in_order():
    result = vp.read_levels(intake(BODY))
    assert result["status"] == "ok" and result["problems"] == []
    assert result["rows"] == [
        {"ac": "AC1", "level": "test", "check": "tests/test_x.py"},
        {"ac": "AC2", "level": "local-run", "check": "GET /health 200"},
        {"ac": "AC3", "level": "deployed", "check": "open the preview URL and look"},
        {"ac": "AC4", "level": "manual", "check": "read the README section"},
    ]


def test_five_prose_styles_all_count_as_defining_an_id():
    body = "- AC1: a\n- AC2： b\n- **AC3** c\n- **AC4（x）** — d\n**AC5 层级**\n"
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             + "".join("| AC%d | manual | step |\n" % n for n in range(1, 5)))
    result = vp.read_levels(intake(body, table))
    assert result["status"] == "invalid"
    assert result["problems"] == ["AC5: no row in Verification levels"]


def test_no_heading_is_legacy_not_an_error():
    result = vp.read_levels("# Intake\n\n- AC1: x\n")
    assert result == {"status": "legacy", "rows": [], "problems": []}


def test_heading_inside_a_fence_does_not_count():
    text = "- AC1: x\n\n```\n## Verification levels\n```\n"
    assert vp.read_levels(text)["status"] == "legacy"


def test_wrong_header_is_invalid():
    table = TABLE.replace("| AC | level | check |", "| AC | level | how |")
    result = vp.read_levels(intake(BODY, table))
    assert result["status"] == "invalid"
    assert any("| AC | level | check |" in p for p in result["problems"])


def test_missing_table_under_the_heading_is_invalid():
    result = vp.read_levels(intake(BODY, "## Verification levels\n\nTBD\n"))
    assert result["status"] == "invalid" and result["problems"]


def test_duplicate_id_and_bad_level_are_named():
    table = TABLE + "| AC2 | local-run | GET / 200 |\n| AC9 | runtime | x |\n"
    body = BODY + "- AC9: z\n"
    result = vp.read_levels(intake(body, table))
    assert result["status"] == "invalid"
    assert "AC2: duplicate row in Verification levels" in result["problems"]
    assert ("AC9: level 'runtime' is not one of test, local-run, deployed, manual"
            in result["problems"])


def test_row_in_prose_but_not_in_table():
    result = vp.read_levels(intake(BODY + "- AC7: new\n"))
    assert result["status"] == "invalid"
    assert result["problems"] == ["AC7: no row in Verification levels"]


def test_row_in_table_but_not_in_prose():
    result = vp.read_levels(intake(BODY + "", TABLE + "| AC8 | manual | x |\n"))
    assert result["status"] == "invalid"
    assert result["problems"] == ["AC8: row in Verification levels has no AC in the body"]


def test_ids_inside_the_levels_section_and_fences_are_not_prose():
    body = BODY + "\n```\n- AC99: example\n```\n"
    assert vp.read_levels(intake(body))["status"] == "ok"


def test_section_ends_at_the_next_heading():
    text = intake(BODY) + "\n## Notes\n\n- AC6: after the table\n"
    result = vp.read_levels(text)
    assert result["problems"] == ["AC6: no row in Verification levels"]


def test_escaped_pipe_is_a_literal_pipe_in_the_cell():
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             '| AC1 | local-run | GET /x 200 "a\\|b" |\n')
    result = vp.read_levels(intake("- AC1: x\n", table))
    assert result["status"] == "ok"
    assert result["rows"][0]["check"] == 'GET /x 200 "a|b"'


def test_row_with_wrong_cell_count_is_named():
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             "| AC1 | test |\n")
    result = vp.read_levels(intake("- AC1: x\n", table))
    assert result["status"] == "invalid" and result["problems"]


def test_row_without_a_closing_pipe_is_named():
    # A stray fourth segment after the last pipe: without the delimiter guard the
    # row would parse as three good cells and the table would read as ok.
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             "| AC1 | test | tests/x.py | trailing\n")
    result = vp.read_levels(intake("- AC1: x\n", table))
    assert result["status"] == "invalid"
    assert result["problems"][0] == ("row is not three cells (AC | level | check): "
                                     "| AC1 | test | tests/x.py | trailing")


def test_row_id_that_is_not_an_ac_number_is_named():
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             "| first | test | tests/x.py |\n")
    result = vp.read_levels(intake("- AC1: x\n", table))
    assert result["status"] == "invalid"
    assert "row id 'first' is not of the form AC<number>" in result["problems"]


def test_crlf_text_reads_the_same():
    result = vp.read_levels(intake(BODY).replace("\n", "\r\n"))
    assert result["status"] == "ok" and len(result["rows"]) == 4


# --- CLI ---------------------------------------------------------------------

def write(tmp_path, text):
    path = tmp_path / "intake.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_cli_ok_prints_each_row_and_exits_0(tmp_path, capsys):
    path = write(tmp_path, intake(BODY))
    assert vp.main(["levels", "--intake", path]) == vp.EXIT_OK == 0
    assert capsys.readouterr().out.splitlines() == [
        "AC1 test tests/test_x.py",
        "AC2 local-run GET /health 200",
        "AC3 deployed open the preview URL and look",
        "AC4 manual read the README section",
    ]


def test_cli_legacy_prints_one_line_and_exits_4(tmp_path, capsys):
    path = write(tmp_path, "# Intake\n- AC1: x\n")
    assert vp.main(["levels", "--intake", path]) == vp.EXIT_LEGACY == 4
    assert capsys.readouterr().out == 'legacy: no "## Verification levels" heading\n'


def test_cli_invalid_prints_each_problem_to_stderr_and_exits_5(tmp_path, capsys):
    path = write(tmp_path, intake(BODY + "- AC7: new\n- AC8: new\n"))
    assert vp.main(["levels", "--intake", path]) == vp.EXIT_INVALID == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == ["AC7: no row in Verification levels",
                                         "AC8: no row in Verification levels"]


def test_cli_unreadable_intake_exits_5_and_names_the_path(tmp_path, capsys):
    missing = str(tmp_path / "nope.md")
    assert vp.main(["levels", "--intake", missing]) == 5
    assert missing in capsys.readouterr().err


def test_cli_reads_a_utf8_bom(tmp_path):
    path = tmp_path / "intake.md"
    path.write_bytes(b"\xef\xbb\xbf" + intake(BODY).encode("utf-8"))
    assert vp.main(["levels", "--intake", str(path)]) == 0


def test_script_runs_as_a_process(tmp_path):
    path = write(tmp_path, intake(BODY))
    proc = subprocess.run([sys.executable, vp.__file__, "levels", "--intake", path],
                          capture_output=True, timeout=30)
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").splitlines()[1] == "AC2 local-run GET /health 200"
    assert os.path.basename(vp.__file__) == "verify_plan.py"


# --- Unit 4: parse_check, plan, merge-list -------------------------------------

@pytest.mark.parametrize("cell, parsed", [
    ("GET /health 200", {"kind": "http", "method": "GET", "path": "/health",
                         "status": 200, "text": None}),
    ('GET /api/items 200 "items"', {"kind": "http", "method": "GET", "path": "/api/items",
                                    "status": 200, "text": "items"}),
    ('POST /x 201 "two words"', {"kind": "http", "method": "POST", "path": "/x",
                                 "status": 201, "text": "two words"}),
    ("HEAD /x 204", {"kind": "http", "method": "HEAD", "path": "/x",
                     "status": 204, "text": None}),
    ("e2e smoke", {"kind": "e2e", "name": "smoke"}),
])
def test_parse_check_good_cells(cell, parsed):
    assert vp.parse_check(cell) == parsed


@pytest.mark.parametrize("cell", [
    'HEAD /x 200 "body"',        # HEAD may not carry a body string
    "FETCH /x 200",              # not a method
    "get /x 200",                # methods are upper-case
    "GET health 200",            # path must start with /
    "GET /x",                    # status is required
    "GET /x ok",                 # status must be a number
    'GET /x 200 "a" "b"',        # one body string at most
    'GET /x 200 "unterminated',  # shlex error
    "e2e",                       # no name
    "e2e a b",                   # two names
    "open the preview and look",
    "",
])
def test_parse_check_bad_cells_are_kind_none_with_a_problem(cell):
    parsed = vp.parse_check(cell)
    assert parsed["kind"] == "none" and parsed["problem"]


def test_parse_check_quoted_text_keeps_a_status_looking_word():
    assert vp.parse_check('GET /x 200 "404"')["text"] == "404"


def make_tool(bindir, name):
    bindir.mkdir(exist_ok=True)
    if os.name == "nt":
        (bindir / (name + ".cmd")).write_text("@echo off\n")
    else:
        path = bindir / name
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A project dir, a track dir and a PATH holding only `bin/` with `faketool`."""
    bindir = tmp_path / "bin"
    make_tool(bindir, "faketool")
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    track = tmp_path / "track"
    track.mkdir()
    return proj, track, bindir


def put_config(proj, run=None, test=None):
    data = {}
    if run is not None:
        data["run"] = run
    if test is not None:
        data["test"] = test
    (proj / ".claude" / "cai.json").write_text(json.dumps(data), encoding="utf-8")


def put_intake(track, rows, body=None):
    ids = [r[0] for r in rows]
    prose = body if body is not None else "".join("- %s: x\n" % i for i in ids)
    table = ("## Verification levels\n| AC | level | check |\n|---|---|---|\n"
             + "".join("| %s | %s | %s |\n" % r for r in rows))
    (track / "intake.md").write_text(intake(prose, table), encoding="utf-8")


RUN = {"start": ["faketool", "serve"], "ready": "http://127.0.0.1:8000/",
       "e2e": {"smoke": ["faketool", "e2e"]}}
FOUR = [("AC1", "test", "tests/x.py"), ("AC2", "local-run", "GET /health 200"),
        ("AC3", "deployed", "open /login after deploy"), ("AC4", "manual", "read the page")]


def by_ac(plan):
    return {r["ac"]: r for r in plan["rows"]}


def test_ac13_a_four_levels_with_a_full_config(env):
    proj, track, _ = env
    put_config(proj, RUN, {"commands": ["python -m pytest"]})
    put_intake(track, FOUR)
    plan = vp.build_plan(str(track), str(proj))
    assert plan["source"] == "track" and plan["intake_status"] == "ok"
    assert plan["intake"] == os.path.join(str(track), "intake.md")
    rows = by_ac(plan)
    assert [rows[a]["route"] for a in ("AC1", "AC2", "AC3", "AC4")] == [
        "test", "local-run", "merge", "merge"]
    assert rows["AC2"]["parsed"]["kind"] == "http" and rows["AC2"]["reason"] is None
    assert plan["runtime"] == {"status": "will-run", "reason": None, "acs": ["AC2"]}
    assert plan["start"]["status"] == "declared"
    assert [c["command"] for c in plan["test_commands"]] == ["python -m pytest"]


def test_ac13_a_cli_prints_the_table(env, capsys):
    proj, track, _ = env
    put_config(proj, RUN, {"commands": ["python -m pytest"]})
    put_intake(track, FOUR + [("AC5", "local-run", "do something odd")],
               )
    assert vp.main(["plan", "--track-dir", str(track), "--project-dir", str(proj)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "verify plan -- 5 AC (source: %s)" % os.path.join(str(track), "intake.md")
    assert lines[1] == "AC1 test       -> tests: python -m pytest (verifier maps the tests)"
    assert lines[2] == ("AC2 local-run  -> start: faketool serve (declared in .claude/cai.json); "
                        "GET /health expect 200")
    assert lines[3] == "AC3 deployed   -> The merge: open /login after deploy"
    assert lines[4] == "AC4 manual     -> The merge: read the page"
    assert lines[5] == ("AC5 local-run  -> Not covered (no-check-data): no HTTP check and no "
                        "declared e2e name; not dispatched")
    assert lines[6] == "runtime: will run 1 AC (AC2)"
    assert len(lines) == 7


def test_ac13_b_no_declaration_marks_local_run_only(env):
    proj, track, _ = env
    put_intake(track, FOUR)
    plan = vp.build_plan(str(track), str(proj))
    rows = by_ac(plan)
    assert rows["AC2"]["route"] == "not-covered" and rows["AC2"]["reason"] == "no-start-declaration"
    assert rows["AC3"]["route"] == "merge" and rows["AC4"]["route"] == "merge"
    assert rows["AC1"]["route"] == "test"
    assert plan["runtime"]["status"] == "skipped"
    assert plan["runtime"]["reason"] == "no-start-declaration"


def test_ac13_c_no_check_data_and_undeclared_e2e_are_named(env):
    proj, track, _ = env
    put_config(proj, RUN)
    put_intake(track, [("AC1", "local-run", "look at it"),
                       ("AC2", "local-run", "e2e nosuch"),
                       ("AC3", "local-run", "e2e smoke")])
    rows = by_ac(vp.build_plan(str(track), str(proj)))
    assert rows["AC1"]["reason"] == "no-check-data" and rows["AC1"]["route"] == "not-covered"
    assert rows["AC2"]["reason"] == "e2e-not-declared"
    assert "nosuch" in rows["AC2"]["detail"]
    assert rows["AC3"]["route"] == "local-run"


def test_ac13_d_missing_executables_are_named(env):
    proj, track, _ = env
    run = {"start": ["faketool", "serve"], "ready": "http://127.0.0.1:8000/",
           "e2e": {"smoke": ["ghosttool", "e2e"]}}
    put_config(proj, run)
    put_intake(track, [("AC1", "local-run", "e2e smoke"), ("AC2", "local-run", "GET / 200")])
    rows = by_ac(vp.build_plan(str(track), str(proj)))
    assert rows["AC1"]["reason"] == "e2e-not-on-path" and "ghosttool" in rows["AC1"]["detail"]
    assert rows["AC2"]["route"] == "local-run"

    put_config(proj, dict(run, start=["ghosttool", "serve"]))
    rows = by_ac(vp.build_plan(str(track), str(proj)))
    assert rows["AC2"]["reason"] == "start-not-on-path" and "ghosttool" in rows["AC2"]["detail"]


def test_a_path_like_first_word_is_not_looked_up_on_path(env):
    proj, track, _ = env
    put_config(proj, dict(RUN, start=["./no/such/app", "serve"]))
    put_intake(track, [("AC1", "local-run", "GET / 200")])
    assert by_ac(vp.build_plan(str(track), str(proj)))["AC1"]["route"] == "local-run"


def snapshot(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def test_ac13_e_plan_writes_nothing_and_starts_nothing(env, tmp_path, capsys):
    proj, track, bindir = env
    marker = tmp_path / "ran.txt"
    # A tool that would leave a marker if it were ever executed.
    if os.name == "nt":
        (bindir / "faketool.cmd").write_text("@echo ran> \"%s\"\n" % marker)
    else:
        (bindir / "faketool").write_text("#!/bin/sh\necho ran > '%s'\n" % marker)
    put_config(proj, RUN, {"commands": ["python -m pytest"]})
    put_intake(track, FOUR)
    (proj / "package.json").write_text('{"scripts": {"dev": "x"}}', encoding="utf-8")
    before = (snapshot(str(proj)), snapshot(str(track)))
    assert vp.main(["plan", "--track-dir", str(track), "--project-dir", str(proj)]) == 0
    capsys.readouterr()
    assert (snapshot(str(proj)), snapshot(str(track))) == before
    assert not marker.exists()


def test_ac9_standalone(env):
    proj, _, _ = env
    plan = vp.build_plan(None, str(proj))
    assert plan["source"] == "standalone" and plan["intake"] is None
    assert plan["rows"] == []
    assert plan["runtime"] == {"status": "skipped", "reason": "standalone", "acs": []}


def test_ac9_legacy_intake(env):
    proj, track, _ = env
    (track / "intake.md").write_text("# Intake\n- AC1: x\n", encoding="utf-8")
    plan = vp.build_plan(str(track), str(proj))
    assert plan["intake_status"] == "legacy" and plan["rows"] == []
    assert plan["runtime"]["reason"] == "legacy-intake"


def test_ac9_no_local_run_ac(env):
    proj, track, _ = env
    put_config(proj, RUN)
    put_intake(track, [("AC1", "test", "t"), ("AC2", "manual", "look")])
    plan = vp.build_plan(str(track), str(proj))
    assert plan["runtime"] == {"status": "skipped", "reason": "no-local-run-ac", "acs": []}


def test_ac9_four_reasons_are_distinct_and_cli_prints_them(env, capsys):
    proj, track, _ = env
    reasons = set()
    reasons.add(vp.build_plan(None, str(proj))["runtime"]["reason"])
    (track / "intake.md").write_text("# Intake\n- AC1: x\n", encoding="utf-8")
    reasons.add(vp.build_plan(str(track), str(proj))["runtime"]["reason"])
    put_intake(track, [("AC1", "local-run", "GET / 200")])
    reasons.add(vp.build_plan(str(track), str(proj))["runtime"]["reason"])
    put_intake(track, [("AC1", "test", "t")])
    reasons.add(vp.build_plan(str(track), str(proj))["runtime"]["reason"])
    assert reasons == {"standalone", "legacy-intake", "no-start-declaration", "no-local-run-ac"}
    assert vp.main(["plan", "--project-dir", str(proj)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "runtime: skipped (standalone)"


def test_ac15_candidates_are_printed_and_nothing_is_written(env, capsys):
    proj, track, _ = env
    (proj / "package.json").write_text('{"scripts": {"dev": "vite", "start": "node ."}}',
                                       encoding="utf-8")
    put_intake(track, [("AC1", "local-run", "GET /health 200")])
    before = (snapshot(str(proj)), snapshot(str(track)))
    plan = vp.build_plan(str(track), str(proj))
    row = plan["rows"][0]
    assert row["route"] == "not-covered" and row["reason"] == "start-candidates"
    assert [c["script"] for c in plan["start"]["candidates"]] == ["dev", "start"]
    assert vp.main(["plan", "--track-dir", str(track), "--project-dir", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "start candidates: 1) npm run dev (package.json scripts.dev)" in out
    assert "2) npm run start (package.json scripts.start)" in out
    assert (snapshot(str(proj)), snapshot(str(track))) == before


@pytest.mark.parametrize("track_rows", [None, [("AC1", "test", "t")], "legacy"])
def test_candidates_are_not_printed_unless_a_local_run_ac_needs_one(env, capsys, track_rows):
    # AC15 asks only when a `local-run` AC has no declaration; AC9 says every other
    # case behaves as it does today, so no "start candidates:" line that a verifier
    # could read as a question to ask.
    proj, track, _ = env
    (proj / "package.json").write_text('{"scripts": {"dev": "vite"}}', encoding="utf-8")
    args = ["plan", "--project-dir", str(proj)]
    if track_rows == "legacy":
        (track / "intake.md").write_text("# Intake\n- AC1: x\n", encoding="utf-8")
    elif track_rows is not None:
        put_intake(track, track_rows)
    if track_rows is not None:
        args += ["--track-dir", str(track)]
    assert vp.main(args) == 0
    assert "start candidates" not in capsys.readouterr().out


def test_invalid_start_declaration_marks_rows_with_the_problem(env):
    proj, track, _ = env
    put_config(proj, {"start": ["faketool"]})  # ready missing
    (proj / "package.json").write_text('{"scripts": {"dev": "x"}}', encoding="utf-8")
    put_intake(track, [("AC1", "local-run", "GET / 200"), ("AC2", "manual", "look")])
    plan = vp.build_plan(str(track), str(proj))
    row = by_ac(plan)["AC1"]
    assert row["reason"] == "invalid-start-declaration" and "ready" in row["detail"]
    assert plan["start"]["candidates"] == []
    assert by_ac(plan)["AC2"]["route"] == "merge"


def test_invalid_levels_exit_5_with_problems_on_stderr_and_no_table(env, capsys):
    proj, track, _ = env
    put_intake(track, FOUR, body="- AC1: x\n- AC9: y\n")
    assert vp.main(["plan", "--track-dir", str(track), "--project-dir", str(proj)]) == 5
    captured = capsys.readouterr()
    assert captured.out == "" and "AC9: no row in Verification levels" in captured.err


def test_missing_intake_in_a_track_dir(env):
    proj, track, _ = env
    plan = vp.build_plan(str(track), str(proj))
    assert plan["intake_status"] == "missing" and plan["rows"] == []
    assert plan["runtime"]["status"] == "skipped"


def test_plan_is_a_function_of_path(env, monkeypatch, tmp_path):
    proj, track, _ = env
    put_config(proj, RUN)
    put_intake(track, [("AC1", "local-run", "GET / 200")])
    assert vp.build_plan(str(track), str(proj))["rows"][0]["route"] == "local-run"
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert vp.build_plan(str(track), str(proj))["rows"][0]["reason"] == "start-not-on-path"


def test_ac6_merge_list_with_deployed_and_manual(env, capsys):
    _, track, _ = env
    put_intake(track, FOUR)
    assert vp.merge_list(str(track)) == ["- AC3 (deployed): open /login after deploy",
                                         "- AC4 (manual): read the page"]
    assert vp.main(["merge-list", "--track-dir", str(track)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "- AC3 (deployed): open /login after deploy", "- AC4 (manual): read the page"]


def test_ac6_merge_list_without_such_rows_prints_nothing(env, capsys):
    _, track, _ = env
    put_intake(track, [("AC1", "test", "t"), ("AC2", "local-run", "GET / 200")])
    assert vp.merge_list(str(track)) == []
    assert vp.main(["merge-list", "--track-dir", str(track)]) == 0
    assert capsys.readouterr().out == ""


def test_merge_list_legacy_and_missing_print_nothing_invalid_exits_5(env, capsys):
    _, track, _ = env
    assert vp.main(["merge-list", "--track-dir", str(track)]) == 0  # no intake
    (track / "intake.md").write_text("# Intake\n- AC1: x\n", encoding="utf-8")
    assert vp.main(["merge-list", "--track-dir", str(track)]) == 0  # legacy
    assert capsys.readouterr().out == ""
    put_intake(track, FOUR, body="- AC1: x\n")
    assert vp.main(["merge-list", "--track-dir", str(track)]) == 5
    assert "AC2: row in Verification levels has no AC in the body" in capsys.readouterr().err


# --- Unit 6: check (assemble + verify) ------------------------------------------

STAMP = "20260101T000000Z"
ALL = [("AC1", "test", "tests/x.py"), ("AC2", "local-run", "GET /health 200"),
       ("AC3", "deployed", "open /login after deploy")]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put_run(track, checks, name=STAMP):
    """A run dir holding run.json in the shape local_run.run() writes, plus one
    evidence file per check that has an `evidence` entry. checks: (ac, outcome,
    reason, body-or-None)."""
    rundir = track / "evidence" / "verify" / name
    rundir.mkdir(parents=True, exist_ok=True)
    entries = []
    for ac, outcome, reason, body in checks:
        entry = {"ac": ac, "check": "GET /health 200", "outcome": outcome, "reason": reason,
                 "evidence": None, "sha256": None, "bytes_seen": None, "truncated": False}
        if body is not None:
            (rundir / (ac + ".txt")).write_bytes(body)
            entry.update(evidence=ac + ".txt", sha256=sha(body))
        entries.append(entry)
    record = {"format": 1, "stage": "verify", "unit": None, "platform": "win32",
              "started": "x", "ended": "y", "budget": {}, "checks": entries,
              "start": {"outcome": "ready"}, "survivors": []}
    (rundir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    return rundir


def put_syn(tmp_path, acs=None, commands=None, **extra):
    syn = {"format": 1, "test_commands": [{"command": "python -m pytest", "passed": 3,
                                           "failed": 0, "narrowed": False}]
           if commands is None else commands, "acs": acs or {}}
    syn.update(extra)
    path = tmp_path / "syn.json"
    path.write_text(json.dumps(syn), encoding="utf-8")
    return str(path)


@pytest.fixture
def chk(env):
    proj, track, _ = env
    put_config(proj, RUN, {"commands": ["python -m pytest"]})
    put_intake(track, ALL)
    return proj, track


def do_assemble(proj, track, syn, run=None):
    path, manifest = vp.assemble(str(track), str(proj), syn, str(run) if run else None)
    return path, {r["ac"]: r for r in manifest["rows"]}, manifest


GOOD = {"AC1": {"tests": ["tests/x.py::t"], "findings": []}}


def test_rule1_plan_not_covered_keeps_the_plans_reason(env, tmp_path):
    proj, track, _ = env  # no start declaration: local-run is not-covered in the plan
    put_intake(track, ALL)
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD))
    assert rows["AC2"]["outcome"] == "not-covered" and rows["AC2"]["reason"] == "no-start-declaration"


def test_rule2_unfixed_blocker_or_major_wins_over_everything_after_rule1(chk, tmp_path):
    proj, track = chk
    acs = {"AC1": {"tests": ["t"], "findings": [{"severity": "Major", "where": "a:1", "fixed": False}]},
           "AC3": {"tests": [], "findings": [{"severity": "Blocker", "where": "b:2", "fixed": False}]}}
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, acs))
    assert (rows["AC1"]["outcome"], rows["AC1"]["reason"]) == ("not-covered", "unfixed-finding")
    assert (rows["AC3"]["outcome"], rows["AC3"]["reason"]) == ("not-covered", "unfixed-finding")


def test_fixed_or_minor_findings_do_not_block(chk, tmp_path):
    proj, track = chk
    acs = {"AC1": {"tests": ["t"], "findings": [
        {"severity": "Major", "where": "a:1", "fixed": True},
        {"severity": "Minor", "where": "a:2", "fixed": False}]}}
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, acs))
    assert rows["AC1"]["outcome"] == "verified-by-test"
    assert len(rows["AC1"]["findings"]) == 2


def test_rule3_deployed_and_manual_confirm_before_merge(chk, tmp_path):
    proj, track = chk
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD))
    assert (rows["AC3"]["outcome"], rows["AC3"]["reason"]) == ("confirm-before-merge", None)


def test_rule4_test_without_a_matching_test(chk, tmp_path):
    proj, track = chk
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, {}))
    assert (rows["AC1"]["outcome"], rows["AC1"]["reason"]) == ("not-covered", "no-matching-test")


def test_rule5_tests_not_run(chk, tmp_path):
    proj, track = chk
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD, commands=[]))
    assert rows["AC1"]["reason"] == "tests-not-run"


def test_rule6_any_failed_command_fails_all(chk, tmp_path):
    proj, track = chk
    cmds = [{"command": "a", "passed": 1, "failed": 0}, {"command": "b", "passed": 0, "failed": 2}]
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD, commands=cmds))
    assert rows["AC1"]["reason"] == "tests-failed"


def test_rule7_verified_by_test(chk, tmp_path):
    proj, track = chk
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD))
    assert (rows["AC1"]["outcome"], rows["AC1"]["reason"]) == ("verified-by-test", None)
    assert rows["AC1"]["tests"] == ["tests/x.py::t"] and rows["AC1"]["level"] == "test"


def test_rule8_runtime_pass_with_matching_fingerprint(chk, tmp_path):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"200 ok")])
    path, rows, manifest = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    row = rows["AC2"]
    assert row["outcome"] == "verified-at-runtime" and row["reason"] is None
    assert row["evidence"] == "evidence/verify/%s/AC2.txt" % STAMP
    assert row["sha256"] == sha(b"200 ok") and row["check"] == "GET /health 200"
    assert path == os.path.join(str(rundir), "manifest.json")
    assert manifest["run"] == "evidence/verify/%s/run.json" % STAMP
    assert manifest["run_sha256"] == sha((rundir / "run.json").read_bytes())
    assert manifest["intake"] == "intake.md"
    assert manifest["intake_sha256"] == sha((track / "intake.md").read_bytes())
    assert manifest["synthesis"]["acs"] == GOOD
    assert json.loads(open(path, encoding="utf-8").read()) == manifest


@pytest.mark.parametrize("outcome, reason, want, detail", [
    ("FAIL", "status 500", "runtime-FAIL", "status 500"),
    ("FAIL", "start-exited (exit code 1)", "runtime-FAIL", "start-exited (exit code 1)"),
    ("TIMEOUT", "ready-timeout", "runtime-TIMEOUT", "ready-timeout"),
    ("NOT-RUN", "port-in-use", "port-in-use", None),
    ("NOT-RUN", "time-budget-exhausted", "time-budget-exhausted", None),
    ("NOT-RUN", "interrupted", "interrupted", None),
])
def test_rule9_runtime_results_become_reasons(chk, tmp_path, outcome, reason, want, detail):
    proj, track = chk
    rundir = put_run(track, [("AC2", outcome, reason, None)])
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert (rows["AC2"]["outcome"], rows["AC2"]["reason"]) == ("not-covered", want)
    assert rows["AC2"]["detail"] == detail


def test_rule8_runtime_pass_without_evidence_is_not_covered(chk, tmp_path):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, None)])  # PASS, but no evidence file
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert (rows["AC2"]["outcome"], rows["AC2"]["reason"]) == ("not-covered", "no-evidence")
    assert rows["AC2"]["evidence"] is None and rows["AC2"]["sha256"] is None


def test_rule9_not_run_when_there_is_no_run_record_entry(chk, tmp_path):
    proj, track = chk
    _, rows, manifest = do_assemble(proj, track, put_syn(tmp_path, GOOD))  # no --run
    assert rows["AC2"]["reason"] == "not-run" and manifest["run"] is None
    assert manifest["run_sha256"] is None
    rundir = put_run(track, [], name="other")  # a record that lacks AC2
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert rows["AC2"]["reason"] == "not-run"


def test_run_dir_without_run_json_still_gets_a_manifest(chk, tmp_path):
    proj, track = chk
    rundir = track / "evidence" / "verify" / "bare"
    rundir.mkdir(parents=True)
    path, rows, manifest = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert manifest["run"] is None and os.path.dirname(path) == str(rundir)


def test_evidence_changed_at_assembly_still_writes_and_exits_3(chk, tmp_path, capsys):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"200 ok")])
    (rundir / "AC2.txt").write_bytes(b"200 oK")  # one byte
    syn = put_syn(tmp_path, GOOD)
    _, rows, _ = do_assemble(proj, track, syn, rundir)
    assert (rows["AC2"]["outcome"], rows["AC2"]["reason"]) == ("not-covered", "evidence-changed")
    (rundir / "manifest.json").unlink()
    code = vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", syn, "--run", str(rundir)])
    assert code == 3 and (rundir / "manifest.json").exists()
    assert "AC2: evidence" in capsys.readouterr().err


def test_deleted_evidence_at_assembly_is_evidence_changed(chk, tmp_path):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"200 ok")])
    (rundir / "AC2.txt").unlink()
    _, rows, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert rows["AC2"]["reason"] == "evidence-changed"


def test_existing_manifest_is_never_overwritten(chk, tmp_path):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"x")])
    first, _, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    before = open(first, "rb").read()
    second, _, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD), rundir)
    assert second != first and open(first, "rb").read() == before


def test_default_manifest_dir_is_new_each_time_even_in_one_second(chk, tmp_path, monkeypatch):
    proj, track = chk

    class Frozen(vp.datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 1, 0, 0, 0, tzinfo=tz)
    monkeypatch.setattr(vp.datetime, "datetime", Frozen)
    syn = put_syn(tmp_path, GOOD)
    one, _, _ = do_assemble(proj, track, syn)
    two, _, _ = do_assemble(proj, track, syn)
    base = os.path.join(str(track), "evidence", "verify")
    assert os.path.dirname(one) == os.path.join(base, STAMP)
    assert os.path.dirname(two) == os.path.join(base, STAMP + "-2")


# synthesis validation: exit 5, names the problem, writes nothing

def written(track):
    base = track / "evidence"
    return sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []


def raw_syn(tmp_path, text):
    path = tmp_path / "syn.json"
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("make, needle", [
    (lambda t: str(t / "missing.json"), "could not be read"),
    (lambda t: raw_syn(t, "{not json"), "could not be read"),
    (lambda t: raw_syn(t, json.dumps({"format": 2, "acs": {}})), "format must be 1"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC9": {}}})), "AC9"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": {"findings": [
        {"severity": "Critical", "fixed": True}]}}})), "severity"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": {"findings": [
        {"severity": "Major", "fixed": "yes"}]}}})), "fixed must be true or false"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": {"findings": [
        {"severity": "Major"}]}}})), "fixed must be true or false"),
    # one byte past the read limit: refused, not silently cut and parsed
    (lambda t: raw_syn(t, json.dumps({"format": 1, "pad": "x" * (
        vp.resolve_test_command.READ_LIMIT + 1)})), "larger than"),
    (lambda t: raw_syn(t, "[]"), "synthesis must be a JSON object"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "test_commands": "pytest"})),
     "test_commands must be a list of objects"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": []})), "acs must be an object"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": 5}})),
     "AC1: synthesis entry must be an object"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": {"tests": "t.py"}}})),
     "AC1: tests must be a list"),
    (lambda t: raw_syn(t, json.dumps({"format": 1, "acs": {"AC1": {"findings": ["x"]}}})),
     "AC1: findings must be a list of objects"),
])
def test_synthesis_errors_exit_5_and_write_nothing(chk, tmp_path, capsys, make, needle):
    proj, track = chk
    syn = make(tmp_path)
    with pytest.raises(vp.CheckError) as err:
        vp.assemble(str(track), str(proj), syn, None)
    assert err.value.code == 5 and needle in " ".join(err.value.problems)
    assert written(track) == []
    assert vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", syn]) == 5
    assert needle in capsys.readouterr().err and written(track) == []


@pytest.mark.parametrize("where", ["outside", "base", "missing", "elsewhere-in-track"])
def test_run_outside_evidence_verify_is_rejected(chk, tmp_path, capsys, where):
    proj, track = chk
    target = {"outside": tmp_path / "elsewhere", "base": track / "evidence" / "verify",
              "missing": track / "evidence" / "verify" / "nope",
              "elsewhere-in-track": track / "evidence" / "build"}[where]
    target.mkdir(parents=True, exist_ok=True)
    if where == "missing":
        target.rmdir()
    code = vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", put_syn(tmp_path, GOOD), "--run", str(target)])
    assert code == 5 and "--run" in capsys.readouterr().err
    assert not list(target.glob("manifest*.json")) if target.exists() else True


def test_unreadable_run_record_exits_5(chk, tmp_path):
    proj, track = chk
    rundir = put_run(track, [])
    (rundir / "run.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(vp.CheckError) as err:
        vp.assemble(str(track), str(proj), put_syn(tmp_path, GOOD), str(rundir))
    assert err.value.code == 5


# verification mode

def assembled(chk, tmp_path, acs=GOOD, passing=True):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"200 ok")]) if passing else None
    path, _, _ = do_assemble(proj, track, put_syn(tmp_path, acs), rundir)
    return proj, track, path, rundir


def mutate(path, fn):
    data = json.loads(open(path, encoding="utf-8").read())
    fn(data)
    open(path, "w", encoding="utf-8").write(json.dumps(data))


def test_ac4_clean_manifest_verifies(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    assert vp.verify_manifest(path, str(track), str(proj)) == []


def test_ac4_one_changed_byte_is_named(chk, tmp_path):
    proj, track, path, rundir = assembled(chk, tmp_path)
    (rundir / "AC2.txt").write_bytes(b"200 oK")
    problems = vp.verify_manifest(path, str(track), str(proj))
    assert len(problems) == 1 and problems[0].startswith("AC2: evidence")
    assert "fingerprint does not match" in problems[0]


def test_ac4_deleted_evidence_file_is_named(chk, tmp_path):
    proj, track, path, rundir = assembled(chk, tmp_path)
    (rundir / "AC2.txt").unlink()
    problems = vp.verify_manifest(path, str(track), str(proj))
    assert len(problems) == 1 and "missing" in problems[0] and "AC2" in problems[0]


def test_ac4_evidence_path_escaping_the_track_dir_is_a_problem(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    (tmp_path / "outside.txt").write_bytes(b"x")
    mutate(path, lambda m: m["rows"][1].update(evidence="../outside.txt", sha256=sha(b"x")))
    assert "outside the track directory" in vp.verify_manifest(path, str(track), str(proj))[0]


def test_ac5_missing_extra_and_duplicate_ids(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    mutate(path, lambda m: m["rows"].pop(0))
    assert "AC1: no row in the manifest" in vp.verify_manifest(path, str(track), str(proj))
    mutate(path, lambda m: m["rows"].append(dict(m["rows"][0], ac="AC9")))
    assert "AC9: row is not an AC of the intake" in vp.verify_manifest(path, str(track), str(proj))
    mutate(path, lambda m: m["rows"].append(dict(m["rows"][0])))
    assert any("more than one row" in p for p in vp.verify_manifest(path, str(track), str(proj)))


def test_ac5_an_outcome_outside_the_four_is_named(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    mutate(path, lambda m: m["rows"][0].update(outcome="done"))
    assert any("AC1: outcome 'done'" in p for p in vp.verify_manifest(path, str(track), str(proj)))


def test_ac14_verified_row_with_unfixed_blocker_is_named(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    finding = {"severity": "Blocker", "where": "a:1", "fixed": False}
    mutate(path, lambda m: m["rows"][0].update(findings=[finding]))
    assert vp.verify_manifest(path, str(track), str(proj)) == [
        "AC1: verified-by-test with an unfixed Blocker or Major finding"]
    # the same finding only in the synthesis copy is caught too
    mutate(path, lambda m: (m["rows"][0].update(findings=[]),
                            m["synthesis"]["acs"]["AC1"].update(findings=[finding])))
    assert len(vp.verify_manifest(path, str(track), str(proj))) == 1


def test_ac14_plan_not_covered_row_turned_verified_is_named(env, tmp_path):
    proj, track, _ = env  # no start declaration: AC2 is not-covered in the plan
    put_intake(track, ALL)
    path, _, _ = do_assemble(proj, track, put_syn(tmp_path, GOOD))
    mutate(path, lambda m: m["rows"][1].update(outcome="verified-at-runtime", reason=None))
    assert vp.verify_manifest(path, str(track), str(proj)) == [
        "AC2: verified-at-runtime but the plan says not-covered (no-start-declaration)"]


def test_ac14_verified_by_test_without_a_test_is_named(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    mutate(path, lambda m: m["rows"][0].update(tests=[]))
    assert vp.verify_manifest(path, str(track), str(proj)) == [
        "AC1: verified-by-test with no matching test"]


def test_manifest_without_a_rows_list_is_named(chk, tmp_path):
    proj, track, path, _ = assembled(chk, tmp_path)
    for rows in ("oops", ["not an object"]):
        mutate(path, lambda m, rows=rows: m.update(rows=rows))
        assert vp.verify_manifest(path, str(track), str(proj)) == ["manifest has no rows list"]
    with open(path, "w", encoding="utf-8") as fh:  # not even an object
        fh.write("[]")
    assert vp.verify_manifest(path, str(track), str(proj)) == ["manifest has no rows list"]


def test_verify_manifest_reports_an_unreadable_manifest(chk, tmp_path):
    proj, track = chk
    bad = tmp_path / "m.json"
    bad.write_text("nope", encoding="utf-8")
    assert "could not be read" in vp.verify_manifest(str(bad), str(track), str(proj))[0]


# legacy / standalone / invalid, and the CLI

LEGACY_MSG = "no manifest for a legacy or standalone verify"


def test_legacy_intake_exits_4_in_both_modes(env, tmp_path, capsys):
    proj, track, _ = env
    (track / "intake.md").write_text("# Intake\n- AC1: x\n", encoding="utf-8")
    base = ["check", "--track-dir", str(track), "--project-dir", str(proj)]
    assert vp.main(base + ["--synthesis", put_syn(tmp_path)]) == 4
    assert LEGACY_MSG in capsys.readouterr().err
    assert vp.main(base + ["--manifest", str(tmp_path / "whatever.json")]) == 4
    assert LEGACY_MSG in capsys.readouterr().err
    assert written(track) == []


def test_no_intake_at_all_exits_4(env, tmp_path, capsys):
    proj, track, _ = env
    assert vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", put_syn(tmp_path)]) == 4
    assert LEGACY_MSG in capsys.readouterr().err


def test_invalid_intake_exits_5_and_prints_the_problems(env, tmp_path, capsys):
    proj, track, _ = env
    put_intake(track, ALL, body="- AC1: x\n- AC9: y\n")
    assert vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", put_syn(tmp_path)]) == 5
    assert "AC9: no row in Verification levels" in capsys.readouterr().err
    assert written(track) == []


def test_cli_assemble_prints_manifest_path_then_one_line_per_ac(chk, tmp_path, capsys):
    proj, track = chk
    rundir = put_run(track, [("AC2", "PASS", None, b"200 ok")])
    code = vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", put_syn(tmp_path, GOOD), "--run", str(rundir)])
    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "manifest: %s" % os.path.join(str(rundir), "manifest.json")
    # AC5: a test-verified line carries the matched tests, the command and its counts
    assert lines[1:] == [
        "AC1 test verified-by-test tests=tests/x.py::t "
        "commands=python -m pytest (3 passed, 0 failed)",
        "AC2 local-run verified-at-runtime evidence/verify/%s/AC2.txt sha256=%s"
        % (STAMP, sha(b"200 ok")),
        "AC3 deployed confirm-before-merge"]


def test_cli_not_covered_line_carries_the_reason(chk, tmp_path, capsys):
    proj, track = chk
    assert vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
                    "--synthesis", put_syn(tmp_path, {})]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "AC1 test not-covered (no-matching-test)" in out
    assert "AC2 local-run not-covered (not-run)" in out


def test_cli_default_dir_lands_under_evidence_verify(chk, tmp_path, capsys):
    proj, track = chk
    vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj),
             "--synthesis", put_syn(tmp_path, GOOD)])
    path = capsys.readouterr().out.splitlines()[0][len("manifest: "):]
    assert os.path.dirname(os.path.dirname(path)) == os.path.join(str(track), "evidence", "verify")


def test_cli_manifest_mode_clean_and_with_problems(chk, tmp_path, capsys):
    proj, track, path, rundir = assembled(chk, tmp_path)
    base = ["check", "--track-dir", str(track), "--project-dir", str(proj), "--manifest", path]
    assert vp.main(base) == 0
    assert capsys.readouterr().out.splitlines()[0] == "manifest: %s" % path
    (rundir / "AC2.txt").write_bytes(b"changed")
    mutate(path, lambda m: m["rows"].pop(0))
    assert vp.main(base) == 3
    err = capsys.readouterr().err.splitlines()
    assert any(line.startswith("AC2: evidence") for line in err)
    assert "AC1: no row in the manifest" in err


def test_cli_manifest_mode_writes_nothing(chk, tmp_path, capsys):
    proj, track, path, _ = assembled(chk, tmp_path)
    before = snapshot(str(track))
    vp.main(["check", "--track-dir", str(track), "--project-dir", str(proj), "--manifest", path])
    assert snapshot(str(track)) == before


def test_cli_needs_exactly_one_mode(chk, tmp_path):
    proj, track = chk
    base = ["check", "--track-dir", str(track)]
    with pytest.raises(SystemExit):
        vp.main(base)
    with pytest.raises(SystemExit):
        vp.main(base + ["--synthesis", "a", "--manifest", "b"])
    with pytest.raises(SystemExit):
        vp.main(base + ["--manifest", "b", "--run", "c"])


def test_check_runs_as_a_process(chk, tmp_path):
    proj, track = chk
    proc = subprocess.run([sys.executable, vp.__file__, "check", "--track-dir", str(track),
                           "--project-dir", str(proj), "--synthesis", put_syn(tmp_path, GOOD)],
                          capture_output=True, timeout=60)
    assert proc.returncode == 0 and proc.stdout.decode("utf-8").startswith("manifest: ")
