# Workflow
- In a git repo, before touching code: switch to master/main, pull latest, then create
  a branch — make changes there, never directly on master/main.
- Non-trivial change → outline a plan first.
- When the project already has tests, loop on verifiable goals (don't add a harness
  uninvited; suggest it if missing): validation → test invalid inputs; bug → reproduce
  in a test; refactor → tests pass before and after. Run tests before saying it's done.
- For large multi-file changes, commit or checkpoint incrementally and keep responses
  concise (no large summaries), so a token or session-limit interruption never leaves
  work half-done or files in a broken, incompilable state.
- Never commit or push unless I explicitly ask.

# Commits
- English, conventional-commit style (feat:, fix:, refactor:).

# Learning from mistakes
- On correction, find the underlying rule, not the one-off fix. If general, propose
  adding to user-scope rules; if project-specific, to that project's CLAUDE.md.
  Ask first, as an imperative.
