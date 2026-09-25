"""gen-codex.py -- the generator that turns plugins/cai into plugins/cai-codex.

The design is docs/design/2026-09-18-codex-support-detail.md ("### gen-codex.py"
in Implementation spec). U1 owns: collect/exclude, the override engine and its
anchor rule, the `${CLAUDE_PLUGIN_ROOT}` and `/cai:` rewrites,
`--check`/`--source`/`--out`, and the first override (approval-gates.md:21).
U2 adds every other override plus the rest of the deny-list, including the
fenced-code-block-only bash-syntax tokens. Emit, fingerprint and `--release`
are later units.

The module file is `gen-codex.py` (hyphenated, to match `gen-models.py`'s CLI
naming), so it cannot be `import`ed by name; it is loaded through `importlib`
instead. Every test that needs a source tree builds one in `tmp_path` rather
than touching the real `plugins/cai/` or `plugins/cai-codex/`, per the
"never let a test write the real tree" rule.
"""
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gen-codex.py"

_spec = importlib.util.spec_from_file_location("gen_codex", SCRIPT)
gen_codex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_codex)


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, encoding="utf-8")


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# collect() / exclusions
# ---------------------------------------------------------------------------

def test_collect_reads_every_file_as_bytes(tmp_path):
    write(tmp_path, "skills/foo/SKILL.md", "hello")
    write(tmp_path, "scripts/ledger.py", "print('x')")

    files = gen_codex.collect(tmp_path)

    assert files["skills/foo/SKILL.md"] == b"hello"
    assert files["scripts/ledger.py"] == b"print('x')"


def test_collect_excludes_the_listed_paths(tmp_path):
    write(tmp_path, "skills/usage/SKILL.md", "x")
    write(tmp_path, "skills/setup/SKILL.md", "x")
    write(tmp_path, "evals/some-case/case.json", "{}")
    write(tmp_path, "hooks/hooks.json", "{}")
    write(tmp_path, "prices.json", "{}")
    write(tmp_path, "scripts/statusline.py", "x")
    write(tmp_path, "scripts/install_statusline.py", "x")
    write(tmp_path, "scripts/usage_report.py", "x")
    write(tmp_path, "scripts/context_peak.py", "x")
    write(tmp_path, "scripts/gen-models.py", "x")
    write(tmp_path, "scripts/gen-commands.py", "x")
    write(tmp_path, "scripts/ledger.py", "x")  # not excluded

    files = gen_codex.collect(tmp_path)

    assert files == {"scripts/ledger.py": b"x"}


def test_collect_excludes_pycache_build_artifacts(tmp_path):
    # __pycache__ is gitignored (.gitignore:6) and holds binary .pyc files a
    # UTF-8 decode would crash on -- it is not part of the source tree the
    # design's exclusion list enumerates, but it is also not source.
    write(tmp_path, "scripts/ledger.py", "x")
    (tmp_path / "scripts" / "__pycache__").mkdir(parents=True)
    (tmp_path / "scripts" / "__pycache__" / "ledger.cpython-313.pyc").write_bytes(b"\x00\x01")

    files = gen_codex.collect(tmp_path)

    assert list(files) == ["scripts/ledger.py"]


# ---------------------------------------------------------------------------
# apply_overrides() / the anchor rule
# ---------------------------------------------------------------------------

def test_apply_overrides_replaces_the_anchor_exactly_once():
    files = {"a.md": "before\nTHE ANCHOR LINE\nafter\n"}
    overrides = [gen_codex.Override("a.md", "THE ANCHOR LINE", "THE REPLACEMENT", "why")]

    out = gen_codex.apply_overrides(files, overrides)

    assert out["a.md"] == "before\nTHE REPLACEMENT\nafter\n"


def test_apply_overrides_raises_when_the_anchor_is_missing():
    files = {"a.md": "no anchor here\n"}
    overrides = [gen_codex.Override("a.md", "THE ANCHOR LINE", "X", "why")]

    try:
        gen_codex.apply_overrides(files, overrides)
        assert False, "expected AnchorError"
    except gen_codex.AnchorError as e:
        assert e.target == "a.md"
        assert "found 0" in str(e)


def test_apply_overrides_raises_when_the_anchor_repeats():
    files = {"a.md": "X\nX\n"}
    overrides = [gen_codex.Override("a.md", "X", "Y", "why")]

    try:
        gen_codex.apply_overrides(files, overrides)
        assert False, "expected AnchorError"
    except gen_codex.AnchorError as e:
        assert "found 2" in str(e)


def test_apply_overrides_raises_when_the_target_file_does_not_exist():
    overrides = [gen_codex.Override("missing.md", "X", "Y", "why")]

    try:
        gen_codex.apply_overrides({}, overrides)
        assert False, "expected AnchorError"
    except gen_codex.AnchorError as e:
        assert e.target == "missing.md"
        assert "missing file" in str(e)


def test_every_shipped_override_matches_the_real_source_file():
    # Every override in codex-overrides.json (U1's first plus U2's rest) must
    # find its anchor exactly once in the real source tree, and its
    # replacement must land after apply_overrides runs against it. (A few
    # D9/D20 overrides append one sentence to the anchor rather than
    # replacing it, so the anchor text can still be present afterwards --
    # only the replacement's presence is asserted here.)
    overrides = gen_codex.load_overrides()
    assert len(overrides) > 1  # U1 shipped one; U2 adds every other one

    source_root = REPO_ROOT / "plugins" / "cai"
    files = {}
    for ov in overrides:
        if ov.target not in files:
            files[ov.target] = (source_root / ov.target).read_text(encoding="utf-8")
        count = files[ov.target].count(ov.anchor)
        assert count == 1, f"{ov.target}: anchor found {count} time(s): {ov.anchor!r}"

    out = gen_codex.apply_overrides(files, overrides)
    for ov in overrides:
        assert ov.replacement in out[ov.target]


def test_real_source_tree_has_zero_deny_hits_after_overrides_and_rewrite():
    # End-to-end on the real plugins/cai tree (read-only): every deny-list
    # site the design names either got an override above or was already
    # clear. This is U2's own "Done when" criterion (R3/I4).
    source_root = REPO_ROOT / "plugins" / "cai"
    raw = gen_codex.collect(source_root)
    text_files = {rel: content.decode("utf-8") for rel, content in raw.items()}
    overridden = gen_codex.apply_overrides(text_files, gen_codex.load_overrides())
    rewritten = gen_codex.rewrite(overridden)

    hits = gen_codex.deny_hits(rewritten)
    assert hits == [], hits


# ---------------------------------------------------------------------------
# rewrite() -- ${CLAUDE_PLUGIN_ROOT} and /cai:
# ---------------------------------------------------------------------------

def test_rewrite_turns_a_python_script_invocation_into_a_launcher_call():
    files = {"a.md": 'First run `python ${CLAUDE_PLUGIN_ROOT}/scripts/track_state.py left-open`.'}

    out = gen_codex.rewrite(files)

    assert "${CLAUDE_PLUGIN_ROOT}" not in out["a.md"]
    assert '<cai> track_state left-open' in out["a.md"]


def test_rewrite_turns_any_other_plugin_root_path_into_cai_root_with_a_preamble():
    files = {"a.md": "See `${CLAUDE_PLUGIN_ROOT}/skills/track/references/stage-build.md`."}

    out = gen_codex.rewrite(files)

    assert "${CLAUDE_PLUGIN_ROOT}" not in out["a.md"]
    assert "<cai-root>/skills/track/references/stage-build.md" in out["a.md"]
    assert "`<cai> --root`" in out["a.md"]


def test_rewrite_preamble_lands_after_frontmatter_not_before_it():
    files = {"a.md": "---\nname: foo\n---\nSee `${CLAUDE_PLUGIN_ROOT}/x.md`.\n"}

    out = gen_codex.rewrite(files)

    assert out["a.md"].startswith("---\nname: foo\n---\n")


def test_rewrite_script_call_only_file_still_gets_the_preamble():
    # A file whose only ${CLAUDE_PLUGIN_ROOT} occurrence is a script-call
    # site: PY_LAUNCHER.sub consumes it before the PLUGIN_ROOT_TOKEN check
    # runs, so the plain `if PLUGIN_ROOT_TOKEN in new` check alone would miss
    # it and ship a `<cai>` placeholder with nothing defining it.
    files = {"a.md": 'Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/track_state.py left-open`.'}

    out = gen_codex.rewrite(files)

    assert gen_codex.CAI_ROOT_PREAMBLE in out["a.md"]
    assert "<cai> track_state left-open" in out["a.md"]


def test_rewrite_leaves_a_file_with_no_plugin_root_token_alone():
    files = {"a.md": "nothing to rewrite here\n"}

    out = gen_codex.rewrite(files)

    assert out["a.md"] == "nothing to rewrite here\n"


def test_rewrite_turns_a_cai_skill_invocation_into_a_dollar_form():
    files = {"a.md": "Run `/cai:track status` then `/cai:build`."}

    out = gen_codex.rewrite(files)

    assert "/cai:" not in out["a.md"]
    assert "$track status" in out["a.md"]
    assert "$build" in out["a.md"]


# ---------------------------------------------------------------------------
# deny_hits()
# ---------------------------------------------------------------------------

def test_deny_hits_finds_a_leftover_plugin_root_token():
    files = {"a.md": "line one\n${CLAUDE_PLUGIN_ROOT} leaked\n"}

    hits = gen_codex.deny_hits(files)

    assert hits == [("a.md", 2, "${CLAUDE_PLUGIN_ROOT}")]


def test_deny_hits_finds_a_leftover_cai_dispatch_token():
    files = {"a.md": "/cai:build leaked\n"}

    hits = gen_codex.deny_hits(files)

    assert hits == [("a.md", 1, "/cai:")]


def test_deny_hits_is_clean_after_a_correct_rewrite():
    files = {"a.md": "python ${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py append and /cai:build\n"}

    assert gen_codex.deny_hits(gen_codex.rewrite(files)) == []


def test_deny_hits_allows_the_two_named_tokens_in_scripts_viewer_py():
    # DENY_ALLOW exempts exactly (scripts/viewer.py, AskUserQuestion) and
    # (scripts/viewer.py, subagent_type) -- the real use case is a Python
    # string literal naming Claude's own tool/parameter, quoted for display.
    files = {"scripts/viewer.py": (
        'ROW = "AskUserQuestion"\n'
        'FIELD = "subagent_type"\n'
    )}

    hits = gen_codex.deny_hits(files)

    assert hits == []


def test_deny_hits_still_blocks_the_same_token_in_a_different_file():
    # Proves the allow-list is scoped to the exact path, not global.
    files = {"skills/something/SKILL.md": "mentions AskUserQuestion here\n"}

    hits = gen_codex.deny_hits(files)

    assert hits == [("skills/something/SKILL.md", 1, "AskUserQuestion")]


def test_deny_hits_still_blocks_other_tokens_in_scripts_viewer_py():
    # Proves the allow-list exempts only the two named tokens, not the whole
    # file.
    files = {"scripts/viewer.py": "leaked ${CLAUDE_PLUGIN_ROOT} here\n"}

    hits = gen_codex.deny_hits(files)

    assert hits == [("scripts/viewer.py", 1, "${CLAUDE_PLUGIN_ROOT}")]


def test_deny_hits_finds_the_u2_anywhere_tokens():
    files = {"a.md": (
        "AskUserQuestion leaked\n"
        "Agent(subagent_type=architect) leaked\n"
        "CLAUDE_CODE_FOO leaked\n"
        "~/.claude/rules/ leaked\n"
    )}

    hits = gen_codex.deny_hits(files)

    assert hits == [
        ("a.md", 1, "AskUserQuestion"),
        ("a.md", 2, "subagent_type"),
        ("a.md", 3, "CLAUDE_CODE_"),
        ("a.md", 4, "~/.claude/"),
    ]


def test_deny_hits_scopes_claude_md_to_rules_and_agents():
    files = {
        "rules/workflow.md": "see that project's CLAUDE.md\n",
        "agents/shipper.md": "see that project's CLAUDE.md\n",
        "skills/setup/SKILL.md": "see that project's CLAUDE.md\n",
    }

    hits = gen_codex.deny_hits(files)

    assert hits == [
        ("rules/workflow.md", 1, "CLAUDE.md"),
        ("agents/shipper.md", 1, "CLAUDE.md"),
    ]


def test_deny_hits_finds_fenced_only_tokens_inside_a_fence():
    files = {"a.md": (
        "prose mentioning `${VAR:-default}` is fine outside a fence\n"
        "```bash\n"
        "one && two\n"
        "git branch \"backup/$(date +%Y%m%d)\"\n"
        "ls foo 2>/dev/null\n"
        "echo \"${BRANCH:-main}\"\n"
        "```\n"
    )}

    hits = gen_codex.deny_hits(files)

    assert ("a.md", 1, "${VAR:-") not in hits  # outside the fence: not flagged
    assert ("a.md", 3, "&&") in hits
    assert ("a.md", 4, "$(date") in hits
    assert ("a.md", 5, "2>/dev/null") in hits
    assert ("a.md", 6, "${VAR:-") in hits


def test_deny_hits_finds_a_hard_coded_interpreter_invoking_the_launcher():
    files = {
        "a.md": 'python "$HOME/.codex/cai/launcher.py" track_state left-open\n',
        "b.md": 'python3 "$HOME/.codex/cai/launcher.py" track_state left-open\n',
        "c.md": 'py "$HOME/.codex/cai/launcher.py" track_state left-open\n',
    }

    hits = gen_codex.deny_hits(files)

    assert ("a.md", 1, 'python "$HOME/.codex/cai/launcher.py"') in hits
    assert any(path == "b.md" for path, _, _ in hits)
    assert any(path == "c.md" for path, _, _ in hits)


def test_real_generated_tree_has_zero_hard_coded_interpreter_hits(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    files = {}
    for p in out.rglob("*"):
        if p.is_file():
            files[p.relative_to(out).as_posix()] = p.read_text(encoding="utf-8")

    hits = [(path, lineno, token) for path, lineno, token in gen_codex.deny_hits(files)
            if "launcher.py" in token]
    assert hits == []


def test_deny_hits_leaves_fenced_only_tokens_alone_outside_a_fence():
    files = {"a.md": "one && two, run it with `$(date)`, `2>/dev/null`, `${VAR:-x}`\n"}

    assert gen_codex.deny_hits(files) == []


# ---------------------------------------------------------------------------
# CLI: --check / --source / --out, end to end on temp trees
#
# Every override in codex-overrides.json (U1's first plus U2's rest) is
# loaded from the fixed OVERRIDES_FILE regardless of --source, so a trimmed
# synthetic source tree would fail every override whose target it does not
# contain. These tests run against a copy of the real plugins/cai tree
# instead -- never the real tree itself, per the "never let a test write the
# real tree" rule in this file's own docstring.
# ---------------------------------------------------------------------------

REAL_SOURCE = REPO_ROOT / "plugins" / "cai"


def _copy_real_source(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(REAL_SOURCE, source)
    return source


def test_check_on_a_freshly_generated_tree_exits_0(tmp_path):
    out = tmp_path / "out"

    gen = run("--source", str(REAL_SOURCE), "--out", str(out))
    assert gen.returncode == 0, gen.stdout + gen.stderr

    # The release record fingerprints the shipped tree -- generated files plus
    # whichever HAND_WRITTEN files exist for real (D13 as modified) -- so a
    # faithful stand-in for that tree needs them too, or --check reports a
    # false UNRELEASED because a real hand-written file (launcher.py, and
    # later install_codex.py/README.md/setup's SKILL.md) is missing from this
    # disposable copy. Read HAND_WRITTEN from the module rather than a
    # hard-coded list, so a later unit's addition is picked up automatically.
    for rel in gen_codex.HAND_WRITTEN:
        real_path = gen_codex.DEFAULT_OUT / rel
        if real_path.is_file():
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(real_path, dest)

    checked = run("--check", "--source", str(REAL_SOURCE), "--out", str(out))
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_check_reports_drift_when_the_disk_tree_is_stale(tmp_path):
    source = _copy_real_source(tmp_path)
    out = tmp_path / "out"
    assert run("--source", str(source), "--out", str(out)).returncode == 0

    # Edit the source after generating -- the on-disk output is now stale.
    write(source, "scripts/new.py", "print('new')")

    checked = run("--check", "--source", str(source), "--out", str(out))
    assert checked.returncode == 1
    assert "DRIFT" in checked.stdout


def test_a_stray_pycache_under_out_is_not_drift_and_not_deleted(tmp_path):
    # __pycache__ under --out is git-ignored (.gitignore:6) and never shipped,
    # but simply importing a hand-written file inside the generated tree (a
    # test, or a maintainer running one of its scripts by hand) creates one --
    # the on-disk comparison and the stale-file deletion must both ignore it,
    # the same way collect() already ignores it on the source side.
    out = tmp_path / "out"
    files = {"scripts/ledger.py": b"x"}
    gen_codex._write_tree(out, files)
    pycache = out / "scripts" / "__pycache__"
    pycache.mkdir()
    stray = pycache / "ledger.cpython-313.pyc"
    stray.write_bytes(b"\x00\x01")

    assert gen_codex._diff_with_disk(out, files) == []

    gen_codex._write_tree(out, files)
    assert stray.is_file()


def test_check_exits_1_when_an_anchor_sentence_is_edited(tmp_path):
    source = _copy_real_source(tmp_path)
    out = tmp_path / "out"
    p = source / "skills/track/references/approval-gates.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "adds that entry", "does something else entirely"),
        encoding="utf-8")

    checked = run("--check", "--source", str(source), "--out", str(out))

    assert checked.returncode == 1
    assert "ANCHOR" in checked.stdout


def test_zero_plugin_root_tokens_in_a_generated_temp_tree(tmp_path):
    out = tmp_path / "out"

    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    for p in out.rglob("*"):
        if p.is_file():
            assert "${CLAUDE_PLUGIN_ROOT}" not in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# C11 (PARTIAL): the live run showed the question tool being available did
# not stop the model from asking a human gate in plain text, so the
# ask-rule overrides now state an explicit if/else on the model's own tool
# list instead of a soft "when it's available".
# ---------------------------------------------------------------------------

def test_generated_tree_states_the_ask_rule_unambiguously(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    for p in out.rglob("*"):
        if p.is_file():
            try:
                assert "when it's available, otherwise" not in p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

    approval_gates = (out / "skills/track/references/approval-gates.md").read_text(encoding="utf-8")
    track_skill = (out / "skills/track/SKILL.md").read_text(encoding="utf-8")
    ticket_mirror = (out / "skills/track/references/ticket-mirror.md").read_text(encoding="utf-8")

    assert "if" in approval_gates and "is in your tool list, ask with it" in approval_gates
    assert "asked with `request_user_input` if it is in your tool list" in track_skill
    assert "If `request_user_input` is in your tool list, ask with it" in ticket_mirror


# ---------------------------------------------------------------------------
# U2 "Done when" rows: I9/G1 (ship prepares only), D9/D20 (no nested
# dispatch), R2/D16 (no bash-only syntax left in a fenced block)
# ---------------------------------------------------------------------------

def test_generated_ship_text_says_prepare_only(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    stage_ship = (out / "skills/track/references/stage-ship.md").read_text(encoding="utf-8")
    shipper = (out / "agents/cai_shipper.toml").read_text(encoding="utf-8")

    assert "prepares only" in stage_ship
    assert "no subagent runs an irreversible git/gh operation" in stage_ship.lower()
    assert "untested through release" in stage_ship  # G1's veto: never present the push prompt as guaranteed
    assert "prepares" in shipper or "Prepares" in shipper
    assert "Do not push" in shipper


def test_generated_build_text_uses_single_line_commit_m(tmp_path):
    # Codex's git skill defaults to a commit-message file when told only
    # "Commit" with no method, tripping a sandbox-approval prompt per unit --
    # the per-unit commit step must spell out a single-quoted, single-line
    # `git commit -m` instead.
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    stage_build = (out / "skills/track/references/stage-build.md").read_text(encoding="utf-8")

    start = stage_build.index("5. **Commit**")
    end = stage_build.index("**Never leave the tree", start)
    span = stage_build[start:end]

    assert "git commit -m '" in span
    assert "no message file" in span
    assert "-F" not in span


def test_generated_build_text_forbids_apostrophes_in_commit_summary(tmp_path):
    # N1 (docs/design/2026-09-23-codex-commit-message-prompts-stance.md): the
    # per-unit summary must stay free of apostrophes -- an embedded `'` closes
    # the single-quoted `-m` string early, and unquoted text after it (e.g. a
    # `$(...)` the summary happens to mention) runs as a live shell command
    # instead of being committed as text.
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    stage_build = (out / "skills/track/references/stage-build.md").read_text(encoding="utf-8")

    start = stage_build.index("5. **Commit**")
    end = stage_build.index("**Never leave the tree", start)
    span = stage_build[start:end]

    assert "apostrophe" in span.lower()


def test_generated_agent_and_stage_text_never_tells_a_subagent_to_dispatch(tmp_path):
    # D9: on Codex the main session does every dispatch build/verify need;
    # verifier only reconciles and implementer only implements one briefed
    # unit -- neither may be told to dispatch/spawn another agent itself.
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    verifier = (out / "agents/cai_verifier.toml").read_text(encoding="utf-8")
    implementer = (out / "agents/cai_implementer.toml").read_text(encoding="utf-8")
    stage_verify = (out / "skills/track/references/stage-verify.md").read_text(encoding="utf-8")
    stage_build = (out / "skills/track/references/stage-build.md").read_text(encoding="utf-8")
    designer = (out / "agents/cai_designer.toml").read_text(encoding="utf-8")
    stage_design = (out / "skills/track/references/stage-design.md").read_text(encoding="utf-8")

    assert "never dispatch" in verifier or "never dispatches" in verifier
    assert "dispatch the four agents" not in verifier
    assert "never dispatch" in implementer or "never dispatches" in implementer
    assert "dispatching the" not in implementer  # the old "dispatching the explorer, implementer..." framing

    assert "main session always reads Step 0 through Step 1" in stage_verify
    assert "always read directly by the main session" in stage_build
    assert "subagent the track dispatches to run this" not in stage_verify
    assert "subagent the track dispatches to run this" not in stage_build

    assert "you never dispatch" in designer.lower()
    assert "dispatch `explorer`" not in stage_design


def test_generated_tree_has_no_bash_only_syntax_left_in_a_fenced_block(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    raw = {}
    for p in out.rglob("*"):
        if p.is_file():
            try:
                raw[str(p.relative_to(out).as_posix())] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

    hits = [h for h in gen_codex.deny_hits(raw)
            if h[2] in ("&&", "$(date", "2>/dev/null", "${VAR:-")]
    assert hits == []


# ---------------------------------------------------------------------------
# Shipped text must not cite this repo's own design ids (CLAUDE.md, "Who a
# file is for": a shipped file "may not assume this repo's layout"). An
# override's `why` field is Ours and may cite them freely; only the
# `replacement` text that actually ships may not gain new citations.
# ---------------------------------------------------------------------------

ID_CITATION = re.compile(r"\((I[0-9]|D[0-9]{1,2}|G[0-9]|C[0-9]{1,2})[^)]{0,12}\)")


def test_no_override_replacement_introduces_a_design_id_citation():
    overrides = gen_codex.load_overrides()
    leaks = [(ov.target, line) for ov in overrides for line in ov.replacement.splitlines()
             if ID_CITATION.search(line)]
    assert leaks == []


def test_generated_tree_cites_no_more_design_ids_than_its_source():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        assert run("--source", str(REAL_SOURCE), "--out", str(out_dir)).returncode == 0

        worse = []
        for p in out_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(out_dir).as_posix()
            src = REAL_SOURCE / rel
            if not src.is_file():
                continue
            try:
                gen_text = p.read_text(encoding="utf-8")
                src_text = src.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            gen_count = len(ID_CITATION.findall(gen_text))
            src_count = len(ID_CITATION.findall(src_text))
            if gen_count > src_count:
                worse.append((rel, src_count, gen_count))
        assert worse == []


# ---------------------------------------------------------------------------
# U3 "Done when" rows: D2/D3/D17 (agent TOMLs, tier table, stages.json
# prefix), D8 (openai.yaml x N), D13 as modified 2026-09-19 (UNRELEASED,
# --release refusal)
# ---------------------------------------------------------------------------

AGENT_SHORT_NAMES = [
    "architect", "designer", "explorer", "implementer",
    "refactoring-detector", "reviewer", "security-reviewer",
    "shipper", "test-runner", "verifier",
]


def test_emit_writes_ten_agent_tomls_with_the_tier_table_and_a_version_stamp(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    tiers = gen_codex.load_tiers()
    roles = gen_codex.json.loads((REAL_SOURCE / "models.json").read_text(encoding="utf-8"))["assignments"]

    for short in AGENT_SHORT_NAMES:
        p = out / f"agents/cai_{short}.toml"
        assert p.is_file(), p
        text = p.read_text(encoding="utf-8")
        assert not (out / f"agents/{short}.md").exists()
        lines = text.splitlines()
        assert lines[0].startswith("# cai-codex-version: ")
        assert f'name = "cai_{short}"' in text
        tier = tiers[roles[f"agents/{short}.md"]]
        assert f'model = "{tier["model"]}"' in text
        assert f'model_reasoning_effort = "{tier["effort"]}"' in text
        assert "sandbox_mode = " in text
        assert "developer_instructions = '''" in text


def test_stages_json_agents_are_all_prefixed(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    stages = gen_codex.json.loads((out / "skills/track/stages.json").read_text(encoding="utf-8"))
    for stage in stages["stages"]:
        assert stage["agent"].startswith("cai_"), stage


def test_openai_yaml_ships_with_the_implicit_invocation_policy_off_for_every_flagged_skill(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    # D8's population is every source SKILL.md carrying the flag (81, "72
    # catalog + 9 ordinary") minus the two of those nine directories excluded
    # from the Codex tree wholesale (skills/usage, skills/setup) -- deviation
    # logged in implementation-notes.md, U3.
    raw = gen_codex.collect(REAL_SOURCE)
    expected = sum(
        1 for rel, content in raw.items()
        if rel.endswith("SKILL.md") and gen_codex.is_flagged_skill(content.decode("utf-8"))
    )

    found = list(out.rglob("agents/openai.yaml"))
    assert len(found) == expected
    for p in found:
        assert p.read_text(encoding="utf-8") == "policy:\n  allow_implicit_invocation: false\n"
        skill_md = p.parent.parent / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        fm_body, _ = gen_codex._split_frontmatter_body(text)
        keys = {key for key, _block in gen_codex._frontmatter_blocks(fm_body)}
        assert keys == {"name", "description"}


def test_relocate_catalog_moves_refactoring_catalog_under_skills():
    files = {
        "refactoring-catalog/extract-method/SKILL.md": "x",
        "refactoring-catalog/extract-method/agents/openai.yaml": "y",
        "skills/ship/SKILL.md": "z",
    }

    out = gen_codex.relocate_catalog(files)

    assert out == {
        "skills/extract-method/SKILL.md": "x",
        "skills/extract-method/agents/openai.yaml": "y",
        "skills/ship/SKILL.md": "z",
    }


def test_relocate_catalog_raises_on_a_name_collision_with_an_existing_skill():
    files = {
        "refactoring-catalog/ship/SKILL.md": "catalog version",
        "skills/ship/SKILL.md": "existing skill",
    }

    try:
        gen_codex.relocate_catalog(files)
        assert False, "expected a collision error"
    except ValueError as e:
        assert "ship" in str(e)


def test_real_source_tree_has_no_catalog_skill_name_collision():
    # The main session's own check, held as a test so a future addition to
    # either skills/ or refactoring-catalog/ cannot silently overwrite the
    # other once relocate_catalog runs for real.
    raw = gen_codex.collect(REAL_SOURCE)
    gen_codex.relocate_catalog(raw)  # raises on collision


def test_manifest_skills_field_is_the_bare_skills_string(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    manifest = gen_codex.json.loads((out / gen_codex.MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["skills"] == "./skills/"


def test_catalog_skills_land_under_skills_not_refactoring_catalog(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    assert (out / "skills/extract-method/SKILL.md").is_file()
    assert (out / "skills/extract-method/agents/openai.yaml").is_file()
    assert not (out / "refactoring-catalog").exists()


def test_claude_plugin_manifest_is_excluded_from_the_codex_tree(tmp_path):
    out = tmp_path / "out"
    assert run("--source", str(REAL_SOURCE), "--out", str(out)).returncode == 0

    assert not (out / ".claude-plugin").exists()


def test_manifest_carries_the_release_version_and_release_writes_the_record(tmp_path):
    # A project dir with no git history at all: find_base_ref returns None,
    # so release_refusal never fires here -- isolates this test from whatever
    # this repo's own base ref happens to have published.
    out = tmp_path / "out"
    release_file = tmp_path / "codex-release.json"
    rc = gen_codex.build(REAL_SOURCE, out, check=False, release="0.3.1",
                         release_file=release_file, project_dir=tmp_path)
    assert rc == 0

    manifest = gen_codex.json.loads((out / gen_codex.MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["version"] == "0.3.1"
    assert manifest["name"] == "cai-codex"

    record = gen_codex.json.loads(release_file.read_text(encoding="utf-8"))
    assert record["version"] == "0.3.1"
    assert record["fingerprint"].startswith("sha256:")

    # Re-running --check against the same out/release_file/project_dir is
    # clean: the record now matches the current fingerprint.
    checked = gen_codex.build(REAL_SOURCE, out, check=True,
                              release_file=release_file, project_dir=tmp_path)
    assert checked == 0


def test_release_refuses_a_version_already_published_on_the_base_ref(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "codex-release.json").write_text(
        '{"version": "0.2.0", "fingerprint": "sha256:whatever"}', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    out = tmp_path / "out"
    release_file = tmp_path / "codex-release.json"
    rc = gen_codex.build(REAL_SOURCE, out, check=False, release="0.2.0",
                         release_file=release_file, project_dir=repo)

    assert rc == 2
    assert not release_file.is_file()
    # A refused --release must not write the tree either -- otherwise `out`
    # is left stamped with the very version the command just refused to
    # record, even though nothing says so happened.
    assert not out.exists(), "a refused --release must not write the tree at all"


# ---------------------------------------------------------------------------
# D13 as modified 2026-09-19: pure decision functions, no git or real files
# ---------------------------------------------------------------------------

def test_check_unreleased_flags_a_changed_fingerprint_under_an_unchanged_version():
    working = {"version": "0.1.0", "fingerprint": "sha256:old"}
    unreleased, reason = gen_codex.check_unreleased(working, None, "sha256:new")
    assert unreleased
    assert "run --release" in reason


def test_check_unreleased_flags_no_record_at_all():
    unreleased, reason = gen_codex.check_unreleased(None, None, "sha256:x")
    assert unreleased
    assert "run --release" in reason


def test_check_unreleased_is_clean_when_fingerprint_matches_and_nothing_published():
    working = {"version": "0.1.0", "fingerprint": "sha256:same"}
    unreleased, _ = gen_codex.check_unreleased(working, None, "sha256:same")
    assert not unreleased


def test_check_unreleased_flags_output_changed_after_the_working_version_was_published():
    working = {"version": "0.1.0", "fingerprint": "sha256:same"}
    published = {"version": "0.1.0", "fingerprint": "sha256:different"}
    unreleased, reason = gen_codex.check_unreleased(working, published, "sha256:same")
    assert unreleased
    assert "0.1.0" in reason


def test_check_unreleased_is_clean_when_published_version_differs():
    # main published an older version -- this repo has since bumped and the
    # working record already agrees with the current fingerprint.
    working = {"version": "0.2.0", "fingerprint": "sha256:same"}
    published = {"version": "0.1.0", "fingerprint": "sha256:whatever"}
    unreleased, _ = gen_codex.check_unreleased(working, published, "sha256:same")
    assert not unreleased


def test_release_refusal_when_the_version_is_not_higher_than_published():
    published = {"version": "0.1.0", "fingerprint": "sha256:x"}
    assert gen_codex.release_refusal("0.1.0", published)
    assert gen_codex.release_refusal("0.0.9", published)
    assert not gen_codex.release_refusal("0.2.0", published)


def test_release_refusal_never_fires_with_no_published_record():
    # Lets U4-U6 keep re-recording 0.1.0 inside this PR: main has no record.
    assert not gen_codex.release_refusal("0.1.0", None)


# ---------------------------------------------------------------------------
# One small integration test with a real (temp) git repo, per the D13
# modification's own instruction: everything else above is pure.
# ---------------------------------------------------------------------------

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8")


def test_read_published_record_reads_the_base_refs_committed_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    release = repo / "scripts"
    release.mkdir()
    (release / "codex-release.json").write_text(
        '{"version": "0.1.0", "fingerprint": "sha256:abc"}', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    branch = _git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()

    record = gen_codex.read_published_record(repo, branch)

    assert record == {"version": "0.1.0", "fingerprint": "sha256:abc"}
    assert gen_codex.read_published_record(repo, "no-such-ref") is None
    assert gen_codex.read_published_record(repo, None) is None


def test_find_base_ref_finds_the_current_branch_when_named_main(tmp_path):
    repo = tmp_path / "repo2"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    assert gen_codex.find_base_ref(repo) == "main"


def test_find_base_ref_returns_none_with_no_usable_ref(tmp_path):
    repo = tmp_path / "repo3"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "some-feature")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    assert gen_codex.find_base_ref(repo) is None
