"""Tests for plugins/cai/scripts/glossary_check.py (#326).

Every test builds its input in tmp_path or as a string; nothing here touches a
real glossary. This file stays ASCII, so a non-ASCII character is built with
chr(), the way tests/test_resolve_test_command.py does.
"""
import os
import shutil
import subprocess
import sys

import pytest

import glossary_check as gc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO, "plugins", "cai", "templates", "cai-context.md.tpl")

SECOND = chr(0x79D2)       # a unit of time
LINE = chr(0x884C)         # a unit of count
ROUND = chr(0x8F2A)        # a unit of count
FULL_OPEN, FULL_CLOSE = chr(0xFF08), chr(0xFF09)
ZH_STOP = chr(0x3002)
ZH_WORD = chr(0x6e2c)


def flagged(definition):
    return gc.reasons(definition)


def test_flags_a_decision_id():
    assert flagged("see D12 for why")
    assert flagged("covered by AC4")
    assert flagged("x" + FULL_OPEN + "I1" + FULL_CLOSE)
    for clean in ("Gate 2 comes after build", "UTF-8 text", "a sha256 digest",
                  "the I2C bus", "run py -3 to start it"):
        assert flagged(clean) == [], clean


@pytest.mark.parametrize("ident", ["C15", "D123", "G2", "I4", "R3", "S4", "U5", "UC6", "AC9"])
def test_flags_every_kind_of_decision_id(ident):
    assert any(r.startswith("decision id") for r in flagged("because " + ident + " said so")), ident


def test_a_letter_digit_run_inside_a_word_is_not_a_decision_id():
    for clean in ("the RFC822 format", "a D1234 tag", "x-D1 and D1-x", "ID1"):
        assert flagged(clean) == [], clean


@pytest.mark.parametrize("bare", ["intake", "discover", "decisions", "stance",
                                  "implementation-notes", "state", "pending"])
def test_flags_every_bare_track_document_name(bare):
    assert any(r.startswith("track-document path") for r in flagged("kept in " + bare + ".md")), bare


@pytest.mark.parametrize("suffix", ["stance", "decisions", "detail", "diagnosis", "delta", "high-level"])
def test_flags_every_design_document_suffix(suffix):
    assert any(r.startswith("track-document path") for r in flagged("named x-" + suffix + ".md")), suffix


@pytest.mark.parametrize("unit", ["ms", "days", "tokens", "%", "KB", "hours", "minutes", "times",
                                  chr(0x500B), chr(0x6B21), chr(0x5929), chr(0x5C0F) + chr(0x6642)])
def test_flags_every_unit_family(unit):
    assert any(r.startswith("number with a unit") for r in flagged("about 5 " + unit)), unit


@pytest.mark.parametrize("phrase", [
    # the three the review of #328 reproduced
    "A box that weighs 5 kg at most.", "Records are kept for 2 years.", "A pack that uses 12 volts.",
    # time
    "lasts 3 months", "every 2 yrs", "takes 40 ns", "takes 3 " + chr(0xB5) + "s", "takes 250 milliseconds",
    # length
    "is 10 cm long", "is 3.5 m wide", "runs 20 km", "is 6 feet tall", "is 12 inches", "is 2 miles away",
    "is 5 ft", "is 40 nm", "is 9 mm",
    # mass
    "weighs 300 g", "weighs 2 lbs", "weighs 8 oz", "weighs 3 tonnes", "weighs 5 pounds", "weighs 70 mg",
    # volume
    "holds 2 L", "holds 500 mL", "holds 5 gallons", "holds 3 litres", "holds 2 cups",
    # temperature
    "heats to 90" + chr(0xB0) + "C", "cools to -4" + chr(0xB0) + "F", "reaches 300 kelvin", "turns 90 degrees",
    # electricity
    "draws 5 amps", "draws 12A", "draws 800 mA", "needs 60 W", "needs 5 kW", "needs 230 V", "needs 4 watts",
    "stores 3000 mAh", "has 50 ohms", "uses 2 kWh",
    # frequency
    "ticks at 60 Hz", "clocks at 3.2 GHz", "ticks at 50 hertz",
    # speed
    "goes 60 mph", "goes 100 km/h", "goes 3 m/s", "goes 30 fps", "goes 12 knots",
    # data and data rates
    "sends 10 Mbps", "sends 1 Gbps", "reads 5 MB/s", "stores 2 TB", "stores 8 bits", "sends 100 kbps",
    # Chinese units, built with chr() below
    "2" + chr(0x5E74), "3" + chr(0x6708), "5" + chr(0x516C) + chr(0x65A4), "12" + chr(0x4F0F) + chr(0x7279),
    "10" + chr(0x516C) + chr(0x91CC), "90" + chr(0x5EA6), "5" + chr(0x516C) + chr(0x5347),
])
def test_flags_physical_and_calendar_units(phrase):
    assert any(r.startswith("number with a unit") for r in flagged(phrase)), phrase


@pytest.mark.parametrize("clean", [
    "5 more files", "3 gates", "2 mice", "top 3 mappings", "Gate 2 in the flow", "2 of us",
    "the 3 Arms", "version 2.1.283", "a 4 Wheeled thing", "5 Vendors", "2 Layers", "3 Gaps", "step 1 then 2",
    "6 members", "has 4 yearly passes", "2 monsters", "1 milestone", "7 grandchildren",
    "3 Hertzes", "2 inchworms", "2 ftp servers",
])
def test_ordinary_prose_next_to_a_number_is_not_a_unit(clean):
    assert flagged(clean) == [], clean


def test_the_repos_own_glossary_passes_the_widened_unit_list(capsys):
    # Every added unit is one more way for ordinary prose to be refused.
    assert gc.main([os.path.join(REPO, ".claude", "cai-context.md")]) == 0
    assert capsys.readouterr().out.strip().endswith(" 0 flagged")


def test_a_line_with_several_defects_prints_every_reason(tmp_path, capsys):
    path = tmp_path / "g.md"
    path.write_text("**A**: see D1 and decisions.md, takes 5 s. Two. Three.\n", encoding="utf-8")
    assert gc.main([str(path)]) == 2
    out = capsys.readouterr().out
    assert ("FAIL line 1: A: decision id D1; track-document path decisions.md; "
            "number with a unit 5 s; 3 sentences, at most 2") in out


def test_an_entry_with_no_definition_is_flagged():
    entries, findings = gc.check_text("**A**:\n")
    assert entries == 0
    assert [f.reasons for f in findings] == [("not a **Term**: definition line",)]


def test_flags_a_track_document_path():
    for bad in ("kept in decisions.md", "kept in .claude/track/x/intake.md",
                "kept in docs/design/a-detail.md", "named x-stance.md"):
        assert any(r.startswith("track-document path") for r in flagged(bad)), bad
    for clean in ("under .claude/track/ only", "see README.md"):
        assert flagged(clean) == [], clean


def test_flags_a_number_with_a_unit():
    for bad in ("takes 600" + SECOND, "uses 1 MiB", "is " + chr(0xB1) + "3" + LINE,
                "runs 2" + ROUND, "waits 5 s"):
        assert any(r.startswith("number with a unit") for r in flagged(bad)), bad
    for clean in ("run py -3", "version 2.1.283", "named v2", "has 3 sections"):
        assert flagged(clean) == [], clean


def test_flags_more_than_two_sentences():
    assert "3 sentences, at most 2" in flagged("One. Two. Three.")
    zh = ZH_WORD + ZH_STOP
    assert "3 sentences, at most 2" in flagged(zh * 3)
    assert flagged("One. Two.") == []
    assert flagged(zh * 2) == []
    # a full stop inside an abbreviation or a code span ends nothing
    assert flagged("Things, e.g. this one, and `a.b. c.` too.") == []


def test_flags_a_repeated_name():
    text = "**A b**: fine\n**`a  B`**: see D12\n"
    entries, findings = gc.check_text(text)
    assert entries == 2
    assert [f.line for f in findings] == [2]
    assert findings[0].reasons == ("decision id D12", "name already used on line 1")


def test_flags_a_malformed_bold_line():
    text = "**Good**: fine\n**Bad** no colon here\n## Heading\nplain prose\n"
    entries, findings = gc.check_text(text)
    assert entries == 1
    assert len(findings) == 1
    assert findings[0].line == 2
    assert findings[0].term == "**Bad** no colon here"
    assert findings[0].reasons == ("not a **Term**: definition line",)


def test_exit_codes(tmp_path, capsys):
    clean = tmp_path / "clean.md"
    clean.write_text("# Glossary\n\n**A**: a thing.\n", encoding="utf-8")
    assert gc.main([str(clean)]) == 0
    assert capsys.readouterr().out.strip() == "-- glossary: 1 entries checked, 0 flagged"

    bad = tmp_path / "bad.md"
    bad.write_text("**A**: see D1\n", encoding="utf-8")
    assert gc.main([str(bad)]) == 2
    out = capsys.readouterr().out
    assert "FAIL line 1: A: decision id D1" in out

    assert gc.main([str(tmp_path / "missing.md")]) == 2
    assert "not readable" in capsys.readouterr().out

    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\xff\xfe\x00bad")
    assert gc.main([str(binary)]) == 2
    assert "not readable" in capsys.readouterr().out


def test_prints_non_ascii_under_an_ascii_stdout(tmp_path):
    # A piped Windows stdout is not UTF-8; the script's own reconfigure is what
    # lets a non-ASCII term through.
    path = tmp_path / "g.md"
    path.write_text("**" + ZH_WORD + "**: see D1\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, gc.__file__, str(path)],
                          capture_output=True, env=dict(os.environ, PYTHONIOENCODING="ascii:strict"))
    assert proc.returncode == 2
    assert ("FAIL line 1: " + ZH_WORD + ": decision id D1") in proc.stdout.decode("utf-8")


def test_template_keeps_the_legacy_header(capsys):
    # Step 6.2 tells an earlier cai's top-level file by these four lines, so
    # the new template must not drift from them.
    legacy = ["# Glossary",
              "",
              "This file is only a glossary " + chr(0x2014) + " one or two sentences per term, no decisions",
              "or specs, and only concepts specific to this project."]
    with open(TEMPLATE, encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert text.splitlines()[:4] == legacy
    assert gc.main([TEMPLATE]) == 0


def test_validate_fails_on_a_planted_glossary(tmp_path):
    # Break a copy, never the real tree: another xdist worker may be reading it.
    repo = os.path.join(str(tmp_path), "repo")
    shutil.copytree(REPO, repo, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".coverage*"))
    with open(os.path.join(repo, ".claude", "cai-context.md"), "w", encoding="utf-8") as fh:
        fh.write("# Glossary\n\n## Domain\n\n**Planted**: decided in D12.\n")
    with open(os.path.join(repo, "CONTEXT.md"), "w", encoding="utf-8") as fh:
        fh.write("# Glossary\n")
    result = subprocess.run(
        [sys.executable, os.path.join("scripts", "validate.py"), "glossary"], cwd=repo,
        capture_output=True, text=True, encoding="utf-8")
    lines = result.stdout.splitlines()
    assert result.returncode == 1, result.stdout
    assert any(l.startswith("FAIL glossary: ") for l in lines), result.stdout
    assert any(l.startswith("FAIL no top-level CONTEXT.md") for l in lines), result.stdout
