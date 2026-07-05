# job-search-agent

A free-tier, single-user, automated job-search pipeline. Each run scrapes
job boards, scores postings against your résumé, tailors a résumé + cover
note for the ones that qualify, and emails you a digest — all running on
free API tiers, with no server to host and no data leaving your own GitHub
repo.

Every candidate-specific detail — name, title, target location, search
terms, scoring rubric, résumé file — lives in one file you generate from
your own résumé. There is no hardcoded candidate anywhere in the code.

## What it does, each run
1. Scrapes Adzuna (your country) + optionally direct employer ATS boards for your search terms
2. Locally pre-filters by keyword overlap (free, no API calls), then scores the top candidates against your résumé (Groq)
3. Tailors a resume — a submittable **PDF** + an editable DOCX — for qualifying jobs (Gemini), capped per run to protect free-tier quota
4. Emails you one HTML digest: match table, per-job recommendations, and "Fast-Apply Packs" (cover note + screening Q&A)

It never auto-submits an application anywhere — the Fast-Apply Pack is
copy-paste material you use manually.

## Deploy your own copy

**1. Get the code.** Use this repo as a GitHub template (or fork it) into
your own repository.

**2. Add your secrets.** In your new repo's Settings → Secrets and
variables → Actions, add:

| Secret | What it's for |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio free tier — résumé tailoring |
| `GROQ_API_KEY` | Groq free tier — job scoring |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna's free job-search API |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | A Gmail account + [app password](https://myaccount.google.com/apppasswords) to send the digest from |
| `DIGEST_RECIPIENT` | Where the digest email is sent |

All of these have free tiers with no credit card required.

**3. Build your profile.** Clone your new repo locally, install deps
(`pip install -r requirements.txt`), copy `.env.example` to `.env` and fill
in the same values as above (for local runs), then run:

```
python setup_profile.py --resume your_resume.docx
```

This makes **one** Gemini call (your own free-tier key — no new cost) to
extract a draft `candidate_profile/config.yaml` from your résumé: name,
title, years of experience, location, search terms, industries, and the
per-employer keyword map used to locate your résumé's bullet points later.

**Review the draft before your first real run** — it's a starting point, not
gospel, exactly like the pipeline's own résumé-tailoring rule never to
fabricate. Open `candidate_profile/config.yaml` and check:
- the extracted fields actually match your résumé
- `target_companies` (optional — for a "⭐ target company" highlight) and `excluded_companies` (e.g. your current employer)
- the notice-period placeholder in `context` (used verbatim for screening-question answers)
- `adzuna_country_code` (Adzuna's two-letter country code)

If you'd rather write the config by hand instead of using the LLM draft,
copy `candidate_profile/config.example.yaml` to `candidate_profile/config.yaml`
and fill it in yourself — every field is commented.

**4. Try a dry run.**

```
python main.py --dry-run
```

This scrapes, scores, and tailors resumes without sending an email or
writing DOCX/PDF files — it dumps `outputs/digest_preview.html` so you can
see exactly what the real digest will look like.

**5. Turn on the schedule.** `.github/workflows/job_search.yml` runs on a
weekday cron by default. Adjust the schedule to taste, or trigger it
manually via the Actions tab's "Run workflow" button (with a dry-run option).

## Commands
- One-time onboarding: `python setup_profile.py --resume your_resume.docx`
- Run the full pipeline: `python main.py`
- Dry run: `python main.py --dry-run`
- Force a full re-score, bypassing the cross-run dedup tracker: `python main.py --no-dedup`
- Use a specific profile or résumé override: `python main.py --profile path/to/config.yaml` / `--resume path/to/resume.docx`
- Local dashboard (browse run history/job matches, trigger runs from a UI): `python -m webapp` → `http://127.0.0.1:8000/`

See `CLAUDE.md` for the full architecture — per-module docs live in nested
`CLAUDE.md` files under `scraper/`, `scorer/`, `optimizer/`, `digest/`,
`storage/`, `webapp/`, `mcp_server/`.

## Optional sources (off by default)
- `ENABLE_CRAWL4AI=true` — scrapes large job-board sites (Naukri, Indeed,
  Foundit, Instahyre, Wellfound) via headless Chromium. Most of these boards
  block datacenter IPs, so this only works reliably from a residential IP —
  run it locally, not in GitHub Actions.
- `ENABLE_ATS_SCRAPING=true` — pulls jobs directly from specific employers'
  Greenhouse/Lever/Ashby/Workable boards. The company lists in
  `scraper/ats_scraper.py` are empty by default — add your own target
  employers' board slugs before enabling.

## What stays private
Nothing about your résumé or search leaves your own GitHub repo and your own
free-tier API accounts. `data/runs/` and `data/tracker.json` are committed to
your repo as run history (this is intentional — see `storage/CLAUDE.md`,
"git is the database"); generated resume/cover-letter files in `outputs/` are
gitignored and never committed.
