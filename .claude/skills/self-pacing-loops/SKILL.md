---
name: self-pacing-loops
description: Operating discipline for background work, polling, and long-running loops (PR watches, triggered GitHub Actions runs, scheduled check-ins). Use whenever starting a background task, deciding a wakeup/poll interval, or running a "watch until X" loop (a live pipeline run, a subscribed PR). Never poll harness-tracked work; match delay to what's actually being waited on; every loop has a terminal condition you drive to, not a timeout you shrug at.
---

# Self-pacing and long-running loops

## Never poll harness-tracked work
If a background command or agent was started through the harness (Bash
`run_in_background`, a backgrounded `Agent` call, a subscribed GitHub webhook),
the harness wakes this session when it finishes or fires. A short-interval
wakeup to "check if it's done yet" burns cache and turns for no reason —
don't schedule one for anything the harness already tracks.

## Match delay to what's actually being waited on
The prompt cache has a 5-minute TTL, so the interval isn't just a vibe:
- **60–270s** — only for state that must be watched closely and that the
  harness cannot notify on its own (a CI run mid-flight, a live pipeline run
  polled via `actions_get`, a deploy).
- **1200–1800s** — the default for "check back later": an idle tick, a PR
  sitting open with no new activity, a long external process.
- **Never exactly 300s** — it pays the cache-miss cost without buying a
  meaningfully longer wait. Round away from `:00`/`:30` on cron-style
  schedules so this doesn't stack with every other job that rounded the
  same way.

## A loop has a terminal condition, and you drive it there
"Watch this PR" ends at merged/closed, not at "nothing happened this hour."
"Trigger and report a live run" ends at the workflow's terminal status
(`completed`/`failure`), not at the first poll. On every real event (a CI
failure, a review comment, a workflow conclusion):
1. Re-diagnose from scratch — don't assume the prior diagnosis still holds.
2. Act: fix now if the change is small and unambiguous; ask if it's an
   architectural or interpretive fork (e.g. a reviewer comment with two
   readings); skip silently only if it's a duplicate or genuinely needs no
   action.
3. One round is never the whole task — re-kick and re-check until the
   terminal condition is reached.

## Silence is a valid outcome only when nothing changed
If a check-in finds nothing new, don't message — just re-arm the next
check-in. If something did change (success, failure, a new review comment),
report it once, without replaying the entire history each time. On success,
the success itself is the deliverable to report — not a no-op to swallow.
