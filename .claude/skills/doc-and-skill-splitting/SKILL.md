---
name: doc-and-skill-splitting
description: Token-efficient documentation discipline for this repo — keep root CLAUDE.md small and high-level, push deep per-module detail into nested CLAUDE.md files loaded only when working in that subtree, and reserve .claude/skills/ for reusable invoked procedures rather than passive background context. Use whenever adding documentation, deciding where a piece of knowledge belongs, or writing/splitting a skill.
---

# Documentation and skill splitting

## Root `CLAUDE.md`: small and high-level only
It's loaded into every single turn regardless of what's being worked on, so
it should say what the system does, the top-level architecture, and the
global constraints that apply everywhere (quota discipline, "git is the
database," never-auto-submit). It should never carry deep per-module
implementation detail — that's the wrong place to pay that token cost on
every turn.

## Nested `CLAUDE.md`: deep detail, loaded only in-subtree
Split module internals, gotchas, and hard-won bug history into a nested
`CLAUDE.md` per subtree (`scorer/CLAUDE.md`, `optimizer/CLAUDE.md`,
`digest/CLAUDE.md`, `storage/CLAUDE.md`, `webapp/CLAUDE.md`,
`mcp_server/CLAUDE.md`). The root file just points at it ("See
`scorer/CLAUDE.md`") rather than duplicating it, so a session touching only
`webapp/` never pays the token cost of `scorer/`'s scoring-rubric internals,
and vice versa.

## Keep nested files honest as code evolves
A rename, a removed constant, a changed default: if it's referenced in prose
in a nested doc, that doc is stale until updated in the same pass as the
code change. Stale docs are worse than no docs — they actively mislead the
next session that loads them. (Pairs with `verify-before-claiming-done`'s
"grep the whole tree after any rename" step — nested `CLAUDE.md` files are
part of that grep, not exempt from it.)

## `.claude/skills/`: reusable procedures, not passive context
The distinction from a `CLAUDE.md` matters: a `CLAUDE.md` is background
knowledge loaded passively by directory; a skill is an active, self-contained
procedure invoked deliberately when its trigger matches (`live-pipeline-run`
for "do a live run," `minimal-code-review` for "simplify this,"
`tailor-resume` for a one-off JD ask). It is not loaded unless the task
actually calls for it.

## A skill's `description` is the entire routing signal
It has to state *when* to use it and *when not to* precisely enough that
intent-matching doesn't misfire on an adjacent-but-different request —
e.g. `tailor-resume`'s description explicitly says "not the automated
pipeline" to avoid colliding with `live-pipeline-run`.

## Fork a skill only when behavior genuinely differs
A directory-scoped skill name wins over an unscoped one when both could
apply, but don't create that split preemptively — only fork once two call
sites actually need different steps, per the same "does this need to exist"
ladder `ponytail-minimalism` applies to code.

## A skill must be a complete, re-runnable procedure, not a hint
Inputs, steps, hard rules, and a definition of "done" (what to verify before
handing back), written so a fresh session with zero prior context can
execute it correctly on the first read — the same bar the rest of this
repo's discipline is held to.
