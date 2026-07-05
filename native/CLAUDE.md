# native/ — deterministic CLI for the Claude-native execution mode

Deep docs for `native/cli.py`. Loads when working in `native/`. High-level
overview is in the root `CLAUDE.md`.

## Why this exists
The Claude-native mode (`.claude/commands/scrape-native.md`,
`.claude/commands/apply-native.md`, `.claude/skills/job-fit-evaluator/`) does
fit scoring and resume tailoring as Claude's own reasoning instead of
Gemini/Groq API calls — but scraping, DOCX patching, PDF rendering, and
run/tracker persistence are already deterministic Python with no LLM
involved. `native/cli.py` exposes those exact functions as subcommands so
Claude shells out to them via `Bash` rather than re-deriving `python-docx`
patching logic (or any other deterministic step) ad hoc inside a skill —
expensive in tokens and fragile.

## Contract: `patch-resume` reuses `optimizer.resume_optimizer.patch_docx` verbatim
`patch_docx(source_path, result, profile, company_name, title)` in
`optimizer/resume_optimizer.py` was **already** decoupled from the Gemini
call — `call_llm()` builds the `result` dict, `patch_docx()` never calls an
LLM itself. `native/cli.py patch-resume` calls the identical function; the
only difference from the existing Gemini path is *who produces the
`result` dict* (Claude's own reasoning inline in `.claude/commands/apply-native.md`,
vs. a Gemini API call). The dict must match the schema `call_llm()`
produces: `optimized_summary` (string), `optimized_competencies` (list of
strings), `optimized_bullets` (object keyed by `profile.roles` keys, each a
list of up to 3 strings), plus optional `cover_note_variants`/
`screening_answers`/etc. Any format drift between what Claude writes and
this schema will surface as a `quality_warnings` entry from `patch_docx`
itself (missing section, missing protected metric) — not a crash.

## Subcommands
Every subcommand reads/writes JSON (stdin or `--*-json PATH`, `-` for
stdin) so results pipe between steps without re-parsing:
- `scrape` — `scraper.job_scraper.scrape_all_jobs(profile)`, zero keys
  required (see `scraper/CLAUDE.md`'s LinkedIn-guest entry).
- `dedupe` — `storage.tracker_store.filter_unscored`, same `RESCORE_TTL_DAYS`
  as the Gemini/Groq path.
- `patch-resume` — see contract above.
- `save-run` — builds a `main.RunSummary` from a JSON dict and calls
  `storage.run_store.save_run_snapshot`. `source` should be `"native"` (vs.
  the implicit `"api"` the Gemini/Groq path writes) so `webapp/` can
  distinguish which pipeline produced a run.
- `mark-seen` / `export-csv` — thin wrappers over
  `storage.tracker_store.mark_seen`/`export_csv`.
- `verify` — end-to-end deterministic pre-flight: runs every subcommand
  above against the example profile + sample résumé with `ADZUNA_APP_ID`
  force-unset, asserts each stage succeeded, and **cleans up every
  artifact it produced** (patched résumé under `outputs/`, run snapshot
  under `data/runs/`, `data/tracker.json`, `data/tracker_export.csv`)
  before exiting. Exit 0 = the deterministic zero-key plumbing works on
  this machine. Anything unverified (interactive `/apply-native`'s
  reasoning steps, a real `workflow_dispatch` of `job_search_native.yml`)
  needs the manual runbook in [`docs/verify-native.md`](../docs/verify-native.md).

## Gotchas
- `save-run`'s `--summary-json` needs `started_at` as an ISO 8601 string
  (`datetime.fromisoformat`) — omit it to default to "now."
- Testing any subcommand that writes to `data/` (`save-run`, `mark-seen`,
  `export-csv`) leaves a real file behind since `data/runs/*.json` and
  `data/tracker.json` are git-committed, not gitignored — delete test
  artifacts before committing, same as any other verification run in this
  repo (see the `verify-before-claiming-done` skill).
- `scrape`'s output keeps `jd_text`/`_full_text` (unlike `run_store`'s
  stripped snapshot) since the native fit-evaluator skill needs the JD text;
  strip them yourself before passing jobs to `save-run` if you want a
  smaller diff (`save_run_snapshot` already strips them internally, so this
  only matters for intermediate files you keep around).
