# Verifying the Claude-native mode

`native/cli.py verify` handles the deterministic plumbing. This document
covers the two things it can't check automatically: an interactive
`/apply-native` run against a real posting, and a first
`workflow_dispatch` of `job_search_native.yml`.

Do these once, before you turn on the scheduled cron.

---

## 1. Pre-flight (deterministic, runnable locally)

```
python -m native.cli verify
```

Passes if:
- LinkedIn guest scraper returns ≥1 job for the example profile
- Dedup + rubric generation don't crash
- `patch_docx` writes a submittable resume (a `.pdf` if LibreOffice is
  fully installed, `.docx` otherwise) and every protected metric from
  the source résumé survives the patch
- Snapshot / tracker / CSV writes all succeed and get cleaned up

Green here means the only failure modes left in the scheduled workflow
are (a) missing `CLAUDE_CODE_OAUTH_TOKEN`, (b) missing
`candidate_profile/config.yaml`, or (c) something in Claude's own
reasoning steps. Everything downstream of those has just been proven
working.

Expected warnings that are **not** failures:
- `PDF render failed — DOCX used as the submit file` if you don't have
  LibreOffice + `libreoffice-java-common` installed locally. The
  workflow's `ubuntu-latest` runner installs both, so this is a
  local-machine-only warning.

---

## 2. Interactive `/apply-native` run (one real posting)

Once, before enabling the schedule:

```
/apply-native https://<a real job URL>
```

Check, in the presented output:

1. **Fit-eval numeric score is sane.** `match_score` is the sum of the
   three category scores (SKILLS + INDUSTRY + ROLE LEVEL), not a
   vibes-based number.
2. **`quality_warnings` from `patch-resume` is empty** — or only contains
   the expected "PDF render failed — DOCX used as the submit file" if
   your local LibreOffice isn't fully set up. A "Professional Summary
   section not found — left unpatched" would mean the résumé's headings
   don't match what `patch_docx` looks for; fix the résumé template or
   `optimizer/resume_optimizer.py`'s section-locator strings.
3. **Protected metrics visible** — open the rendered `.pdf` (or `.docx`
   fallback). Every percentage / dollar-figure / `Nx` multiplier in the
   original résumé is still there verbatim.
4. **`cover_note_variants`** — 2–3 entries with genuinely different
   `angle`s (`domain-fit` / `delivery-track-record` / `growth-story`),
   not reworded duplicates.
5. **`screening_answers`** — every answer is grounded in
   `profile.context`. No specific salary figure invented; no notice
   period claimed that isn't stated in the profile.

If any of these fail, iterate on the profile or the command's prompt
before enabling scheduled runs.

---

## 3. First scheduled run (`workflow_dispatch`)

In the GitHub UI: **Actions → Job Search Pipeline (Claude-native,
zero-key) → Run workflow**. Set `max_applies: 1` for the first run — a
bug then only wastes one tailoring pass.

Check, once the run finishes:

- [ ] The **"Commit run snapshot"** step's log contains
      `data: add native run snapshot <ts>` (means new snapshot was
      committed).
- [ ] The new commit on `main` (or your default branch) adds a
      `data/runs/<run_id>.json` whose `"source"` field is `"native"`.
- [ ] The **artifact `job-search-native-outputs-<n>`** contains a
      tailored file (`.pdf` if LibreOffice's apt install worked, `.docx`
      otherwise).
- [ ] If Gmail secrets are set, a digest email arrived at
      `DIGEST_RECIPIENT`.

If any step fails, jump to the failure diagnosis below.

Once this passes, the cron trigger in `job_search_native.yml` will now
run automatically on schedule. If you want to change or disable the
schedule, edit the `cron:` line or comment the `schedule:` block.

---

## Failure diagnosis (ranked most-likely-first)

**"Verify profile is set up" step fails.**
`candidate_profile/config.yaml` isn't committed to the branch the
workflow ran on. Run `/setup-native` (or `python setup_profile.py`) and
commit the result.

**"Run Claude-native pipeline" step fails with a missing-secret error.**
Add `CLAUDE_CODE_OAUTH_TOKEN` to Settings → Secrets and variables →
Actions. Get one via `claude setup-token` on any machine with Claude
Code installed.

**Claude runs out of context / hits a length limit.**
Reduce `max_applies` from the default 5 to 1–2 and re-run. Each apply
adds a full JD + résumé + reviewer transcript to the context.

**"Ensure LibreOffice" step fails.**
Rare — `libreoffice-writer` is almost always available on
`ubuntu-latest`. If it does fail, the pipeline still commits DOCX
tailored files (the fallback path); nothing else breaks.

**A `data/runs/<run_id>.json` gets committed but has no jobs / all
zeros.**
LinkedIn's guest endpoint may have transiently rate-limited the runner.
Re-run once. If it happens repeatedly on the schedule, disable
`ENABLE_LINKEDIN_SCRAPE` and add Adzuna keys instead (see the README).
