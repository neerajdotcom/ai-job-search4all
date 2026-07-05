---
name: ponytail-minimalism
description: Standing minimalism discipline applied continuously while writing or reviewing code — not just a one-time cleanup pass. Use whenever adding a new abstraction, helper, flag, or config knob, and whenever reviewing existing code for the same. Complements minimal-code-review (that skill is the manual whole-repo audit; this one is the standing question asked at write-time and at review-time alike).
---

# Ponytail minimalism, applied continuously

## The standing question
Before adding any abstraction, helper, flag, or config knob — and before
removing anything found during review — ask: **does this need to exist?**
This isn't a cleanup-day ritual; it's the question asked at the moment of
writing, every time.

## Rules
- **Three similar lines beat a premature abstraction.** Don't build a
  framework for a pattern used twice. Don't add config for a case that can't
  currently happen.
- **No half-finished implementations.** A feature either fully works
  end-to-end or it doesn't ship this turn.
- **Validate only at real boundaries** — user input, external API responses,
  file I/O that can genuinely fail. Trust your own internal call graph;
  don't defensively check invariants your own code already guarantees.
- **Never touch deliberate guards while simplifying.** Quota throttles
  (`_MIN_INTERVAL`, `AI_SCORE_LIMIT`/`AI_OPTIMIZE_LIMIT`-style caps), retry
  backoffs, safety checks, and "never fabricate"/protected-metric logic look
  like extra complexity to a naive minimizer — they are load-bearing and out
  of scope for a simplification pass. See `minimal-code-review`'s
  non-negotiable boundaries list for the concrete examples in this repo.
- **Report verified findings before fixing.** State what's actually wrong
  and why, distinctly from what you intend to change — don't silently
  rewrite while reviewing.

## Relationship to `minimal-code-review`
`minimal-code-review` is the deliberate, whole-repo audit workflow (the
decision ladder, the Explore-agent delegation, the verified-findings report).
This skill is the same philosophy applied inline, continuously, at the
moment new code is written or an existing diff is reviewed — it has no
separate process of its own, just the standing question above.
