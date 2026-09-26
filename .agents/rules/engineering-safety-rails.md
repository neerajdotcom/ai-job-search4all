---
trigger: always_on
description: >
  Safety and correctness rails for autonomous operation on this repo —
  never fabricate, fail-open on optional paths, never take irreversible
  actions on the candidate's behalf.
---

# Engineering Safety Rails

## Never fabricate
Resume optimization only reframes existing experience in the JD's language.
Protected metrics (quantifiable figures from the candidate's own resume) are
never dropped or altered. Screening answers are grounded only in
`candidate_profile/config.yaml`'s `context` field — never invent a fact not
stated there (e.g. never state a specific salary figure).

## Never auto-submit
The pipeline never submits an application anywhere. Fast-Apply packs
(cover note + screening Q&A) are copy-paste material the user applies
manually. Never write code or take any action that would submit a form on
a job board.

## Operate on a copy
`native/cli.py patch-resume` always copies the source DOCX — never modify
the candidate's original resume file in place.

## Fail-open on optional paths, fail-loud on core ones
A per-job scoring or optimization failure should be logged as a soft error,
not abort the whole run. But a failure to send the digest (or save the run
snapshot) is core — surface it clearly.

## State lives in git
`data/runs/*.json` and `data/tracker.json` are git-committed history. Never
delete or overwrite them without the user's explicit instruction.

## Free-tier quota awareness
`AI_SCORE_LIMIT` (50) and `AI_OPTIMIZE_LIMIT` (15) in `main.py` exist to
protect free-tier quotas. Don't remove or raise them without checking the
per-provider throttle in `match_scorer.py` and `resume_optimizer.py`.

## `candidate_profile/config.yaml` is PII — never commit it
The profile contains the candidate's real name, location, and resume path.
It is gitignored by design. Never stage or commit it.
