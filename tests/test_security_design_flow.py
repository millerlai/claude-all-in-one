"""Workflow callers must enforce the Security core, including omitted flags."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

import design_probe
import ledger
import preflight
import security_design as sd
from test_design_probe_diagnosis import DIAGNOSIS
from test_design_probe_tiers import STANCE
from test_intake_signals import intake
from test_security_design import (approve_case, current_case, document, evidence,
                                  set_response, write_context)


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "cai"
PROBE = PLUGIN / "scripts" / "design_probe.py"


def track_case(tmp_path, *, applies="no", kind=None):
    case = current_case(tmp_path, entry="track", applies=applies, kind=kind,
                        artifact_path=".cai/track/case/intake.md")
    text = case["artifact"].read_text(encoding="utf-8")
    security = "## Security" + text.split("## Security", 1)[1].split("## Verification levels", 1)[0]
    case["artifact"].write_text(intake().replace("## Verification levels", security + "## Verification levels"),
                               encoding="utf-8")
    if applies != "no":
        set_response(case)
    case["track"].joinpath("state.md").write_text(
        "| stage | status | artifact | note |\n|---|---|---|---|\n"
        "| design | done | .cai/track/case/intake.md | |\n| build | | | |\n"
        "| verify | | | |\n| ship | | | |\n", encoding="utf-8")
    approve_case(case)
    return case


def probe(case, *extra):
    return subprocess.run([sys.executable, str(PROBE), "--kind", "intake",
                           "--project-dir", str(case["root"]), *extra, str(case["artifact"])],
                          capture_output=True, text=True, encoding="utf-8")


def build(case):
    return preflight.build(str(case["track"]), str(case["root"]))


def test_build_cannot_skip_resume_by_omitting_design_probe_security_flags(tmp_path):
    case = track_case(tmp_path)
    assert probe(case).returncode == 0
    case["directory"].joinpath("context.json").unlink()
    checks = build(case)
    assert any(not ok and "provenance-unknown" in label for ok, label in checks), checks
    assert all(ok for ok, label in checks if label.startswith(("artifact_unchanged", "design_signed_off")))


def test_build_accepts_an_approved_current_short_path(tmp_path):
    case = track_case(tmp_path)
    assert all(ok for ok, _ in build(case)), build(case)


@pytest.mark.parametrize("kind,accepted", [("implementation-baseline", True), ("live-constraint", False)])
def test_build_calls_resume_instead_of_rechecking_a_changed_implementation_as_ready(tmp_path, kind, accepted):
    case = track_case(tmp_path, applies="yes", kind=kind)
    (tmp_path / "callback.py").write_bytes(b"implementation changed after approval\n")
    checks = build(case)
    assert all(ok for ok, _ in checks) is accepted, checks
    if not accepted:
        assert any(not ok and "stale-source" in label for ok, label in checks)


def test_build_rejects_a_dependency_kind_change_even_when_it_would_skip_live_content(tmp_path):
    case = track_case(tmp_path, applies="yes", kind="live-constraint")
    (tmp_path / "callback.py").write_bytes(b"changed live policy\n")
    case["context"]["dependencies"][0]["kind"] = "implementation-baseline"
    write_context(case)
    assert any(not ok for ok, _ in build(case))


def test_proven_legacy_short_path_is_read_only_and_not_a_missing_context_exemption(tmp_path):
    case = track_case(tmp_path)
    text = case["artifact"].read_text(encoding="utf-8")
    text = text.split("## Security", 1)[0] + "## Verification levels" + text.split("## Verification levels", 1)[1]
    case["artifact"].write_text(text, encoding="utf-8")
    ledger.append(str(case["track"]), "design", "passed", artifact=str(case["artifact"]), gate="human")
    proofs = [("workflow-version", b"Fixture workflow before Security policy"),
              ("approval", json.dumps(ledger.records(str(case["track"]), "design")).encode("utf-8")),
              ("artifact-snapshot", case["artifact"].read_bytes())]
    case["context"].update(policy="legacy", policy_version=0, review=None, dependencies=None,
                            provenance=[evidence(tmp_path, case["directory"], kind, body) for kind, body in proofs])
    write_context(case)
    original = case["artifact"].read_bytes()
    assert all(ok for ok, _ in build(case)), build(case)
    assert case["artifact"].read_bytes() == original
    case["directory"].joinpath("context.json").unlink()
    assert any(not ok and "provenance-unknown" in label for ok, label in build(case))


@pytest.mark.parametrize("phase", ["draft", "ready"])
def test_intake_probe_runs_the_explicit_security_phase(tmp_path, phase):
    case = track_case(tmp_path)
    done = probe(case, "--security-phase", phase, "--security-entry", "track")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Context" in done.stdout


def test_intake_security_must_precede_the_verification_levels(tmp_path):
    case = track_case(tmp_path)
    text = case["artifact"].read_text(encoding="utf-8")
    before, rest = text.split("## Security", 1)
    security, levels = rest.split("## Verification levels", 1)
    case["artifact"].write_text(before + "## Verification levels" + levels + "\n## Security" + security,
                               encoding="utf-8")
    done = probe(case, "--security-phase", "draft", "--security-entry", "track")
    assert done.returncode == 2
    assert "security_placement" in done.stdout


def test_security_is_a_shared_template_section_not_a_fifth_mode():
    assert design_probe.DESIGN_SECTIONS == ("Diagnosis", "Stance", "Decisions", "Detail")
    text = (PLUGIN / "templates" / "design.md.tpl").read_text(encoding="utf-8")
    assert list(design_probe.sections(text)) == [*design_probe.DESIGN_SECTIONS, "Security"]
    assert "security.md.tpl" in design_probe.sections(text)["Security"]
    assert "### Applicability" not in text
    diagnosis = (PLUGIN / "templates" / "design-diagnosis.md.tpl").read_text(encoding="utf-8")
    assert list(design_probe.sections(diagnosis)) == [*design_probe.DIAGNOSIS_HEADINGS, "Security"]


@pytest.mark.parametrize("kind,body", [("stance", STANCE), ("diagnosis", DIAGNOSIS)])
def test_shared_security_content_does_not_inflate_a_modes_page_budget(tmp_path, kind, body):
    path = tmp_path / (kind + ".md")
    path.write_text(body + "\n## Security\n\n### Scope\n" + "Shared model narrative.\n" * 150,
                    encoding="utf-8")
    done = subprocess.run([sys.executable, str(PROBE), "--kind", kind, "--project-dir", str(ROOT), str(path)],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr


def test_validator_accepts_shared_security_roots_without_changing_mode_contracts(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("validate_security_under_test", ROOT / "scripts" / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.read_text
    def with_security(path):
        text = original(path)
        if Path(path).name in ("design.md.tpl", "design-diagnosis.md.tpl") and not re.search(r"^## Security$", text, re.M):
            text += "\n## Security\n\n<!-- Use templates/security.md.tpl. -->\n"
        return text
    results = []
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(module, "read_text", with_security)
    monkeypatch.setattr(module, "check", lambda label, passed: results.append((label, passed)))
    # Other probe behavior has integration tests; isolate the template comparison.
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout=""))
    module._design_probe()
    capsys.readouterr()
    wanted = {"design template sections match the probe", "diagnosis template headings match the probe"}
    assert {label for label, passed in results if passed and label in wanted} == wanted


@pytest.mark.parametrize("relative,required", [
    ("skills/track/references/stage-design.md", ("threat-modeling.md", "--security-phase draft")),
    ("skills/track/SKILL.md", ("security_design.py", "--phase ready", "Context")),
    ("skills/design/SKILL.md", ("security_design.py", "--phase ready", "--entry standalone")),
    ("skills/track/references/approval-gates.md", ("--phase ready", "Risk decisions")),
    ("skills/track/references/stage-build.md", ("--phase resume", "--entry standalone")),
    ("skills/plan-review/SKILL.md", ("threat-modeling.md", "Security")),
])
def test_shared_entry_points_pin_their_security_handoff(relative, required):
    text = " ".join((PLUGIN / relative).read_text(encoding="utf-8").split())
    assert all(phrase in text for phrase in required)


def test_common_reference_adopts_all_three_sources_and_keeps_review_in_the_main_session():
    text = (PLUGIN / "skills/track/references/threat-modeling.md").read_text(encoding="utf-8")
    for phrase in ("CLAUDE.security.md", "threat-model.md", "security-architect.md",
                   "implementation-baseline", "live-constraint", "finding-impact", "author_id",
                   "review-response.md", "risk-acceptance:Tn", "three rounds"):
        assert phrase in text
    assert "main session" in text and "architect" in text


def draft_long_case(tmp_path, entry):
    case = current_case(tmp_path, entry=entry)
    case["artifact"].write_text(document(), encoding="utf-8")
    case["context"]["review"] = None
    path = (case["directory"] if entry == "standalone" else case["track"]) / "intake.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# Requirements\n\n## Acceptance criteria\n\n- AC1: Reject forged callbacks.\n\n"
                     b"## Verification levels\n\n| AC | level | check |\n|---|---|---|\n"
                     b"| AC1 | test | reject forged callbacks |\n")
    write_context(case)
    return case, path


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_draft_uses_explicit_intake_before_main_writes_the_final_ac_binding(tmp_path, entry, capsys):
    case, path = draft_long_case(tmp_path, entry)
    kwargs = {"project_dir": str(tmp_path), "intake": str(path), "entry": entry,
              "track_dir": str(case["track"]) if entry == "track" else None}
    assert all(ok for ok, _ in sd.check_document(str(case["artifact"]), phase="draft", **kwargs))
    ready = sd.check_document(str(case["artifact"]), phase="ready", **kwargs)
    assert any(not ok and "AC:" in label for ok, label in ready)
    assert sd.main(["fingerprint", "--project-dir", str(tmp_path), "--document", str(case["artifact"]),
                    "--intake", str(path)]) == 2
    assert "AC:" in capsys.readouterr().out
    kwargs["intake"] = None
    assert any(not ok for ok, _ in sd.check_document(str(case["artifact"]), phase="draft", **kwargs))


@pytest.mark.parametrize("entry", ["track", "standalone"])
@pytest.mark.parametrize("candidate", ["malformed", "duplicate"])
def test_draft_does_not_ignore_a_malformed_or_duplicate_binding_candidate(tmp_path, entry, candidate):
    case, path = draft_long_case(tmp_path, entry)
    if candidate == "malformed":
        binding = "AC: intake.md sha256 not-a-digest\n"
    else:
        import hashlib
        binding = ("AC: %s sha256 %s\n" % (path.relative_to(tmp_path).as_posix(),
                                            hashlib.sha256(path.read_bytes()).hexdigest())) * 2
    case["artifact"].write_text(case["artifact"].read_text(encoding="utf-8").replace(
        "## Security\n", binding + "\n## Security\n"), encoding="utf-8")
    checks = sd.check_document(str(case["artifact"]), project_dir=str(tmp_path), intake=str(path),
                                phase="draft", entry=entry,
                                track_dir=str(case["track"]) if entry == "track" else None)
    assert any(not ok and "AC:" in label for ok, label in checks)
