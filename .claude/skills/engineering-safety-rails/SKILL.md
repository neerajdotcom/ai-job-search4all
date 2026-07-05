---
name: engineering-safety-rails
description: The safety and correctness rails that make autonomous operation on this repo safe — never fabricate, always operate on a copy, fail-open on optional paths / fail-loud on core ones, flag-don't-drop, quota awareness at every call site, outcome-based success criteria, state in the system of record, never take irreversible actions on the user's behalf, diagnose before overwriting, ask when the fork is real. Use as a standing checklist whenever touching scoring, optimization, digest sending, git history, or anything that talks to an external API or the user's real resume/email.
---

# Engineering safety rails

These are the boundaries the other skills in this repo (`ponytail-minimalism`,
`verify-before-claiming-done`, `self-pacing-loops`) operate inside of. They
are never in scope for a simplification or cleanup pass.

## Never fabricate
Reframe existing, real material only — experience, tools, metrics. Anything
that must survive a rewrite verbatim (a protected metric, a candidate fact)
is derived from the source itself at the time of the operation
(`extract_protected_metrics()` on the actual resume text), never hardcoded
once and left to drift out of sync with what the source actually contains.

## Always operate on a copy
The source of truth — a resume DOCX, `candidate_profile/config.yaml`, a git
branch — is never mutated in place by an automated step. Patch a duplicate
into `outputs/`, write to a new path, branch before rewriting history.

## Fail open on optional/best-effort paths, fail loud on core ones
A missing PDF renderer, a blocked ATS scrape target, an exhausted daily
Gemini/Groq quota — these degrade gracefully (skip, fall back to DOCX-only,
short-circuit remaining calls in that provider category) and get logged as
soft errors, never crash the whole run. A genuine data-integrity gap (a
resume section that should have been patched but wasn't) surfaces as a
first-class warning attached to the output, not a silent no-op.

## Flag, don't drop
Anything the automation is unsure about (a possible ghost listing, an
off-target posting, a role outside `experience_exclude_years`) gets tagged
and deprioritized in `all_scored`, not removed from the digest. Automated
filtering removes noise from ranking, never removes visibility — a human
still sees it and can override the automation's judgment.

## Quota and rate-limit awareness at every call site
A per-provider throttle (`_MIN_INTERVAL` in `match_scorer.py` and
`resume_optimizer.py`) plus a "daily cap already hit, stop trying"
short-circuit belongs at each call site, not just as one global cap — so one
exhausted quota doesn't burn the rest of a run retrying doomed calls.

## Success criteria track the outcome that matters
`main.py`'s exit code reflects only whether the digest actually sent (or it
was a dry run) — a single soft per-job scoring/optimization failure inside a
larger batch must not suppress everything downstream of it.

## State lives in the system of record
Durable state (run snapshots, the dedup tracker, profile config) belongs in
git / `data/runs/` / `storage/`, not a side channel — every consumer (CI,
CLI, the `webapp/` dashboard) reads the same truth instead of a drifting
cache.

## Never take an irreversible action on the user's behalf
Draft the resume, the email, the PR — hand it back. The user is the one who
submits an application, sends the real digest manually, merges the PR, or
deletes a branch. (`tailor-resume` explicitly hands files back via
`SendUserFile` rather than auto-submitting.)

## Diagnose before overwriting
Before any force-push, hard reset, or history rewrite, inspect what's
actually on the other side — what commits, what content, whether it's
someone else's in-progress work — rather than assuming it's safe to clobber.

## Ask when the fork is real, proceed when it isn't
A missing scope/permission, an ambiguous reading of a review comment, an
architecturally significant change: stop and ask. A small, unambiguous,
in-scope fix: just do it and report what changed afterward.

## Respect scope boundaries under refactor
When working on a generalized/derivative branch or repo, the original stays
provably untouched — verified by diff, not assumed.
