"""
storage/run_store.py — git-committed JSON "database" for pipeline run history.

Each pipeline run (CLI, GitHub Actions, or dashboard-triggered) is persisted as
one JSON file under data/runs/<run_id>.json. Git is the only persistence layer
here — no SQLite, no server-side DB — so the same history is visible whether a
run happened in an ephemeral CI container or on a local machine, at zero
hosting cost.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent.parent / "data" / "runs"

# Fields stripped from each job dict before writing — large JD text has no
# dashboard value and would bloat git history on every run.
_STRIP_FIELDS = ("jd_text", "_full_text")

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def run_id_for(started_at: datetime) -> str:
    return started_at.strftime("%Y%m%dT%H%M%SZ")


def _safe_run_id(run_id: str) -> str | None:
    """Reject anything that isn't a plain filename component (defends against
    path traversal since run_id arrives from a URL path parameter)."""
    if not run_id or not _RUN_ID_RE.match(run_id):
        return None
    return run_id


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _strip_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in _STRIP_FIELDS}


def save_run_snapshot(summary, jobs: list[dict], source: str,
                       github_run_url: str | None = None) -> Path:
    """
    Serialize a RunSummary + every scored job (qualifying or not) to
    data/runs/<run_id>.json. run_id is derived from summary.started_at.
    """
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    run_id = run_id_for(summary.started_at)
    path = RUNS_DIR / f"{run_id}.json"
    suffix = 2
    while path.exists():
        path = RUNS_DIR / f"{run_id}-{suffix}.json"
        suffix += 1

    payload = {
        "run_id": path.stem,
        "started_at": summary.started_at,
        "finished_at": datetime.now(timezone.utc),
        "dry_run": summary.dry_run,
        "email_sent": summary.email_sent,
        "total_scraped": summary.total_scraped,
        "total_scored": summary.total_scored,
        "total_qualifying": summary.total_qualifying,
        "ghost_flagged_count": getattr(summary, "ghost_flagged_count", 0),
        "off_target_skipped_count": getattr(summary, "off_target_skipped_count", 0),
        "errors": list(summary.errors),
        "skill_gaps": list(getattr(summary, "skill_gaps", [])),
        "training_recs": list(getattr(summary, "training_recs", [])),
        "source": source,
        "github_run_url": github_run_url,
        "jobs": [_strip_job(job) for job in jobs],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default, ensure_ascii=False)

    logger.info("Saved run snapshot → %s", path)
    return path


def list_runs() -> list[dict]:
    """Return summary-only dicts (no jobs[]) for every run on disk, newest first."""
    if not RUNS_DIR.exists():
        return []

    runs = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable run snapshot %s: %s", path, exc)
            continue

        runs.append({
            "run_id": data.get("run_id", path.stem),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
            "dry_run": data.get("dry_run", False),
            "email_sent": data.get("email_sent", False),
            "total_scraped": data.get("total_scraped", 0),
            "total_scored": data.get("total_scored", 0),
            "total_qualifying": data.get("total_qualifying", 0),
            "ghost_flagged_count": data.get("ghost_flagged_count", 0),
            "off_target_skipped_count": data.get("off_target_skipped_count", 0),
            "source": data.get("source", "unknown"),
            "github_run_url": data.get("github_run_url"),
            "error_count": len(data.get("errors", [])),
        })
    return runs


def load_run(run_id: str) -> dict | None:
    """Load and return the full parsed JSON (including jobs[]) for one run_id."""
    safe_id = _safe_run_id(run_id)
    if safe_id is None:
        return None

    path = RUNS_DIR / f"{safe_id}.json"
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load run snapshot %s: %s", path, exc)
        return None


def compute_stats() -> dict:
    """Aggregate across all run snapshots for the dashboard's charts."""
    runs = list_runs()

    buckets = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    source_breakdown: dict[str, int] = {}
    company_qualifying: dict[str, int] = {}
    runs_over_time = []

    for summary in sorted(runs, key=lambda r: r["run_id"]):
        runs_over_time.append({
            "run_id": summary["run_id"],
            "started_at": summary["started_at"],
            "total_scored": summary["total_scored"],
            "total_qualifying": summary["total_qualifying"],
        })
        source_breakdown[summary["source"]] = source_breakdown.get(summary["source"], 0) + 1

        full = load_run(summary["run_id"])
        if not full:
            continue
        for job in full.get("jobs", []):
            score = job.get("match_score") or 0
            if score < 60:
                buckets["0-59"] += 1
            elif score < 70:
                buckets["60-69"] += 1
            elif score < 80:
                buckets["70-79"] += 1
            elif score < 90:
                buckets["80-89"] += 1
            else:
                buckets["90-100"] += 1

            if job.get("qualifying"):
                company = job.get("company", "Unknown")
                company_qualifying[company] = company_qualifying.get(company, 0) + 1

    top_companies = sorted(
        ({"company": c, "count": n} for c, n in company_qualifying.items()),
        key=lambda x: x["count"], reverse=True,
    )[:10]

    return {
        "total_runs": len(runs),
        "total_jobs_scraped": sum(r["total_scraped"] for r in runs),
        "total_jobs_qualifying": sum(r["total_qualifying"] for r in runs),
        "runs_over_time": runs_over_time,
        "score_distribution": buckets,
        "source_breakdown": source_breakdown,
        "top_companies": top_companies,
    }
