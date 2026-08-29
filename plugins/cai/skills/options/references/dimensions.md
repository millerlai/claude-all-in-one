# Dimension library

Pick 2-4 per question. Do not mix sets from different situations, and do not
invent a set when one below fits — a stable axis is what makes two options
comparable at all.

## Picking a library or tool
- Ecosystem maturity: community size, documentation quality, the odds of
  finding an answer when stuck
- Lock-in: how hard it is to replace later
- Debuggability: whether the error messages mean anything, whether you can read
  the source when they do not
- Team familiarity: how much the people here would have to learn

## Architecture decisions
- Blast radius: how many files or modules have to change
- Reversibility: what backing out costs
- Performance: the actual order of magnitude, never "faster"
- Test cost: how many tests have to exist before it is safe to change

## Refactoring routes
- Step count: how many independently committable steps it splits into
- Verifiability per step: whether the tests can run after each one
- Safe to stop halfway: whether the code still works if the route is abandoned
  mid-way
- Prerequisites: which other refactorings have to land first

## Data and storage
- Volume ceiling: how many records before it starts to hurt
- Consistency: whether a reader can see stale data
- Backup and restore: whether it can actually be recovered after an incident
- Migration cost: how much data has to move if this is changed later

## Deployment and environment
- First-time setup: how long to get it running once
- Ongoing operations: how much attention it needs per week
- Visibility on failure: whether you find out when it breaks
- Cost shape: a fixed fee, or billed by usage

## Generic fallback — when none of the above fits
- What has to be learned
- How hard it is to diagnose when it goes wrong
- Whether it still makes sense to whoever reads it three months later
