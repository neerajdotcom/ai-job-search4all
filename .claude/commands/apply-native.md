# /apply-native - Zero-key drafter-reviewer application workflow

Claude-native equivalent of `optimizer.resume_optimizer.optimize_resume`
(the Gemini call) plus a real second-agent review — modeled directly on
`MadsLorentzen/ai-job-search`'s `.claude/commands/apply.md` drafter-reviewer
loop, adapted to this repo's DOCX+LibreOffice pipeline instead of LaTeX. The
job posting is `$ARGUMENTS` (a URL or pasted text). No API keys required.

**Token-efficiency rule:** don't re-Read a file whose contents are already
in your context from an earlier step in this same command.

---

## Step 0: Parse Input

- If `$ARGUMENTS` looks like a URL, use `WebFetch` to retrieve it.
- If it's pasted text, use it directly.
- Extract company name, role title, location.

## Step 1: DRAFTER - Evaluate Fit

Invoke the **job-fit-evaluator** skill on this posting. Present the result
(match_score, matched/missing keywords, seniority_fit, industry_fit,
recommendation) to the user and ask:

> "Should I proceed with drafting a tailored resume for this role?"

If no, stop here.

## Step 2: DRAFTER - Draft Tailoring JSON

Read (if not already in context):
- `candidate_profile/config.yaml` (`profile.archetypes`, `profile.context`, `profile.roles`)
- The candidate's resume text: `python -m native.cli` doesn't expose a raw
  text-extract subcommand — use `Read` on `profile.resume_path` directly
  (python-docx text is readable enough via Read for a .docx, but if it isn't,
  run `python3 -c "from optimizer.resume_optimizer import extract_docx_text; print(extract_docx_text('<path>'))"`)

Get the protected metrics that must survive verbatim:

```bash
python3 -c "from optimizer.resume_optimizer import extract_docx_text, extract_protected_metrics as epm; print(epm(extract_docx_text('<resume_path>')))"
```

Compose the tailoring JSON **inline, in your own reasoning** — this is the
step that replaces the Gemini call in `resume_optimizer.call_llm`. The
schema must match exactly (see `native/CLAUDE.md`'s contract note):

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

Rules, identical to the existing Gemini path:
- Only reframe existing experience in the JD's language — never fabricate.
- Preserve every protected metric from the step above verbatim somewhere in
  the optimized bullets.
- `cover_note_variants`: 2-3 genuinely different hooks, not reworded
  duplicates.
- `screening_answers`: grounded only in `profile.context` — never invent a
  fact not stated there (e.g. don't state a specific salary figure).

Write this JSON to a temp file, e.g. `/tmp/apply-native-tailoring.json`.
Keep the JSON in your working memory — you'll revise it in Step 4 without
re-reading the file.

## Step 3: REVIEWER - Research & Critique

Spawn a fresh-context reviewer using the **Agent tool** (`general-purpose`),
same pattern as this repo's own `minimal-code-review` skill's Explore
delegation. Pass the drafted JSON, the JD, and the profile context **inline
in the prompt** — do not make the reviewer read files you already have
loaded.

```
You are a hiring-manager proxy reviewing a job application draft. Research
the company (WebSearch/WebFetch: mission, recent news, the specific
team/department if named) and critique the draft below.

<JOB_POSTING>
<insert JD text>
</JOB_POSTING>

<CANDIDATE_CONTEXT>
<insert profile.context>
</CANDIDATE_CONTEXT>

<TAILORING_DRAFT>
<insert the JSON from Step 2>
</TAILORING_DRAFT>

Return feedback in two parts:
1. Structured edits: a JSON array of {"field": "optimized_summary" |
   "optimized_competencies" | "optimized_bullets.<role_key>" |
   "cover_note_variants", "new_value": ..., "reason": "..."} for concrete,
   mechanical changes.
2. Narrative suggestions grouped by: missed keywords/requirements,
   company-specific angles from your research, action-oriented reframing,
   tone/style issues. Produce every category even if "no issues."

Do not suggest fabricating anything. If a requirement is a genuine gap, say
so honestly. Report under 400 words.
```

## Step 4: DRAFTER - Revise

Apply the reviewer's structured edits directly to your in-memory JSON.
Incorporate narrative suggestions using judgment — company-specific angles
into the cover note, missed keywords into bullets/summary (prefer concrete
bullets over the abstract summary), tone fixes throughout. Never incorporate
a suggestion that would fabricate content — acknowledge a genuine gap
instead. Save the revised JSON to `/tmp/apply-native-tailoring.json`.

## Step 5: Patch & Render (MANDATORY — never skip)

```bash
python -m native.cli patch-resume --docx "<profile.resume_path>" \
    --profile candidate_profile/config.yaml \
    --company "<Company>" --title "<Role>" \
    --tailoring-json /tmp/apply-native-tailoring.json
```

This calls the **identical** `patch_docx`/`_render_pdf` code the Gemini path
uses — same protected-metrics guard, same DOCX→PDF LibreOffice render, same
`quality_warnings` if a section couldn't be located or LibreOffice isn't
installed. Read the returned `ats_output` path:

- If it's a `.pdf`: **Read the PDF** via the Read tool and visually verify —
  content reads naturally, no obviously-truncated section, protected metrics
  visible. (Our DOCX/LibreOffice pipeline doesn't have LaTeX's page-break
  fragility, so this is a content sanity-check, not a layout-iteration loop
  like the inspiration repo's LaTeX step — but still verify before
  presenting, never skip straight from JSON to "done.")
- If it's a `.docx` (LibreOffice unavailable): note this in the final
  summary — the DOCX is still a valid deliverable, just not pre-rendered
  to PDF.

If `quality_warnings` came back non-empty, surface every one of them to the
user — don't silently drop a "section not found" warning.

## Step 6: Present Final Output

```
### Fit Evaluation
[Step 1's result]

### Key Tailoring Decisions
- What was emphasized and why
- What the reviewer's research surfaced that got incorporated
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

## Hard rules (same as the existing Gemini path's, see root CLAUDE.md)
- Never fabricate experience, skills, or metrics.
- Never modify the source resume in place — `patch-resume` always copies.
- Never auto-submit — hand the files back.
