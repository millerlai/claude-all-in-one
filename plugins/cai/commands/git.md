---
description: Use this whenever the user asks to run a git or GitHub CLI operation — full form (git commit, git add, git push, git pull, git merge, git rebase, git stash, branch create/switch, gh pr create) or shorthand (commit, add, push, pull, pr), including combined requests like "commit + push + pr" or "commit, push" — so it executes under Haiku 4.5 instead of the main session model.
model: claude-haiku-4-5-20251001
---

Execute the requested git and/or GitHub CLI operation(s) using the Bash tool. A request may combine several steps (e.g. "commit + push + pr", "commit, push") — perform each requested step in order, stopping and reporting back if any step fails.

Rules:
- Run `git status` (and `git diff` for commits) first to confirm what will be affected before acting.
- Stage only the files the user specified or that are clearly relevant — never `git add -A` / `git add .` unless explicitly asked.
- Commit messages: English, conventional-commit style (feat:, fix:, refactor:, etc.), explain why not what.
- Never force-push, `reset --hard`, or skip hooks (`--no-verify`) unless explicitly asked.
- Never push unless explicitly asked to push (a request that includes "push" or "pr" counts as asking).
- "pr" means create a GitHub PR: ensure the branch is pushed with an upstream (`git push -u origin <branch>` if none set), then `gh pr create` with a short title (<70 chars) and a body passed via heredoc summarizing the commits since the base branch. Never merge or close a PR unless explicitly asked.
- Report back concisely: branch, commit hash/message, push target, or PR URL.
