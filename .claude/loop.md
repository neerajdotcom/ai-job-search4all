# Project loop policy

When `/loop` runs in this repo with no interval and no prompt, the job is to
keep the current `claude/...` branch's open pull request mergeable — nothing
else. This is PR/CI babysitting, not a general maintenance task.

## Each iteration
1. Look up the open PR for the current branch (GitHub MCP
   `pull_request_read` / `list_pull_requests`).
2. **Failing CI** (e.g. the `claude-review` check, or any other check in
   `failure`/`error`): pull the logs (`get_job_logs` / `get_check_run`),
   diagnose the real cause, and push the minimal fix as a **new** commit.
3. **Unresolved review comments**: address each with a real code change, or
   reply explaining why not if the suggestion is wrong or out of scope —
   then resolve the thread once it's actually addressed.
4. **Merge conflicts with `main`**: merge or rebase `main` in and resolve
   conflicts by hand. Never force-push over review history to "solve" a
   conflict.
5. **Nothing actionable** (CI green, no new unresolved comments, no
   conflicts): say so in one line and stop. Don't keep iterating just to
   have something to report.

## Hard rules (inherited from the root `CLAUDE.md`)
- Never auto-submit anything outside this repo — no job applications, no
  external form submissions. This loop is scoped to PR hygiene only.
- Never push to a branch other than the current `claude/...` branch, and
  never push directly to `main`.
- Never amend a commit that's already been pushed — add a new commit instead.
- Never force-push, never `git reset --hard`, never skip hooks (`--no-verify`)
  to get a check to pass.
- `data/runs/*.json` and `data/tracker.json` are pipeline-generated history,
  not code to "fix" — leave them alone during PR babysitting.
