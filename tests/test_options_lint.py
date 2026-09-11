"""options_lint.py: the shape half of rules/option-explainer.md (#73).

The rule listed six fields and never said what the block looks like, so a
reply that ran all six into one paragraph per option broke nothing the rule
could name. These tests are written against the two examples the issue itself
carries: the numbered, one-field-per-item shape it calls correct, and the
run-on paragraph it calls wrong.
"""
import options_lint


def verdicts(text):
    """{probe name: passed} -- the probe label minus its parenthesised detail,
    so a test asserts on the probe and not on its wording."""
    return {label.split(" (")[0]: ok for ok, label in options_lint.probes(text)}


def detail(text, probe):
    return next(label for _, label in options_lint.probes(text)
                if label.startswith(probe + " "))


FIELDS = ("1. **What it literally is**: it keeps the draft in one file.\n"
          "2. **ELI5**: like reading a letter aloud before posting it.\n"
          "3. **What actually changes**: one more file under scripts/.\n"
          "4. **What it costs**: a minute per list.\n"
          "5. **How reversible**: high -- deleting the file undoes it.\n"
          "6. **When it fits**: the same mistake keeps coming back.\n")

DIMENSIONS = ("## Dimensions compared here\n\n"
              "- **Where it is caught** — before the reply is sent, or after\n"
              "- **What it costs each time** — steps taken on every list\n\n")

PICK = ("If you would rather not weigh it, pick A, because the failure it\n"
        "catches is the one nobody notices. That stops being the right pick\n"
        "when the list is two options nobody disagrees about.\n")


def draft(options=("A (recommended)", "B"), fields=FIELDS,
          dimensions=DIMENSIONS, pick=PICK, table=""):
    body = "".join("## Option %s\n\n%s\n" % (name, fields) for name in options)
    return dimensions + table + body + pick


def test_a_compliant_draft_passes_every_probe():
    assert all(verdicts(draft()).values())


def test_the_run_on_paragraph_shape_finds_no_options():
    """The issue's second example in miniature: every field is present, none
    of them is a list item."""
    prose = ("Option A -- literally it keeps the draft in one file. ELI5: like\n"
             "reading a letter aloud. Changes: one more file. Costs: a minute.\n"
             "Reversible: high. Fits: the mistake keeps coming back.\n")
    result = verdicts(DIMENSIONS + prose + prose + PICK)
    assert result["options_found"] is False
    assert result["six_fields"] is False


def test_plain_text_titles_are_options_too():
    """The shape the issue calls correct writes `選項 A — ...` as plain text.
    Requiring a `##` heading would fail the example being enforced."""
    body = "".join("選項 %s — 名稱\n%s\n" % (name, FIELDS)
                   for name in ("A（recommended）", "B"))
    assert verdicts(DIMENSIONS + body + PICK)["options_found"] is True


def test_a_missing_field_is_named_with_its_option():
    five = FIELDS.replace("4. **What it costs**: a minute per list.\n", "")
    result = verdicts(draft(fields=five))
    assert result["six_fields"] is False
    assert "Option A" in detail(draft(fields=five), "six_fields")


def test_a_field_that_is_only_its_label_counts_as_empty():
    hollow = FIELDS.replace("2. **ELI5**: like reading a letter aloud before posting it.",
                            "2. **ELI5**:")
    assert verdicts(draft(fields=hollow))["fields_filled"] is False


def test_a_placeholder_field_counts_as_empty():
    tbd = FIELDS.replace("4. **What it costs**: a minute per list.",
                         "4. **What it costs**: TBD")
    assert verdicts(draft(fields=tbd))["fields_filled"] is False


def test_exactly_one_option_carries_the_marker():
    assert verdicts(draft(options=("A", "B")))["one_recommended"] is False
    assert verdicts(draft(options=("A (recommended)", "B (recommended)"))
                    )["one_recommended"] is False


def test_a_list_that_ends_on_its_last_option_has_no_pick():
    assert verdicts(draft(pick=""))["pick_closes"] is False


def test_a_wrapped_sixth_field_is_not_mistaken_for_the_pick():
    """`tail()` starts counting at the blank line, not at the last item, so a
    long sixth field cannot stand in for the closing paragraph."""
    wrapped = FIELDS.replace(
        "6. **When it fits**: the same mistake keeps coming back.\n",
        "6. **When it fits**: the same mistake keeps coming back, round after\n"
        "   round, in a shape nobody has managed to describe in one line yet.\n")
    assert verdicts(draft(fields=wrapped, pick=""))["pick_closes"] is False


def test_three_options_need_the_side_by_side_table():
    three = ("A (recommended)", "B", "C")
    assert verdicts(draft(options=three))["table_for_three_or_more"] is False
    table = "| | A | B | C |\n|---|---|---|---|\n| cost | a | b | c |\n\n"
    assert verdicts(draft(options=three, table=table))["table_for_three_or_more"] is True


def test_two_options_are_not_asked_for_a_table():
    assert "table_for_three_or_more" not in verdicts(draft())


def test_dimensions_written_as_a_numbered_list_are_not_dimensions():
    """Bullets there are what makes a list numbered from 1 mean `option`. A
    numbered dimensions list is read as an option block instead -- which is
    the failure being reported, not a parse to repair."""
    numbered = ("## Dimensions compared here\n\n"
                "1. **Where it is caught** — before the reply is sent, or after\n"
                "2. **What it costs each time** — steps taken on every list\n\n")
    result = verdicts(draft(dimensions=numbered))
    assert result["dimensions_declared"] is False
    assert result["six_fields"] is False
