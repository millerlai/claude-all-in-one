"""The Security contract is structural; these checks do not judge safe designs."""
import hashlib
import json
from pathlib import Path

import pytest

import ledger
import security_design as sd


CATEGORIES = (
    "spoofing", "tampering", "repudiation", "information-disclosure",
    "denial-of-service", "elevation-of-privilege", "abuse", "race-replay",
    "business-logic", "supply-chain",
)
AC_ROWS = [{"ac": "AC1", "level": "test", "check": "reject forged callbacks"},
           {"ac": "AC2", "level": "manual", "check": "read deployment policy"}]
THREAT = ("| T1 | F1 | spoofing | An attacker forges a paid callback and ships an "
          "unpaid order | Verify the signature a\\|b before changing state | AC1 | "
          "control-planned | Signing-key compromise remains possible |\n")


def document(*, applies="yes", review="pending"):
    coverage = "".join("| %s | %s | %s |\n" % (
        category, "yes" if category == "spoofing" else "no",
        "T1 covers this attack" if category == "spoofing"
        else "The callback does not change this part of the system")
        for category in CATEGORIES)
    return ("# Callback — design\n\n## Stance\n\n### Status\n\ndraft\n\n"
            "### Purpose\n\nKeep unpaid orders from shipping.\n\n"
            "## Security\n\n### Applicability\n\n| Field | Value |\n|---|---|\n"
            "| schema | 1 |\n| applies | %s |\n| reason | Changes payment state |\n"
            "| evidence | callback.py records provider input |\n\n"
            "### Scope\n\nAn unauthenticated sender can reach the payment callback; "
            "order status and inventory are the assets.\n\n"
            "### Flows\n\n| ID | From | To | Data | Trust boundary |\n"
            "|---|---|---|---|---|\n| F1 | Provider | Callback | Payment event | "
            "Untrusted network to order service |\n\n"
            "### Coverage\n\n| Category | Relevance | Reason |\n|---|---|---|\n%s\n"
            "### Threats\n\n| ID | Flow | Category | Scenario | Control | AC | "
            "Disposition | Residual risk |\n|---|---|---|---|---|---|---|---|\n%s\n"
            "### Assumptions\n\n| ID | Statement | State | Evidence |\n|---|---|---|---|\n"
            "| A1 | Provider publishes signing keys | confirmed | Provider contract v1 |\n\n"
            "### Risk decisions\n\n| Threat | Decision | Reason | Evidence |\n|---|---|---|---|\n\n"
            "### Review\n%s\n" % (applies, coverage, THREAT, review))


def no_model():
    return ("# Wording correction\n\n## Security\n\n### Applicability\n\n"
            "| Field | Value |\n|---|---|\n| schema | 1 |\n| applies | no |\n"
            "| reason | Only corrects spelling |\n| evidence | README diff only |\n"
            "| dependencies_sha256 | %s |\n\n"
            "### Review\nnot-applicable\n" % hashlib.sha256(b"[]").hexdigest())


def problems(text, phase="draft", ac_rows=None):
    return [label for ok, label in sd.model_checks(
        sd.parse_security(text), AC_ROWS if ac_rows is None else ac_rows,
        phase=phase) if not ok]


def test_absent_security_is_distinct_from_evidenced_no():
    assert sd.parse_security("# No model yet\n") is None
    model = sd.parse_security(no_model())
    assert model.applicability["applies"] == "no"
    assert problems(no_model(), "ready") == []


def test_model_reads_fixed_data_and_escaped_pipes_without_semantic_claims():
    model = sd.parse_security(document())
    assert model.flows[0]["ID"] == "F1"
    assert model.threats[0]["Control"] == "Verify the signature a|b before changing state"
    assert model.review == "pending"
    assert problems(document()) == []
    assert all("safe" not in label.lower() for _, label in
               sd.model_checks(model, AC_ROWS, phase="draft"))


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fenced_headings_and_tables_do_not_create_model_sections(fence):
    fake = "%smd\n## Security\n### Applicability\n| schema | 99 |\n%s\n" % (fence, fence)
    assert problems(fake + document()) == []
    assert sd.parse_security(fake) is None


@pytest.mark.parametrize("old,new,field", [
    ("## Security\n", "## Security\n\n## Security\n", "Security"),
    ("### Scope\n", "### Scope\n\n### Scope\n", "Scope"),
    ("### Scope\n", "### Unspecified\n", "Unspecified"),
    ("| schema | 1 |", "| schema | 2 |", "schema"),
    ("| schema | 1 |", "| schema | 1 |\n| schema | 1 |", "schema"),
    ("| schema | 1 |", "| undocumented | 1 |", "undocumented"),
    ("| applies | yes |", "| applies | maybe |", "applies"),
    ("| reason | Changes payment state |\n", "", "reason"),
    ("| Field | Value |", "| Field | Result |", "Applicability"),
    ("| F1 | Provider | Callback | Payment event | Untrusted network to order service |",
     "| F1 | Provider | Callback | Payment event |", "Flows"),
    ("| F1 | Provider", "| F0 | Provider", "F0"),
    (THREAT, THREAT + THREAT, "T1"),
    ("| spoofing | yes |", "| spoofing | sometimes |", "Relevance"),
    ("| tampering | no |", "| spoofing | no |", "spoofing"),
    ("| A1 | Provider publishes signing keys | confirmed |",
     "| A1 | Provider publishes signing keys | assumed |", "State"),
    ("| control-planned |", "| implemented |", "Disposition"),
])
def test_malformed_contract_names_the_field_without_echoing_the_model(old, new, field):
    with pytest.raises(sd.SecurityFormatError, match=field) as exc:
        sd.parse_security(document().replace(old, new))
    assert "unpaid order" not in str(exc.value)


@pytest.mark.parametrize("old,new,field", [
    ("| F1 | Provider", "| test-secret-not-for-output | Provider", "Flows.ID"),
    ("| T1 | F1 |", "| T1 | test-secret-not-for-output |", "Flow"),
    ("| AC1 | control-planned |", "| test-secret-not-for-output | control-planned |", "AC"),
])
def test_malformed_identifiers_do_not_echo_arbitrary_input(old, new, field):
    try:
        model = sd.parse_security(document().replace(old, new))
    except sd.SecurityFormatError as exc:
        labels = str(exc)
    else:
        labels = "\n".join(label for _, label in sd.model_checks(model, AC_ROWS, phase="draft"))
    assert "test-secret-not-for-output" not in labels
    assert field in labels


def test_missing_required_model_section_is_not_an_empty_model():
    with pytest.raises(sd.SecurityFormatError, match="Scope"):
        sd.parse_security(document().replace("### Scope\n", ""))


@pytest.mark.parametrize("old,new,identifier", [
    ("| T1 | F1 |", "| T1 | F9 |", "F9"),
    ("| AC1 | control-planned |", "| AC9 | control-planned |", "AC9"),
    ("| AC1 | control-planned |", "| none | control-planned |", "T1"),
    ("| spoofing | yes | T1 covers this attack |",
     "| spoofing | yes |  |", "spoofing"),
])
def test_cross_links_and_required_evidence_fail_by_identifier(old, new, identifier):
    assert any(identifier in issue for issue in problems(document().replace(old, new)))


@pytest.mark.parametrize("rows", [
    AC_ROWS + [AC_ROWS[0]],
    [{"ac": "AC1", "level": "test", "check": ""}],
    [{"ac": "AC1", "level": "runtime", "check": "send forged callback"}],
])
def test_referenced_acceptance_criteria_need_unique_valid_verification(rows):
    assert any("AC1" in issue for issue in problems(document(), ac_rows=rows))


def test_draft_preserves_unknown_open_and_unresolved_but_ready_refuses_them():
    text = document(applies="unknown").replace("| confirmed |", "| open |")
    text = text.replace("| control-planned |", "| unresolved |")
    assert problems(text) == []
    ready = problems(text, "ready")
    assert any("applies" in issue for issue in ready)
    assert any("A1" in issue for issue in ready)
    assert any("T1" in issue for issue in ready)
    assert any("Review" in issue for issue in ready)


def test_no_cannot_hide_unresolved_threats_and_open_assumptions():
    text = document(applies="no", review="not-applicable")
    text = text.replace("| confirmed |", "| open |")
    assert problems(text)


def test_scope_needs_narrative_rather_than_only_a_template_comment():
    scope = ("An unauthenticated sender can reach the payment callback; "
             "order status and inventory are the assets.")
    text = document().replace(scope, "<!-- Fill in the scope before review. -->")
    assert any("Scope" in issue for issue in problems(text))


@pytest.mark.parametrize("phase", ["draft", "ready"])
def test_scope_preserves_a_literal_pipe_in_narrative(phase):
    scope = ("An unauthenticated sender can reach the payment callback; "
             "order status and inventory are the assets.")
    text = document(review="Independent review response").replace(
        scope, "The gateway accepts A | B messages from external senders.")
    assert problems(text, phase) == []


def test_no_cannot_hide_unknown_coverage_in_an_optional_model():
    text = document(applies="no", review="not-applicable").replace(THREAT, "")
    text = text.replace("| spoofing | yes |", "| spoofing | unknown |")
    assert any("Coverage" in issue for issue in problems(text, "ready"))


def test_no_cannot_claim_a_confirmed_optional_assumption_without_evidence():
    text = document(applies="no", review="not-applicable").replace(THREAT, "")
    text = text.replace("| confirmed | Provider contract v1 |", "| confirmed |  |")
    assert any("A1" in issue for issue in problems(text, "ready"))


def test_pending_risk_without_an_answer_is_allowed_only_during_draft():
    text = document().replace("| control-planned |", "| risk-proposed |")
    text = text.replace("### Review\n", "| T1 | pending | Ask the owner before acceptance | |\n\n### Review\n")
    assert problems(text) == []
    assert any("T1" in issue for issue in problems(text, "ready"))


def test_empty_threat_table_needs_an_explicit_no_threat_reason():
    assert any("Threats" in issue for issue in problems(document().replace(THREAT, "")))
    explained = document().replace(THREAT, "\nNo threat scenario was identified in this bounded flow.\n")
    assert problems(explained) == []


@pytest.mark.parametrize("phase", ["draft", "ready"])
def test_no_threat_explanation_preserves_a_literal_pipe(phase):
    text = document(review="Independent review response").replace(
        THREAT, "\nNo threat was identified for the read-only A | B message flow.\n")
    assert problems(text, phase) == []


@pytest.mark.parametrize("decision", ["pending", "reject"])
def test_ready_refuses_unaccepted_risk_proposals(decision):
    text = document(review="review response belongs to unit 2")
    text = text.replace("| control-planned |", "| risk-proposed |")
    text = text.replace("### Review\n", "| T1 | %s | Owner decision needed | reply:17 |\n\n### Review\n" % decision)
    assert problems(text) == []
    assert any("T1" in issue for issue in problems(text, "ready"))


def test_orphan_risk_decision_and_duplicate_ac_are_not_ignored():
    text = document().replace("### Review\n", "| T9 | accept | Accepted | reply:17 |\n\n### Review\n")
    assert any("T9" in issue for issue in problems(text))
    assert any("AC1" in issue for issue in problems(document().replace(
        "| AC1 | control-planned |", "| AC1,AC1 | control-planned |")))


def test_empty_template_does_not_pass_a_draft_check():
    path = Path(__file__).resolve().parents[1] / "plugins/cai/templates/security.md.tpl"
    try:
        model = sd.parse_security(path.read_text(encoding="utf-8"))
    except sd.SecurityFormatError:
        return
    assert any(not ok for ok, _ in sd.model_checks(model, AC_ROWS, phase="draft"))


def dependency(identifier="D1", **changes):
    row = {"id": identifier, "path": "callback.py", "source_ref": "git:abc",
           "sha256": "a" * 64, "kind": "implementation-baseline",
           "snapshot_path": ".cai/design-security/key/dependencies/D1-a.snapshot"}
    return dict(row, **changes)


def digest(text, intake=b"requirements\n", dependencies=None):
    return sd.review_input_digest(text.encode("utf-8"), intake,
                                  [dependency()] if dependencies is None else dependencies)


def test_digest_uses_specified_length_delimiters_and_dependency_contents():
    text = document()
    projected = text.replace("\ndraft\n", "\n<approval-status>\n")
    projected = projected.replace("### Review\npending\n", "### Review\n<excluded-review>\n")
    d, i = projected.encode("utf-8"), b"requirements\n"
    s = json.dumps([dependency()], sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    expected = b"cai-security-input-v1\0" + b"".join(
        len(part).to_bytes(8, "big") + part for part in (d, i, s))
    assert digest(text) == hashlib.sha256(expected).hexdigest()


def test_review_can_contain_its_digest_without_a_self_reference():
    text = document()
    fingerprint = digest(text)
    completed = text.replace("### Review\npending\n", "### Review\n#### Result\n"
                             "input_sha256: %s\n\nAll findings retained.\n" % fingerprint)
    assert digest(completed) == fingerprint
    assert digest(completed + "\n## Other section\nchanged\n") != fingerprint


def test_only_formal_mode_status_lines_are_projected():
    text = document() + "\n## Status\n\ndraft\n"
    assert digest(text) == digest(text.replace("### Status\n\ndraft", "### Status\n\napproved 2026-10-28"))
    assert digest(text) != digest(text.replace("## Status\n\ndraft", "## Status\n\napproved 2026-10-28"))
    assert digest(text) != digest(text.replace("Keep unpaid orders", "Keep paid orders"))


@pytest.mark.parametrize("mode", ["stance", "diagnosis", "high-level design"])
def test_standalone_template_status_is_projected(mode):
    text = no_model().replace("# Wording correction\n", "# Callback — %s\n\n## Status\n\ndraft\n" % mode)
    assert digest(text) == digest(text.replace("\ndraft\n", "\napproved 2026-10-28\n"))


@pytest.mark.parametrize("status", ["draft\nAdditional approval claim", "draft\napproved 2026-10-28", "done"])
def test_status_subsection_cannot_hide_extra_content(status):
    with pytest.raises(sd.SecurityFormatError, match="Status"):
        digest(document().replace("\ndraft\n", "\n%s\n" % status))


def test_fake_review_and_status_in_code_remain_part_of_the_fingerprint():
    text = document().replace("### Purpose\n", "### Purpose\n\n```md\n### Review\npending\n### Status\ndraft\n```\n")
    assert digest(text) != digest(text.replace("pending\n### Status", "ready\n### Status"))


def test_digest_normalizes_only_newlines_and_not_whitespace_or_intake_changes():
    text = document()
    assert digest(text) == digest(text.replace("\n", "\r\n"), b"requirements\r\n")
    assert digest(text) == digest(text.replace("\n", "\r"), b"requirements\r")
    assert digest(text) != digest(text.replace("Callback |", "Callback  |"))
    assert digest(text) != digest(text, b"changed requirements\n")
    assert digest(text, None) != digest(text, b"requirements\n")


@pytest.mark.parametrize("field,new", [
    ("id", "D2"), ("path", "other.py"), ("source_ref", "git:def"),
    ("sha256", "b" * 64), ("kind", "live-constraint"),
    ("snapshot_path", ".cai/another.snapshot"),
])
def test_every_dependency_field_participates_in_the_digest(field, new):
    assert digest(document()) != digest(document(), dependencies=[dependency(**{field: new})])


def test_dependency_order_does_not_change_the_digest_but_a_new_source_does():
    deps = [dependency("D2"), dependency("D1")]
    assert digest(document(), dependencies=deps) == digest(document(), dependencies=list(reversed(deps)))
    assert digest(document(), dependencies=deps) != digest(document(), dependencies=deps[:1])


def test_dependency_binding_hashes_the_complete_canonical_list():
    dependencies = [dependency("D2"), dependency("D1")]
    expected = json.dumps(list(reversed(dependencies)), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    assert sd.dependency_digest(dependencies) == hashlib.sha256(expected).hexdigest()


def test_invalid_utf8_is_reported_as_a_format_error():
    with pytest.raises(sd.SecurityFormatError, match="UTF-8"):
        sd.review_input_digest(b"\xff", None, [])


# Unit 2: persisted evidence, unchanged inputs, and both approval entry points.

def response(fingerprint, *, execution="complete", verdict="ready", finding="", assumption=""):
    return ("#### Result\n\n| Field | Value |\n|---|---|\n"
            "| input_sha256 | %s |\n| execution | %s |\n| verdict | %s |\n\n"
            "#### Findings\n\n| ID | Severity | Threat or AC | Scenario | Required change |\n"
            "|---|---|---|---|---|\n%s\n"
            "#### Assumptions\n\n| ID | Statement | Evidence |\n|---|---|---|\n%s\n"
            "#### Limitations\n\nnone\n" % (fingerprint, execution, verdict, finding, assumption))


def evidence(root, directory, kind, content=b"Original message", source_ref=None):
    path = directory / (kind.replace(":", "-") + ".txt")
    path.write_bytes(content)
    return {"kind": kind, "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_ref": source_ref or "conversation:message-" + kind,
            "explanation": "Main session matched the original evidence to this artifact"}


def write_context(case):
    (case["directory"] / "context.json").write_text(
        json.dumps(case["context"]), encoding="utf-8")


def current_case(tmp_path, *, entry="standalone", applies="yes", kind=None, artifact_path="design.md"):
    root = tmp_path
    artifact = root / artifact_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(artifact_path.encode("utf-8")).hexdigest()
    directory = root / ".cai" / "design-security" / key
    directory.mkdir(parents=True)
    security = (no_model() if applies == "no" else document()).split("## Security", 1)[1]
    text = ("# Callback request\n\n## Acceptance criteria\n\n- AC1: Reject forged payment callbacks.\n\n"
            "## Security" + security + "\n## Verification levels\n\n"
            "| AC | level | check |\n|---|---|---|\n| AC1 | test | reject forged callbacks |\n")
    entry_evidence = evidence(root, directory, "design-entry", b"New design under security policy 1")
    context = {"schema": 1, "artifact": artifact_path, "entry": entry,
               "policy": "current", "policy_version": 1,
               "provenance": [entry_evidence], "provenance_verified": True,
               "dependencies": [], "review": None, "approval": None}
    if kind:
        source = root / "callback.py"
        source.write_bytes(b"original implementation\n")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        snapshots = directory / "dependencies"
        snapshots.mkdir()
        snapshot = snapshots / ("D1-%s.snapshot" % sha)
        snapshot.write_bytes(source.read_bytes())
        context["dependencies"] = [{"id": "D1", "path": "callback.py", "source_ref": "git:baseline",
                                    "sha256": sha, "kind": kind,
                                    "snapshot_path": snapshot.relative_to(root).as_posix()}]
    case = {"root": root, "artifact": artifact, "directory": directory, "entry": entry,
            "context": context, "track": root / ".cai" / "track" / "case"}
    if applies == "no":
        text = text.replace(hashlib.sha256(b"[]").hexdigest(), sd.dependency_digest(context["dependencies"]))
    artifact.write_text(text, encoding="utf-8")
    if applies != "no":
        set_response(case)
    write_context(case)
    return case


def set_response(case, *, intake_bytes=None, **changes):
    context, artifact = case["context"], case["artifact"]
    fingerprint = sd.review_input_digest(artifact.read_bytes(), intake_bytes, context["dependencies"])
    reply = response(fingerprint, **changes)
    path = case["directory"] / "review-response.md"
    path.write_text(reply, encoding="utf-8")
    text = artifact.read_text(encoding="utf-8")
    begin = text.index("### Review\n")
    end = text.find("## Verification levels", begin)
    end = len(text) if end < 0 else end
    artifact.write_text(text[:begin] + "### Review\n\n" + reply +
                        ("\n" if end < len(text) else "") + text[end:], encoding="utf-8")
    context["review"] = {"input_sha256": fingerprint,
                         "response_path": path.relative_to(case["root"]).as_posix(),
                         "response_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "source_ref": "agent:independent-review/message-17",
                         "verified_items": ["verdict", "findings", "assumptions", "limitations", "finding-impact"]}


def approve_case(case):
    context = case["context"]
    if context["entry"] == "track":
        case["track"].mkdir(parents=True, exist_ok=True)
        ledger.append(str(case["track"]), "design", "passed", artifact=str(case["artifact"]), gate="human")
    else:
        proof = next((row for row in context["provenance"] if row["kind"] == "approval"), None)
        if proof is None:
            proof = evidence(case["root"], case["directory"], "approval", b"Approve this complete design")
        context["approval"] = {"artifact_sha256": hashlib.sha256(case["artifact"].read_bytes()).hexdigest(),
                               "source_ref": proof["source_ref"], "evidence_path": proof["path"],
                               "evidence_sha256": proof["sha256"]}
    write_context(case)


def document_checks(case, phase="ready", *, intake=None, track_dir=None):
    return sd.check_document(str(case["artifact"]), project_dir=str(case["root"]),
                             intake=intake, phase=phase, entry=case["entry"],
                             track_dir=str(case["track"]) if track_dir is None and
                             case["entry"] == "track" else track_dir)


def failures(checks):
    return [label for ok, label in checks if not ok]


def test_context_identity_uses_the_normalized_project_relative_path(tmp_path):
    artifact = tmp_path / "docs" / "design.md"
    expected_key = hashlib.sha256(b"docs/design.md").hexdigest()
    expected = tmp_path / ".cai" / "design-security" / expected_key / "context.json"
    assert Path(sd.context_path(str(tmp_path), str(artifact))) == expected
    assert sd.context_path(str(tmp_path), str(tmp_path / "docs" / ".." / "docs" / "design.md")) == str(expected)
    with pytest.raises(sd.SecurityFormatError, match="artifact"):
        sd.context_path(str(tmp_path), str(tmp_path.parent / "outside.md"))
    assert sd.read_context(str(tmp_path), str(artifact)) is None


def test_context_corruption_is_not_absence_and_rename_does_not_reuse_identity(tmp_path):
    case = current_case(tmp_path)
    assert sd.read_context(str(tmp_path), str(case["artifact"])) == case["context"]
    assert sd.read_context(str(tmp_path), str(tmp_path / "renamed.md")) is None
    (case["directory"] / "context.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(sd.SecurityFormatError, match="Context"):
        sd.read_context(str(tmp_path), str(case["artifact"]))


@pytest.mark.parametrize("entry", ["track", "standalone"])
@pytest.mark.parametrize("kind", ["implementation-baseline", "live-constraint"])
def test_dependency_checks_distinguish_review_preparation_from_approved_continuation(tmp_path, entry, kind):
    case = current_case(tmp_path, entry=entry, kind=kind)
    dependencies = case["context"]["dependencies"]
    assert failures(sd.dependency_checks(dependencies, phase="prepare", project_dir=str(tmp_path))) == []
    assert failures(document_checks(case)) == []
    approve_case(case)
    (tmp_path / "callback.py").write_bytes(b"approved implementation has changed\n")
    assert any("stale-source" in issue for issue in failures(
        sd.dependency_checks(dependencies, phase="prepare", project_dir=str(tmp_path))))
    assert failures(document_checks(case, "ready"))
    resumed = failures(document_checks(case, "resume"))
    assert bool(resumed) == (kind == "live-constraint")


@pytest.mark.parametrize("phase", ["prepare", "ready", "resume"])
def test_every_phase_rejects_missing_or_damaged_dependency_snapshots(tmp_path, phase):
    case = current_case(tmp_path, kind="implementation-baseline")
    dep = case["context"]["dependencies"][0]
    snapshot = tmp_path / dep["snapshot_path"]
    snapshot.write_bytes(b"damaged evidence")
    assert any("stale-source" in issue for issue in failures(
        sd.dependency_checks([dep], phase=phase, project_dir=str(tmp_path))))
    snapshot.unlink()
    assert failures(sd.dependency_checks([dep], phase=phase, project_dir=str(tmp_path)))


def test_dependency_reads_before_and_after_detect_a_source_race(tmp_path, monkeypatch):
    case = current_case(tmp_path, kind="live-constraint")
    source, original, reads = tmp_path / "callback.py", Path.read_bytes, []
    def changing(path):
        if path == source:
            reads.append(path)
            if len(reads) > 1:
                return b"changed during check"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", changing)
    assert any("stale-source" in issue for issue in failures(sd.dependency_checks(
        case["context"]["dependencies"], phase="ready", project_dir=str(tmp_path))))


@pytest.mark.parametrize("change", ["kind", "remove", "duplicate", "snapshot-outside", "missing-source"])
def test_dependency_list_cannot_be_tampered_to_reuse_a_review(tmp_path, change):
    case = current_case(tmp_path, kind="live-constraint")
    approve_case(case)
    dep = case["context"]["dependencies"][0]
    if change == "kind":
        dep["kind"] = "implementation-baseline"
        (tmp_path / "callback.py").write_bytes(b"changed policy")
    elif change == "remove":
        case["context"]["dependencies"] = []
    elif change == "duplicate":
        case["context"]["dependencies"].append(dict(dep))
    elif change == "snapshot-outside":
        dep["snapshot_path"] = "../outside.snapshot"
    else:
        (tmp_path / "callback.py").unlink()
    write_context(case)
    assert failures(document_checks(case, "resume"))


@pytest.mark.parametrize("entry", ["track", "standalone"])
@pytest.mark.parametrize("change", ["remove", "refresh", "kind"])
def test_no_dependency_changes_cannot_reuse_the_original_approval(tmp_path, entry, change):
    case = current_case(tmp_path, entry=entry, applies="no", kind="live-constraint")
    approve_case(case)
    assert failures(document_checks(case, "resume")) == []
    original = case["artifact"].read_bytes()
    dependency = case["context"]["dependencies"][0]
    source = tmp_path / dependency["path"]
    if change == "remove":
        case["context"]["dependencies"] = []
    else:
        source.write_bytes(b"Changed policy after approval\n")
        if change == "kind":
            dependency["kind"] = "implementation-baseline"
        else:
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            snapshot = case["directory"] / "dependencies" / ("D1-%s.snapshot" % sha)
            snapshot.write_bytes(source.read_bytes())
            dependency.update(sha256=sha, source_ref="policy:v2",
                              snapshot_path=snapshot.relative_to(tmp_path).as_posix())
    write_context(case)
    assert failures(document_checks(case, "resume"))
    assert case["artifact"].read_bytes() == original


def test_no_requires_its_dependency_binding_only_at_final_handoff(tmp_path):
    case = current_case(tmp_path, applies="no")
    text = case["artifact"].read_text(encoding="utf-8")
    case["artifact"].write_text("".join(line for line in text.splitlines(keepends=True)
                                        if not line.startswith("| dependencies_sha256 |")),
                                encoding="utf-8")
    assert failures(document_checks(case, "draft")) == []
    assert failures(document_checks(case, "ready"))


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_no_rebinding_dependencies_requires_a_new_document_approval(tmp_path, entry):
    case = current_case(tmp_path, entry=entry, applies="no", kind="live-constraint")
    approve_case(case)
    old_binding = sd.dependency_digest(case["context"]["dependencies"])
    case["context"]["dependencies"] = []
    text = case["artifact"].read_text(encoding="utf-8")
    case["artifact"].write_text(text.replace(old_binding, sd.dependency_digest([])), encoding="utf-8")
    write_context(case)
    assert failures(document_checks(case, "ready")) == []
    assert failures(document_checks(case, "resume"))
    approve_case(case)
    assert failures(document_checks(case, "resume")) == []


def test_review_parser_keeps_minor_findings_and_requires_its_exact_contract():
    minor = "| R1 | Minor | T1 | A sender with a stolen key can forge a paid event and ship an unpaid order | Document key rotation |\n"
    parsed = sd.parse_review(response("a" * 64, finding=minor))
    assert parsed.result["execution"] == "complete"
    assert parsed.findings[0]["Severity"] == "Minor"
    assert parsed.assumptions == [] and parsed.limitations == "none"
    for broken in (response("a" * 64).replace("#### Limitations", "#### Other"),
                   response("a" * 64).replace("| execution | complete |", "| execution | done |"),
                   response("a" * 64).replace("#### Result", "#### Result\n\n#### Result"),
                   response("a" * 64, finding=minor + minor)):
        with pytest.raises(sd.SecurityFormatError):
            sd.parse_review(broken)


@pytest.mark.parametrize("field,row", [
    ("finding", "R1 | Major | T1 | Forged callbacks ship unpaid orders | Authenticate callbacks\n"),
    ("assumption", "A1 | Provider authenticates callbacks | Not confirmed\n"),
])
@pytest.mark.parametrize("gap", ["", "\n"])
def test_unbordered_review_rows_cannot_be_silently_dropped(tmp_path, field, row, gap):
    case = current_case(tmp_path)
    set_response(case, **{field: gap + row})
    write_context(case)
    assert failures(document_checks(case))


def test_review_rejects_a_non_table_line_attached_to_its_findings_table():
    with pytest.raises(sd.SecurityFormatError, match="Review.Findings"):
        sd.parse_review(response("a" * 64, finding="R1 Major T1: authentication is missing\n"))


@pytest.mark.parametrize("execution,verdict", [("failed", "ready"), ("insufficient", "insufficient"), ("complete", "revise")])
def test_incomplete_or_unready_review_is_never_ready(tmp_path, execution, verdict):
    case = current_case(tmp_path)
    set_response(case, execution=execution, verdict=verdict)
    write_context(case)
    assert failures(document_checks(case))


@pytest.mark.parametrize("severity,blocked", [("Minor", False), ("Major", True), ("Blocker", True)])
def test_review_findings_are_preserved_and_blocking_severities_refuse_ready(tmp_path, severity, blocked):
    case = current_case(tmp_path)
    finding = "| R1 | %s | T1 | A stolen key allows forged callbacks to ship unpaid orders | Rotate signing keys |\n" % severity
    set_response(case, finding=finding)
    write_context(case)
    assert bool(failures(document_checks(case))) == blocked
    assert severity in (case["directory"] / "review-response.md").read_text(encoding="utf-8")


def test_unconfirmed_review_assumptions_and_unverified_impact_are_not_ready(tmp_path):
    case = current_case(tmp_path)
    set_response(case, assumption="| A1 | Provider authenticates all callbacks | Not confirmed |\n")
    write_context(case)
    assert failures(document_checks(case))
    set_response(case)
    case["context"]["review"]["verified_items"].remove("finding-impact")
    write_context(case)
    assert failures(document_checks(case))


@pytest.mark.parametrize("change", ["missing-original", "changed-original", "changed-embedded", "unverified", "missing-source-ref", "pending"])
def test_review_evidence_cannot_be_replaced_by_a_success_summary(tmp_path, change):
    case = current_case(tmp_path)
    path = case["directory"] / "review-response.md"
    if change == "missing-original":
        path.unlink()
    elif change == "changed-original":
        path.write_text("successful dispatch", encoding="utf-8")
    elif change == "changed-embedded":
        case["artifact"].write_text(case["artifact"].read_text(encoding="utf-8").replace("none\n", "Edited summary\n"), encoding="utf-8")
    elif change == "unverified":
        case["context"]["review"]["verified_items"] = []
    elif change == "missing-source-ref":
        case["context"]["review"]["source_ref"] = ""
    else:
        case["context"]["review"] = None
    write_context(case)
    assert failures(document_checks(case))


def test_review_comparison_normalizes_newlines_but_preserves_reply_whitespace(tmp_path):
    case = current_case(tmp_path)
    path = case["directory"] / "review-response.md"
    original = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    path.write_bytes(original.replace(b"\n", b"\r\n"))
    case["context"]["review"]["response_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_context(case)
    assert failures(document_checks(case)) == []
    path.write_bytes(b"\n" + original + b" \n")
    case["context"]["review"]["response_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_context(case)
    assert failures(document_checks(case))


def test_review_hash_and_embedded_comparison_use_the_same_snapshot(tmp_path, monkeypatch):
    case = current_case(tmp_path)
    path = case["directory"] / "review-response.md"
    original = path.read_bytes()
    changed = original + b"\nChanged review qualification.\n"
    document_bytes = case["artifact"].read_bytes().replace(original, changed)
    read_bytes, reads = Path.read_bytes, []
    def changing(named):
        if named == path:
            reads.append(named)
            return original if len(reads) <= 2 else changed
        return read_bytes(named)
    monkeypatch.setattr(Path, "read_bytes", changing)
    assert failures(sd.review_checks(document_bytes, None, case["context"],
                                     project_dir=str(tmp_path)))


@pytest.mark.parametrize("decision,has_reply,ready", [("pending", False, False), ("reject", True, False), ("accept", False, False), ("accept", True, True)])
def test_risk_decisions_require_exact_original_acceptance_evidence(tmp_path, decision, has_reply, ready):
    case = current_case(tmp_path)
    proof = evidence(tmp_path, case["directory"], "risk-acceptance:T1", b"Accept the specific remaining T1 risk", "conversation:accept-T1")
    text = case["artifact"].read_text(encoding="utf-8").replace("| control-planned |", "| risk-proposed |")
    text = text.replace("### Review\n", "| T1 | %s | Owner decides this remaining risk | %s |\n\n### Review\n" %
                        (decision, proof["source_ref"] if has_reply else ""))
    case["artifact"].write_text(text, encoding="utf-8")
    if has_reply:
        case["context"]["provenance"].append(proof)
    set_response(case)
    write_context(case)
    assert bool(failures(document_checks(case))) != ready


@pytest.mark.parametrize("change", ["context-missing", "entry", "artifact", "version", "verified", "dependencies", "delete-model"])
def test_current_provenance_never_degrades_to_a_legacy_exemption(tmp_path, change):
    case = current_case(tmp_path)
    original = case["artifact"].read_bytes()
    if change == "context-missing":
        (case["directory"] / "context.json").unlink()
    elif change == "delete-model":
        case["artifact"].write_bytes(b"# Design without a Security model\n")
    else:
        values = {"entry": "track", "artifact": "other.md", "version": 0,
                  "verified": False, "dependencies": None}
        key = {"version": "policy_version", "verified": "provenance_verified"}.get(change, change)
        case["context"][key] = values[change]
        write_context(case)
    before = case["artifact"].read_bytes()
    assert failures(document_checks(case))
    assert case["artifact"].read_bytes() == before
    assert before == original or change == "delete-model"


def legacy_case(tmp_path, *, entry="standalone"):
    case = current_case(tmp_path, entry=entry, applies="no")
    case["artifact"].write_bytes(b"# Previously approved design\n\napproved 2026-01-01\n")
    case["context"].update(policy="legacy", policy_version=0, dependencies=None,
                           review=None, provenance=[])
    for kind, content in (("workflow-version", b"Historical workflow without security policy"),
                          ("approval", b"Original user approval under that workflow"),
                          ("artifact-snapshot", case["artifact"].read_bytes())):
        case["context"]["provenance"].append(evidence(tmp_path, case["directory"], kind, content))
    approve_case(case)
    return case


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_proven_legacy_resumes_without_rewriting_the_approved_artifact(tmp_path, entry):
    case = legacy_case(tmp_path, entry=entry)
    original = case["artifact"].read_bytes()
    assert failures(document_checks(case, "resume")) == []
    assert case["artifact"].read_bytes() == original


def test_legacy_hash_and_artifact_comparison_use_the_same_snapshot(tmp_path, monkeypatch):
    case = legacy_case(tmp_path)
    proof = next(row for row in case["context"]["provenance"] if row["kind"] == "artifact-snapshot")
    path = tmp_path / proof["path"]
    original = path.read_bytes()
    changed = b"# A different design from the historical snapshot\n"
    read_bytes, reads = Path.read_bytes, []
    def changing(named):
        if named == path:
            reads.append(named)
            return original if len(reads) <= 2 else changed
        return read_bytes(named)
    monkeypatch.setattr(Path, "read_bytes", changing)
    assert failures(sd.provenance_checks(case["context"], changed, entry="standalone",
                                         project_dir=str(tmp_path)))


@pytest.mark.parametrize("kind", ["workflow-version", "approval", "artifact-snapshot"])
def test_legacy_needs_each_link_of_historical_evidence(tmp_path, kind):
    case = legacy_case(tmp_path)
    case["context"]["provenance"] = [row for row in case["context"]["provenance"] if row["kind"] != kind]
    write_context(case)
    assert any("provenance-unknown" in issue for issue in failures(document_checks(case, "resume")))


def test_legacy_snapshot_and_current_schema_cannot_be_used_for_an_exemption(tmp_path):
    case = legacy_case(tmp_path)
    case["artifact"].write_bytes(b"# Changed after old approval\n")
    assert failures(document_checks(case, "resume"))
    case["artifact"].write_text(no_model(), encoding="utf-8")
    approve_case(case)
    assert failures(document_checks(case, "resume"))
    assert failures(document_checks(case, "ready"))


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_resume_requires_its_own_approval_and_detects_artifact_changes(tmp_path, entry):
    case = current_case(tmp_path, entry=entry)
    assert failures(document_checks(case, "resume"))
    approve_case(case)
    assert failures(document_checks(case, "resume")) == []
    case["artifact"].write_bytes(case["artifact"].read_bytes() + b"\nChanged after approval.\n")
    assert failures(document_checks(case, "resume"))


def test_document_before_after_check_rejects_a_mixed_snapshot(tmp_path, monkeypatch):
    case = current_case(tmp_path)
    original, reads = Path.read_bytes, []
    def changing(path):
        if path == case["artifact"]:
            reads.append(path)
            if len(reads) > 1:
                return original(path) + b"changed during check"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", changing)
    assert any("stale" in issue for issue in failures(document_checks(case)))


def test_fingerprint_cli_uses_only_persisted_dependencies_and_writes_nothing(tmp_path, capsys):
    case = current_case(tmp_path, kind="live-constraint")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert sd.main(["fingerprint", "--project-dir", str(tmp_path), "--document", str(case["artifact"])]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"schema": 1, "input_sha256": case["context"]["review"]["input_sha256"],
                      "dependencies_sha256": sd.dependency_digest(case["context"]["dependencies"]),
                      "dependencies": case["context"]["dependencies"]}
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    (tmp_path / "callback.py").write_bytes(b"changed source")
    assert sd.main(["fingerprint", "--project-dir", str(tmp_path), "--document", str(case["artifact"])]) == 2
    captured = capsys.readouterr()
    assert "stale-source" in captured.out + captured.err


def test_check_cli_uses_fail_exit_2_and_rejects_missing_track_approval_input(tmp_path, capsys):
    case = current_case(tmp_path, entry="track")
    assert sd.main(["check", "--phase", "resume", "--entry", "track", "--project-dir", str(tmp_path),
                    "--document", str(case["artifact"])]) == 2
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_no_still_requires_provenance_and_approval_but_not_a_special_review(tmp_path, entry):
    case = current_case(tmp_path, entry=entry, applies="no")
    assert failures(document_checks(case)) == []
    assert case["context"]["review"] is None
    approve_case(case)
    assert failures(document_checks(case, "resume")) == []
    case["context"]["provenance_verified"] = False
    write_context(case)
    assert failures(document_checks(case, "resume"))


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_long_design_requires_the_actual_bound_intake_and_detects_changes(tmp_path, entry):
    case = current_case(tmp_path, entry=entry)
    intake_path = (case["directory"] if entry == "standalone" else case["track"]) / "intake.md"
    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text("# Requirements\n\n## Acceptance criteria\n\n- AC1: Reject forged callbacks.\n\n"
                           "## Verification levels\n\n| AC | level | check |\n|---|---|---|\n"
                           "| AC1 | test | reject forged callbacks |\n", encoding="utf-8")
    sha = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    text = document().replace("## Security\n", "AC: %s sha256 %s\n\n## Security\n" %
                              (intake_path.relative_to(tmp_path).as_posix(), sha))
    case["artifact"].write_text(text, encoding="utf-8")
    set_response(case, intake_bytes=intake_path.read_bytes())
    write_context(case)
    assert failures(document_checks(case, intake=str(intake_path))) == []
    assert failures(document_checks(case))
    intake_path.write_bytes(intake_path.read_bytes() + b"\nChanged acceptance criteria.\n")
    assert failures(document_checks(case, intake=str(intake_path)))


@pytest.mark.parametrize("key", ["dependencies", "review", "approval", "provenance", "provenance_verified"])
def test_context_mandatory_fields_cannot_disappear(tmp_path, key):
    case = current_case(tmp_path)
    del case["context"][key]
    write_context(case)
    assert failures(document_checks(case))


def test_risk_acceptance_evidence_must_name_the_exact_original_reply(tmp_path):
    case = current_case(tmp_path)
    proof = evidence(tmp_path, case["directory"], "risk-acceptance:T1", b"Accept T1", "conversation:accept-T1")
    case["context"]["provenance"].append(proof)
    text = case["artifact"].read_text(encoding="utf-8").replace("| control-planned |", "| risk-proposed |")
    text = text.replace("### Review\n", "| T1 | accept | Accepted remaining risk | conversation:other-reply |\n\n### Review\n")
    case["artifact"].write_text(text, encoding="utf-8")
    set_response(case)
    write_context(case)
    assert failures(document_checks(case))


def as_diagnosis(case, *, merged=False):
    title = ("# Callback — design\n\n## Diagnosis\n\n### Status\n\ndraft\n\n"
             "### Symptom\n\nForged callbacks update unpaid orders.\n" if merged else
             "# Callback — diagnosis\n\n## Status\n\ndraft\n")
    text = case["artifact"].read_text(encoding="utf-8").replace("# Callback request\n", title)
    case["artifact"].write_text(text, encoding="utf-8")


@pytest.mark.parametrize("entry", ["track", "standalone"])
@pytest.mark.parametrize("merged", [False, True])
def test_diagnosis_can_use_its_own_acceptance_criteria_without_an_independent_intake(tmp_path, entry, merged):
    case = current_case(tmp_path, entry=entry)
    as_diagnosis(case, merged=merged)
    set_response(case)
    write_context(case)
    assert failures(document_checks(case)) == []
    approve_case(case)
    assert failures(document_checks(case, "resume")) == []


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_diagnosis_with_a_bound_independent_intake_cannot_omit_it(tmp_path, entry):
    case = current_case(tmp_path, entry=entry)
    as_diagnosis(case)
    intake = (case["directory"] if entry == "standalone" else case["track"]) / "intake.md"
    intake.parent.mkdir(parents=True, exist_ok=True)
    intake.write_bytes(b"# Requirements\n\n## Acceptance criteria\n\n- AC1: Reject forged callbacks.\n\n"
                       b"## Verification levels\n\n| AC | level | check |\n|---|---|---|\n"
                       b"| AC1 | test | reject forged callbacks |\n")
    binding = "AC: %s sha256 %s\n\n" % (intake.relative_to(tmp_path).as_posix(),
                                           hashlib.sha256(intake.read_bytes()).hexdigest())
    case["artifact"].write_text(case["artifact"].read_text(encoding="utf-8").replace(
        "## Security\n", binding + "## Security\n"), encoding="utf-8")
    set_response(case, intake_bytes=intake.read_bytes())
    write_context(case)
    assert failures(document_checks(case, intake=str(intake))) == []
    assert failures(document_checks(case))


@pytest.mark.parametrize("entry", ["track", "standalone"])
def test_malformed_diagnosis_binding_cannot_fall_back_to_its_own_criteria(tmp_path, entry):
    case = current_case(tmp_path, entry=entry)
    as_diagnosis(case)
    case["artifact"].write_text(case["artifact"].read_text(encoding="utf-8").replace(
        "## Security\n", "AC: missing-intake.md sha256 not-a-digest\n\n## Security\n"), encoding="utf-8")
    set_response(case)
    write_context(case)
    assert failures(document_checks(case))
