---
name: job-fit-evaluator
description: >
  Score a single job posting against the candidate profile in
  candidate_profile/config.yaml, using the exact same profile-driven merit
  rubric (SKILLS + INDUSTRY + ROLE LEVEL out of 100) the Groq-based pipeline
  uses — but computed by Claude's own reasoning, zero API key required. Use
  as the fit-scoring step inside /scrape-native and /apply-native, or
  standalone when asked to "evaluate this job" or "score my fit" without
  wanting the full apply workflow.
allowed-tools: Read, Bash(python -m native.cli rubric:*), Bash(python3 -m native.cli rubric:*)
---

# Job Fit Evaluator (Claude-native)

Zero-API-key equivalent of `scorer.match_scorer.score_job` (which calls
Groq). Same rubric, same output schema — computed as Claude's own reasoning
instead of an external LLM call, so results are drop-in compatible with the
existing tracker/run-snapshot format.

## Why this reuses the rubric text instead of restating it
`scorer/match_scorer.py`'s `build_scoring_instructions(profile)` builds the
scoring rubric from `profile.skill_areas`/`industry_bands`/`role_level_bands`
at call time — it is **not** static text. If this skill hardcoded its own
copy of the rubric, it would silently drift from the Groq path the moment a
user edits their profile's bands. Instead, always fetch the live rubric:

```bash
python -m native.cli rubric --profile candidate_profile/config.yaml
```

(Omit `--profile` to use the example profile.) Read the output — it already
names the candidate, their experience, and the exact point bands to use.

## Steps

1. **Load context** (skip anything you already have from an earlier step in
   the same command — see the token-efficiency note in `apply-native.md`):
   - Run the `rubric` command above.
   - Read `candidate_profile/config.yaml` for `experience_exclude_years` and
     `adjacent_industries` (used below).
   - You need the resume text (already loaded by the caller, or read
     `profile.resume_path` via the Read tool) and the job posting's
     title/company/location/description (already loaded by the caller, or
     fetched via WebFetch if given only a URL).

2. **Experience gate.** If the posting states a required-years figure
   clearly exceeding `experience_exclude_years`, cap the score at 45
   (mirrors `main.py`'s auto-exclude) and skip straight to step 4 — no need
   to reason through the full rubric for a role that's gated out anyway.

3. **Score.** Apply the rubric text exactly as written: sum SKILLS +
   INDUSTRY + ROLE LEVEL. Judge the role's actual function/domain, not
   shared job-title vocabulary — a role that shares generic words with the
   resume but whose real domain is unrelated must score its industry band
   as unrelated, not inflated. Use `adjacent_industries` to distinguish a
   genuinely adjacent domain from an unrelated one.

4. **Output** exactly this JSON shape (matches `score_job`'s schema, so it's
   directly usable by `native/cli.py save-run`/`mark-seen` and the tracker):

```json
{
  "match_score": 0,
  "matched_keywords": [],
  "missing_keywords": [],
  "seniority_fit": "under | good | over",
  "industry_fit": "<one of profile.industry_bands' value strings>",
  "recommendation": "one sentence"
}
```

## Non-negotiable
- Never fabricate a skill/keyword match that isn't actually in the resume
  text — `missing_keywords` should be honest, not minimized to inflate the
  score.
- `match_score` is the literal sum of the three category scores, not a
  vibes-based number — show your addition if asked, don't just assert a
  total.
