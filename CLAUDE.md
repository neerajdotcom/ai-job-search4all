# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Docs are split for token efficiency.** This root file is loaded into
> every session. Deep per-module detail lives in nested `CLAUDE.md` files
> that Claude Code loads only when you work in that subtree:
> `scraper/` · `scorer/` · `optimizer/` · `digest/` · `storage/` · `webapp/`
> · `mcp_server/` · `native/`. Reusable task workflows live in `.claude/skills/`.

> **Two execution modes.** The pipeline described below (`main.py`,
> Gemini/Groq) is the original **API mode** — still fully supported. A
> second **Claude-native mode** (`native/`, `.claude/commands/scrape-native.md`,
> `.claude/commands/apply-native.md`, `.claude/skills/job-fit-evaluator/`)
> does the same scrape → fit-score → tailor flow with **zero LLM API keys**:
> scoring and resume tailoring happen as Claude's own reasoning instead of
> Gemini/Groq calls. It reuses the same deterministic building blocks
> (scraper, DOCX patch/PDF render, tracker, run snapshots) via `native/cli.py`,
> runs interactively (`/scrape-native`, `/apply-native <url>`) or headlessly
> in CI (`.github/workflows/job_search_native.yml`, authenticated with the
> same `CLAUDE_CODE_OAUTH_TOKEN` this repo already uses for `claude.yml`).
> See `native/CLAUDE.md` for the mode's internals.

## What This Is
A deploy-your-own, single-user job-search pipeline. Every candidate-specific
detail — name, title, years of experience, target location, search terms,
scoring rubric, résumé file — lives in one file, `candidate_profile/config.yaml`,
loaded by `candidate_profile/loader.py` into a `Profile` object that's threaded
through every stage. There is no hardcoded candidate anywhere in the code.

**First-time setup:** run `python setup_profile.py --resume your_resume.docx`
(one free-tier Gemini call extracts a draft profile from your résumé — review
it before your first real run) or copy `candidate_profile/config.example.yaml`
to `candidate_profile/config.yaml` and fill it in by hand.

## What This Does
Each run:
1. Scrapes LinkedIn's public guest job search (zero API key, on by default) + optionally Adzuna (country from `profile.adzuna_country_code`) + optionally direct employer ATS feeds for `profile.search_terms`
2. Locally pre-filters by keyword overlap (free, no API calls), then scores the top candidates against the résumé
3. Optimizes a tailored resume (a submittable **PDF** + an editable DOCX companion) for qualifying jobs, capped per run to protect free-tier quota
4. Emails one HTML digest with the match table, per-job recommendations, and "Fast-Apply Packs" (cover note + screening Q&A)

Runs on a schedule via GitHub Actions (`.github/workflows/job_search.yml`), or manually via `workflow_dispatch` with an optional dry-run input. A local-only web dashboard (`webapp/`) additionally lets you browse run history/job matches and trigger real runs from a UI.

## The Profile (`candidate_profile/`)
`candidate_profile/loader.py`'s `Profile` dataclass is the single source of
truth for everything candidate-specific: `name`, `title`, `years_experience`,
`context` (a short factual block the LLM quotes verbatim for screening
answers), `location`, `target_location_country` + `target_location_aliases` +
`blocked_locations`, `search_terms`, `target_companies`, `excluded_companies`,
`experience_exclude_years`, `adjacent_industries`, the scoring rubric bands
(`skill_areas`/`industry_bands`/`role_level_bands`, with generic 3-tier
defaults if a profile doesn't set them), résumé-tailoring `archetypes`,
`resume_path` (+ optional `secondary_resume_path` for a second track),
`roles` (employer → keyword list, used to locate each job's bullets in the
résumé DOCX), and `writing_style`. Every prompt in `scorer/match_scorer.py`
and `optimizer/resume_optimizer.py` is built from these fields at call time —
nothing is baked into the prompt text. See `candidate_profile/config.example.yaml`
for a fully-commented template.

## Commands
- One-time onboarding: `python setup_profile.py --resume your_resume.docx`
- Run the full pipeline: `python main.py`
- Dry run (scrape/score/optimize, no email, no DOCX writes, dumps `outputs/digest_preview.html`): `python main.py --dry-run`
- Force a full re-score, bypassing the cross-run dedup tracker: `python main.py --no-dedup`
- Use a specific profile or résumé override: `python main.py --profile path/to/config.yaml` / `--resume path/to/resume.docx`
- Install deps: `pip install -r requirements.txt`
- Exercise a single stage standalone (each module has a `__main__` block using the loaded profile):
  - `python -m scraper.job_scraper`
  - `python -m scorer.match_scorer`
  - `python -m optimizer.resume_optimizer [resume.docx]`
  - `python -m digest.email_digest` (sends a real test email with dummy jobs, or falls back to writing `outputs/digest_preview.html` if SMTP creds are missing)
- No automated test suite exists — verification is via `--dry-run` and the per-module `__main__` blocks above.

Required env vars (see `.env.example`): `GEMINI_API_KEY`, `GROQ_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT`. **`ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are optional** — the pipeline scrapes real jobs with zero keys via LinkedIn's public guest search (see `scraper/CLAUDE.md`); Adzuna is an additional, higher-volume source if you have keys.

Optional, off by default: `ENABLE_CRAWL4AI` (web-board scraping via headless Chromium — most boards block datacenter IPs, so this is best run from a residential IP). On by default: `ENABLE_LINKEDIN_SCRAPE` (LinkedIn's public guest job search — zero API key) and `ENABLE_ATS_SCRAPING` (direct Greenhouse/Lever/Ashby/Workable public APIs — zero API key, hand-picked company slugs in `scraper/ats_scraper.py`, currently iGaming/gaming-focused; irrelevant-industry profiles just get low-scoring results the 60-point gate filters out). Set either to `false` to disable.

## Pipeline Architecture (orchestration overview)
`main.py` orchestrates everything:

`candidate_profile.loader.load_profile()` → `scraper.job_scraper.scrape_all_jobs(profile)` → `scorer.match_scorer.prefilter_jobs(jobs, resume_text, profile)` → per-job `score_job(job, resume_text, profile)` → per-job `optimizer.resume_optimizer.optimize_resume(docx_path, jd, profile, ...)` → `digest.email_digest.send_digest(primary, profile, ...)`

Stage-by-stage internals live in the nested `CLAUDE.md` files. What lives in `main.py` itself:

- **Caps & thresholds:** `AI_SCORE_LIMIT` (50, max jobs scored on Groq), `AI_OPTIMIZE_LIMIT` (15, max resumes optimized on Gemini), `SCORE_THRESHOLD` (60, the single qualification gate), `REVIEW_BAND_MAX` (75, upper bound of the reviewer-pass band). The Groq scorer's merit rubric (`build_scoring_instructions(profile)`) sums SKILLS + INDUSTRY + ROLE LEVEL out of 100 using `profile.skill_areas`/`industry_bands`/`role_level_bands`, with an auto-exclude past `profile.experience_exclude_years`. `profile.target_companies` flags matching jobs for a "⭐ target company" highlight in the digest/dashboard — presentation-only, no effect on scoring or ordering. See `scorer/CLAUDE.md`.
- **Second resume track (optional):** set `profile.secondary_resume_path` to a second, differently-focused résumé. When present, `AI_SCORE_LIMIT` is split across two keyword-ranking passes (one per résumé) instead of doubling Groq usage; jobs the second pass surfaces are tagged `resume_track: "secondary"`, scored/tailored against that résumé, and rendered as a separate digest group (`profile.secondary_track_label`). Leave it unset to fall back to single-resume behavior. See `scorer/CLAUDE.md` and `digest/CLAUDE.md`.
- **Scoring-loop gates (skip, never drop):** ghost-job check and the off-target skip both tag a job (`ghost_flagged` / `off_target_skipped`) with placeholder `match_score: 0` and bypass Groq/Gemini, but the job still appears in the run snapshot and dashboard. See `scorer/CLAUDE.md`.
- **Mid-run tracker write:** `mark_seen(all_scored)` is called after scoring/optimizing and before the digest, so the weekly report and digest see fresh state. See `storage/CLAUDE.md`.
- **End-of-run:** skill-gap report + training recs (→ digest + snapshot), liveness re-check on qualifying jobs, digest bucketed into `primary`/`outside_target_location`/`qa_roles`, run snapshot saved, CSV exported, weekly report on Fridays.

## Key constraints / gotchas (global)
- **Free-tier-only by design.** The whole pipeline runs entirely on free LLM/API tiers. When changing models or call volume, check the per-provider throttle (`_MIN_INTERVAL` in `match_scorer.py` and `resume_optimizer.py`) and the caps in `main.py` (`AI_SCORE_LIMIT`, `AI_OPTIMIZE_LIMIT`) rather than just removing them.
- **Git is the database.** `data/runs/*.json` and `data/tracker.json` are git-committed history (not gitignored) and are how CLI / GitHub Actions / dashboard runs stay in sync. See `storage/CLAUDE.md`.
- **Never auto-submit.** The pipeline never submits an application anywhere (job-board ToS risk) — the Fast-Apply Pack is copy-paste material the user applies manually.
- **Never fabricate.** Résumé optimization only reframes existing experience in the JD's language; protected metrics (quantifiable figures found in the candidate's own résumé, extracted dynamically per-résumé) are never dropped or altered. Screening-question answers are grounded only in `profile.context`.
- `outputs/` is gitignored except `.gitkeep` — generated PDF/DOCX/HTML files are never committed; the GitHub Actions workflow uploads them as a run artifact instead (7-day retention).
- `main.py`'s exit code only reflects whether the digest was actually sent (or it was a dry run) — per-job scoring/optimization failures are logged as soft errors and don't fail the run, since one job's transient API error shouldn't suppress the whole digest.
- Module-specific gotchas (location matching, QA tagging, role_map, archetypes, LibreOffice, quota flags, dedup TTL) live in the relevant nested `CLAUDE.md`.
