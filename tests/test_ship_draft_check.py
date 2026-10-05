"""ship_draft_check.py: mechanical checks on ship's drafted commit message
and PR body, run by the main session before either menu in
references/approval-gates.md's Gate 2 (issue 196). No git repository is
needed here -- the script never shells out to git, only reads the files it
is given plus, for the ticket checks, a track's ticket.json.
"""
import json
import os
import subprocess
import sys

import ticket

SCRIPT = os.path.join(os.path.dirname(ticket.__file__), "ship_draft_check.py")


def run(message, body=None, ticket_number=None, track_dir=None, tmp_path=None):
    message_file = tmp_path / "message.txt"
    message_file.write_text(message, encoding="utf-8")
    args = [sys.executable, SCRIPT, "--message-file", str(message_file)]
    if body is not None:
        body_file = tmp_path / "body.md"
        body_file.write_text(body, encoding="utf-8")
        args += ["--body-file", str(body_file)]
    if ticket_number is not None:
        args += ["--ticket", str(ticket_number)]
    if track_dir is not None:
        args += ["--track-dir", str(track_dir)]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


# --- title -------------------------------------------------------------

def test_conventional_title_within_72_passes(tmp_path):
    done = run("fix(cai): a short title\n\n- a bullet\n", tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout
    assert "PASS title_format" in done.stdout
    assert "PASS title_length" in done.stdout


def test_title_over_72_fails(tmp_path):
    title = "fix(cai): " + "x" * 70
    assert len(title) > 72
    done = run(title + "\n", tmp_path=tmp_path)
    assert done.returncode == 2, done.stdout
    assert "FAIL title_length" in done.stdout
    assert "PASS title_format" in done.stdout


def test_non_conventional_title_fails(tmp_path):
    done = run("Fixed the thing\n", tmp_path=tmp_path)
    assert done.returncode == 2, done.stdout
    assert "FAIL title_format" in done.stdout


# --- closing keyword -----------------------------------------------------

def test_closing_keyword_with_ticket_fails(tmp_path):
    for phrase in ("Closes #7", "fix: #7", "Resolves owner/repo#7"):
        message = "fix(cai): a title\n\n%s\n" % phrase
        done = run(message, ticket_number=7, tmp_path=tmp_path)
        assert done.returncode == 2, (phrase, done.stdout)
        assert "FAIL closing_keyword_message" in done.stdout, (phrase, done.stdout)


def test_closing_keyword_in_body_fails(tmp_path):
    message = "fix(cai): a title\n\n- a bullet\n"
    done = run(message, body="Closes #7\n", ticket_number=7, tmp_path=tmp_path)
    assert done.returncode == 2, done.stdout
    assert "FAIL closing_keyword_body" in done.stdout
    assert "PASS closing_keyword_message" in done.stdout


def test_closing_keyword_without_ticket_pointer_is_not_checked(tmp_path):
    message = "fix(cai): a title\n\nCloses #7\n"
    done = run(message, tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout
    assert "closing_keyword" not in done.stdout


def test_ticket_json_without_number_still_forbids_closing_keyword(tmp_path):
    track = tmp_path / "track"
    track.mkdir()
    (track / "ticket.json").write_text(
        json.dumps({"backend": "github", "ref": "7", "login": None, "projection": None}),
        encoding="utf-8")
    message = "fix(cai): a title\n\nCloses #7\n"
    done = run(message, track_dir=track, tmp_path=tmp_path)
    assert done.returncode == 2, done.stdout
    assert "FAIL closing_keyword_message" in done.stdout


# --- Refs #N exactly once -------------------------------------------------

def test_refs_must_appear_exactly_once_in_message_and_body(tmp_path):
    zero = run("fix(cai): a title\n\nno pointer here\n",
               body="no pointer here either\n", ticket_number=9, tmp_path=tmp_path)
    assert zero.returncode == 2, zero.stdout
    assert "FAIL refs_message" in zero.stdout
    assert "FAIL refs_body" in zero.stdout

    twice = run("fix(cai): a title\n\nRefs #9\nRefs #9\n",
                body="Refs #9\nRefs #9\n", ticket_number=9, tmp_path=tmp_path)
    assert twice.returncode == 2, twice.stdout
    assert "FAIL refs_message" in twice.stdout
    assert "FAIL refs_body" in twice.stdout

    once = run("fix(cai): a title\n\nRefs #9\n",
               body="Refs #9\n", ticket_number=9, tmp_path=tmp_path)
    assert once.returncode == 0, once.stdout
    assert "PASS refs_message" in once.stdout
    assert "PASS refs_body" in once.stdout


def test_refs_to_a_different_number_sharing_a_prefix_fails(tmp_path):
    # "Refs #196" must not satisfy a check for ticket 19 -- a plain substring
    # count treats "Refs #196" as containing "Refs #19" once.
    done = run("fix(cai): a title\n\nRefs #196\n", ticket_number=19, tmp_path=tmp_path)
    assert done.returncode == 2, done.stdout
    assert "FAIL refs_message" in done.stdout


# --- attribution: not this script's job (main's #216) ----------------------

def test_no_attribution_check(tmp_path):
    message = ("fix(cai): a title\n\n- a bullet\n\n"
               "Co-Authored-By: Someone <someone@example.com>\n")
    done = run(message, tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout
    with open(SCRIPT, encoding="utf-8") as fh:
        assert "Co-Authored" not in fh.read()


# --- usage error -----------------------------------------------------------

def test_usage_error_exits_1(tmp_path):
    done = subprocess.run([sys.executable, SCRIPT], capture_output=True,
                          text=True, encoding="utf-8")
    assert done.returncode == 1, done.stdout


def test_missing_message_file_exits_1(tmp_path):
    done = subprocess.run(
        [sys.executable, SCRIPT, "--message-file", str(tmp_path / "nope.txt")],
        capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 1, done.stdout


# --- approval-gates.md and stage-ship.md name the script -------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPROVAL_GATES = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "approval-gates.md")
STAGE_SHIP = os.path.join(
    REPO_ROOT, "plugins", "cai", "skills", "track", "references", "stage-ship.md")


def _section(text, heading):
    import re
    start = text.index(heading)
    rest = text[start + len(heading):]
    m = re.search(r"\n## ", rest)
    end = start + len(heading) + (m.start() if m else len(rest))
    return text[start:end]


def test_approval_gates_squash_and_gate2_name_the_script():
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        text = fh.read()
    gate2 = _section(text, "## Gate 2")
    assert "ship_draft_check.py" in gate2
    # The squash message and the PR body are checked before the one Gate 2
    # front menu quotes them (S2); there is no separate squash item any more.
    assert "The squash**, `stage-ship.md` Step 4" not in text
    assert "ship_draft_check.py --message-file <the squash message draft>" in " ".join(gate2.split())


def test_gate2_pr_body_invocation_also_passes_message_file():
    # --message-file is required (test_usage_error_exits_1 above) -- the
    # documented `gh pr create` check must pass it alongside --body-file or
    # the quoted command exits 1 instead of running the checks (issue 196).
    with open(APPROVAL_GATES, encoding="utf-8") as fh:
        text = fh.read()
    gate2 = _section(text, "## Gate 2")
    pr_body_line_start = gate2.index("ship_draft_check.py")
    pr_body_paragraph = gate2[pr_body_line_start:pr_body_line_start + 200]
    assert "--message-file" in pr_body_paragraph, pr_body_paragraph
    assert "--body-file" in pr_body_paragraph, pr_body_paragraph


def test_stage_ship_step4_points_at_approval_gates():
    with open(STAGE_SHIP, encoding="utf-8") as fh:
        text = fh.read()
    section = _section(text, "## Step 4")
    assert "approval-gates.md" in section
