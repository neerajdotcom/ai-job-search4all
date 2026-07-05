"""
native/cli.py — deterministic helpers for the Claude-native execution mode.

Claude should never hand-write python-docx patching or PDF-rendering logic
ad hoc inside a skill/command — expensive in tokens and fragile. This CLI
wraps the parts of the pipeline that are ALREADY deterministic (no LLM call)
so both the Gemini/Groq pipeline (main.py) and the Claude-native
commands/skills (.claude/commands/*-native.md) call the identical code.
Every subcommand reads/writes JSON so Claude can pipe data through without
re-deriving formats.

Usage:
    python -m native.cli scrape --profile candidate_profile/config.yaml
    python -m native.cli dedupe --profile candidate_profile/config.yaml < jobs.json
    python -m native.cli patch-resume --docx resume.docx --profile config.yaml \
        --company Acme --title "Product Manager" --tailoring-json result.json
    python -m native.cli save-run --profile config.yaml --source native \
        --summary-json summary.json --jobs-json jobs.json
    python -m native.cli mark-seen --profile config.yaml < jobs.json
    python -m native.cli export-csv
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_profile(path: str | None):
    from candidate_profile.loader import load_profile, EXAMPLE_PROFILE_PATH
    return load_profile(path or str(EXAMPLE_PROFILE_PATH))


def _read_json_input(path: str | None):
    """Read JSON from a file path, or stdin if path is '-' or omitted."""
    if path and path != "-":
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def cmd_scrape(args) -> None:
    from scraper.job_scraper import scrape_all_jobs
    profile = _load_profile(args.profile)
    jobs = scrape_all_jobs(profile)
    # jd_text/_full_text can be large; keep them for the caller (fit
    # evaluation needs the JD text) but this is the same shape main.py uses.
    _print_json(jobs)


def cmd_dedupe(args) -> None:
    from storage.tracker_store import filter_unscored
    profile = _load_profile(args.profile)
    jobs = _read_json_input(args.jobs_json)
    unscored = filter_unscored(jobs)
    _print_json(unscored)


def cmd_rubric(args) -> None:
    """Print the exact same profile-driven scoring rubric text
    scorer.match_scorer.build_scoring_instructions() sends to Groq — so the
    native fit-evaluator skill scores against the identical rubric with zero
    risk of drifting from the Groq path's wording over time."""
    from scorer.match_scorer import build_scoring_instructions
    profile = _load_profile(args.profile)
    print(build_scoring_instructions(profile))


def cmd_patch_resume(args) -> None:
    from optimizer.resume_optimizer import patch_docx
    profile = _load_profile(args.profile)
    tailoring_result = _read_json_input(args.tailoring_json)

    ats_path, review_path, quality_warnings = patch_docx(
        args.docx, tailoring_result, profile, args.company, args.title or "",
    )
    _print_json({
        "ats_output": str(ats_path),
        "review_output": str(review_path),
        "quality_warnings": quality_warnings,
    })


def cmd_save_run(args) -> None:
    from main import RunSummary
    from storage.run_store import save_run_snapshot

    summary_data = _read_json_input(args.summary_json)
    jobs = _read_json_input(args.jobs_json)

    summary = RunSummary(
        started_at=datetime.fromisoformat(summary_data["started_at"])
        if summary_data.get("started_at") else datetime.now(timezone.utc),
        total_scraped=summary_data.get("total_scraped", 0),
        total_scored=summary_data.get("total_scored", 0),
        total_qualifying=summary_data.get("total_qualifying", 0),
        email_sent=summary_data.get("email_sent", False),
        dry_run=summary_data.get("dry_run", False),
        errors=summary_data.get("errors", []),
        skill_gaps=summary_data.get("skill_gaps", []),
        training_recs=summary_data.get("training_recs", []),
        ghost_flagged_count=summary_data.get("ghost_flagged_count", 0),
        off_target_skipped_count=summary_data.get("off_target_skipped_count", 0),
    )
    path = save_run_snapshot(summary, jobs, args.source, args.github_run_url)
    _print_json({"run_snapshot_path": str(path)})


def cmd_mark_seen(args) -> None:
    from storage.tracker_store import mark_seen
    jobs = _read_json_input(args.jobs_json)
    tracker = mark_seen(jobs)
    _print_json({"tracker_entries": len(tracker)})


def cmd_export_csv(args) -> None:
    from storage.tracker_store import export_csv
    path = export_csv()
    _print_json({"csv_path": str(path)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="Scrape jobs (LinkedIn guest + optional Adzuna/ATS), zero keys required")
    p_scrape.add_argument("--profile", help="Path to candidate_profile/config.yaml (defaults to config.example.yaml)")
    p_scrape.set_defaults(func=cmd_scrape)

    p_dedupe = sub.add_parser("dedupe", help="Filter jobs already scored within the tracker TTL. Reads job list JSON from --jobs-json or stdin")
    p_dedupe.add_argument("--profile", help="Path to candidate_profile/config.yaml")
    p_dedupe.add_argument("--jobs-json", help="Path to jobs JSON, or omit/'-' to read stdin")
    p_dedupe.set_defaults(func=cmd_dedupe)

    p_rubric = sub.add_parser("rubric", help="Print the profile-driven scoring rubric (same text the Groq path uses) as plain text")
    p_rubric.add_argument("--profile", help="Path to candidate_profile/config.yaml")
    p_rubric.set_defaults(func=cmd_rubric)

    p_patch = sub.add_parser("patch-resume", help="Patch a DOCX resume + render PDF from a tailoring JSON result (same schema as optimizer.resume_optimizer.call_llm's output)")
    p_patch.add_argument("--docx", required=True, help="Path to the source resume DOCX")
    p_patch.add_argument("--profile", help="Path to candidate_profile/config.yaml")
    p_patch.add_argument("--company", required=True)
    p_patch.add_argument("--title", default="")
    p_patch.add_argument("--tailoring-json", required=True, help="Path to a JSON file with optimized_summary/optimized_competencies/optimized_bullets/etc., or '-' for stdin")
    p_patch.set_defaults(func=cmd_patch_resume)

    p_save = sub.add_parser("save-run", help="Write a run snapshot to data/runs/<run_id>.json")
    p_save.add_argument("--profile", help="Path to candidate_profile/config.yaml")
    p_save.add_argument("--source", default="native")
    p_save.add_argument("--summary-json", required=True, help="Path to a JSON dict with started_at/total_scraped/etc., or '-' for stdin")
    p_save.add_argument("--jobs-json", required=True, help="Path to the scored jobs JSON list, or '-' for stdin")
    p_save.add_argument("--github-run-url")
    p_save.set_defaults(func=cmd_save_run)

    p_mark = sub.add_parser("mark-seen", help="Record scored jobs in the cross-run dedup tracker (data/tracker.json)")
    p_mark.add_argument("--profile", help="Path to candidate_profile/config.yaml")
    p_mark.add_argument("--jobs-json", help="Path to jobs JSON, or omit/'-' to read stdin")
    p_mark.set_defaults(func=cmd_mark_seen)

    p_csv = sub.add_parser("export-csv", help="Regenerate data/tracker_export.csv from the tracker")
    p_csv.set_defaults(func=cmd_export_csv)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
