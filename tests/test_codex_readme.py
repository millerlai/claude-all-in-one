"""plugins/cai-codex/README.md -- the hand-written Codex mapping table.

Design: docs/design/2026-09-18-codex-support-detail.md, "### Codex README and
marketplace". U6 owns this file. AC6 requires every mapping-table row to
carry a Status, and four of them an exact one. This file asserts against the
real, shipped README -- it is hand-written (HAND_WRITTEN in gen-codex.py),
never regenerated, so there is no synthetic fixture to build instead.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "plugins" / "cai-codex" / "README.md"

STATUSES = {"verified", "documented, not tested", "degraded"}

# A design-id citation, e.g. "(C9)" or "(D5=A)" -- CLAUDE.md's "Who a file is
# for" makes a path into this repo's own tooling a defect in a shipped file,
# and a bare design id is exactly that: unreadable and unshippable outside
# this repository.
DESIGN_ID = re.compile(r"\((I[0-9]|D[0-9]{1,2}|G[0-9]|C[0-9]{1,2}|E[0-9])[^)]{0,12}\)")
REPO_INTERNAL_PATHS = (".claude/track", "docs/design", "raw/")


def _table_rows(text):
    """Every data row of the mapping table, as a list of cell strings."""
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| Claude Code behaviour"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue  # the header separator row
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
    return rows


def test_readme_exists():
    assert README.is_file()


def test_every_row_has_a_status_from_the_allowed_set():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    assert rows, "no mapping-table rows found"
    for row in rows:
        assert len(row) == 4, row
        assert row[2] in STATUSES, row


def test_push_approval_row_is_verified():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "approval prompt" in r[0].lower())
    assert row[2] == "verified"


def test_guard_row_is_verified_and_mentions_inactive_until_trusted():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "guard" in r[0].lower())
    assert row[2] == "verified"
    assert "inactive until trusted" in row[3]


def test_menu_gate_row_is_verified():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "menu gate" in r[0].lower())
    assert row[2] == "verified"


def test_launcher_paths_row_is_verified():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "plugin_root" in r[0].lower())
    assert row[2] == "verified"


def test_agents_md_cap_row_is_verified():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "global instructions file" in r[0].lower())
    assert row[2] == "verified"


def test_enable_default_mode_request_user_input_flag_is_documented():
    text = README.read_text(encoding="utf-8")
    assert "--enable default_mode_request_user_input" in text


def test_tools_allowlist_row_is_degraded():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "tools:" in r[0])
    assert row[2] == "degraded"


def test_usage_row_is_degraded():
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "usage" in r[0].lower())
    assert row[2] == "degraded"


def test_no_design_id_citation():
    text = README.read_text(encoding="utf-8")
    assert not DESIGN_ID.search(text)


def test_no_repo_internal_path():
    text = README.read_text(encoding="utf-8")
    for bad in REPO_INTERNAL_PATHS:
        assert bad not in text


def test_launcher_path_is_always_under_the_real_home_directory():
    """install_codex.py:12-13,81 -- the launcher is fixed under `$HOME`,
    never `$CODEX_HOME`."""
    text = README.read_text(encoding="utf-8")
    assert "$HOME/.codex/cai/" in text
    assert "$CODEX_HOME/cai" not in text


def test_requirements_describe_interpreter_lookup_order_not_a_bare_python():
    """The old wording claimed a bare `python` on PATH is enough; the real
    behavior is that $setup records its own interpreter (sys.executable) and
    every generated command reuses that recorded one instead of guessing."""
    text = README.read_text(encoding="utf-8")
    assert "python3" in text
    assert '"python"/"py -3"' in text or "`python`/`py -3`" in text
    assert "records" in text and "recorded interpreter" in text
    assert "`python` on PATH in the shell Codex runs commands in. Every generated" not in text


def test_windows_launcher_row_mentions_piping_output_through_powershell():
    """The Windows form of the recorded command additionally pipes the
    launcher's stdout/stderr through PowerShell so it reaches the tool
    output -- install_codex.py's cai_command_line()."""
    text = README.read_text(encoding="utf-8")
    assert "pipes the launcher's output through PowerShell" in text


def test_agents_are_not_claimed_fixed_under_home():
    """install_codex.py:14 -- agents follow `$CODEX_HOME`, unlike the
    launcher; the README must not claim `$HOME/.codex/agents/` as the
    install target."""
    text = README.read_text(encoding="utf-8")
    assert "$HOME/.codex/agents/" not in text


def test_guard_row_does_not_misattribute_inactivity_to_the_removed_feature():
    """The guard is inactive until trusted with /hooks -- not because a
    plugin-hooks feature flag is reported removed, which is irrelevant to
    the setup-written user-level hooks.json entry."""
    text = README.read_text(encoding="utf-8")
    rows = _table_rows(text)
    row = next(r for r in rows if "guard" in r[0].lower())
    assert "features list" not in row[3]
    assert "removed" not in row[3]


def _section(text, heading):
    """The text between one '## Heading' and the next (or end of file)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    assert start is not None, f"{heading!r} not found"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def test_usage_section_exists_and_mentions_setup_and_menu_flag():
    text = README.read_text(encoding="utf-8")
    section = _section(text, "## Usage")
    assert "$setup" in section
    assert "--enable default_mode_request_user_input" in section


def test_stale_not_exercised_claims_are_gone():
    text = README.read_text(encoding="utf-8")
    assert "was not exercised inside a real Codex session in this build" not in text
    assert "not yet re-exercised inside a live Codex session" not in text


ROOT_README = REPO_ROOT / "README.md"


def test_root_readme_mentions_codex_install_and_setup():
    text = ROOT_README.read_text(encoding="utf-8")
    assert "cai-codex@claude-all-in-one" in text
    assert "$setup" in text
