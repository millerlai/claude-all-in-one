# Workflow

## Codex sandbox permissions
- Run routine verification inside the sandbox first. Request escalation only
  for a known required resource or an observed sandbox denial; a failing test
  alone is not evidence of a permission problem. Do not skip tests or weaken
  coverage to avoid an approval. Never install dependencies without asking.
- Preserve the project's declared verification command and environment.
  Use an existing project-local `.venv` only when that is the declared entry
  point or its equivalence has been checked; do not bypass setup performed
  by `make`, `uv`, or another project wrapper. For an approved uv command,
  prefer `uv run --cache-dir <workspace-local-cache> --offline --no-sync ...`
  when dependencies are already installed and no sync is required. A new
  cache may be empty: report missing dependencies rather than downloading
  them silently. `--no-cache` still creates a temporary cache.
- `<scratch-dir>` is an existing writable location for disposable outputs:
  prefer one inside the workspace whose output paths are ignored by Git
  (check with `git check-ignore`); otherwise use a temporary location already
  allowed by the active sandbox. Do not edit ignore files just to make one.
  Use it for test logs, diagrams, downloads, and message/report/answer files.
  Leave disposable files in place once consumed: deleting one is a separate
  command Codex may stop to approve, once per file, even inside a writable
  root. A temporary location is cleaned by the system and an ignored path
  stays out of `git status`; a later write to the same path overwrites it.
  If no suitable location is allowed, request permission for the
  exact required location. Do not assume `/private/tmp` is allowed or denied
  on macOS: the actual writable roots decide.
- Moving an output does not grant network access, localhost socket binding,
  Chromium execution, Docker access, or writes to protected Git metadata.
  Keep necessary approvals, including setup/model writes under the user's
  Codex home. Explain the required resource rather than blaming the tool name.
  Keep escalated commands simple and scoped. Never create allow rules or
  change sandbox settings without explicit user authorization; suggesting a
  `prefix_rule` in an escalation request, which the person then approves or
  not, is neither.
- Once a command has needed escalation for a known resource in this session
  (localhost sockets, network), do not retry it in the sandbox first on later
  runs: ask for it directly. When network is all it lacks, ask with
  `with_additional_permissions` (`network.enabled`) rather than
  `require_escalated`.
- Give a command you escalate the same leading words every run, so one
  approval can cover the next: no `VAR=value` and no `source ... &&` in front
  (load a `.env` with `uv run --env-file <file>` or the wrapper's own
  option), the same cache path each time, and what varies between runs --
  test paths, `-k`, node ids -- last. Suggest a `prefix_rule` of exactly
  those fixed leading words (`["make", "test"]`, `["uv", "run",
  "--cache-dir", ".cache/uv", "--offline", "--no-sync", "pytest"]`), never
  the test paths: approving a prefix that names them stops none of the next
  run's prompts.

## Development workflow
- In a git repo, before touching code: switch to master/main, pull latest, then create
  a branch — make changes there, never directly on master/main.
- Non-trivial change → outline a plan first.
- Order the plan by what I'm most likely to change — data model, interfaces, and
  anything user-facing first; mechanical refactoring last.
- Exception: when the result is judged by look or feel, a throwaway prototype beats a
  written plan. Build the cheapest thing that can be reacted to — a mock, a few
  variants, sample output — before wiring anything into the real code.
- When the project already has tests, loop on verifiable goals (don't add a harness
  uninvited; suggest it if missing): validation → test invalid inputs; bug → reproduce
  in a test; refactor → tests pass before and after. Run tests before saying it's done.
- A large multi-file change runs in checkpointed units, never as one long edit: an
  interruption must not leave work half-done or the tree incompilable. Keep responses
  concise as you go (no large summaries) so the budget goes to the work.
- Plans are written with incomplete information. When implementation hits something the
  plan didn't anticipate, take the conservative option, log the deviation and its reason
  (an `implementation-notes.md` for long runs), and keep going — then report the
  deviations with the result. Silently re-scoping hands back a change I never approved.
- Never commit or push unless I explicitly ask.
- Never install packages or otherwise change the environment (`pip install`,
  `npm i -g`) without asking first — least of all on a dirty working tree.

# Commits
- English, conventional-commit style (feat:, fix:, refactor:).

# Learning from mistakes
- On correction, find the underlying rule, not the one-off fix. If general, propose
  adding to user-scope rules; if project-specific, to that project's AGENTS.md.
  Ask first, as an imperative.

# Recurring procedures → skills
- When a request closely resembles one already performed in this project (same
  steps, different inputs) for the second time or more, check whether the steps
  form a repeatable procedure.
- If they do: complete the task first, then propose capturing it as a skill and
  ask which scope — project (`.claude/skills/<name>/`) or user-global
  (a user-global location outside any project, if this platform has one). On approval, create it: SKILL.md with
  frontmatter `name` + `description` (written for triggering), the procedure
  steps, and extract any reusable scripts/templates alongside.
- Bar: a multi-step procedure likely to recur. Don't propose for one-off tasks
  or trivial single commands, and don't re-propose one the user declined.
