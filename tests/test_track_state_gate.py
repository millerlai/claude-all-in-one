"""UC4: `/cai:track status` says which stages a person let through.

The gate lives in the ledger record that passed, and a stage's streak begins
*after* that record -- so this is the one thing `streak()` can never answer.
Design is the exception (#139): its gate is the sign-off `build` checks,
which the last pass alone does not settle.
"""
import ledger
import track_state

ROWS = [("intake", "done", "—", ""), ("discover", "done", "—", ""),
        ("design", "done", "docs/design/thing-detail.md", ""),
        ("build", "in-progress", "—", "unit 3 of 5"),
        ("verify", "", "", ""), ("ship", "", "", "")]


def make_track(tmp_path, rows=ROWS):
    track = tmp_path / "billing-export"
    track.mkdir()
    lines = ["# fixture", "", "branch: feat/fixture", "started: 2026-08-29", "",
             "| stage | status | artifact | note |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    (track / "state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(track)


def status_text(track):
    return track_state.format_status("billing-export", track, ledger.stage_ids())


def write_design(tmp_path, text="the detail design"):
    """The document ROWS' design row names, at that path under the project
    root -- the directory `/cai:track status` runs from."""
    doc = tmp_path / "docs" / "design" / "thing-detail.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    return str(doc)


def design_line(track):
    return next(l for l in status_text(track).splitlines() if l.startswith("design"))


def test_the_human_gate_is_shown_against_the_stage_it_passed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    track = make_track(tmp_path)
    doc = write_design(tmp_path)
    ledger.append(track, "intake", "passed", artifact="—")
    ledger.append(track, "design", "passed", artifact=doc, gate="human",
                  note="signed off")
    # A later failure must not hide who signed the passing run off.
    ledger.append(track, "design", "failed", note="reopened")

    lines = {line.split()[0]: line for line in status_text(track).splitlines()
             if line and not line.startswith(("current", "next", "other", "skipped"))}
    assert "(gate: human)" in lines["design"]
    assert "(gate: auto)" in lines["intake"]
    # build has no passing record at all, so there is nobody to name.
    assert "gate:" not in lines["build"]


def test_a_track_with_no_ledger_prints_exactly_what_it_used_to(tmp_path):
    # R4: the ledger is optional. Every track that existed before this feature
    # has none, and its status output must not gain a column of blanks.
    track = make_track(tmp_path)
    assert "gate:" not in status_text(track)
    assert "next: build" in status_text(track)


# --- #139: design's gate is the one build checks, not the last pass's -------

def test_an_approve_recorded_before_the_stages_own_pass_shows_human(tmp_path, monkeypatch):
    """Gate 1 handed up as a pending question lands before design's own pass
    (approval-gates.md); build accepts it, so status must not read auto."""
    monkeypatch.chdir(tmp_path)
    track = make_track(tmp_path)
    doc = write_design(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc, gate="human")
    ledger.append(track, "design", "passed", artifact=doc)

    assert "(gate: human)" in design_line(track)


def test_an_approve_without_an_artifact_is_not_signed_off(tmp_path, monkeypatch):
    """#126's shape: nothing ties this Approve to a document, and build
    refuses it -- so a human row last must not read as signed off."""
    monkeypatch.chdir(tmp_path)
    track = make_track(tmp_path)
    doc = write_design(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc)
    ledger.append(track, "design", "passed", artifact="—", gate="human")

    assert "(gate: not signed off)" in design_line(track)


def test_a_design_that_passed_with_no_approve_is_not_signed_off(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    track = make_track(tmp_path)
    doc = write_design(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc)

    assert "(gate: not signed off)" in design_line(track)


def test_a_design_edited_after_its_approve_is_not_signed_off(tmp_path, monkeypatch):
    """What only the document itself can tell -- the ledger alone would still
    see a human pass of the last sha."""
    monkeypatch.chdir(tmp_path)
    track = make_track(tmp_path)
    doc = write_design(tmp_path)
    ledger.append(track, "design", "passed", artifact=doc)
    ledger.append(track, "design", "passed", artifact=doc, gate="human")
    write_design(tmp_path, "the detail design, edited after sign-off")

    assert "(gate: not signed off)" in design_line(track)
