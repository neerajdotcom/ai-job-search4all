"""
storage/tracker_store.py — persistent cross-run application tracker.

Sibling to run_store.py and built on the same "git is the database" idea: a
single git-committed JSON file (data/tracker.json) that remembers every job
posting the pipeline has already seen/scored across runs, keyed by a cleaned
apply URL (with a title+company fallback for ATS URLs that carry volatile
query params).

Why it exists: run_store.py writes one immutable full snapshot per run, which
is great for history but useless for the per-job question "have I already
scored this exact posting on a previous day?". Without that memory, the same
Scopely/Riot/Epic postings get re-scored every run, each one burning one of
the scarce AI_SCORE_LIMIT Groq slots on a job already judged. This module is
the cross-run dedup gate that stops that waste, and doubles as a lightweight
application-status tracker (new → scored → qualifying → applied →
rejected/closed) the dashboard can update by hand.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

TRACKER_PATH = Path(__file__).parent.parent / "data" / "tracker.json"

# Re-score a long-lived posting after this many days even if we've seen it
# before — a JD can change, and a role still open two weeks later is worth a
# fresh look. Until then, a previously-scored posting is skipped to save quota.
RESCORE_TTL_DAYS = 14

# Canonical status flow (mirrors career-ops's tracker states, trimmed to what
# this pipeline can set automatically plus what the dashboard sets by hand).
# These are set automatically by the pipeline as a job clears each stage.
AUTO_STATUSES = {"new", "scored", "qualifying", "optimized"}

# Ordered manual progression — used to reject backward moves (e.g. "offer"
# can't be set back to "applied"). Terminal states (rejected/withdrawn/
# archived) and the older short-form aliases (kept valid so pre-existing
# tracker entries from before this vocabulary don't become "invalid") are
# exempt from ordinal enforcement.
MANUAL_PROGRESSION = ["applied", "interview_scheduled", "interview_complete", "offer"]
TERMINAL_MANUAL_STATUSES = {"rejected", "withdrawn", "archived"}
_LEGACY_MANUAL_STATUSES = {"responded", "interview", "closed"}
MANUAL_STATUSES = set(MANUAL_PROGRESSION) | TERMINAL_MANUAL_STATUSES | _LEGACY_MANUAL_STATUSES
VALID_STATUSES = AUTO_STATUSES | MANUAL_STATUSES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def entry_key(job: dict) -> str:
    """Stable identity for a posting across runs. Reuses the scraper's own URL
    cleaner and dedup-normalizer so this matches the within-run dedup logic
    exactly (no second, divergent notion of 'same job')."""
    from scraper.job_scraper import _clean_url, _normalize_for_dedup

    url_key = _clean_url(job.get("apply_url", "") or "")
    if url_key:
        return url_key
    tc = (_normalize_for_dedup(job.get("title", "")) + "|" +
          _normalize_for_dedup(job.get("company", "")))
    return tc if tc != "|" else ""


def load_tracker() -> dict:
    """Return the tracker dict {url_key: entry}. Missing/corrupt file → {}."""
    if not TRACKER_PATH.exists():
        return {}
    try:
        with open(TRACKER_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read tracker %s: %s — starting fresh", TRACKER_PATH, exc)
        return {}
    # Tolerate either a flat map or a wrapped {"entries": {...}} shape.
    if isinstance(data, dict) and "entries" in data and isinstance(data["entries"], dict):
        return data["entries"]
    return data if isinstance(data, dict) else {}


def save_tracker(tracker: dict) -> Path:
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False, sort_keys=True)
    return TRACKER_PATH


def _is_recent(iso_str: str, ttl_days: int) -> bool:
    if not iso_str:
        return False
    try:
        when = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (_now() - when).days < ttl_days


def filter_unscored(jobs: list[dict], tracker: dict | None = None,
                    rescore_after_days: int = RESCORE_TTL_DAYS) -> list[dict]:
    """Drop jobs already scored within the last `rescore_after_days` so they
    don't re-spend a Groq scoring slot. A posting we've never seen, or one
    last scored longer ago than the TTL, is kept for (re)scoring."""
    if tracker is None:
        tracker = load_tracker()

    kept: list[dict] = []
    skipped = 0
    for job in jobs:
        key = entry_key(job)
        entry = tracker.get(key) if key else None
        if entry and _is_recent(entry.get("last_scored", ""), rescore_after_days):
            skipped += 1
            continue
        kept.append(job)

    if skipped:
        logger.info(
            "Cross-run dedup: skipped %d job(s) already scored within %d days, "
            "%d remain for scoring", skipped, rescore_after_days, len(kept),
        )
    return kept


# Substring marking a fallback result from a daily-quota-exhausted short
# circuit (see match_scorer._fallback / resume_optimizer's equivalent) — a
# job that hit this never actually got evaluated, so it must not be recorded
# as "scored" or it'll be wrongly skipped by filter_unscored for the full TTL.
_QUOTA_EXHAUSTED_MARKER = "quota exhausted"


def _is_quota_exhausted_fallback(job: dict) -> bool:
    return _QUOTA_EXHAUSTED_MARKER in (job.get("recommendation") or "").lower()


def mark_seen(jobs: list[dict], tracker: dict | None = None) -> dict:
    """Record/refresh tracker entries for every scored job, then persist.
    Never downgrades a user-set status (applied/rejected/etc.) back to an
    automatic one — only the auto statuses are advanced here.

    Jobs whose score came from a daily-quota-exhausted fallback (never
    actually evaluated) only get first_seen/last_seen refreshed — last_scored
    and status are left untouched so they're still picked up by
    filter_unscored on the next run instead of being skipped for the TTL."""
    if tracker is None:
        tracker = load_tracker()

    now_iso = _now().isoformat()
    for job in jobs:
        key = entry_key(job)
        if not key:
            continue
        entry = tracker.get(key, {})
        entry.setdefault("first_seen", now_iso)
        entry.setdefault("resume_version", "")
        entry.setdefault("recruiter_name", "")
        entry.setdefault("notes", "")
        entry.setdefault("follow_up_date", "")
        entry.setdefault("status_history", [])
        entry["last_seen"] = now_iso
        entry["title"] = job.get("title", entry.get("title", ""))
        entry["company"] = job.get("company", entry.get("company", ""))
        entry["apply_url"] = job.get("apply_url", entry.get("apply_url", ""))
        entry["source"] = job.get("source", entry.get("source", ""))
        entry["run_count"] = int(entry.get("run_count", 0)) + 1

        if _is_quota_exhausted_fallback(job):
            tracker[key] = entry
            continue

        entry["last_scored"] = now_iso
        entry["last_score"] = job.get("match_score", entry.get("last_score"))
        entry["industry_fit"] = job.get("industry_fit", entry.get("industry_fit", ""))
        entry["seniority_fit"] = job.get("seniority_fit", entry.get("seniority_fit", ""))
        entry["missing_keywords"] = job.get("missing_keywords", entry.get("missing_keywords", []))
        entry["ghost_flagged"] = bool(job.get("ghost_flagged", False))
        entry["ghost_reason"] = job.get("ghost_reason", "") if job.get("ghost_flagged") else ""
        entry["off_target_skipped"] = bool(job.get("off_target_skipped", False))
        if job.get("chosen_archetype"):
            entry["chosen_archetype"] = job["chosen_archetype"]
        else:
            entry.setdefault("chosen_archetype", "")

        resume_path = job.get("ats_output") or job.get("review_output")
        if resume_path:
            entry["resume_version"] = Path(resume_path).name

        current = entry.get("status")
        if current not in MANUAL_STATUSES:
            if job.get("ats_output"):
                new_status = "optimized"
            elif job.get("qualifying"):
                new_status = "qualifying"
            else:
                new_status = "scored"
            if new_status != current:
                entry["status_history"].append({"status": new_status, "at": now_iso})
            entry["status"] = new_status
        tracker[key] = entry

    save_tracker(tracker)
    return tracker


def set_status(key: str, status: str) -> bool:
    """Set a posting's tracker status from the dashboard. Returns False for an
    unknown status, a key not present in the tracker, or a backward move
    within the manual applied→...→offer progression (e.g. offer → applied)."""
    status = (status or "").strip().lower()
    if status not in VALID_STATUSES:
        return False
    tracker = load_tracker()
    entry = tracker.get(key)
    if entry is None:
        return False

    current = entry.get("status")
    if status in MANUAL_PROGRESSION and current in MANUAL_PROGRESSION:
        if MANUAL_PROGRESSION.index(status) < MANUAL_PROGRESSION.index(current):
            return False

    now_iso = _now().isoformat()
    entry["status"] = status
    entry["status_updated_at"] = now_iso
    entry.setdefault("status_history", []).append({"status": status, "at": now_iso})
    tracker[key] = entry
    save_tracker(tracker)
    return True


def set_fields(key: str, **fields) -> bool:
    """Update manual bookkeeping fields (recruiter_name/notes/follow_up_date)
    on an existing entry. Returns False if the key isn't in the tracker.
    Unknown field names are ignored — callers pass only the fixed set the
    dashboard form exposes."""
    allowed = {"recruiter_name", "notes", "follow_up_date"}
    tracker = load_tracker()
    entry = tracker.get(key)
    if entry is None:
        return False
    for name, value in fields.items():
        if name in allowed:
            entry[name] = value
    tracker[key] = entry
    save_tracker(tracker)
    return True


CSV_COLUMNS = [
    "date_discovered", "last_seen", "company", "role_title", "match_score",
    "resume_version", "application_status", "apply_url", "source",
    "missing_keywords", "industry_fit", "seniority_fit", "follow_up_date",
    "recruiter_name", "notes",
]


def export_csv(path: Path | None = None) -> Path:
    """Flatten the JSON tracker into a spreadsheet-friendly CSV. This is a
    derived view, not a second source of truth — data/tracker.json stays
    canonical and git-committed; the CSV is regenerated each run and
    gitignored (see .gitignore)."""
    import csv

    if path is None:
        path = TRACKER_PATH.parent / "tracker_export.csv"
    tracker = load_tracker()

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for entry in tracker.values():
            writer.writerow({
                "date_discovered": entry.get("first_seen", ""),
                "last_seen": entry.get("last_seen", ""),
                "company": entry.get("company", ""),
                "role_title": entry.get("title", ""),
                "match_score": entry.get("last_score", ""),
                "resume_version": entry.get("resume_version", ""),
                "application_status": entry.get("status", ""),
                "apply_url": entry.get("apply_url", ""),
                "source": entry.get("source", ""),
                "missing_keywords": "; ".join(entry.get("missing_keywords") or []),
                "industry_fit": entry.get("industry_fit", ""),
                "seniority_fit": entry.get("seniority_fit", ""),
                "follow_up_date": entry.get("follow_up_date", ""),
                "recruiter_name": entry.get("recruiter_name", ""),
                "notes": entry.get("notes", ""),
            })
    return path


# Kanban column order — the application pipeline only, not the pre-application
# auto stages (new/scored aren't yet "in the pipeline" from the applicant's
# point of view). Closed-out entries (terminal + legacy aliases) are bucketed
# separately rather than given their own columns, since "rejected" /
# "withdrawn" / "archived" aren't a sequence.
KANBAN_COLUMNS = [
    ("qualifying", "Qualifying"),
    ("optimized", "Resume Ready"),
    ("applied", "Applied"),
    ("interview_scheduled", "Interview Scheduled"),
    ("interview_complete", "Interview Complete"),
    ("offer", "Offer"),
]
_CLOSED_STATUSES = TERMINAL_MANUAL_STATUSES | _LEGACY_MANUAL_STATUSES


def kanban_board(tracker: dict | None = None) -> dict:
    """Group tracker entries into ordered pipeline columns for /kanban.
    Returns {"columns": [{"status", "label", "entries": [...]}], "closed": [...]}.
    Entries still at "new"/"scored" (not yet qualifying) are excluded — they
    aren't part of an application pipeline yet."""
    if tracker is None:
        tracker = load_tracker()

    by_status: dict[str, list[dict]] = {status: [] for status, _ in KANBAN_COLUMNS}
    closed: list[dict] = []
    for key, entry in tracker.items():
        status = entry.get("status")
        card = {**entry, "key": key}
        if status in by_status:
            by_status[status].append(card)
        elif status in _CLOSED_STATUSES:
            closed.append(card)

    columns = [
        {"status": status, "label": label, "entries": by_status[status]}
        for status, label in KANBAN_COLUMNS
    ]
    return {"columns": columns, "closed": closed}


def get_status(job: dict, tracker: dict | None = None) -> str | None:
    """Look up the stored status for a job (used to surface it in the UI)."""
    if tracker is None:
        tracker = load_tracker()
    key = entry_key(job)
    entry = tracker.get(key) if key else None
    return entry.get("status") if entry else None
