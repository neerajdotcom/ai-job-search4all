---
name: job-fit-evaluator
description: >
  Score a single job posting against the candidate profile in
  candidate_profile/config.yaml, using the exact same profile-driven merit
  rubric (SKILLS + INDUSTRY + ROLE LEVEL out of 100) the Groq-based pipeline
  uses — but computed by the agent's own reasoning, zero API key required.
  Use as the fit-scoring step inside /scrape-native and /apply-native, or
  standalone when asked to "evaluate this job" or "score my fit" without
  wanting the full apply workflow.
---

# Job Fit Evaluator (native)

Zero-API-key equivalent of `scorer.match_scorer.score_job` (which calls
Groq). Same rubric, same output schema — computed as the agent's own
reasoning, so results are drop-in compatible with the existing
tracker/run-snapshot format.

## Why this fetches the live rubric

`scorer/match_scorer.py`'s `build_scoring_instructions(profile)` builds the
scoring rubric from `profile.skill_areas`/`industry_bands`/`role_level_bands`
at call time — it is **not** static text. Fetching it live means edits to
the profile's bands are automatically reflected here.

```bash
python -m native.cli rubric --profile candidate_profile/config.yaml
```

Read the output — it already names the candidate, their experience, and the
exact point bands to use.

## Steps

1. **Load context** (skip anything already in context from the calling skill):
   - Run the `rubric` command above.
   - Read `candidate_profile/config.yaml` for `experience_exclude_years` and
     `adjacent_industries`.
   - You need the resume text (already loaded by caller, or read
     `profile.resume_path` directly) and the job posting's
     title/company/location/description (already loaded, or fetched via
     browser/web tools if given only a URL).

2. **Experience gate.** If the posting clearly states a required-years figure
   exceeding `experience_exclude_years`, cap the score at 45 (mirrors
   `main.py`'s auto-exclude) and skip to step 4.

3. **Score.** Apply the rubric text exactly: sum SKILLS + INDUSTRY + ROLE
   LEVEL. Judge the role's actual function/domain, not shared job-title
   vocabulary — a role that shares generic words with the resume but whose
   real domain is unrelated must score its industry band as unrelated.
   Use `adjacent_industries` to distinguish a genuinely adjacent domain
   from an unrelated one.

4. **Output** exactly this JSON shape (matches `score_job`'s schema):

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
  vibes-based number.
