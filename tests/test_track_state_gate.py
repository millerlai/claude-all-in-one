"""UC4: `/cai:track status` says which stages a person let through.

The gate lives in the ledger record that passed, and a stage's streak begins
*after* that record -- so this is the one thing `streak()` can never answer.
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


def test_the_human_gate_is_shown_against_the_stage_it_passed(tmp_path):
    track = make_track(tmp_path)
    ledger.append(track, "intake", "passed", artifact="—")
    ledger.append(track, "design", "passed", artifact="—", gate="human",
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
