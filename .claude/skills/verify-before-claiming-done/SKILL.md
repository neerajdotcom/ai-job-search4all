---
name: verify-before-claiming-done
description: Verification discipline for this repo's no-test-framework setup — how to actually confirm a change works before reporting it done. Use before claiming any change to scorer/, optimizer/, digest/, scraper/, storage/, or webapp/ is complete. Complements the repo-wide /verify skill with the specific checks this codebase relies on in place of a test suite (--dry-run, per-module __main__ blocks, real-fixture regression, grep-after-rename, compile-check, read-back-the-actual-output).
---

# Verification without a test framework

This repo has no automated test suite (`CLAUDE.md`: "verification is via
`--dry-run` and the per-module `__main__` blocks"). That makes each of the
following load-bearing, not optional.

## Every module is self-checkable
Each pipeline module carries a `__main__` block exercising itself against a
realistic sample (a sample job, a sample resume) — e.g.
`python -m scorer.match_scorer`, `python -m optimizer.resume_optimizer`,
`python -m digest.email_digest`. Run the relevant one standalone after
touching that module, before running the full pipeline.

## `--dry-run` is the standing pre-flight check
`python main.py --dry-run` runs every real stage (scrape → prefilter →
score → optimize) but stops short of irreversible steps (sending the email,
final DOCX/PDF writes to a tracked location) and dumps
`outputs/digest_preview.html` instead. This is what to run before ever
claiming a pipeline-level change "works" — not just "it compiled."

## Regress against real fixtures when available
Validate against the actual production `.docx` templates and real profile
config when they're accessible, not just synthetic stubs. Only fall back to
synthetic fixtures when the real ones genuinely aren't available (e.g. after
a scrub), and even then build them to mirror the real structure (same
heading/bold/size pattern in a resume DOCX, same field shape in a profile
YAML) rather than a shortcut shape that wouldn't exercise the real code path.

## Grep the whole tree after any rename or removal
A refactor isn't done until a search for the old identifier comes back empty
everywhere — code, nested `CLAUDE.md` docs, `.claude/skills/`, and the
GitHub Actions YAML in `.github/workflows/`. Missing a doc or workflow
reference is a real, shippable bug in this repo (a stale `CLAUDE.md` is
worse than none, and a stale workflow input actively breaks
`live-pipeline-run`).

## Cheap mechanical checks, every touched file
`python3 -m py_compile <file>` and a bare `import` on every touched module
before considering the change complete — catches the dumbest class of
breakage immediately, before any semantic verification.

## Read back the actual output — don't trust the log line
"No errors logged" is not verification. For a resume-patch change, re-open
the patched DOCX and confirm the specific text that was supposed to change
did, and that every protected metric (`extract_protected_metrics`) survived
verbatim. For a pipeline change, re-open the run snapshot JSON or
`digest_preview.html` and read the actual field, not just the exit code.

## Clean up verification artifacts before committing
A verification run must never leave a stray `outputs/` file, `data/runs/`
snapshot, or preview artifact in what gets committed. Verification that
pollutes the real state isn't free — check `git status` after any dry run
or standalone module check and remove/ignore anything it produced that
isn't meant to ship.

## Trust but verify your own summary
A description of what you intended to do is not evidence of what happened.
Before reporting a change complete, re-check the actual diff (`git diff`),
not your own prior claim about it.
