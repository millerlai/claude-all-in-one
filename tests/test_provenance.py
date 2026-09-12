"""provenance.py: the probe layer for docs/rule-provenance.md (unit 2 of 6,
issue #78). These tests cover `entries`, `normalise`, `section_of`, the first
four probe labels, and `main`'s CLI/pre-check -- everything unit 2 owns.
`restated_quote_in_section` and `shared_value_in_every_quote` are unit 3's
job and are not tested here.
"""
import ast
import os
import subprocess
import sys

import provenance

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "plugins", "cai", "scripts")


# --- entries() ---------------------------------------------------------

LEDGER_FIXTURE = """# Rule provenance ledger

Some intro prose.

## normal-entry — a normal entry

- Date: 2026-01-01
- Failure: something broke once.
- Rule: Always do the thing.
- Cited by: rules/foo.md § Some Heading
- Restated in: rules/bar.md § Other Heading | Always do the thing, restated.
- Restated in: rules/baz.md § Third Heading | Always do the thing, restated again.
- Shared value: the thing

## missing-field-entry — missing a required field

- Date: 2026-01-02
- Failure: something else broke.
- Cited by: rules/foo.md § Some Heading

## normal-entry — a duplicate id

- Date: 2026-01-03
- Failure: yet another failure.
- Rule: Do another thing.
- Cited by: rules/foo.md § Another Heading

## unparseable-citation — cited by does not split

- Date: 2026-01-04
- Failure: a citation typo.
- Rule: Do a third thing.
- Cited by: rules/foo.md without the separator

## restated-malformed-entry — one restated line does not parse

- Date: 2026-01-05
- Failure: a restated-in typo.
- Rule: Do a fourth thing.
- Cited by: rules/foo.md § Some Heading
- Restated in: rules/bar.md § Other Heading | Do a fourth thing, restated.
- Restated in: rules/bar.md without the separators
"""


def _by_id(entries, entry_id):
    return next(e for e in entries if e["id"] == entry_id)


def test_entries_parses_a_normal_entry():
    entries = provenance.entries(LEDGER_FIXTURE)
    e = _by_id(entries, "normal-entry")
    assert e["fields"]["Date"] == "2026-01-01"
    assert e["fields"]["Rule"] == "Always do the thing."
    assert e["cited"] == ("rules/foo.md", "Some Heading")
    assert e["restated"] == [
        ("rules/bar.md", "Other Heading", "Always do the thing, restated."),
        ("rules/baz.md", "Third Heading", "Always do the thing, restated again."),
    ]
    assert e["shared"] == "the thing"


def test_entries_marks_a_malformed_entry_without_raising():
    entries = provenance.entries(LEDGER_FIXTURE)
    e = _by_id(entries, "missing-field-entry")
    assert "Rule" not in e["fields"]


def test_entries_keeps_duplicate_ids_as_separate_entries():
    entries = provenance.entries(LEDGER_FIXTURE)
    matches = [e for e in entries if e["id"] == "normal-entry"]
    assert len(matches) == 2


def test_entries_leaves_cited_none_when_citation_does_not_split():
    entries = provenance.entries(LEDGER_FIXTURE)
    e = _by_id(entries, "unparseable-citation")
    assert e["cited"] is None


def test_entries_on_empty_ledger_is_empty():
    assert provenance.entries("") == []
    assert provenance.entries("just prose, no headings\n") == []


def test_entries_keeps_a_malformed_restated_line_without_dropping_it():
    entries = provenance.entries(LEDGER_FIXTURE)
    e = _by_id(entries, "restated-malformed-entry")
    assert e["restated"] == [
        ("rules/bar.md", "Other Heading", "Do a fourth thing, restated."),
    ]
    assert e["restated_malformed"] == ["rules/bar.md without the separators"]


# --- normalise() ---------------------------------------------------------

def test_normalise_folds_whitespace():
    assert provenance.normalise("a   b\n\tc") == "a b c"


def test_normalise_strips_backticks():
    assert provenance.normalise("use `preflight.resolve()` here") == \
        "use preflight.resolve() here"


def test_normalise_converts_en_dash_to_hyphen():
    assert provenance.normalise("2–3 subagents") == "2-3 subagents"


def test_normalise_leaves_em_dash_untouched():
    assert provenance.normalise("id — title") == "id — title"


# --- section_of() ---------------------------------------------------------

def test_section_of_skips_a_fenced_code_block_decoy_before_the_real_heading():
    text = (
        "# Intro\n\n"
        "Example output:\n\n"
        "```markdown\n"
        "# Real Heading\n"
        "This is decoy body text that must never be returned.\n"
        "```\n\n"
        "# Real Heading\n\n"
        "This is the real body.\n"
    )
    section = provenance.section_of(text, "# Real Heading")
    assert "decoy body text" not in section
    assert "real body" in section


def test_section_of_terminates_at_next_same_level_heading():
    text = (
        "# A\n\n"
        "A's body text.\n\n"
        "# B\n\n"
        "B's body text.\n"
    )
    section = provenance.section_of(text, "# A")
    assert "A's body text" in section
    assert "B's body text" not in section
    assert "# B" not in section


def test_section_of_heading_not_found_returns_empty_string():
    assert provenance.section_of("# Something\n\nbody\n", "# Nonexistent") == ""


def test_section_of_skips_a_fenced_code_block_decoy_after_the_real_heading():
    # The start-of-section match already skips a decoy heading found before
    # the real one (test above). The terminating search walks the same kind
    # of heading-shaped lines looking for where the section ends, and must
    # apply the same fence check -- a decoy inside the section's own body
    # (e.g. a fenced example block, same shape as
    # plugins/cai/skills/refactor/references/procedure-scan.md:58-61) must
    # not be mistaken for the next real heading and truncate the section.
    text = (
        "## Output format\n\n"
        "```markdown\n"
        "# Refactoring scan -- <target>\n"
        "```\n\n"
        "## Rules\n\nRules body.\n"
    )
    section = provenance.section_of(text, "## Output format")
    assert "```markdown" in section
    assert "# Refactoring scan" in section
    assert "Rules body" not in section


def test_section_of_start_match_is_anchored_to_end_of_line():
    # A heading that is a text-prefix of another heading (e.g. "# Environment"
    # vs. "# Environment Variables") must not resolve to the longer one just
    # because both start with the shorter heading's text.
    text = (
        "# Environment Variables\n\n"
        "Wrong section body.\n\n"
        "# Environment\n\n"
        "Right section body.\n"
    )
    section = provenance.section_of(text, "# Environment")
    assert "Right section body" in section
    assert "Wrong section body" not in section


# --- probes() --------------------------------------------------------------

def verdicts(entries, project_dir="."):
    return {label.split(" (")[0]: ok for ok, label in provenance.probes(entries, project_dir)}


def detail(entries, probe, project_dir="."):
    return next(label for _, label in provenance.probes(entries, project_dir)
                if label.startswith(probe + " "))


def _entry(id_="e1", date="2026-01-01", failure="f", rule="r", cited_by="a.md § H",
           restated=None, restated_malformed=None, shared=None):
    fields = {"Date": date, "Failure": failure, "Rule": rule, "Cited by": cited_by}
    for k in list(fields):
        if fields[k] is None:
            del fields[k]
    cited = None
    if cited_by and " § " in cited_by:
        path, _, heading = cited_by.partition(" § ")
        cited = (path, heading)
    return {"id": id_, "fields": fields, "cited": cited,
            "restated": restated or [], "restated_malformed": restated_malformed or [],
            "shared": shared}


def test_entry_fields_complete_fails_when_a_required_field_is_missing():
    entries = [_entry(rule=None)]
    assert verdicts(entries)["entry_fields_complete"] is False


def test_entry_fields_complete_passes_when_all_present():
    entries = [_entry()]
    assert verdicts(entries)["entry_fields_complete"] is True


def test_entry_ids_unique_fails_on_a_duplicate():
    entries = [_entry(id_="dup"), _entry(id_="dup")]
    assert verdicts(entries)["entry_ids_unique"] is False


def test_entry_ids_unique_passes_when_all_distinct():
    entries = [_entry(id_="a"), _entry(id_="b")]
    assert verdicts(entries)["entry_ids_unique"] is True


def test_cited_by_resolves_fails_when_file_is_missing(tmp_path):
    entries = [_entry(cited_by="does-not-exist.md § H")]
    assert verdicts(entries, str(tmp_path))["cited_by_resolves"] is False


def test_cited_by_resolves_fails_when_citation_does_not_parse():
    entries = [_entry(cited_by="no separator here")]
    assert verdicts(entries)["cited_by_resolves"] is False


def test_cited_by_resolves_passes_when_file_and_heading_exist(tmp_path):
    target = tmp_path / "rule.md"
    target.write_text("# Heading\n\nSome rule text.\n", encoding="utf-8")
    entries = [_entry(cited_by="rule.md § Heading")]
    assert verdicts(entries, str(tmp_path))["cited_by_resolves"] is True


def test_cited_by_resolves_and_rule_quote_ignore_a_fenced_decoy_heading(tmp_path):
    # A fenced example block containing a heading-shaped decoy line whose
    # stripped title matches the cited heading, but at a different `#`
    # level, must not be picked over the real heading -- same decoy shape
    # as plugins/cai/skills/refactor/references/procedure-scan.md:61.
    # Before the fix, _resolve_heading() (unlike section_of()) had no
    # fence-awareness, so it resolved to the fenced "### Report" line;
    # section_of() then correctly refused to return that fenced match,
    # yielding an empty section and a false "drifted" report for a
    # citation that never moved.
    target = tmp_path / "target.md"
    target.write_text(
        "# Doc\n\n"
        "Example:\n\n"
        "```markdown\n"
        "### Report\n"
        "decoy body must not count\n"
        "```\n\n"
        "## Report\n\n"
        "Always do the thing.\n",
        encoding="utf-8",
    )
    entries = [_entry(rule="Always do the thing.", cited_by="target.md § Report")]
    v = verdicts(entries, str(tmp_path))
    assert v["cited_by_resolves"] is True
    assert v["rule_quote_in_cited_section"] is True


def test_rule_quote_in_cited_section_fails_when_rule_text_has_drifted(tmp_path):
    target = tmp_path / "rule.md"
    target.write_text("# Heading\n\nSomething completely different.\n", encoding="utf-8")
    entries = [_entry(rule="Always do the thing.", cited_by="rule.md § Heading")]
    assert verdicts(entries, str(tmp_path))["rule_quote_in_cited_section"] is False


def test_rule_quote_in_cited_section_passes_when_rule_text_is_present(tmp_path):
    target = tmp_path / "rule.md"
    target.write_text("# Heading\n\nAlways do the thing.\n", encoding="utf-8")
    entries = [_entry(rule="Always do the thing.", cited_by="rule.md § Heading")]
    assert verdicts(entries, str(tmp_path))["rule_quote_in_cited_section"] is True


def test_rule_quote_in_cited_section_skipped_when_citation_does_not_resolve():
    # Not resolving is cited_by_resolves's own failure; this label must not
    # also crash trying to read a file that was never found.
    entries = [_entry(cited_by="does-not-exist.md § H")]
    assert verdicts(entries)["rule_quote_in_cited_section"] is True


def test_restated_quote_in_section_passes_when_quote_is_present(tmp_path):
    target = tmp_path / "restated.md"
    target.write_text("# Heading\n\nAlways do the thing, restated.\n", encoding="utf-8")
    entries = [_entry(restated=[("restated.md", "Heading", "Always do the thing, restated.")])]
    assert verdicts(entries, str(tmp_path))["restated_quote_in_section"] is True


def test_restated_quote_in_section_fails_when_quote_has_drifted(tmp_path):
    target = tmp_path / "restated.md"
    target.write_text("# Heading\n\nSomething completely different.\n", encoding="utf-8")
    entries = [_entry(restated=[("restated.md", "Heading", "Always do the thing, restated.")])]
    assert verdicts(entries, str(tmp_path))["restated_quote_in_section"] is False


def test_restated_quote_in_section_fails_when_file_is_missing(tmp_path):
    entries = [_entry(restated=[("does-not-exist.md", "Heading", "quote")])]
    assert verdicts(entries, str(tmp_path))["restated_quote_in_section"] is False


def test_restated_quote_in_section_fails_when_heading_is_missing(tmp_path):
    target = tmp_path / "restated.md"
    target.write_text("# Other Heading\n\nSomething else.\n", encoding="utf-8")
    entries = [_entry(restated=[("restated.md", "Heading", "quote")])]
    assert verdicts(entries, str(tmp_path))["restated_quote_in_section"] is False


def test_restated_quote_in_section_fails_on_a_malformed_restated_line():
    entries = [_entry(restated_malformed=["rules/bar.md without the separators"])]
    assert verdicts(entries)["restated_quote_in_section"] is False


def test_restated_quote_in_section_passes_when_no_restated_lines_at_all():
    entries = [_entry()]
    assert verdicts(entries)["restated_quote_in_section"] is True


def test_shared_value_in_every_quote_ignores_entries_without_a_shared_value():
    entries = [_entry(shared=None, restated=[("bar.md", "H", "no relation to rule")])]
    assert verdicts(entries)["shared_value_in_every_quote"] is True


def test_shared_value_in_every_quote_passes_when_present_in_rule_and_every_quote():
    entries = [_entry(rule="Always do the shared thing.", shared="shared thing",
                       restated=[("bar.md", "H", "Do the shared thing too.")])]
    assert verdicts(entries)["shared_value_in_every_quote"] is True


def test_shared_value_in_every_quote_fails_when_missing_from_a_restated_quote():
    entries = [_entry(rule="Always do the shared thing.", shared="shared thing",
                       restated=[("bar.md", "H", "This quote drifted away from it.")])]
    assert verdicts(entries)["shared_value_in_every_quote"] is False
    assert "bar.md" in detail(entries, "shared_value_in_every_quote")


def test_shared_value_in_every_quote_fails_when_missing_from_the_rule_itself():
    entries = [_entry(rule="This rule drifted away from it.", shared="shared thing",
                       restated=[("bar.md", "H", "Do the shared thing too.")])]
    assert verdicts(entries)["shared_value_in_every_quote"] is False
    assert "Rule" in detail(entries, "shared_value_in_every_quote")


# --- main() ------------------------------------------------------------

def _run_main(args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "provenance.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


def test_main_is_silent_when_no_ledger_file_exists(tmp_path):
    done = _run_main(["--project-dir", str(tmp_path)])
    assert done.stdout == ""
    assert done.returncode == 0


def test_main_is_silent_when_ledger_has_no_entries(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rule-provenance.md").write_text("just prose, no headings\n", encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("probes() must not be called when there are no entries")

    monkeypatch.setattr(provenance, "probes", _boom)
    # entries() truly returns [] for this fixture -- the monkeypatch above
    # only guards against probes() being entered in-process; main() itself
    # runs as a subprocess below, so also assert the parse result directly.
    assert provenance.entries("just prose, no headings\n") == []

    done = _run_main(["--project-dir", str(tmp_path)])
    assert done.stdout == ""
    assert done.returncode == 0


def test_main_hint_mentions_confirming_the_claim_for_a_drift_failure(tmp_path):
    # The failure hint used to be one fixed "add an entry" string regardless
    # of which probe failed -- actively wrong advice for a drift (the entry
    # is already complete and well-formed; nothing needs *adding*). See
    # docs/design/2026-09-12-issue78-rule-guards-detail.md's D-8 and the
    # `main` row of `## Implementation spec`.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rule-provenance.md").write_text(
        "# Rule provenance ledger\n\n"
        "## drifted-entry — a drifted rule\n\n"
        "- Date: 2026-01-01\n"
        "- Failure: something broke once.\n"
        "- Rule: Always do the thing.\n"
        "- Cited by: rule.md § Heading\n",
        encoding="utf-8",
    )
    (tmp_path / "rule.md").write_text(
        "# Heading\n\nSomething completely different.\n", encoding="utf-8")

    done = _run_main(["--project-dir", str(tmp_path)])
    assert done.returncode == 2
    assert "FAIL rule_quote_in_cited_section" in done.stdout
    assert "add an entry" not in done.stdout
    assert "re-confirm the claim" in done.stdout


def test_main_hint_still_explains_how_to_add_an_entry_for_a_structural_failure(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rule-provenance.md").write_text(
        "# Rule provenance ledger\n\n"
        "## missing-field-entry — missing a required field\n\n"
        "- Date: 2026-01-01\n"
        "- Failure: something broke once.\n"
        "- Cited by: rule.md § Heading\n",
        encoding="utf-8",
    )
    done = _run_main(["--project-dir", str(tmp_path)])
    assert done.returncode == 2
    assert "FAIL entry_fields_complete" in done.stdout
    assert "add or complete an entry" in done.stdout
    assert "re-confirm the claim" not in done.stdout


def test_main_does_not_crash_when_ledger_is_not_utf8(tmp_path):
    # _resolve_heading() (used for Cited by/Restated in targets) already
    # catches (OSError, UnicodeDecodeError) and reports "not readable as
    # UTF-8" instead of raising. main()'s own read of the ledger file must
    # follow the same contract -- an unreadable ledger is "feature not
    # configured", the same outcome as a missing file, not an uncaught
    # traceback that leaves scripts/validate.py's subprocess call with an
    # empty stdout and no FAIL line to relay.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rule-provenance.md").write_bytes(
        b"## entry-1 \xe2\x80\x94 title\n- Rule: something\n- bad byte: \x92\n")

    done = _run_main(["--project-dir", str(tmp_path)])
    assert done.stderr == ""
    assert done.stdout == ""
    assert done.returncode == 0


# --- R2: zero dependency -------------------------------------------------

def _top_level_imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_provenance_py_imports_only_stdlib_and_preflight():
    allowed = set(sys.stdlib_module_names) | {"preflight"}
    found = _top_level_imports(os.path.join(SCRIPTS_DIR, "provenance.py"))
    assert found <= allowed, found - allowed
