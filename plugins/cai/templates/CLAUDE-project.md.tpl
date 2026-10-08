# Project Name

<!-- Write only what ~/.claude/rules/ and each contributor's personal
     ~/.claude/CLAUDE.md cannot know about this repo — its own verification
     command, its architecture, its conventions. A sentence that is already
     a rule is sent to the model twice every session, and the two copies
     drift apart as soon as one is edited. -->

## Verification

<!-- The one command that says a change is done, e.g. `npm test` or `pytest`.
     Paste the last lines of a healthy, all-green run verbatim below it, so a
     new session knows what green looks like without running it first.
     No test command yet? Leave this section empty and fill it in once the
     first one exists. The stages that run tests do not read this section:
     they take `test.commands` from `.claude/cai.json`, or detect a command at
     the repo root (see the README, "Which test command runs"). -->

## Architecture

<!-- One paragraph mapping the repo for a new session: the pieces, how they
     connect, where to start reading. Not a copy of the README. -->

## Conventions

<!-- Only what is specific to this repo and not already covered by
     ~/.claude/rules/ — naming, layout, patterns a new session would not
     guess. If this repo keeps a `.claude/cai-context.md` glossary, add
     one line here pointing to it; the terms themselves stay in that file,
     not in this one. -->

## Mistakes Claude repeats here

<!-- Empty on purpose. Add an entry only once Claude makes the same mistake
     in this repo a second time. A mistake that would happen in any repo
     belongs in ~/.claude/rules/ instead. -->
