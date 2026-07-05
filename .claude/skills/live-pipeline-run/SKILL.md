---
name: live-pipeline-run
description: Trigger a real (non-dry-run) job-search pipeline run via GitHub Actions and report the result. Use when the user asks to "do a live run", "run the pipeline for real", or "send today's digest". Triggers job_search.yml, polls to completion, and reports email_sent / scraped / qualifying from the new run snapshot, including the dedup-TTL explanation for a 0-scored result.
---

# Trigger and report a live pipeline run

A live run scrapes Adzuna + ATS feeds, scores up to 50 jobs on Groq,
optimizes up to 15 resumes on Gemini, **sends a real digest email**, and
commits a run snapshot. It's consequential — real email, real API quota, real
commit — so run it deliberately and report back.

## Why not run it in the sandbox
The 7 required credentials (`GEMINI_API_KEY`, `GROQ_API_KEY`, `ADZUNA_APP_ID`,
`ADZUNA_APP_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT`) are
not present locally — `python main.py` would fail at the first Adzuna call.
The repo's GitHub Actions secrets have them, so a live run goes through
`workflow_dispatch`.

## Steps
1. **Trigger** `job_search.yml` via the GitHub MCP `actions_run_trigger`
   (`run_workflow`): `owner: neerajdotcom`, `repo: job-search-agent`,
   `workflow_id: job_search.yml`, `ref: main` (or the branch the user names),
   `inputs: {"dry_run": "false"}`.
2. **Find the run** with `actions_list` (`list_workflow_runs`, filter to the
   `workflow_dispatch` event, newest first) and **poll** `actions_get`
   (`get_workflow_run`) until `status: completed`. A run typically takes
   several minutes (Gemini's 13s-per-call throttle on up to 15 optimizes).
   Don't busy-wait with shell `sleep` — re-check on a sensible cadence.
3. **Report** the conclusion plus, from the new `data/runs/<run_id>.json` on
   the target branch (read via the GitHub MCP file tools or `git show`):
   `email_sent`, `total_scraped`, `total_qualifying`, and any soft `errors`.
   The snapshot filename comes from `started_at` and can differ slightly from
   the commit-message timestamp — confirm the real filename via the commit's
   file list, don't assume.

## Interpreting results
- **`total_scored: 0` is usually not a failure.** The cross-run dedup tracker
  (`RESCORE_TTL_DAYS` = 14) skips postings already scored within the TTL, so a
  run minutes after another run on the same day legitimately scores nothing
  new. Check whether a recent prior snapshot already scored the same set
  before calling it a bug. Use `--no-dedup` (a separate code path) only if a
  forced re-score is genuinely wanted.
- A run that hit a mid-run Gemini/Groq daily-quota wall but still sent the
  digest is **fail-open behavior, not a failure** — `main.py`'s exit code only
  reflects whether the digest sent.
- If the workflow conclusion is `failure`, pull the job logs
  (`get_job_logs` / the run's logs URL) to diagnose before reporting.
