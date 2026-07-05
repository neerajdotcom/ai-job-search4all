# /scrape-native — Zero-key job search

You are running the Claude-native equivalent of `python main.py`'s scrape
stage — same job sources and tracker as the Gemini/Groq pipeline, but the
fit pass is Claude's own reasoning, not a Groq call. No API keys required
for this command; `candidate_profile/config.yaml` is the only input.

`$ARGUMENTS` may optionally narrow the search, e.g. `/scrape-native data
science` (matches `job-scraper`'s inspiration-repo convention) — otherwise
run the full `profile.search_terms` list.

## Step 1: Scrape

```bash
python -m native.cli scrape --profile candidate_profile/config.yaml > /tmp/scrape-native-jobs.json
```

This runs `scraper.job_scraper.scrape_all_jobs` — LinkedIn guest search (zero
key, on by default) plus Adzuna/ATS if the user has those optional keys
configured. Report the raw count.

## Step 2: Drop already-scored postings

```bash
python -m native.cli dedupe --profile candidate_profile/config.yaml --jobs-json /tmp/scrape-native-jobs.json > /tmp/scrape-native-unscored.json
```

Wraps `storage.tracker_store.filter_unscored` — same `RESCORE_TTL_DAYS` (14)
as the Gemini/Groq path, so a posting scored within the last two weeks isn't
re-surfaced.

## Step 3: Quick fit pass

Read `/tmp/scrape-native-unscored.json`. For each job, invoke the
**job-fit-evaluator** skill to get a `match_score`. This is a quick signal
per job, not the full drafter-reviewer workflow — don't over-invest tokens
per posting at this stage; a one-paragraph read of the JD plus the rubric is
enough for a ranking pass. If the list is large, batch several jobs per
fit-evaluator invocation rather than one Bash/Read round-trip per job.

## Step 4: Present results

```
## New Job Matches (Claude-native) — YYYY-MM-DD

Found X new positions (Y high [75+], Z medium [60-74], W low [<60]).

| # | Fit | Title | Company | Location | Source | URL |
|---|-----|-------|---------|----------|--------|-----|
| 1 | 82  | ...   | ...     | ...      | linkedin | [Link](...) |
```

Sort by `match_score` descending. After presenting, ask:
> "Want me to run the full application workflow on any of these? Give me
> the number(s) or a URL, and I'll run `/apply-native`."

## Step 5: Persist (only if the user wants to record this run)

If asked to save this as a tracked run:

```bash
python -m native.cli mark-seen --profile candidate_profile/config.yaml --jobs-json /tmp/scrape-native-unscored.json
python -m native.cli save-run --profile candidate_profile/config.yaml --source native \
    --summary-json <a small JSON dict you construct: started_at/total_scraped/total_scored/total_qualifying/dry_run=false/email_sent=false/errors=[]> \
    --jobs-json /tmp/scrape-native-unscored.json
python -m native.cli export-csv
```

This is what makes a `/scrape-native` run show up in `webapp/`'s dashboard
alongside Gemini/Groq runs, tagged `source: "native"`.

## Rules
1. Never fabricate a job posting — only present what `native/cli.py scrape`
   actually returned.
2. Respect the dedup step — don't re-present something already in the
   tracker within the TTL.
3. Don't run `native/cli.py mark-seen`/`save-run` unless the user asks to
   persist the run — a quick exploratory `/scrape-native` shouldn't silently
   write to git-committed state.
