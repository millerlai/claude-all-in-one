<!--
  cai delta design template, filled in by /cai:design in delta mode.

  Every heading below is required. `design_probe.py --kind delta <this file>`
  fails if one is missing or still empty, so this template does not pass its
  own probe until it has been filled in — which is the point.

  Guidance lives in HTML comments and does not count as content. Delete each
  comment as you answer it.

  Headings and table headers stay English: the probe matches on them, and this
  file ships to every user. What you write into them follows communication.md.
-->

# <topic> — delta design

## Scope

<!--
  The base ref, the commit range, and how many files changed. Write it as a
  sentence — `filled()` wants one line of at least 20 characters, so a bare
  `a3f21bc..HEAD` is read as an empty section and reported as one.

  This is the heading the document cannot be reconstructed without. Six months
  and three features later "the new exporter" names nothing; the range still
  does.
-->

## Problem

<!--
  What this change set was for. One paragraph.

  Not a summary of the diff. The diff is already in git, and restating it in
  prose is what makes a delta document worth less than reading the diff.
-->

## Before / After

<!--
  Two diagrams: how it worked before, how it works now. Mermaid, per
  documentation.md — elk renderer, labels in double quotes rather than
  hand-escaped entities, and classDef colouring so added, modified and
  unchanged nodes are distinguishable at a glance.

  Two, not one. A single diagram of the end state is a picture the reader
  could have drawn from the code; the delta is the pair.

  Render them before shipping. Never write "validated" for a diagram you did
  not render.
-->

## Decisions

<!--
  One row per deliberate choice whose reasoning is not visible in the diff.
  Evidence is a file:line, a documentation URL, or the commit that explains it.

  This command does not stop to ask. A decision whose reason you could not
  source is written UNVERIFIED, and it stays that way in the finished document,
  where it tells the author which rows are theirs to fill in. Inventing a
  plausible reason is the one thing that makes this document actively harmful:
  a wrong "why" outlives everyone who could have corrected it.

  Every row needs both outer pipes. `items()` counts a row by them, so a line
  written without the leading `|` is not counted at all.
-->

| Decision | Why | Evidence |
|---|---|---|

## Impact

<!--
  What this change assumes about code it does not touch, and what breaks if
  those assumptions are wrong. This is where the merge-day surprises live.
-->

| What it touches | The assumption | What breaks if it is wrong |
|---|---|---|

## Limits

<!--
  Known limitations, and what was deliberately left undone.

  If there is genuinely nothing, say why in a sentence rather than leaving it
  blank. A blank section reads the same as a forgotten one.
-->
