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
    python -m native.cli verify        # pre-flight, cleans up after itself
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


def cmd_verify(args) -> None:
    """End-to-end deterministic pre-flight check for Claude-native mode.

    Runs every deterministic native/cli.py subcommand against the sample
    profile + sample resume with zero API keys, asserts each step
    succeeded, and cleans up every artifact it produced before exiting.
    Green exit code = the mode's deterministic plumbing works on this
    machine; only the reasoning-heavy steps of /apply-native (fit eval,
    drafter, reviewer) and the actual `anthropics/claude-code-action`
    workflow run remain unverified.

    Deliberately imports each stage inline (not at module top) so a single
    failing stage doesn't mask the rest — we still print which stage
    failed before propagating the exception.
    """
    import os
    from candidate_profile.loader import EXAMPLE_PROFILE_PATH, load_profile

    print("=" * 70)
    print("native/cli.py verify — zero-key pre-flight")
    print("=" * 70)

    profile = load_profile(str(EXAMPLE_PROFILE_PATH))
    resume_docx = Path(profile.resume_path)
    if not resume_docx.exists():
        # Sample profile always ships one; a missing sample resume means the
        # repo layout was tampered with and every downstream step will fail.
        raise SystemExit(f"Sample resume not found at {resume_docx} — repo layout broken")

    # Track everything we write so we can delete it at the end regardless of
    # whether the run passed or failed (matches the verify-before-claiming-done
    # skill's "clean up every artifact" rule — verification that pollutes real
    # state isn't free).
    artifacts_to_clean: list[Path] = []
    failures: list[str] = []

    def _step(label: str) -> None:
        print(f"\n[STEP] {label}")

    try:
        # ── 1. Scrape (zero keys) ──────────────────────────────────────────
        _step("scrape (LinkedIn guest source, zero keys required)")
        # Force-unset Adzuna to prove the LinkedIn-only path works.
        prior_adzuna = (os.environ.pop("ADZUNA_APP_ID", None),
                        os.environ.pop("ADZUNA_APP_KEY", None))
        try:
            from scraper.job_scraper import scrape_all_jobs
            jobs = scrape_all_jobs(profile)
        finally:
            if prior_adzuna[0] is not None:
                os.environ["ADZUNA_APP_ID"] = prior_adzuna[0]
            if prior_adzuna[1] is not None:
                os.environ["ADZUNA_APP_KEY"] = prior_adzuna[1]
        if not jobs:
            failures.append("scrape returned zero jobs — LinkedIn source is not producing matches")
            print("  ✗ 0 jobs (expected at least 1)")
        else:
            print(f"  ✓ {len(jobs)} jobs")

        # ── 2. Dedupe ─────────────────────────────────────────────────────
        _step("dedupe (filter_unscored, respects RESCORE_TTL_DAYS)")
        from storage.tracker_store import filter_unscored
        unscored = filter_unscored(jobs)
        print(f"  ✓ {len(unscored)} jobs remain after dedup")

        # ── 3. Rubric ─────────────────────────────────────────────────────
        _step("rubric (build_scoring_instructions — same text Groq path uses)")
        from scorer.match_scorer import build_scoring_instructions
        rubric = build_scoring_instructions(profile)
        if not rubric or "match_score" not in rubric:
            failures.append("rubric text is empty or missing 'match_score' — build_scoring_instructions is broken")
            print("  ✗ rubric text malformed")
        else:
            print(f"  ✓ rubric text {len(rubric)} chars")

        # ── 4. Patch resume (deterministic patch + PDF render) ────────────
        _step("patch-resume (patch_docx + LibreOffice PDF render OR DOCX fallback)")
        from optimizer.resume_optimizer import (
            extract_docx_text, extract_protected_metrics, patch_docx,
        )
        pre_patch_text = extract_docx_text(str(resume_docx))
        protected = extract_protected_metrics(pre_patch_text)
        first_role_key = next(iter(profile.roles), "role1")
        fabricated_tailoring = {
            "match_score": 82,
            "missing_keywords": [],
            "strong_matches": [],
            "chosen_archetype": next(iter(profile.archetypes), "default"),
            "optimized_summary": (
                "Verify-step optimized summary: reframing existing experience "
                "for TestCo without adding new claims."
            ),
            "optimized_competencies": ["Product Roadmapping", "Delivery"],
            "optimized_bullets": {
                first_role_key: [
                    (
                        # Preserve at least one protected metric verbatim so
                        # the "never drop a metric" guard is genuinely tested.
                        f"Led delivery improving activation by "
                        f"{next(iter(protected), '25%')} in verify-mode fixture"
                    ),
                ],
            },
            "cover_note_variants": [
                {"angle": "domain-fit", "text": "Verify-mode fixture cover note."}
            ],
            "screening_answers": [
                {"question": "Notice period?", "answer": "As stated in profile.context"}
            ],
        }
        ats_path, review_path, quality_warnings = patch_docx(
            str(resume_docx), fabricated_tailoring, profile, "VerifyTestCo", "Product Manager",
        )
        artifacts_to_clean.append(Path(ats_path))
        if str(review_path) != str(ats_path):
            artifacts_to_clean.append(Path(review_path))

        # Verify every protected metric survived — this is the guard the
        # Gemini path relies on, so a broken build here breaks both modes.
        post_patch_text = extract_docx_text(str(review_path))
        dropped = [m for m in protected if m not in post_patch_text]
        if dropped:
            failures.append(f"patch-resume dropped protected metrics: {dropped}")
            print(f"  ✗ dropped metrics: {dropped}")
        else:
            print(f"  ✓ patched, protected metrics preserved ({len(protected)} tracked)")
        if quality_warnings:
            # Not a failure by itself — a missing role section or an absent
            # LibreOffice is fail-open by design. Just surface it so the
            # runbook reader can distinguish "expected" from "surprising."
            for w in quality_warnings:
                print(f"    ⚠ {w}")

        # ── 5. save-run + mark-seen + export-csv ───────────────────────────
        _step("save-run + mark-seen + export-csv (git-committed state)")
        # RunSummary import lives in main.py; keep the import inline so a
        # broken import doesn't take out the earlier steps.
        from main import RunSummary
        from storage.run_store import RUNS_DIR, save_run_snapshot
        from storage.tracker_store import (
            export_csv as _export_csv, load_tracker,
            mark_seen, save_tracker,
        )
        # Snapshot the *current* tracker state so we can restore it after
        # the verify run — we must not persist a fake entry to real
        # git-committed state.
        pre_tracker = load_tracker()

        summary = RunSummary(dry_run=True)
        summary.total_scraped = len(jobs)
        summary.total_scored = 0
        summary.total_qualifying = 0
        snapshot_path = save_run_snapshot(summary, unscored[:1], source="verify")
        artifacts_to_clean.append(snapshot_path)
        print(f"  ✓ run snapshot: {snapshot_path.name}")

        mark_seen(unscored[:1])
        csv_path = _export_csv()
        artifacts_to_clean.append(csv_path)
        # Tracker JSON — restore rather than delete, since a real tracker
        # would already exist for a real user; but if none existed before,
        # remove ours so we don't create it as a side-effect.
        from storage.tracker_store import TRACKER_PATH
        if pre_tracker:
            save_tracker(pre_tracker)
        else:
            artifacts_to_clean.append(TRACKER_PATH)
        print(f"  ✓ tracker CSV: {csv_path.name}")

    finally:
        # Clean up EVERY artifact this run produced — the verify-before-
        # claiming-done skill's cardinal rule.
        _step(f"cleanup ({len(artifacts_to_clean)} artifact(s))")
        for p in artifacts_to_clean:
            try:
                if p.exists():
                    p.unlink()
                    print(f"  ✓ removed {p}")
            except Exception as exc:
                print(f"  ⚠ could not remove {p}: {exc}")

    print("\n" + "=" * 70)
    if failures:
        print(f"FAIL ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  • {f}")
        print("=" * 70)
        raise SystemExit(1)
    print("PASS — deterministic zero-key pipeline is green.")
    print("Still unverified (require a real Claude session / real GHA run):")
    print("  • /apply-native's reasoning steps (fit-eval, draft, reviewer, revise)")
    print("  • job_search_native.yml running end-to-end on a GHA runner")
    print("See docs/verify-native.md for the runbook to cover those manually.")
    print("=" * 70)


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

    p_verify = sub.add_parser("verify", help="End-to-end deterministic pre-flight check for Claude-native mode (zero keys, cleans up its own artifacts)")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
