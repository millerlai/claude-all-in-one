<!--
  Shared fragment for the same artifact the person approves. Insert after the
  design/diagnosis modes, or before Verification levels in a short intake.
  Keep this one field contract; callers link here rather than copying a schema.
  The empty fragment intentionally fails checks until evidence is filled in.
  Structure checks do not establish that a design is safe.
-->

## Security

### Applicability

| Field | Value |
|---|---|
| schema | 1 |
| applies | unknown |
| reason | |
| evidence | |
| dependencies_sha256 | |

<!-- For applies=no, copy fingerprint's dependencies_sha256 here before approval.
     It binds the dependency list even when there is no independent review. -->

### Scope

<!-- State the change, assets, actors and attacker capabilities. -->

### Flows

| ID | From | To | Data | Trust boundary |
|---|---|---|---|---|

### Coverage

| Category | Relevance | Reason |
|---|---|---|
| spoofing | unknown | |
| tampering | unknown | |
| repudiation | unknown | |
| information-disclosure | unknown | |
| denial-of-service | unknown | |
| elevation-of-privilege | unknown | |
| abuse | unknown | |
| race-replay | unknown | |
| business-logic | unknown | |
| supply-chain | unknown | |

### Threats

<!--
  IDs are T plus a positive integer; Flow names an existing F ID. Category is a
  Coverage value. Use comma-separated existing AC IDs for controls to implement;
  none is allowed only without an implementation control. Disposition is
  control-planned, risk-proposed or unresolved. Describe remaining risk explicitly.
  With no identified threats, explain why here and obtain independent review.
  Separate prose from the table with a blank line; table rows need outer pipes.
-->

| ID | Flow | Category | Scenario | Control | AC | Disposition | Residual risk |
|---|---|---|---|---|---|---|---|

### Assumptions

<!-- IDs are A plus a positive integer; State is confirmed or open. -->

| ID | Statement | State | Evidence |
|---|---|---|---|

### Risk decisions

<!--
  For each risk-proposed threat: pending, accept or reject. Accept needs the
  person's actual reply and its matching Context provenance source_ref. Reject
  returns to control/scope revision; it cannot make the same proposal ready.
-->

| Threat | Decision | Reason | Evidence |
|---|---|---|---|

### Review

pending
