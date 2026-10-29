#!/usr/bin/env python3
"""Read the shared Security section and fingerprint its review inputs.

These checks establish structure and content identity, not design safety.
"""
from dataclasses import dataclass, field
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import ledger
import verify_plan


Check = tuple[bool, str]
CATEGORIES = (
    "spoofing", "tampering", "repudiation", "information-disclosure",
    "denial-of-service", "elevation-of-privilege", "abuse", "race-replay",
    "business-logic", "supply-chain",
)
HEADERS = {
    "Applicability": ("Field", "Value"),
    "Flows": ("ID", "From", "To", "Data", "Trust boundary"),
    "Coverage": ("Category", "Relevance", "Reason"),
    "Threats": ("ID", "Flow", "Category", "Scenario", "Control", "AC",
                "Disposition", "Residual risk"),
    "Assumptions": ("ID", "Statement", "State", "Evidence"),
    "Risk decisions": ("Threat", "Decision", "Reason", "Evidence"),
}
SECTIONS = ("Applicability", "Scope", "Flows", "Coverage", "Threats",
            "Assumptions", "Risk decisions", "Review")
MODES = ("Diagnosis", "Stance", "Decisions", "Detail")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
STATUS = re.compile(r"(?:draft|approved \d{4}-\d{2}-\d{2})$")


class SecurityFormatError(ValueError):
    """A malformed field, never an absent or inapplicable model."""


@dataclass
class SecurityModel:
    applicability: dict[str, str]
    scope: str
    flows: list[dict[str, str]]
    coverage: list[dict[str, str]]
    threats: list[dict[str, str]]
    assumptions: list[dict[str, str]]
    risk_decisions: list[dict[str, str]]
    review: str
    _text: str = field(default="", init=False, repr=False)
    _sections: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _security_range: tuple[int, int] = field(default=(0, 0), init=False, repr=False)
    _review_range: tuple[int, int] = field(default=(0, 0), init=False, repr=False)


def _lf(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _visible(lines):
    """Yield original line positions; fenced examples cannot define fields."""
    fence, in_comment = None, False
    for index, line in enumerate(lines):
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if fence:
            if re.fullmatch(r" {0,3}%s{%d,}\s*" % (re.escape(fence[0]), fence[1]),
                            line.rstrip("\n")):
                fence = None
            continue
        match = FENCE.match(line)
        if match:
            fence = (match[1][0], len(match[1]))
            continue
        if line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        yield index, line


def _headings(lines):
    return [(index, len(match[1]), match[2])
            for index, line in _visible(lines)
            if (match := HEADING.match(line))]


def _end(headings, start, level, length):
    return next((index for index, depth, _ in headings
                 if index > start and depth <= level), length)


def _table(text, name, headers=None):
    headers = HEADERS[name] if headers is None else headers
    lines = [line.strip() for _, line in _visible(text.splitlines())
             if line.strip().startswith("|") or line.strip().endswith("|")]
    if not lines or verify_plan._cells(lines[0]) != list(headers):
        raise SecurityFormatError("%s: expected table header %s" % (name, " / ".join(headers)))
    separator = verify_plan._cells(lines[1]) if len(lines) > 1 else None
    if (separator is None or len(separator) != len(headers)
            or not all(re.fullmatch(r":?-+:?", cell) for cell in separator)):
        raise SecurityFormatError("%s: missing table separator" % name)
    rows = []
    for line in lines[2:]:
        cells = verify_plan._cells(line)
        if cells is None or len(cells) != len(headers):
            raise SecurityFormatError("%s: wrong table cell count" % name)
        rows.append(dict(zip(headers, cells)))
    return rows


def _id_label(value):
    return value if re.fullmatch(r"(?:AC|[FATDR])\d+", value) else "<invalid>"


def _unique(rows, name, key, pattern=None):
    seen = set()
    for row in rows:
        identifier = row[key]
        if pattern and not re.fullmatch(pattern, identifier):
            raise SecurityFormatError("%s.%s: invalid ID %s" % (name, key, _id_label(identifier)))
        if identifier in seen:
            raise SecurityFormatError("%s: duplicate %s" % (name, identifier))
        seen.add(identifier)


def _enum(rows, name, key, values):
    for row in rows:
        if row[key] not in values:
            raise SecurityFormatError("%s.%s: unknown value" % (name, key))


def parse_security(text: str) -> SecurityModel | None:
    lines = _lf(text).splitlines(keepends=True)
    headings = _headings(lines)
    roots = [index for index, level, name in headings if level == 2 and name == "Security"]
    if not roots:
        return None
    if len(roots) != 1:
        raise SecurityFormatError("Security: duplicate root section")
    start = roots[0]
    end = _end(headings, start, 2, len(lines))
    children = [(index, name) for index, level, name in headings
                if start < index < end and level == 3]
    sections, ranges = {}, {}
    for index, name in children:
        if name not in SECTIONS:
            raise SecurityFormatError("Security: unknown subsection %s" % name)
        if name in sections:
            raise SecurityFormatError("Security: duplicate subsection %s" % name)
        stop = _end(headings, index, 3, end)
        sections[name] = "".join(lines[index + 1:stop])
        ranges[name] = (index, stop)
    for name in ("Applicability", "Review"):
        if name not in sections:
            raise SecurityFormatError("Security: missing %s" % name)

    fields = _table(sections["Applicability"], "Applicability")
    _unique(fields, "Applicability", "Field")
    required = {"schema", "applies", "reason", "evidence"}
    applicability = {row["Field"]: row["Value"] for row in fields}
    for name in applicability:
        if name not in required:
            raise SecurityFormatError("Applicability: unknown field %s" % name)
    for name in sorted(required - applicability.keys()):
        raise SecurityFormatError("Applicability: missing field %s" % name)
    if applicability["schema"] != "1":
        raise SecurityFormatError("Applicability.schema: expected 1")
    if applicability["applies"] not in ("yes", "no", "unknown"):
        raise SecurityFormatError("Applicability.applies: unknown value")
    if applicability["applies"] != "no":
        for name in SECTIONS:
            if name not in sections:
                raise SecurityFormatError("Security: missing %s" % name)

    tables = {name: _table(sections[name], name) if name in sections else []
              for name in HEADERS if name != "Applicability"}
    for name, prefix in (("Flows", "F"), ("Threats", "T"), ("Assumptions", "A")):
        _unique(tables[name], name, "ID", prefix + r"[1-9]\d*")
    _unique(tables["Coverage"], "Coverage", "Category")
    _enum(tables["Coverage"], "Coverage", "Category", CATEGORIES)
    _enum(tables["Coverage"], "Coverage", "Relevance", ("yes", "no", "unknown"))
    if "Coverage" in sections:
        present = {row["Category"] for row in tables["Coverage"]}
        if present != set(CATEGORIES):
            raise SecurityFormatError("Coverage: missing categories %s" % ", ".join(
                category for category in CATEGORIES if category not in present))
    _enum(tables["Threats"], "Threats", "Category", CATEGORIES)
    _enum(tables["Threats"], "Threats", "Disposition",
          ("control-planned", "risk-proposed", "unresolved"))
    _enum(tables["Assumptions"], "Assumptions", "State", ("confirmed", "open"))
    _unique(tables["Risk decisions"], "Risk decisions", "Threat", r"T[1-9]\d*")
    _enum(tables["Risk decisions"], "Risk decisions", "Decision", ("pending", "accept", "reject"))

    model = SecurityModel(applicability, sections.get("Scope", "").strip(),
                          tables["Flows"], tables["Coverage"], tables["Threats"],
                          tables["Assumptions"], tables["Risk decisions"],
                          sections["Review"].strip())
    model._text, model._sections = text, sections
    model._security_range, model._review_range = (start, end), ranges["Review"]
    return model


def _prose(text):
    return "\n".join(line.strip() for _, line in _visible(text.splitlines())
                     if line.strip() and verify_plan._cells(line) is None).strip()


def model_checks(model: SecurityModel, ac_rows: list[dict], *, phase: str) -> list[Check]:
    if phase not in ("draft", "ready", "resume"):
        raise SecurityFormatError("phase: unknown value")
    if model is None:
        return [(False, "Security: missing section")]
    final = phase != "draft"
    checks = [(bool(model.applicability[key].strip()), "Applicability.%s: nonempty" % key)
              for key in ("reason", "evidence")]
    applies = model.applicability["applies"]
    if applies != "no" or "Scope" in model._sections:
        checks.append((bool(_prose(model.scope)), "Scope: nonempty narrative"))
    for row in model.flows:
        checks.append((all(row[key] for key in HEADERS["Flows"]), "%s: complete flow" % row["ID"]))
    for row in model.coverage:
        checks.append((bool(row["Reason"]), "Coverage.%s: reason required" % row["Category"]))
        if final or applies == "no":
            checks.append((row["Relevance"] != "unknown",
                           "Coverage.%s: unknown requires further analysis" % row["Category"]))
    for row in model.assumptions:
        checks.append((bool(row["Statement"]) and bool(row["Evidence"]), "%s: assumption evidence required" % row["ID"]))
        if final:
            checks.append((row["State"] == "confirmed", "%s: open assumption" % row["ID"]))
    if applies == "no":
        checks += [(model.review == "not-applicable", "Review: no requires not-applicable"),
                   (not model.threats and not model.risk_decisions
                    and not any(row["State"] == "open" for row in model.assumptions),
                    "Applicability.no: no unresolved model items")]
        return checks

    if applies == "yes":
        checks.append((bool(model.flows), "Flows: applicable model needs a flow"))
    if final:
        checks.append((applies == "yes", "Applicability.applies: unknown cannot be ready"))
    flow_ids = {row["ID"] for row in model.flows}
    if not model.threats:
        checks.append((bool(_prose(model._sections.get("Threats", ""))),
                       "Threats: no-threat explanation required"))

    acs = {}
    for row in ac_rows:
        identifier = row.get("ac", "")
        checks.append((bool(verify_plan.AC_ID.fullmatch(identifier)), "AC: valid verification ID"))
        checks.append((identifier not in acs, "%s: unique verification row" % _id_label(identifier)))
        acs[identifier] = row
    threat_ids = {row["ID"] for row in model.threats}
    decisions = {row["Threat"]: row for row in model.risk_decisions}
    for row in model.threats:
        identifier = row["ID"]
        checks.append((row["Flow"] in flow_ids, "%s: Flow %s must exist" % (identifier, _id_label(row["Flow"]))))
        checks.append((all(row[key] for key in ("Scenario", "Control", "Residual risk")),
                       "%s: Scenario, Control and Residual risk required" % identifier))
        references = [] if row["AC"] == "none" else [part.strip() for part in row["AC"].split(",")]
        checks.append((row["AC"] == "none" or bool(row["AC"]), "%s: AC required" % identifier))
        checks.append((len(set(references)) == len(references), "%s: duplicate AC %s" % (
            identifier, ",".join(_id_label(ac) for ac in references))))
        if row["Disposition"] == "control-planned":
            checks.append((bool(references), "%s: implementation control needs AC" % identifier))
        for ac in references:
            verification = acs.get(ac)
            checks.append((verification is not None, "%s: AC %s must exist" % (identifier, _id_label(ac))))
            if verification is not None:
                checks.append((verification.get("level") in verify_plan.LEVELS
                               and bool(verification.get("check", "").strip()),
                               "%s: %s needs a verification level and check" % (identifier, _id_label(ac))))
        if final:
            checks.append((row["Disposition"] != "unresolved", "%s: unresolved threat" % identifier))
            if row["Disposition"] == "risk-proposed":
                decision = decisions.get(identifier)
                checks.append((decision is not None and decision["Decision"] == "accept"
                               and bool(decision["Evidence"]), "%s: accepted risk decision required" % identifier))
    for row in model.risk_decisions:
        threat = next((item for item in model.threats if item["ID"] == row["Threat"]), None)
        checks.append((row["Threat"] in threat_ids and threat["Disposition"] == "risk-proposed",
                       "%s: decision must name a risk-proposed threat" % row["Threat"]))
        checks.append((bool(row["Reason"]) and (row["Decision"] == "pending" or bool(row["Evidence"])),
                       "%s: risk decision reason and answer evidence required when decided" % row["Threat"]))
    checks.append((bool(model.review) and model.review != "not-applicable", "Review: applicable model needs a response"))
    if final:
        checks.append((model.review != "pending", "Review: pending cannot be ready"))
    return checks


def _status_replacements(lines):
    headings = _headings(lines)
    merged = any(level == 2 and name in MODES for _, level, name in headings)
    titles = [name for _, level, name in headings if level == 1]
    standalone = not merged and any(re.search(
        r"(?:—|-)\s*(?:stance|diagnosis|high-level design)$", title, re.IGNORECASE)
        for title in titles)
    mode, seen, replacements = None, set(), []
    for index, level, name in headings:
        if level <= 2:
            mode = name if level == 2 and name in MODES else None
        formal = name == "Status" and ((level == 3 and mode in MODES)
                                       or (level == 2 and standalone))
        if not formal:
            continue
        identity = mode if level == 3 else "standalone"
        if identity in seen:
            raise SecurityFormatError("Status: duplicate formal subsection")
        seen.add(identity)
        stop = _end(headings, index, level, len(lines))
        content = [(position, lines[position]) for position in range(index + 1, stop)
                   if lines[position].strip()]
        if len(content) != 1 or not STATUS.fullmatch(content[0][1].strip()):
            raise SecurityFormatError("Status: expected only draft or approved YYYY-MM-DD")
        position, line = content[0]
        replacements.append((position, position + 1,
                             "<approval-status>" + ("\n" if line.endswith("\n") else "")))
    return replacements


def _utf8_lf(data):
    try:
        return _lf(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise SecurityFormatError("input: expected UTF-8") from None


def review_input_digest(document: bytes, intake: bytes | None,
                        dependencies: list[dict]) -> str:
    text = _utf8_lf(document)
    model = parse_security(text)
    if model is None:
        raise SecurityFormatError("Security: missing section")
    lines = text.splitlines(keepends=True)
    start, stop = model._review_range
    replacements = _status_replacements(lines) + [(start, stop, "### Review\n<excluded-review>\n")]
    # Apply backwards so only parser-owned ranges can disappear from the input.
    for first, last, replacement in sorted(replacements, reverse=True):
        lines[first:last] = [replacement]
    d = "".join(lines).encode("utf-8")
    i = _utf8_lf(intake).encode("utf-8") if intake is not None else b""
    s = json.dumps(sorted(dependencies, key=lambda row: row["id"]), sort_keys=True,
                   ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"cai-security-input-v1\0" + b"".join(
        len(part).to_bytes(8, "big") + part for part in (d, i, s))).hexdigest()


@dataclass
class ReviewResponse:
    result: dict[str, str]
    findings: list[dict[str, str]]
    assumptions: list[dict[str, str]]
    limitations: str


def _shape(value, keys):
    return isinstance(value, dict) and set(value) == set(keys)


def _strings(value, keys):
    return all(isinstance(value.get(key), str) and value[key].strip() for key in keys)


def _sha(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _project_path(project_dir, value, *, external=False):
    if not isinstance(value, str) or not value.strip():
        raise SecurityFormatError("path: expected a nonempty local path")
    try:
        root, named = Path(project_dir).resolve(), Path(value)
        path = (root / named).resolve()
    except (OSError, ValueError):
        raise SecurityFormatError("path: invalid local path") from None
    if path == root or (not path.is_relative_to(root) and not (external and named.is_absolute())):
        raise SecurityFormatError("path: must stay inside the project")
    return path


def context_path(project_dir: str, document: str) -> str:
    root = Path(project_dir).resolve()
    try:
        artifact = _project_path(project_dir, document).relative_to(root).as_posix()
    except SecurityFormatError:
        raise SecurityFormatError("artifact: must stay inside the project") from None
    key = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
    return str(_project_path(project_dir, str(root / ".cai" / "design-security" / key / "context.json")))


def read_context(project_dir: str, document: str) -> dict | None:
    path = Path(context_path(project_dir, document))
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        raise SecurityFormatError("Context: unreadable") from None
    try:
        result = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SecurityFormatError("Context: invalid JSON") from None
    if not isinstance(result, dict):
        raise SecurityFormatError("Context: expected an object")
    return result


def _file_checks(path, expected, label, *, content=None):
    try:
        # Parsed evidence must be hashed from the snapshot the caller used.
        first = path.read_bytes() if content is None else content
        last = path.read_bytes()
        valid = hashlib.sha256(first).hexdigest() == expected and first == last
    except OSError:
        valid = False
    return [(valid, label)]


def _evidence_checks(proofs, document, *, project_dir, legacy=False):
    checks = []
    kinds = {"design-entry", "workflow-version", "approval", "artifact-snapshot"}
    for proof in proofs:
        valid = (_shape(proof, ("kind", "path", "sha256", "source_ref", "explanation"))
                 and _strings(proof, ("kind", "path", "sha256", "source_ref", "explanation")))
        if not valid:
            checks.append((False, "provenance-unknown: malformed Evidence"))
            continue
        kind = proof["kind"]
        known = kind in kinds or bool(re.fullmatch(r"risk-(?:acceptance|rejection):T[1-9]\d*", kind))
        checks.append((known and _sha(proof["sha256"]), "provenance-unknown: Evidence kind and fingerprint"))
        if not known or not _sha(proof["sha256"]):
            continue
        try:
            path = _project_path(project_dir, proof["path"])
            content = path.read_bytes()
            matches = content == document
            checks.extend(_file_checks(path, proof["sha256"], "provenance-unknown: %s evidence" % kind,
                                       content=content))
            if legacy and kind == "artifact-snapshot":
                checks.append((matches, "provenance-unknown: artifact-snapshot differs"))
        except (SecurityFormatError, OSError):
            checks.append((False, "provenance-unknown: %s evidence unavailable" % kind))
    return checks


def provenance_checks(context: dict | None, document: bytes,
                      *, entry: str, project_dir: str) -> list[Check]:
    keys = ("schema", "artifact", "entry", "policy", "policy_version", "provenance",
            "provenance_verified", "dependencies", "review", "approval")
    if not _shape(context, keys):
        return [(False, "provenance-unknown: missing or malformed Context fields")]
    checks = [(type(context["schema"]) is int and context["schema"] == 1, "Context.schema: expected 1"),
              (context["entry"] == entry and entry in ("track", "standalone"), "Context.entry: caller must match"),
              (context["provenance_verified"] is True, "provenance-unknown: original evidence not verified")]
    policy = context["policy"]
    checks.append((policy in ("current", "legacy"), "provenance-unknown: policy must be current or legacy"))
    checks.append((type(context["policy_version"]) is int and context["policy_version"] ==
                   (1 if policy == "current" else 0), "Context.policy_version: policy must match"))
    try:
        artifact = _project_path(project_dir, context["artifact"])
        checks.append((context["artifact"] == artifact.relative_to(Path(project_dir).resolve()).as_posix(),
                       "Context.artifact: normalized project-relative path required"))
    except SecurityFormatError:
        checks.append((False, "Context.artifact: invalid path"))
    proofs = context["provenance"]
    if not isinstance(proofs, list):
        return checks + [(False, "provenance-unknown: Evidence array required")]
    checks.extend(_evidence_checks(proofs, document, project_dir=project_dir, legacy=policy == "legacy"))
    present = {proof.get("kind") for proof in proofs if isinstance(proof, dict) and isinstance(proof.get("kind"), str)}
    required = {"design-entry"} if policy == "current" else {"workflow-version", "approval", "artifact-snapshot"}
    for kind in sorted(required):
        checks.append((kind in present, "provenance-unknown: %s evidence required" % kind))
    if policy == "current":
        checks.append((isinstance(context["dependencies"], list), "Context.dependencies: explicit array required"))
        checks.append((context["review"] is None or isinstance(context["review"], dict), "Context.review: object or null required"))
    else:
        checks.append((context["dependencies"] is None and context["review"] is None,
                       "Context.legacy: dependencies and review must be null"))
        try:
            checks.append((parse_security(_utf8_lf(document)) is None, "Context.legacy: current Security cannot be exempted"))
        except SecurityFormatError:
            checks.append((False, "Context.legacy: malformed Security cannot be exempted"))
    checks.append((context["approval"] is None if entry == "track" else
                   context["approval"] is None or isinstance(context["approval"], dict),
                   "Context.approval: approval belongs to its entry point"))
    return checks


def dependency_checks(dependencies: list[dict], *, phase: str,
                      project_dir: str) -> list[Check]:
    if phase not in ("prepare", "ready", "resume") or not isinstance(dependencies, list):
        return [(False, "stale-source: dependency phase and array required")]
    checks, paths, seen = [], [], set()
    keys = ("id", "path", "source_ref", "sha256", "kind", "snapshot_path")
    for row in dependencies:
        valid = (_shape(row, keys) and _strings(row, keys) and
                 bool(re.fullmatch(r"D[1-9]\d*", row["id"])) and _sha(row["sha256"]) and
                 row["kind"] in ("implementation-baseline", "live-constraint"))
        if not valid:
            checks.append((False, "stale-source: malformed Dependency"))
            continue
        identifier = row["id"]
        checks.append((identifier not in seen, "stale-source: %s must be unique" % identifier))
        seen.add(identifier)
        try:
            snapshot = _project_path(project_dir, row["snapshot_path"])
            checks.append((snapshot.name == "%s-%s.snapshot" % (identifier, row["sha256"]),
                           "stale-source: %s snapshot identity" % identifier))
            paths.append((snapshot, row["sha256"], identifier))
            if phase != "resume" or row["kind"] == "live-constraint":
                paths.append((_project_path(project_dir, row["path"], external=True), row["sha256"], identifier))
        except SecurityFormatError:
            checks.append((False, "stale-source: %s invalid source path" % identifier))
    # All first reads precede all final reads so changes during another read count.
    first = []
    for path, _, _ in paths:
        try:
            first.append(path.read_bytes())
        except OSError:
            first.append(None)
    for (path, sha, identifier), before in zip(paths, first):
        try:
            after = path.read_bytes()
            valid = before is not None and before == after and hashlib.sha256(after).hexdigest() == sha
        except OSError:
            valid = False
        checks.append((valid, "stale-source: %s content must match its snapshot fingerprint" % identifier))
    return checks


def parse_review(text: str) -> ReviewResponse:
    lines = _lf(text).splitlines(keepends=True)
    headings = _headings(lines)
    roots = [(index, name) for index, level, name in headings if level <= 4]
    names = ("Result", "Findings", "Assumptions", "Limitations")
    if ([name for _, name in roots] != list(names) or
            any(level != 4 for _, level, _ in headings if level <= 4)):
        raise SecurityFormatError("Review: expected Result, Findings, Assumptions, Limitations in order")
    if any(line.strip() for line in lines[:roots[0][0]]):
        raise SecurityFormatError("Review: unexpected content before Result")
    sections = {name: "".join(lines[index + 1:roots[position + 1][0] if position < 3 else len(lines)])
                for position, (index, name) in enumerate(roots)}
    rows = _table(sections["Result"], "Review.Result", ("Field", "Value"))
    _unique(rows, "Review.Result", "Field")
    result = {row["Field"]: row["Value"] for row in rows}
    if (set(result) != {"input_sha256", "execution", "verdict"} or not _sha(result.get("input_sha256")) or
            result.get("execution") not in ("complete", "failed", "insufficient") or
            result.get("verdict") not in ("ready", "revise", "insufficient")):
        raise SecurityFormatError("Review.Result: missing field or unknown value")
    findings = _table(sections["Findings"], "Review.Findings",
                      ("ID", "Severity", "Threat or AC", "Scenario", "Required change"))
    _unique(findings, "Review.Findings", "ID", r"R[1-9]\d*")
    _enum(findings, "Review.Findings", "Severity", ("Blocker", "Major", "Minor"))
    assumptions = _table(sections["Assumptions"], "Review.Assumptions", ("ID", "Statement", "Evidence"))
    _unique(assumptions, "Review.Assumptions", "ID")
    if any(not all(row.values()) for row in findings + assumptions) or not sections["Limitations"].strip():
        raise SecurityFormatError("Review: nonempty finding, assumption and limitations fields required")
    return ReviewResponse(result, findings, assumptions, sections["Limitations"].strip())


def _review_body(model):
    lines = model._sections["Review"].splitlines(keepends=True)
    if lines and lines[0] == "\n":
        lines = lines[1:]
    if (model._review_range[1] < len(_lf(model._text).splitlines(keepends=True))
            and lines and lines[-1] == "\n"):
        lines = lines[:-1]
    return "".join(lines)


def review_checks(document: bytes, intake: bytes | None, context: dict,
                  *, project_dir: str) -> list[Check]:
    model = parse_security(_utf8_lf(document))
    if model is None:
        return [(False, "Review: missing Security")]
    if model.applicability["applies"] == "no":
        return [(context.get("review") is None, "Review: no requires null Context.review")]
    review = context.get("review")
    keys = ("input_sha256", "response_path", "response_sha256", "source_ref", "verified_items")
    if not _shape(review, keys) or not _strings(review, keys[:-1]):
        return [(False, "Review: complete original response metadata required")]
    verified = review["verified_items"]
    checks = [(isinstance(verified, list) and len(verified) == 5 and
               set(item for item in verified if isinstance(item, str)) ==
               {"verdict", "findings", "assumptions", "limitations", "finding-impact"},
               "Review: main session must verify every result and finding impact")]
    try:
        path = _project_path(project_dir, review["response_path"])
        expected = Path(context_path(project_dir, context["artifact"])).parent / "review-response.md"
        checks.append((path == expected, "Review: response must use its Context directory"))
        content = path.read_bytes()
        original = _utf8_lf(content)
        body = _review_body(model)
        checks.append((body == original, "Review: embedded text must equal the complete original response"))
        response = parse_review(body)
        digest = review_input_digest(document, intake, context["dependencies"])
        checks += [(review["input_sha256"] == digest and response.result["input_sha256"] == digest,
                    "Review: stale input fingerprint"),
                   (response.result["execution"] == "complete" and response.result["verdict"] == "ready",
                    "Review: complete and ready required"),
                   (not any(row["Severity"] in ("Blocker", "Major") for row in response.findings),
                    "Review: no unresolved Blocker or Major"),
                   (not response.assumptions, "Review: no unconfirmed assumptions")]
        checks.extend(_file_checks(path, review["response_sha256"], "Review: original response fingerprint",
                                   content=content))
    except (OSError, SecurityFormatError):
        checks.append((False, "Review: original or embedded response unavailable or malformed"))
    for threat in model.threats:
        if threat["Disposition"] != "risk-proposed":
            continue
        identifier = threat["ID"]
        decision = next((row for row in model.risk_decisions if row["Threat"] == identifier), None)
        matching = [proof for proof in context.get("provenance", []) if isinstance(proof, dict) and
                    proof.get("kind") == "risk-acceptance:" + identifier and decision is not None and
                    proof.get("source_ref") == decision["Evidence"]]
        checks.append((decision is not None and decision["Decision"] == "accept" and bool(matching)
                       and context.get("provenance_verified") is True,
                       "%s: exact original risk acceptance required" % identifier))
        checks.extend(_evidence_checks(matching, document, project_dir=project_dir))
    return checks


def _approval_checks(context, document, *, project_dir, track_dir):
    digest = hashlib.sha256(document).hexdigest()
    if context["entry"] == "track":
        if track_dir is None:
            return [(False, "approval: track resume requires track_dir")]
        try:
            path = _project_path(project_dir, track_dir)
            approved = ledger.approved(ledger.records(str(path), "design"), digest)
        except (OSError, SecurityFormatError, ledger.LedgerError):
            approved = False
        return [(approved, "approval: matching human Gate 1 required")]
    approval = context["approval"]
    keys = ("artifact_sha256", "source_ref", "evidence_path", "evidence_sha256")
    if not _shape(approval, keys) or not _strings(approval, keys):
        return [(False, "approval: original standalone approval required")]
    checks = [(approval["artifact_sha256"] == digest, "approval: artifact unchanged since approval")]
    try:
        path = _project_path(project_dir, approval["evidence_path"])
        checks.extend(_file_checks(path, approval["evidence_sha256"], "approval: original standalone answer fingerprint"))
    except SecurityFormatError:
        checks.append((False, "approval: standalone answer must stay in the project"))
    if context["policy"] == "legacy":
        checks.append((any(proof.get("kind") == "approval" and
                           proof.get("source_ref") == approval["source_ref"] and
                           proof.get("path") == approval["evidence_path"] and
                           proof.get("sha256") == approval["evidence_sha256"]
                           for proof in context["provenance"] if isinstance(proof, dict)),
                       "provenance-unknown: standalone approval must match historical evidence"))
    return checks


def _intake_data(document, *, project_dir, intake, context, track_dir, phase):
    text = _utf8_lf(document)
    lines = text.splitlines()
    headings = _headings(lines)
    ac_line = re.compile(r"^\s*AC:\s*(.+?)\s+sha256\s+([0-9a-fA-F]{64})\s*$")
    candidates = [line for _, line in _visible(lines) if re.match(r"^\s*AC:", line)]
    bindings = [match for line in candidates if (match := ac_line.fullmatch(line))]
    modes = {name for _, level, name in headings if level == 2 and name in MODES}
    titles = [name for _, level, name in headings if level == 1]
    diagnosis = "Diagnosis" in modes or any(re.search(r"(?:—|-)\s*diagnosis$", title, re.IGNORECASE)
                                            for title in titles)
    long = bool(candidates) or bool(modes - {"Diagnosis"})
    long = long or any(re.search(
        r"(?:—|-)\s*(?:stance|decisions|detail design|high-level design|delta design)$",
        title, re.IGNORECASE) for title in titles)
    long = long or (not diagnosis and any(re.search(r"(?:—|-)\s*design$", title, re.IGNORECASE)
                                         for title in titles))
    checks, data = [], None
    if candidates:
        checks.append((len(candidates) == len(bindings) == 1,
                       "AC: exactly one valid external intake binding required"))
    if intake is None:
        checks.append((not long, "AC: long design requires its bound intake"))
    else:
        try:
            path = _project_path(project_dir, intake)
            data = path.read_bytes()
            if len(bindings) == 1:
                bound = _project_path(project_dir, bindings[0][1])
                checks.append((path == bound and hashlib.sha256(data).hexdigest() == bindings[0][2].lower(),
                               "AC: intake path and fingerprint must match"))
            elif phase != "draft" or candidates:
                checks.append((False, "AC: exactly one intake fingerprint line required"))
            if context["entry"] == "standalone":
                expected = Path(context_path(project_dir, context["artifact"])).parent / "intake.md"
                checks.append((path == expected, "AC: standalone intake belongs to its Context directory"))
            elif track_dir is not None:
                checks.append((path == _project_path(project_dir, track_dir) / "intake.md",
                               "AC: track intake belongs to its track directory"))
        except (OSError, SecurityFormatError):
            checks.append((False, "AC: bound intake unavailable"))
    levels = verify_plan.read_levels(_utf8_lf(data) if data is not None else text)
    checks.append((levels["status"] == "ok", "AC: complete verification levels required"))
    return data, levels["rows"], checks


def _snapshot_directory_checks(context, project_dir):
    directory = Path(context_path(project_dir, context["artifact"])).parent / "dependencies"
    checks = []
    for dependency in context["dependencies"]:
        if isinstance(dependency, dict) and _strings(dependency, ("snapshot_path",)):
            try:
                valid = _project_path(project_dir, dependency["snapshot_path"]).parent == directory
            except SecurityFormatError:
                valid = False
            checks.append((valid, "stale-source: dependency snapshot must use its Context directory"))
    return checks


def _loaded_checks(document, context, *, project_dir, intake, phase, entry, track_dir):
    checks = provenance_checks(context, document, entry=entry, project_dir=project_dir)
    if not all(ok for ok, _ in checks):
        return checks
    if context["policy"] == "legacy":
        checks.append((phase == "resume", "Context.legacy: new or reopened design must register current"))
        if phase == "resume":
            checks.extend(_approval_checks(context, document, project_dir=project_dir, track_dir=track_dir))
        return checks
    model = parse_security(_utf8_lf(document))
    data, rows, intake_checks = _intake_data(document, project_dir=project_dir, intake=intake,
                                             context=context, track_dir=track_dir, phase=phase)
    checks.extend(intake_checks)
    checks.extend(model_checks(model, rows, phase=phase))
    if phase != "draft":
        checks.extend(dependency_checks(context["dependencies"], phase=phase, project_dir=project_dir))
        checks.extend(_snapshot_directory_checks(context, project_dir))
        if model is not None and all(ok for ok, _ in checks):
            checks.extend(review_checks(document, data, context, project_dir=project_dir))
    if phase == "resume":
        checks.extend(_approval_checks(context, document, project_dir=project_dir, track_dir=track_dir))
    return checks


def check_document(document: str, *, project_dir: str, intake: str | None,
                   phase: str, entry: str,
                   track_dir: str | None = None) -> list[Check]:
    if phase not in ("draft", "ready", "resume") or entry not in ("track", "standalone"):
        return [(False, "Security: unknown phase or entry")]
    if (entry == "standalone" and track_dir is not None) or (entry == "track" and phase == "resume" and track_dir is None):
        return [(False, "approval: entry requires its own approval input")]
    try:
        path = _project_path(project_dir, document)
        before = path.read_bytes()
        context = read_context(project_dir, str(path))
        checks = []
        if context is not None:
            relative = path.relative_to(Path(project_dir).resolve()).as_posix()
            checks.append((context.get("artifact") == relative, "Context.artifact: caller must match"))
        checks.extend(_loaded_checks(before, context, project_dir=project_dir, intake=intake,
                                     phase=phase, entry=entry, track_dir=track_dir))
        checks.append((before == path.read_bytes(), "Security: stale document during check"))
        checks.append((context == read_context(project_dir, str(path)), "Security: stale Context during check"))
        return checks
    except (OSError, SecurityFormatError):
        return [(False, "Security: unreadable or malformed document, Context or evidence")]


def _print_checks(checks):
    for ok, label in checks:
        print(("PASS " if ok else "FAIL ") + label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fingerprint", "check"):
        command = commands.add_parser(name)
        command.add_argument("--project-dir", required=True)
        command.add_argument("--document", required=True)
        command.add_argument("--intake")
        if name == "check":
            command.add_argument("--phase", choices=("draft", "ready", "resume"), required=True)
            command.add_argument("--entry", choices=("track", "standalone"), required=True)
            command.add_argument("--track-dir")
    args = parser.parse_args(argv)
    if args.command == "check":
        checks = check_document(args.document, project_dir=args.project_dir, intake=args.intake,
                                 phase=args.phase, entry=args.entry, track_dir=args.track_dir)
        _print_checks(checks)
        return 0 if all(ok for ok, _ in checks) else 2
    try:
        context = read_context(args.project_dir, args.document)
        if context is None or context.get("policy") != "current":
            raise SecurityFormatError("provenance-unknown: fingerprint requires current Context")
        path = _project_path(args.project_dir, args.document)
        before = path.read_bytes()
        checks = check_document(args.document, project_dir=args.project_dir, intake=args.intake,
                                 phase="draft", entry=context.get("entry"))
        if not all(ok for ok, _ in checks):
            _print_checks(checks)
            return 2
        checks.extend(dependency_checks(context.get("dependencies"), phase="prepare", project_dir=args.project_dir))
        checks.extend(_snapshot_directory_checks(context, args.project_dir))
        data, _, intake_checks = _intake_data(before, project_dir=args.project_dir, intake=args.intake,
                                              context=context, track_dir=None, phase="ready")
        checks.extend(intake_checks)
        checks.append((before == path.read_bytes() and context == read_context(args.project_dir, args.document),
                       "Security: stale fingerprint input"))
        if not all(ok for ok, _ in checks):
            _print_checks(checks)
            return 2
        print(json.dumps({"schema": 1, "input_sha256": review_input_digest(before, data, context["dependencies"]),
                          "dependencies": context["dependencies"]}, ensure_ascii=False))
        return 0
    except (OSError, SecurityFormatError):
        print("FAIL Security: fingerprint input unavailable or malformed")
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
