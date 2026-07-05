---
name: tailor-resume
description: Tailor the candidate's CV/resume to a specific job description (pasted text, URL, or screenshots) and produce a submittable PDF + editable DOCX. Use for one-off "optimize my CV for this role" requests — not the automated pipeline. Reframes existing experience to the JD's language without fabricating, preserves protected metrics, flags honest gaps, never auto-submits.
---

# Tailor resume to a specific job

A manual, one-off workflow for "optimize my CV for this JD." It reuses the
conventions in `optimizer/resume_optimizer.py` but runs them by hand (the
sandbox has no `GEMINI_API_KEY`, so `optimize_resume()` can't be called
live). Keep everything truthful — reframe real experience, never invent it.

## Inputs
- **Base resume:** `candidate_profile/config.yaml`'s `resume_path` (load the
  profile via `candidate_profile.loader.load_profile()` to find it) unless
  the user points to another file.
- **JD:** may arrive as pasted text, a URL, or screenshots. If screenshots,
  read them with the Read tool. If a non-English JD, still produce English
  output unless asked otherwise.

## Steps
1. **Read the base resume** and the JD. Extract the JD's must-have criteria
   and core responsibilities into a short list.
2. **Honest gap check.** Map each must-have to real resume evidence. Where
   there's genuinely no evidence (e.g. a tool/domain the candidate hasn't
   used), **do not fabricate it** — note it as a gap to surface to the user.
3. **Draft optimized content**, reframing existing experience in the JD's
   vocabulary:
   - Professional Summary (the paragraph after the "Professional Summary" heading)
   - Core Competencies (the line after the "Core Competencies" heading)
   - Up to 3 bullets per role (see the profile's `roles` map for employer keys)
   - **Preserve protected metrics verbatim** — run
     `optimizer.resume_optimizer.extract_protected_metrics()` on the original
     resume text to get the exact set of percentages/dollar figures/
     multipliers this candidate's resume actually contains, then don't drop
     or alter any of them. Do not touch dates, titles, companies, education,
     contact info, or the Tools section.
4. **Patch a copy of the DOCX** with `python-docx` (never edit the source).
   Follow `optimizer/resume_optimizer.py`'s `_replace_paragraph_text` pattern
   (clear runs, set text on `runs[0]`) so formatting survives. Locate target
   paragraphs by anchor heading text, or reuse `patch_docx`'s font-size-based
   section/bullet detection. Write to
   `outputs/<ResumeSlug>_<Company>_<RoleSlug>.docx`.
5. **Render PDF** via headless LibreOffice, mirroring
   `resume_optimizer._render_pdf` (use a private
   `-env:UserInstallation=file://<tmpdir>` profile). If conversion fails or
   produces no PDF, fall back to delivering the DOCX and say so — never block
   on the renderer.
6. **Verify:** re-extract the patched DOCX text and confirm every protected
   metric found in step 3 is still present and only the intended paragraphs
   changed (diff against the original).
7. **Deliver** the PDF (and DOCX) via `SendUserFile`. In the reply, list what
   changed and explicitly call out any must-have gaps from step 2 so the user
   can decide how to address them (e.g. in a cover note).

## Hard rules
- Never fabricate experience, tools, or metrics.
- Never modify the source resume in place — always work from a copy in `outputs/`.
- Never auto-submit the application — hand the files back; the user applies.
- Output files go in `outputs/` (gitignored) and are not committed unless the
  user asks. If asked to keep a file out of git, deliver via `SendUserFile`
  only and don't write it anywhere tracked.
