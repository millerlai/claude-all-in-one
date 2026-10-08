# test-command — where every stage gets this project's test command

One program decides which command runs this project's tests, and every stage
that needs one — build, verify, goal, refactor, the `test-runner` and
`verifier` agents — asks it instead of guessing. A caller that picks a command
on its own when the program says it cannot is the defect this file exists to
prevent.

## Ask the program

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_test_command.py
```

Run it from the project; add `--project-dir <dir>` from anywhere else. It
only reads files and prints one JSON object: `status`, `source`, `root`,
`commands`, `candidates`, `problem` and `notes`. Each entry of `commands` and
`candidates` has `command`, `whole`, `narrow` and `origin`. A person's
`test.commands` list in `.claude/cai.json` wins; without one, the program
derives candidates from the root's own files and never runs anything it finds.

## What each exit code means

| Exit | `status` | What you do |
|---|---|---|
| 0 | `resolved` | Run `commands` as the next section says. |
| 3 | `several` | Run nothing. `candidates` lists what was found, and only a person picks. |
| 4 | `unknown` | Report that no test command was found, with `notes` (the files it skipped and why). Guess nothing. |
| 5 | `invalid` | Report `problem`. Do not fall back to detection and do not write anything: the declaration exists but cannot be read, so which command the person meant is unknown. |

**Exit 3.** The menu is: first "Run all of them (recommended)", then each
candidate on its own, at most three of them — a menu holds two to four
options. Recommending "all" picks no candidate for the person, which is why it
leads. With more than three candidates the menu is only "Run all of them
(recommended)" and "I will name which ones", and the full candidate list goes
in the text above it. Who asks depends on who you are:

- **In a subagent** you have no way to ask. End your report with a `## Pending
  questions` item in `references/pending-questions.md`'s format, candidates
  listed in its Options, and run nothing.
- **In the main session** ask with a menu (`references/approval-gates.md`).
  Then record the answer — a candidate with a non-empty `whole` is recorded as
  `command` followed by a space and `whole`:

  ```bash
  python ${CLAUDE_PLUGIN_ROOT}/scripts/record_test_command.py "<command>" ["<command>" ...]
  ```

  It keeps every other key in `.claude/cai.json`. Run the resolver again and
  expect exit 0 with `source` `declared`.

**Exit 4.** A subagent only reports. The main session may ask the person to
type the command (the menu's free-text entry) and record it the same way.

Only the main session writes `.claude/cai.json`, and only through
`record_test_command.py` — never by editing the file. Nothing enforces that
for the verifier, which has Write and Edit: the guard treats the declaration
as trusted input, as it does the `Makefile` or `conftest.py` a resolved
command runs.

## Before build: settled once, never a block

`build` never waits on a test command. Before it starts — under a track ahead
of its first dispatch, standing alone before its Step 0 — you, the main
session, run the resolver and settle the command with the person in one menu
(`references/approval-gates.md`), or settle that there is none. This menu
replaces the exit table above for this one moment only; everything that runs
the resolver later still follows that table.

Ask nothing when `.claude/track/<feature>/implementation-notes.md` already has
a line starting `Test command: skipped`: an earlier start of this build took
that answer, and you carry the line on as the last paragraph says.

| Exit | The menu |
|---|---|
| 0, `source` `declared` | None: the person already chose it. |
| 0, `source` `detected` | "Use `<command>` (recommended)" and "Skip: build without a test command". A different command goes in the free-text entry. |
| 3 | "Run all of them (recommended)", each candidate on its own when there are at most two, and "Skip: build without a test command". With more than two the menu is "Run all of them (recommended)", "I will name which ones" and the Skip option, the full candidate list in the text above it. |
| 4 | "Skip: build without a test command (recommended)" and "Check again: I have just added one", the resolver's `notes` in the text above, which also says the command can be typed into the free-text entry. |
| 5 | "Check again: I have fixed it (recommended)" and "Skip: build without a test command", `problem` in the text above. |

What each answer does:

- **A command** — picked, named or typed: record it with
  `record_test_command.py` as exit 3's main-session bullet above says, run the
  resolver again, and expect exit 0 with `source` `declared`. Nothing asks
  again after that, in this stage or a later one. When the recorder refuses
  (it changes nothing when `.claude/cai.json` cannot be read), say what it
  printed and start this section again, so the menu, Skip included, comes back.
- **Check again** — start this section again from the resolver.
- **Skip** — write nothing to `.claude/cai.json`, so the next track asks
  again. The line `Test command: skipped by the person before build` goes in
  build's dispatch prompt.

A menu here that closes on its own counts as Skip: nothing is written, no
detected command is used, and the line reads `Test command: skipped (the menu
timed out)`. Say so in one line.

A skip holds for the rest of the track. Every later dispatch of `build` or
`verify` carries the same line, taken from `implementation-notes.md` once
build has copied it there. Holding that line, neither stage runs the resolver
or any test command, and neither asks about one. Each still does every other
step of its own, and reports `not run: test command skipped` wherever a test
run's result would go. Standing alone there is no dispatch: the same holds
for the run you are in.

## Running the commands

- `commands` all run, in order, each reported on its own line with its own
  counts. Any failure fails all: one red command makes the whole result red,
  however many others passed.
- `narrow` says whether a command can be pointed at less than everything.
  `paths` or `packages`: append the files, directories or package paths this
  run is about to the `command`, and do not run the whole suite. `none`: run
  `command` followed by `whole` (empty for most), set the Bash tool's
  `timeout` to its ceiling of 600000 ms, and write "not narrowed" in the
  report. A run the tool cuts off is red, with TIMEOUT as the reason and
  `BASH_MAX_TIMEOUT_MS` named as the setting that raises the ceiling.
- A `narrow` of `paths` or `packages` still needs a scope. Given none and none
  readable off the change, report that instead of running everything.

## NOT RUN does not depend on the runner

Ask the runner for per-file, per-test results with skip reasons — whichever
option it has for that. A test file named in the brief or the command that
collected 0 tests, or whose tests were all skipped, gets its own report line,
`NOT RUN <file>` with the reason, and counts as red even with 0 failures.

## What the boundary does and does not limit

On Claude Code a hook holds the Bash of `test-runner` and `verifier` to the
resolver and the commands it resolved, each optionally followed by arguments
without shell symbols. It limits which command a call starts with, not what
the project's own test scripts do (a Makefile recipe, a conftest). It does not
limit where an argument points the command either: an argument without shell
symbols passes, so a command can be pointed at another file or directory, and
a `verifier` that can write files can write one first. Some runners also take
an argument that names the program to run (`go test -exec`, `cargo test
--config` with a runner), and that passes as well. That limit is accepted, not
an oversight, and no further rule is added for it.

The hook also needs a working Python. With none working, the dispatcher blocks
these agents' Bash outright; if the interpreter it recorded fails partway
through a call, that call is blocked for every caller, and the next call looks
for one again.

Three habits are blocked outright, so do not start them: appending a
redirection such as `2>&1` (the Bash tool already returns stderr), `cd`-ing
first (the working directory is already the project root), and exploring with
`find` or `ls` (run the resolver instead).
