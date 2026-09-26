"""gap03-review-benchmark: the sample collection, its schema check, the
pure-Python scorer, and the address-rate data file.

Puts repo-root `scripts/` on `sys.path` itself (D6) rather than touching
`tests/conftest.py`, which only puts `plugins/cai/scripts` on the path
(`tests/conftest.py:17-20`) and whose two autouse fixtures apply to the whole
suite -- this collection only needs the one file. Same in-file `sys.path`
pattern `tests/test_ledger_concurrent.py:20` already uses.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import review_benchmark_score as rbs

COLLECTION_DIR = os.path.join(REPO_ROOT, "tests", "review-benchmark")

# The design's Table B "承重行" column -- the string V3 requires each case's
# diff.patch to contain, so a case can never be reduced to a bare SHA.
LOAD_BEARING_STRINGS = {
    "argv-echo-in-run": 'print("backend %s -> %s" % (" ".join(argv), category))',
    "cp950-decode-guard": 'encoding="utf-8", errors="replace"',
    "quoted-grader-type": "return m.group(1).strip() if m else None",
    "stale-guard-citation": "tests/test_track_state_status_vocabulary.py:51",
    "illegal-rows-order-untested":
        "def test_two_illegal_rows_each_print_their_own_line_in_stage_order(tmp_path):",
    "repo-only-script-in-plugin": "+++ b/plugins/cai/scripts/review_benchmark_cases.py",
}

# AC3's "no bare SHA" scan is mechanical: 7-40 hex chars, word-bounded.
_HEX_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")


def _case_dirs():
    return sorted(
        d for d in os.listdir(COLLECTION_DIR)
        if os.path.isdir(os.path.join(COLLECTION_DIR, d))
    )


def _load_expected(case):
    path = os.path.join(COLLECTION_DIR, case, "expected.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Unit 1 -- collection shape (AC1) and load-bearing strings / no-bare-SHA (AC3)
# ---------------------------------------------------------------------------

def test_collection_has_at_least_five_cases():
    # True only from unit 5 on -- kept out of unit 1's commit (see
    # implementation-notes.md's Step 5 deviation) so the suite never sits
    # red between the unit-1 and unit-5 commits.
    assert len(_case_dirs()) >= 5


def test_each_case_dir_has_exactly_diff_patch_and_expected_json():
    for case in _case_dirs():
        files = sorted(os.listdir(os.path.join(COLLECTION_DIR, case)))
        assert files == ["diff.patch", "expected.json"], case


def test_every_diff_patch_contains_its_load_bearing_string():
    for case, needle in LOAD_BEARING_STRINGS.items():
        path = os.path.join(COLLECTION_DIR, case, "diff.patch")
        with open(path, encoding="utf-8") as fh:
            assert needle in fh.read(), case


def test_no_case_refers_to_the_defect_by_bare_sha():
    # base_sha/base_ref and diff.patch's own commit/index headers are outside
    # the scan (D2/decision 2 requires storing the SHA there); AC3 only bans
    # using a bare SHA to stand in for the defect itself, in cause or notes.
    for case in _case_dirs():
        expected = _load_expected(case)
        texts = [expected.get("notes", "")]
        texts += [e.get("cause", "") for e in expected.get("expected", [])]
        for text in texts:
            assert not _HEX_TOKEN.search(text), (case, text)


# ---------------------------------------------------------------------------
# Unit 2 -- schema check (AC2): load_cases() and schema_problems()
# ---------------------------------------------------------------------------

GOOD_EXPECTED = {
    "base_sha": "abc1234",
    "base_ref": "origin/main",
    "expected": [
        {
            "lens": "correctness",
            "file": "scripts/example.py",
            "line_start": 10,
            "line_end": 12,
            "severity": "Major",
            "cause": "off-by-one in the loop bound",
        }
    ],
    "expected_absent": ["security"],
    "notes": "a hand-written fixture, not a real case",
}


def test_schema_problems_on_a_good_fixture_is_empty():
    assert rbs.schema_problems(GOOD_EXPECTED) == []


def test_schema_problems_names_a_missing_field():
    bad = dict(GOOD_EXPECTED)
    del bad["base_ref"]
    problems = rbs.schema_problems(bad)
    assert any("base_ref" in p for p in problems)


def test_schema_problems_names_a_type_error():
    bad = json.loads(json.dumps(GOOD_EXPECTED))
    bad["expected"][0]["line_end"] = 3  # < line_start (10)
    problems = rbs.schema_problems(bad)
    assert any("line_end" in p and "line_start" in p for p in problems)


def test_load_cases_returns_sorted_case_names():
    cases = rbs.load_cases(COLLECTION_DIR)
    names = [c["case"] for c in cases]
    assert names == sorted(names)
    assert set(LOAD_BEARING_STRINGS) <= set(names)


def test_load_cases_every_case_is_schema_clean():
    for case in rbs.load_cases(COLLECTION_DIR):
        problems = rbs.schema_problems(case["expected"])
        assert problems == [], (case["case"], problems)


# ---------------------------------------------------------------------------
# Unit 3 -- the scorer (AC4, AC7): scored_lenses, matches, score_case,
# score_all, format_report
# ---------------------------------------------------------------------------

ONE_FINDING_EXPECTED = {
    "base_sha": "abc1234",
    "base_ref": "origin/main",
    "expected": [
        {
            "lens": "security",
            "file": "scripts/example.py",
            "line_start": 10,
            "line_end": 12,
            "severity": "Major",
            "cause": "an example defect",
        }
    ],
    "expected_absent": [],
    "notes": "a hand-written fixture",
}


def _run(case, run_no, findings, lens_runs=None):
    return {"case": case, "run": run_no, "findings": findings,
            "lens_runs": lens_runs or {}}


def test_v4_a_finding_three_lines_from_the_range_is_a_hit():
    # line_end (12) + 3 = 15, within tolerance
    finding = {"lens": "security", "file": "scripts/example.py", "line": 15,
               "severity": "Major", "cause": "x"}
    want = ONE_FINDING_EXPECTED["expected"][0]
    assert rbs.matches(finding, want) is True


def test_v5_a_finding_four_lines_from_the_range_is_not_a_hit():
    finding = {"lens": "security", "file": "scripts/example.py", "line": 16,
               "severity": "Major", "cause": "x"}
    want = ONE_FINDING_EXPECTED["expected"][0]
    assert rbs.matches(finding, want) is False


def test_v6_severity_mismatch_still_counts_tp_but_not_severity_match():
    findings = [{"lens": "security", "file": "scripts/example.py", "line": 11,
                 "severity": "Blocker", "cause": "x"}]
    row = rbs.score_case(ONE_FINDING_EXPECTED, _run("c", 1, findings))
    assert row["per_lens"]["security"]["tp"] == 1
    assert row["per_lens"]["security"]["severity_pairs"] == 1
    assert row["per_lens"]["security"]["severity_match"] == 0


def test_v7_format_report_has_2n_rows_with_an_f1_delta_column():
    row_a1 = rbs.score_case(ONE_FINDING_EXPECTED, _run("case-a", 1, [
        {"lens": "security", "file": "scripts/example.py", "line": 11,
         "severity": "Major", "cause": "x"}]))
    row_a2 = rbs.score_case(ONE_FINDING_EXPECTED, _run("case-a", 2, []))
    row_b1 = rbs.score_case(ONE_FINDING_EXPECTED, _run("case-b", 1, []))
    row_b2 = rbs.score_case(ONE_FINDING_EXPECTED, _run("case-b", 2, []))
    report = rbs.format_report([row_a1, row_a2, row_b1, row_b2])
    body_rows = report.splitlines()[2:]  # past the header and separator rows
    assert len(body_rows) == 4
    assert "f1_delta" in report.splitlines()[0]


def test_v8_unscored_and_duplicate_do_not_change_precision():
    # a correctness finding on a case whose only ground truth is security ->
    # unscored, not FP.
    findings = [{"lens": "correctness", "file": "scripts/example.py",
                 "line": 11, "severity": "Major", "cause": "x"}]
    row = rbs.score_case(ONE_FINDING_EXPECTED, _run("c", 1, findings))
    assert row["unscored"] == 1
    assert row["per_lens"]["correctness"]["fp"] == 0
    assert row["overall"]["precision"] is None

    # two security findings both landing in the same expected range -> the
    # second is a duplicate, not a second FP.
    findings2 = [
        {"lens": "security", "file": "scripts/example.py", "line": 10,
         "severity": "Major", "cause": "x"},
        {"lens": "security", "file": "scripts/example.py", "line": 11,
         "severity": "Major", "cause": "x"},
    ]
    row2 = rbs.score_case(ONE_FINDING_EXPECTED, _run("c", 1, findings2))
    assert row2["per_lens"]["security"]["tp"] == 1
    assert row2["duplicate"] == 1
    assert row2["per_lens"]["security"]["fp"] == 0
    assert row2["overall"]["precision"] == 1.0


# ---------------------------------------------------------------------------
# Unit 4 -- address-rate data file (AC8): V9's recompute check
# ---------------------------------------------------------------------------

ADDRESS_RATE_PATH = os.path.join(COLLECTION_DIR, "address-rate.md")

# A number, or the literal string UNVERIFIED (F10) -- never guessed.
_UNVERIFIED = "UNVERIFIED"


def _parse_address_rate():
    """Every data row of address-rate.md's table, as
    {track, raised, fixed, left_minor, triaged, source}. raised/left_minor
    are ints, or the string UNVERIFIED when the design marks them so."""
    with open(ADDRESS_RATE_PATH, encoding="utf-8") as fh:
        text = fh.read()

    def _cell(value):
        value = value.strip()
        return value if value == _UNVERIFIED else int(value)

    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in ("track", ""):
            continue
        track, raised, fixed, left_minor, triaged, source = cells
        rows.append({
            "track": track,
            "raised": _cell(raised),
            "fixed": int(fixed),
            "left_minor": _cell(left_minor),
            "triaged": int(triaged),
            "source": source,
        })
    return rows


def test_address_rate_has_twelve_rows():
    assert len(_parse_address_rate()) == 12


def test_address_rate_identity_holds_on_every_fully_known_row():
    for row in _parse_address_rate():
        if row["raised"] == _UNVERIFIED or row["left_minor"] == _UNVERIFIED:
            continue
        assert row["fixed"] + row["left_minor"] + row["triaged"] == row["raised"], row["track"]


def test_address_rate_recomputes_the_two_rates_from_eleven_rows():
    known = [r for r in _parse_address_rate()
             if r["raised"] != _UNVERIFIED and r["left_minor"] != _UNVERIFIED]
    assert len(known) == 11

    raised = sum(r["raised"] for r in known)
    fixed = sum(r["fixed"] for r in known)
    left_minor = sum(r["left_minor"] for r in known)
    triaged = sum(r["triaged"] for r in known)

    assert (raised, fixed, left_minor, triaged) == (61, 25, 31, 5)
    assert fixed + left_minor + triaged == raised

    fix_rate = fixed / raised
    response_rate = (fixed + triaged) / raised
    assert abs(fix_rate - 25 / 61) < 1e-9
    assert abs(response_rate - 30 / 61) < 1e-9


def test_address_rate_pb06_row_is_marked_unverified_not_guessed():
    rows = {r["track"]: r for r in _parse_address_rate()}
    pb06 = rows["pb06-ledger-metrics"]
    assert pb06["raised"] == _UNVERIFIED
    assert pb06["left_minor"] == _UNVERIFIED
    assert pb06["fixed"] == 3
    assert pb06["triaged"] == 0


# ---------------------------------------------------------------------------
# convention-benchmark-case (#152) -- procedure step 3 cites stage-verify.md
# by file:line; a citation that drifts from the paragraph it names must fail.
# ---------------------------------------------------------------------------

PROCEDURE = os.path.join(REPO_ROOT, "scripts", "review-benchmark-procedure.md")
STAGE_VERIFY = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-verify.md"
)

STEP3_ANCHORS = [
    ("Four agents, in parallel", "caps parallel subagents at 2"),
    ("Give each agent the base ref", "With both, compare against both"),
    ("The three severity words Step 2 ranks by", "lens it is reviewing against"),
]

# Named ("stage-verify.md:44-48") or the old filename-omitted form
# ("`:64-66`") -- both are a citation into that file.
_CITE = re.compile(r"(?:[\w./-]*stage-verify\.md)?:(\d+)-(\d+)")


def _procedure_step3():
    with open(PROCEDURE, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("\n3. ") + 1
    end = text.index("\n4. ", start) + 1
    return text[start:end]


def _stage_verify_span(a, b):
    with open(STAGE_VERIFY, encoding="utf-8") as fh:
        lines = fh.readlines()
    span = " ".join(line.strip() for line in lines[a - 1:b])
    return re.sub(r"\s+", " ", span)


def test_procedure_step3_cites_resolve_to_their_paragraphs():
    step3 = _procedure_step3()
    matches = [(int(a), int(b)) for a, b in _CITE.findall(step3)]
    assert len(matches) == 3, matches
    for (a, b), (head, tail) in zip(matches, STEP3_ANCHORS):
        span = _stage_verify_span(a, b)
        assert head in span, f"stage-verify.md:{a}-{b} lacks {head!r}"
        assert tail in span, f"stage-verify.md:{a}-{b} lacks {tail!r}"


def test_procedure_step3_gives_conformance_the_convention_files():
    step3 = _procedure_step3()
    assert "useless without" not in step3
    assert "CLAUDE.md" in step3
