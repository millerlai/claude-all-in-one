# Workflow
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

# Commits
- English, conventional-commit style (feat:, fix:, refactor:).

# Learning from mistakes
- On correction, find the underlying rule, not the one-off fix. If general, propose
  adding to user-scope rules; if project-specific, to that project's CLAUDE.md.
  Ask first, as an imperative.

# Recurring procedures → skills
- When a request closely resembles one already performed in this project (same
  steps, different inputs) for the second time or more, check whether the steps
  form a repeatable procedure.
- If they do: complete the task first, then propose capturing it as a skill and
  ask which scope — project (`.claude/skills/<name>/`) or user-global
  (`~/.claude/skills/<name>/`). On approval, create it: SKILL.md with
  frontmatter `name` + `description` (written for triggering), the procedure
  steps, and extract any reusable scripts/templates alongside.
- Bar: a multi-step procedure likely to recur. Don't propose for one-off tasks
  or trivial single commands, and don't re-propose one the user declined.
