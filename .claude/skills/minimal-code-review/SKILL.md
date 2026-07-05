---
name: minimal-code-review
description: Audit this repo (or a specific module/diff) for over-engineering — dead code, unused imports, premature abstraction, reinvented stdlib logic — using a "does this need to exist?" decision ladder. Use when the user asks to "minimize code", "simplify the codebase", "remove dead code", or references the ponytail philosophy. Reports verified findings before applying any fix; never touches deliberate quota/throttle/safety guards.
---

# Minimal-code audit (decision ladder)

A repo-local version of the `ponytail` philosophy, run manually instead of as
an always-on plugin hook — no third-party startup script, no external
dependency, fully reviewable as a normal diff.

## The ladder
For any code under review, ask in order:
1. Does this need to exist at all? (YAGNI)
2. Is the same capability already implemented elsewhere in the repo?
3. Does Python's stdlib already do this?
4. Is there a native/platform feature that does this?
5. Does an already-imported dependency already do this?
6. Can it collapse to one line at its single call site?
7. Only then: write the minimum new code that works.

**Read and trace first.** The ladder runs after understanding the real call
path of the code in question — never guess that something is unused without
grepping for it.

## Non-negotiable boundaries — never minimize these
- Anything tied to the free-tier API constraints: `_MIN_INTERVAL` throttles,
  `_daily_quota_exhausted` flags, `AI_SCORE_LIMIT`/`AI_OPTIMIZE_LIMIT` caps in
  `main.py` (see root `CLAUDE.md`).
- The ghost-job / off-target / liveness "flag, never drop" skip logic in
  `main.py` and `scorer/match_scorer.py` — these intentionally bypass scoring
  but must still land in `all_scored` with placeholder fields. (A past audit
  pass nearly removed a `setdefault` here, mistaking it for redundant — it
  wasn't, since the ghost/off-target branches `continue` past the line that
  would otherwise set that key. Verify by reading the *actual* control flow,
  not just by counting call sites.)
- Error handling/validation at a real boundary (user input, external API
  responses, file I/O that can genuinely fail) — only remove defensive code
  proven unreachable given how a function is actually called internally.
- The protected-metrics guard (`extract_protected_metrics`) and any resume-content logic in `optimizer/`.

## Process
1. **Scope.** Default to the whole repo's `.py` files; if the user names a
   module, diff, or PR, scope to that instead.
2. **Find candidates.** For a whole-repo pass, delegate to an `Explore` agent
   (the codebase is too large to hold in one context) with explicit
   instructions to grep every flagged symbol for usages before reporting it
   — false positives waste review time. For a diff-sized pass, do this
   directly without a subagent.
3. **Verify every finding yourself before touching anything** — re-run the
   grep, read the surrounding control flow (especially branches with
   `continue`/`return`/`raise` that might be the only place a value is set).
   Drop anything that turns out load-bearing; say so rather than silently
   skipping it.
4. **Apply only confirmed fixes.** Prefer deletion over commenting-out.
   Remove now-orphaned imports in the same pass.
5. **Sanity check:** `python3 -m py_compile` and a plain `import` on every
   touched module.
6. **Diff review:** `git diff --stat` should show only the intended files;
   read the full diff to confirm no unintended changes.
7. **Report** findings grouped by file with confidence (high/medium/low) and
   a one-line reason each, before or alongside applying — the user should be
   able to see what was removed and why even after the fact.
8. **Commit/PR** per this repo's standing convention (one focused commit, a
   draft PR on `claude/tool-dashboard-frontend-ui-ghm2ox` describing what was
   checked and what was kept, subscribe to its activity).

## Outcome to aim for
Net code reduction with zero behavior change — every removal should be
something nothing else in the repo references, confirmed by grep and a clean
compile/import, not assumed from a function's name or apparent unused-ness.
