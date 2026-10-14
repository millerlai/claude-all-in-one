# open-items-report — how build and verify list what they leave unfixed

This file is read by the build and verify stages, and only by them; each
stage's `## Report` points here. An open item is one finding of the kinds
below that you leave unfixed. It is kept with its details so that, before
`ship` drafts anything, the person can pick one outcome for it: Fix now, File
a GitHub issue, Note on the PR, or Accept as is. A line in `## Report`'s
left-open field does none of that. The main session, not you, reads the
section and holds the record: you run no command for it and write no track
file.

## The section

End the report with `## Open items`, one numbered entry per item:

```
## Open items
1. new unfixed-minor
   What: <one line, at most 200 characters; it becomes an issue title>
   Where: <repo-relative path:line, or none>
   Why left: <one line>
   Severity: <major or minor>
   Quoted: <optional; see "What goes under Quoted" below>
2. still open-3
3. fixed open-1
```

- `new <kind>` — a finding that is not among the open items your brief lists.
  `What`, `Where`, `Why left` and `Severity` are all required. One entry per
  finding, never several joined into one.
- `still open-<n>` — an open item your brief lists that you looked at and left.
  Name it by its id. Restating it in new words makes a second item, which the
  person is asked about twice.
- `fixed open-<n>` — verify only, and only for an open item your brief quoted
  that you fixed.

The kinds each stage may open:

| Stage | Kinds |
|---|---|
| build | `deviation` — every deviation from the design, however small; `out-of-scope` — a problem you found outside the change's scope and did not touch |
| verify | `unfixed-minor` — each Minor left unfixed, with its `path:line`; `parked-proposal` — each parked proposal |

A `new` entry from another stage, or of a kind its stage does not own, is
refused.

`Severity` is your judgement, not the person's: before ship they are asked
one menu for every item, grouped by it, and "Fix major" fixes only the major
ones. `major` — left as it is, the change does something wrong or other than
what the design says, or a reviewer must know about it before merging.
`minor` — wording, naming, style, a missing nicety, or a problem outside the
change that nothing in it makes worse. An `unfixed-minor` is `minor`.

## Where it sits

- Placed directly before `## Pending questions` when the report hands
  questions up, so the report still ends in `## Pending questions` (`SKILL.md`
  reads that ending as "no outcome").
- A report that hands questions up is not recorded as an outcome, so its
  entries are not applied yet. The report of the round that finally passes
  lists every `new` entry from all of this stage's rounds, the earlier rounds'
  included.
- Outside `## Report`'s 4000-character ceiling, as `## Pending questions` is.

## What stays in `## Report`

Reminders: anything left open that is not one of the four kinds. A manual step
(`stage-build.md` Step 6.4), "no unit ran a test", and verify's changes made
from an answer (not reviewed by the four lenses) are reminders; they stay in
the left-open field, are printed, and are never asked about.

## What goes under Quoted

Text the brief labels as posted by a third party goes only under `Quoted:`;
`What` and `Why left` are your own words. `Quoted:` is kept for a Fix now and
is never written to GitHub. `What`, `Where` and `Why left` are written to
GitHub when the person picks File or Note, so they carry no credential, no
absolute local path, no raw command output and no full command line either.

Indent every line of a `Quoted:` block under its label. A line that starts in
column 0 is read as an entry or a heading of the report, not as quoted text,
so pasted text can add entries or end the section there. Two checks guard
this: a second `## Open items` heading with no other heading between it and
the first is refused, and so is a `fixed open-<n>` for an undecided item in a
report that also carries `Quoted:` text. Write the heading exactly as
`## Open items`; any other spelling is refused, not read as "no findings".
