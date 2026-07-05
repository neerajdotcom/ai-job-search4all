"""
main.py — Job Search Pipeline Orchestrator

Usage:
    python main.py [--profile PATH] [--resume PATH] [--dry-run]

Options:
    --profile PATH  Path to your profile/config.yaml (default: candidate_profile/config.yaml).
                    Run setup_profile.py first if you haven't created one yet.
    --resume PATH   Override the primary resume DOCX for this run only
                    (default: profile.resume_path from your profile)
    --dry-run       Run scrape + score + optimize without sending email or writing DOCX files
"""

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 60

# Hybrid: scoring runs on Groq (high free volume), optimization on Gemini (~20/day).
AI_SCORE_LIMIT = 100     # max jobs sent to Groq for detailed scoring
AI_OPTIMIZE_LIMIT = 15   # max resumes optimized on Gemini per run

# The reviewer pass only earns its token cost on borderline scores — a job
# already at 90% isn't going to get meaningfully reassessed by a cheap
# excerpt-only audit. Jobs scoring in [SCORE_THRESHOLD, REVIEW_BAND_MAX) get
# reviewed; anything clearly above that band skips the extra Groq call.
REVIEW_BAND_MAX = 75

# Sort tiebreak within each digest section: prefer an exact ("good") fit over
# an overqualified one over an underqualified one.
_SENIORITY_RANK = {"good": 0, "over": 1, "under": 2}


# ---------------------------------------------------------------------------
# Run-summary dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_scraped: int = 0
    total_scored: int = 0
    total_qualifying: int = 0
    email_sent: bool = False
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)
    skill_gaps: list[dict] = field(default_factory=list)
    training_recs: list[dict] = field(default_factory=list)
    ghost_flagged_count: int = 0
    off_target_skipped_count: int = 0

    def log(self):
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        separator = "─" * 52
        logger.info(separator)
        logger.info("  Pipeline Run Summary")
        logger.info(separator)
        logger.info("  Mode            : %s", "DRY RUN" if self.dry_run else "LIVE")
        logger.info("  Jobs scraped    : %d", self.total_scraped)
        logger.info("  Jobs scored     : %d", self.total_scored)
        logger.info("  Ghost flagged   : %d  (skipped scoring)", self.ghost_flagged_count)
        logger.info("  Off-target      : %d  (skipped scoring)", self.off_target_skipped_count)
        logger.info("  Jobs qualifying : %d  (>= %d%%)", self.total_qualifying, SCORE_THRESHOLD)
        logger.info("  Email sent      : %s", "yes" if self.email_sent else "no")
        logger.info("  Elapsed         : %.1fs", elapsed)
        if self.errors:
            logger.info("  Errors (%d):", len(self.errors))
            for err in self.errors:
                logger.info("    • %s", err)
        else:
            logger.info("  Errors          : none")
        logger.info(separator)


# ---------------------------------------------------------------------------
# Resume extraction
# ---------------------------------------------------------------------------

def load_resume_text(docx_path: str) -> str:
    from docx import Document
    path = Path(docx_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {docx_path}")
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    logger.info("Loaded resume from '%s' (%d chars)", docx_path, len(text))
    return text


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _notify(progress_callback: Optional[Callable[[dict], None]], update: dict):
    if progress_callback is None:
        return
    try:
        progress_callback(update)
    except Exception:
        logger.exception("Progress callback raised — ignoring")


def run(
    dry_run: bool,
    profile=None,
    resume_path: Optional[str] = None,
    source: Optional[str] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    no_dedup: bool = False,
) -> RunSummary:
    """
    profile: a candidate_profile.loader.Profile. If omitted, the default
    candidate_profile/config.yaml is loaded (run setup_profile.py first if
    that file doesn't exist yet).
    resume_path: overrides profile.resume_path for this run only (e.g. the
    webapp's "trigger a run" form lets you pick a different resume file
    without editing your profile).
    """
    if source is None:
        source = "github_actions" if os.getenv("GITHUB_ACTIONS") == "true" else "cli"

    if profile is None:
        from candidate_profile.loader import load_profile
        profile = load_profile()

    if resume_path is None:
        resume_path = profile.resume_path

    summary = RunSummary(dry_run=dry_run)

    if dry_run:
        logger.info("*** DRY RUN MODE — no emails will be sent, no DOCX files written ***")

    # 1. Load resume(s)
    try:
        resume_text = load_resume_text(resume_path)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        summary.errors.append(str(exc))
        summary.log()
        return summary

    secondary_resume_text = None
    if profile.secondary_resume_path and os.path.exists(profile.secondary_resume_path):
        try:
            secondary_resume_text = load_resume_text(profile.secondary_resume_path)
        except Exception as exc:
            logger.warning("Secondary resume failed to load, skipping that track: %s", exc)

    # 2. Scrape
    logger.info("Step 1/3 — Scraping job listings")
    _notify(progress_callback, {"stage": "scraping"})
    from scraper.job_scraper import scrape_all_jobs
    try:
        jobs = scrape_all_jobs(profile)
    except Exception as exc:
        msg = f"Scraper crashed: {exc}"
        logger.error(msg)
        summary.errors.append(msg)
        jobs = []

    summary.total_scraped = len(jobs)
    logger.info("Scraped %d fresh jobs total", len(jobs))
    _notify(progress_callback, {"stage": "scraped", "total_scraped": summary.total_scraped})

    if not jobs:
        logger.warning("No jobs scraped — sending zero-match digest")

    # 3. Pre-filter locally (free), then score + optimize with Gemini
    logger.info("Step 2/3 — Pre-filtering, scoring and optimizing")
    _notify(progress_callback, {"stage": "prefiltering"})
    from scorer.match_scorer import (
        score_job, prefilter_jobs, review_score,
        is_ghost_job, build_jd_fingerprint_index,
    )
    from optimizer.resume_optimizer import optimize_resume

    # Cross-run dedup FIRST — drop postings already scored within the TTL
    # from the full scraped pool, before ranking eats the AI_SCORE_LIMIT
    # slots on jobs that already had their turn. (Previously this ran after
    # the prefilter cut, which meant dedup only ever saw the same ~50
    # keyword-top jobs and had nothing left to skip — see CLAUDE.md history.)
    if jobs and not no_dedup:
        from storage.tracker_store import filter_unscored
        before_dedup = len(jobs)
        jobs = filter_unscored(jobs)
        deduped = before_dedup - len(jobs)
        if deduped:
            logger.info("Cross-run dedup skipped %d already-scored job(s)", deduped)
            _notify(progress_callback, {
                "stage": "deduped", "skipped": deduped, "remaining": len(jobs),
            })

    # Drop out-of-target-location jobs before prefilter so all scoring slots
    # go to roles in the candidate's target location.
    before_location_filter = len(jobs)
    jobs = [j for j in jobs if j.get("is_target_location", True)]
    location_dropped = before_location_filter - len(jobs)
    if location_dropped:
        logger.info("Target-location filter dropped %d job(s)", location_dropped)

    # Free keyword pre-filter — pick the most relevant *unseen* jobs to spend
    # AI quota on. With a secondary resume present, split the AI_SCORE_LIMIT
    # budget across both tracks rather than doubling Groq usage: the second
    # pass ranks only what the first pass didn't already claim, so the
    # combined total never exceeds AI_SCORE_LIMIT.
    if jobs and secondary_resume_text:
        primary_n = AI_SCORE_LIMIT // 2
        secondary_n = AI_SCORE_LIMIT - primary_n
        primary_candidates = prefilter_jobs(jobs, resume_text, profile, top_n=primary_n)
        claimed_ids = {id(j) for j in primary_candidates}
        remaining = [j for j in jobs if id(j) not in claimed_ids]
        secondary_candidates = prefilter_jobs(remaining, secondary_resume_text, profile, top_n=secondary_n)
        for j in secondary_candidates:
            j["resume_track"] = "secondary"
        jobs = primary_candidates + secondary_candidates
    elif jobs:
        jobs = prefilter_jobs(jobs, resume_text, profile, top_n=AI_SCORE_LIMIT)

    primary: list[dict] = []
    outside_target_location: list[dict] = []
    qa_roles: list[dict] = []
    all_scored: list[dict] = []
    optimized_count = 0

    # Ghost-job fingerprint index — built once over the prefiltered/deduped
    # batch so the duplicate-JD heuristic in is_ghost_job is O(n), not O(n^2).
    ghost_fingerprints = build_jd_fingerprint_index(jobs) if jobs else {}

    for i, job in enumerate(jobs, start=1):
        title = job.get("title", "?")
        company = job.get("company", "?")
        is_secondary_track = job.get("resume_track") == "secondary"
        job_resume_text = secondary_resume_text if is_secondary_track else resume_text
        job_resume_path = profile.secondary_resume_path if is_secondary_track else resume_path

        _notify(progress_callback, {
            "stage": "scoring", "current": i, "total": len(jobs),
            "title": title, "company": company,
        })

        # Off-target check — free, no API call. ATS feeds return a company's
        # *entire* job board unfiltered by title (unlike Adzuna, which is
        # queried per profile.search_terms), so an unrelated role can
        # otherwise consume a scarce Groq scoring slot just for sharing
        # vocabulary with the resume. Skip scoring entirely for ATS-sourced
        # jobs that are neither on the candidate's own target-role track
        # (profile.search_terms) nor a QA role (QA roles still get scored —
        # they have their own digest section). Adzuna jobs are exempted
        # since they were already relevance-filtered at query time.
        if job.get("source") != "adzuna" and not job.get("is_target_role") and not job.get("is_qa_role"):
            summary.off_target_skipped_count += 1
            logger.info(
                "[%d/%d] OFF-TARGET %s @ %s — not a target role — scoring skipped",
                i, len(jobs), title, company,
            )
            all_scored.append({
                **job,
                "off_target_skipped": True,
                "match_score": 0,
                "qualifying": False,
                "matched_keywords": [],
                "missing_keywords": [],
                "seniority_fit": "unknown",
                "industry_fit": "unknown",
                "recommendation": "Skipped scoring: not a target role for this profile.",
            })
            continue

        # Out-of-target-location skip — postings outside profile.location are
        # skipped before scoring to avoid spending a Groq slot on jobs the
        # user cannot pursue.
        if not job.get("is_target_location", True):
            summary.off_target_skipped_count += 1
            logger.info(
                "[%d/%d] OUT-OF-REGION %s @ %s (%s) — scoring skipped",
                i, len(jobs), title, company, job.get("location", ""),
            )
            all_scored.append({
                **job,
                "off_target_skipped": True,
                "match_score": 0,
                "qualifying": False,
                "matched_keywords": [],
                "missing_keywords": [],
                "seniority_fit": "unknown",
                "industry_fit": "unknown",
                "recommendation": f"Skipped scoring: outside {profile.location}.",
            })
            continue

        # Ghost-job check — four free local heuristics, no API call. A
        # flagged posting never spends a Groq scoring slot (let alone a
        # scarce Gemini optimize slot), but it isn't hard-dropped from the
        # run snapshot — it's recorded with the reason so the digest/dashboard
        # can show why it was excluded and the user can override by re-running.
        ghost_flagged, ghost_reason = is_ghost_job(job, ghost_fingerprints)
        if ghost_flagged:
            summary.ghost_flagged_count += 1
            logger.info(
                "[%d/%d] GHOST %s @ %s — %s — scoring skipped",
                i, len(jobs), title, company, ghost_reason,
            )
            all_scored.append({
                **job,
                "ghost_flagged": True,
                "ghost_reason": ghost_reason,
                "match_score": 0,
                "qualifying": False,
                "matched_keywords": [],
                "missing_keywords": [],
                "seniority_fit": "unknown",
                "industry_fit": "unknown",
                "recommendation": f"Ghost-job flagged: {ghost_reason}",
            })
            continue

        # Score
        try:
            scored_job = score_job(job, job_resume_text, profile)
        except Exception as exc:
            msg = f"[{i}/{len(jobs)}] Scorer failed for '{title}' @ {company}: {exc}"
            logger.error(msg)
            summary.errors.append(msg)
            continue

        summary.total_scored += 1
        score = scored_job.get("match_score", 0)
        scored_job["qualifying"] = score >= SCORE_THRESHOLD
        all_scored.append(scored_job)

        if score < SCORE_THRESHOLD:
            logger.info(
                "[%d/%d] SKIP  %s @ %s — score %d%% below threshold",
                i, len(jobs), title, company, score,
            )
            continue

        summary.total_qualifying += 1

        # Drafter-reviewer second pass — a cheap Groq sanity-check of this
        # job's own qualifying score before spending Gemini optimize quota on
        # it. Only worth the extra call for borderline scores (see
        # REVIEW_BAND_MAX) — a clearly-strong match doesn't need auditing.
        # Fails open: a reviewer error or exhausted quota just leaves the
        # first-pass score as-is (review_score returns None in both cases).
        review = review_score(scored_job, profile) if score < REVIEW_BAND_MAX else None
        if review:
            scored_job["reviewer_score"] = review["reviewed_score"]
            scored_job["reviewer_notes"] = review["reviewer_notes"]
            if review["score_adjusted"] and review["reviewed_score"] != score:
                logger.info(
                    "[%d/%d] REVIEW %s @ %s — Groq %d%% -> reviewer %d%%: %s",
                    i, len(jobs), title, company, score, review["reviewed_score"], review["reviewer_notes"],
                )
                score = review["reviewed_score"]
                scored_job["match_score"] = score
                scored_job["qualifying"] = score >= SCORE_THRESHOLD
                if score < SCORE_THRESHOLD:
                    summary.total_qualifying -= 1
                    logger.info(
                        "[%d/%d] DEMOTE %s @ %s — reviewer dropped score below threshold, skipping optimize",
                        i, len(jobs), title, company,
                    )
                    continue

        # Bucket: only target-location + non-QA jobs ("primary") get a
        # tailored resume. Out-of-region and QA/testing roles are
        # informational-only in the digest — no Gemini call, no DOCX/PDF, no
        # cover note.
        is_primary = job.get("is_target_location", True) and not job.get("is_qa_role", False)

        if not is_primary:
            scored_job["ats_output"] = None
            scored_job["review_output"] = None
            logger.info(
                "[%d/%d] QUALIFY (informational) %s @ %s — score %d%% — %s",
                i, len(jobs), title, company, score,
                "QA/testing role" if job.get("is_qa_role") else f"outside {profile.location}",
            )
        elif dry_run:
            logger.info(
                "[%d/%d] QUALIFY (dry-run) %s @ %s — score %d%% — skipping DOCX write",
                i, len(jobs), title, company, score,
            )
            scored_job["ats_output"] = None
            scored_job["review_output"] = None
        elif optimized_count >= AI_OPTIMIZE_LIMIT:
            logger.info(
                "[%d/%d] QUALIFY %s @ %s — score %d%% — optimize cap reached, attaching base resume",
                i, len(jobs), title, company, score,
            )
            scored_job["ats_output"] = None
            scored_job["review_output"] = None
        else:
            _notify(progress_callback, {
                "stage": "optimizing", "current": i, "total": len(jobs),
                "title": title, "company": company,
            })
            try:
                result = optimize_resume(job_resume_path, job.get("jd_text", ""), profile, company, title)
                scored_job["ats_output"] = result.get("ats_output")
                scored_job["review_output"] = result.get("review_output")
                scored_job["cover_note"] = result.get("cover_note")
                scored_job["cover_note_variants"] = result.get("cover_note_variants")
                scored_job["chosen_archetype"] = result.get("chosen_archetype")
                scored_job["screening_answers"] = result.get("screening_answers")
                scored_job["quality_warnings"] = result.get("quality_warnings", [])
                optimized_count += 1
                logger.info(
                    "[%d/%d] QUALIFY %s @ %s — score %d%% — fast-apply pack ready",
                    i, len(jobs), title, company, score,
                )
            except Exception as exc:
                msg = f"[{i}/{len(jobs)}] Optimizer failed for '{title}' @ {company}: {exc}"
                logger.error(msg)
                summary.errors.append(msg)
                scored_job["ats_output"] = None
                scored_job["review_output"] = None

        scored_job["optimized"] = bool(scored_job.get("ats_output"))

        if job.get("is_qa_role"):
            qa_roles.append(scored_job)
        elif not job.get("is_target_location", True):
            outside_target_location.append(scored_job)
        else:
            primary.append(scored_job)

        # Polite pause between API calls
        time.sleep(0.5)

    for scored_job in all_scored:
        scored_job.setdefault("optimized", bool(scored_job.get("ats_output")))
        scored_job.setdefault("quality_warnings", [])
        scored_job.setdefault("reviewer_score", None)
        scored_job.setdefault("reviewer_notes", "")

    # Rank each digest section by match score, then seniority fit (an
    # overqualified match still beats an underqualified one).
    def _section_sort_key(j):
        return (-j.get("match_score", 0), _SENIORITY_RANK.get(j.get("seniority_fit"), 99))

    primary.sort(key=_section_sort_key)
    outside_target_location.sort(key=_section_sort_key)
    qa_roles.sort(key=_section_sort_key)

    # Liveness re-check — right before surfacing matches, re-verify each
    # qualifying Adzuna posting is still reachable (a job fresh at scrape time
    # can be filled days later). Bounded: runs only on the small qualifying
    # set, skips live-board ATS jobs, and fails open (see check_job_live).
    # Dead postings are flagged (live=False), not dropped — the user still
    # sees the match with a "may be closed" note.
    from scraper.job_scraper import check_job_live
    dead = 0
    for scored_job in primary + outside_target_location + qa_roles:
        is_live = check_job_live(scored_job)
        scored_job["live"] = is_live
        if not is_live:
            dead += 1
    if dead:
        logger.info("Liveness re-check: %d qualifying posting(s) flagged as likely closed", dead)
        _notify(progress_callback, {"stage": "liveness", "dead": dead})

    # Skill-gap report — zero extra LLM cost, reuses each job's missing_keywords
    # (already produced by Groq scoring above) to surface what shows up most
    # often across this run's matches. Scoped to is_target_role jobs only —
    # ATS feeds return a company's entire board unfiltered by title, so an
    # unrelated role (concept artist, data scientist) that scored decently on
    # generic gaming-keyword overlap would otherwise pollute the aggregate
    # with irrelevant "missing keywords" that aren't actually worth training for.
    from digest.presentation import compute_skill_gaps
    on_track = [j for j in all_scored if j.get("is_target_role")]
    summary.skill_gaps = compute_skill_gaps(on_track)

    # Training recommendations — one Groq call (not per job) that turns the
    # recurring skill gaps above into concrete course/cert picks. Fails open to
    # [] on any error/quota, so the digest just omits the section.
    try:
        from scorer.match_scorer import generate_training_recommendations
        summary.training_recs = generate_training_recommendations(summary.skill_gaps, profile)
    except Exception as exc:
        logger.warning("Training recommendations skipped: %s", exc)
        summary.training_recs = []

    # Remember every job scored this run so the cross-run dedup gate can skip
    # them next time, and refresh the derived CSV export. Runs even on a dry
    # run (tracker is run-history memory, not a side effect of sending the
    # digest) and before the digest is built below so the weekly report (also
    # below) reflects this run's freshly scored jobs. Fails soft — a tracker
    # write error must never fail the run.
    try:
        if all_scored:
            from storage.tracker_store import mark_seen, export_csv
            mark_seen(all_scored)
            export_csv()
    except Exception as exc:
        logger.error("Failed to update cross-run tracker: %s", exc)
        summary.errors.append(f"Tracker update failed: {exc}")

    # Weekly career report — Friday-only (IST), no LLM call: every figure is a
    # deterministic aggregation over storage.run_store/tracker_store via
    # digest.analytics. Built after the tracker update above so it sees this
    # run's data, and before the digest so the Friday email can include it.
    weekly_report_md = None
    try:
        from digest.weekly_report import is_report_day, build_weekly_report
        if is_report_day(summary.started_at):
            weekly_report_md, weekly_report_path = build_weekly_report(summary.started_at)
            logger.info("Weekly career report written to %s", weekly_report_path)
    except Exception as exc:
        logger.warning("Weekly report skipped: %s", exc)
        weekly_report_md = None

    # 4. Send digest
    logger.info("Step 3/3 — Sending digest (%d qualifying job(s))", summary.total_qualifying)
    _notify(progress_callback, {"stage": "sending_digest", "qualifying_count": summary.total_qualifying})
    from digest.email_digest import send_digest

    if dry_run:
        from digest.email_digest import _build_html
        date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
        html = _build_html(primary, outside_target_location, qa_roles, date_str, profile,
                           skill_gaps=summary.skill_gaps, training_recs=summary.training_recs,
                           weekly_report=weekly_report_md)
        preview_path = Path("outputs/digest_preview.html")
        preview_path.parent.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        logger.info("Dry-run: digest HTML written to %s", preview_path)
        summary.email_sent = False
    else:
        try:
            sent = send_digest(primary, profile, outside_target_location, qa_roles,
                               skill_gaps=summary.skill_gaps, training_recs=summary.training_recs,
                               weekly_report=weekly_report_md)
            summary.email_sent = sent
            if not sent:
                summary.errors.append("send_digest returned False — check SMTP credentials")
        except Exception as exc:
            msg = f"Digest send crashed: {exc}"
            logger.error(msg)
            summary.errors.append(msg)

    # 5. Persist run snapshot (git-committed JSON "database")
    try:
        from storage.run_store import save_run_snapshot
        github_run_url = None
        if source == "github_actions":
            server = os.getenv("GITHUB_SERVER_URL")
            repo = os.getenv("GITHUB_REPOSITORY")
            run_id_env = os.getenv("GITHUB_RUN_ID")
            if server and repo and run_id_env:
                github_run_url = f"{server}/{repo}/actions/runs/{run_id_env}"
        save_run_snapshot(summary, all_scored, source=source, github_run_url=github_run_url)
    except Exception as exc:
        logger.error("Failed to save run snapshot: %s", exc)
        summary.errors.append(f"Snapshot save failed: {exc}")

    summary.log()
    _notify(progress_callback, {"stage": "done"})
    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Job Search Pipeline — scrape, score, optimize, and digest",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Path to your profile/config.yaml (default: candidate_profile/config.yaml). "
             "Run setup_profile.py first if you haven't created one yet.",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Override the primary resume DOCX for this run only "
             "(default: profile.resume_path from your profile)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score jobs without writing DOCX files or sending email; saves digest preview to outputs/",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Bypass the cross-run tracker and re-score every prefiltered job, "
             "even ones already scored in a recent run.",
    )
    args = parser.parse_args()

    from candidate_profile.loader import load_profile
    try:
        profile = load_profile(args.profile)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    summary = run(profile=profile, resume_path=args.resume, dry_run=args.dry_run, no_dedup=args.no_dedup)

    # Treat the run as successful if the digest was sent (or it was a dry run),
    # even if some per-job optimizations hit transient rate limits. Only a real
    # failure (digest never sent) should trigger the failure notification.
    succeeded = args.dry_run or summary.email_sent
    if succeeded:
        if summary.errors:
            logger.warning("Run completed with %d soft error(s) — digest still sent.",
                           len(summary.errors))
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
