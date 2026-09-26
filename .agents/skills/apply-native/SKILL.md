---
name: apply-native
description: >
  Zero-key full application workflow: evaluate fit, draft a tailored resume
  JSON, run a self-review pass, patch the DOCX, and render a PDF — all
  without Gemini or Groq. The job posting is the argument (a URL or pasted
  text). Use when the user says "/apply-native <url>" or asks to tailor
  their resume for a specific job without API keys.
---

# /apply-native — Zero-key drafter-reviewer application workflow

Native equivalent of `optimizer.resume_optimizer.optimize_resume` (the
Gemini call) plus a second-pass self-review. The job posting is the argument
(a URL or pasted text). No API keys required.

**Token-efficiency rule:** don't re-read a file whose contents are already
in context from an earlier step in this same skill.

---

## Step 0: Parse Input

- If the argument looks like a URL, fetch it with browser tools.
- If it's pasted text, use it directly.
- Extract company name, role title, location.

## Step 1: DRAFTER — Evaluate Fit

Invoke the **job-fit-evaluator** skill on this posting. Present the result
(`match_score`, matched/missing keywords, `seniority_fit`, `industry_fit`,
`recommendation`) to the user and ask:

> "Should I proceed with drafting a tailored resume for this role?"

If no, stop here.

## Step 2: DRAFTER — Draft Tailoring JSON

Read (if not already in context):
- `candidate_profile/config.yaml` (`profile.archetypes`, `profile.context`,
  `profile.roles`)
- The candidate's resume text:
  ```bash
  python3 -c "from optimizer.resume_optimizer import extract_docx_text; print(extract_docx_text('<resume_path>'))"
  ```

Get the protected metrics that must survive verbatim:
```bash
python3 -c "from optimizer.resume_optimizer import extract_docx_text, extract_protected_metrics as epm; print(epm(extract_docx_text('<resume_path>')))"
```

Compose the tailoring JSON **in your own reasoning**. The schema must match
exactly:

```json
{
  "match_score": 0,
  "missing_keywords": [],
  "strong_matches": [],
  "chosen_archetype": "<one of profile.archetypes' keys>",
  "optimized_summary": "string",
  "optimized_competencies": ["..."],
  "optimized_bullets": { "<role_key from profile.roles>": ["...", "...", "..."] },
  "cover_note_variants": [{"angle": "domain-fit|delivery-track-record|growth-story", "text": "..."}],
  "screening_answers": [{"question": "...", "answer": "..."}]
}
```

Rules:
- Only reframe existing experience in the JD's language — never fabricate.
- Preserve every protected metric verbatim somewhere in the optimized bullets.
- `cover_note_variants`: 2–3 genuinely different hooks, not reworded duplicates.
- `screening_answers`: grounded only in `profile.context` — never invent a
  fact not stated there.

Write this JSON to `/tmp/apply-native-tailoring.json`.

## Step 3: REVIEWER — Research & Self-Review

Now switch perspective: act as a hiring-manager proxy reviewing the draft
you just produced. Use `/browser` (or web tools) to research the company
(mission, recent news, the specific team if named in the JD).

Critique the draft against:
1. Missed keywords/requirements from the JD
2. Company-specific angles your research surfaced
3. Action-oriented reframing opportunities
4. Tone/style issues

If you need deeper multi-model reasoning on a complex role, use `/boost`
before this step.

Produce feedback as:
- **Structured edits**: a JSON array of `{"field": "...", "new_value": ...,
  "reason": "..."}` for concrete mechanical changes
- **Narrative suggestions**: grouped by the four categories above

## Step 4: DRAFTER — Revise

Apply the structured edits to the in-memory JSON. Incorporate narrative
suggestions using judgment — company-specific angles into the cover note,
missed keywords into bullets/summary, tone fixes throughout. Never
incorporate a suggestion that would fabricate content — acknowledge a
genuine gap instead. Save the revised JSON to `/tmp/apply-native-tailoring.json`.

## Step 5: Patch & Render (MANDATORY — never skip)

```bash
python -m native.cli patch-resume --docx "<profile.resume_path>" \
    --profile candidate_profile/config.yaml \
    --company "<Company>" --title "<Role>" \
    --tailoring-json /tmp/apply-native-tailoring.json
```

This calls the identical `patch_docx`/`_render_pdf` code the Gemini path
uses — same protected-metrics guard, same DOCX→PDF LibreOffice render, same
`quality_warnings` if a section couldn't be located.

- If the output is a `.pdf`: visually verify the content reads naturally and
  protected metrics are visible.
- If it's a `.docx` (LibreOffice unavailable): note this — the DOCX is a
  valid deliverable, just not pre-rendered to PDF.
- If `quality_warnings` came back non-empty, surface every one to the user.

## Step 6: Present Final Output

```
### Fit Evaluation
[Step 1's result]

### Key Tailoring Decisions
- What was emphasized and why
- What the reviewer pass surfaced (company research, missed keywords)
- Any gaps acknowledged rather than papered over

### Files
- Resume: <ats_output>
- Editable DOCX: <review_output>
- Cover note (chosen variant + why): ...
- Screening answers: ...

### Quality Warnings
[list, or "none"]
```

Tell the user: "Review both files before sending — I never submit an
application on your behalf."

## Hard rules
- Never fabricate experience, skills, or metrics.
- Never modify the source resume in place — `patch-resume` always copies.
- Never auto-submit — hand the files back to the user.
