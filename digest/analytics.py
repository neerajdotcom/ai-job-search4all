"""
digest/analytics.py — pure aggregation over the cross-run tracker.

Reads only storage/tracker_store.load_tracker() — no new API calls, no LLM,
no new persisted state. Consumed by digest/weekly_report.py; deliberately not
its own digest section, to avoid a fourth place readers have to check for the
same numbers that already live in the tracker.

Ghost-flagged entries (storage.tracker_store, set when scorer.match_scorer.
is_ghost_job flags a posting) and off-target-skipped entries (set when
main.py skips Groq scoring for an ATS-sourced job that's neither a target
PM/Delivery/Producer role nor a QA role) are excluded everywhere here —
their last_score is a placeholder 0, never a real evaluation, and would
skew every average/conversion rate below if counted.
"""

from storage import tracker_store

# Mirrors storage.tracker_store.MANUAL_PROGRESSION plus the pre-existing
# legacy aliases — "reached Applied or beyond" for conversion-rate purposes.
_APPLIED_OR_BEYOND = {
    "applied", "interview_scheduled", "interview_complete", "offer",
    "responded", "interview",
}
_INTERVIEWED_OR_BEYOND = {"interview_scheduled", "interview_complete", "offer", "interview"}

_SCORE_BANDS = [(0, 59), (60, 69), (70, 79), (80, 89), (90, 100)]


def _entries(tracker: dict | None = None) -> list[dict]:
    tracker = tracker_store.load_tracker() if tracker is None else tracker
    return [e for e in tracker.values() if not e.get("ghost_flagged") and not e.get("off_target_skipped")]


def resume_performance(tracker: dict | None = None) -> list[dict]:
    """Per framing archetype (delivery-process / live-ops-production /
    technical-program — see resume_optimizer.ARCHETYPES): how many postings
    were optimized with it, how many reached Applied or Interview, and the
    resulting interview rate. Entries optimized before chosen_archetype was
    tracked fall back to 'unknown' rather than being dropped."""
    groups: dict[str, dict] = {}
    for entry in _entries(tracker):
        if not entry.get("resume_version"):
            continue
        archetype = entry.get("chosen_archetype") or "unknown"
        g = groups.setdefault(archetype, {
            "archetype": archetype, "optimized": 0, "applied": 0, "interviewed": 0,
        })
        g["optimized"] += 1
        status = entry.get("status", "")
        if status in _APPLIED_OR_BEYOND:
            g["applied"] += 1
        if status in _INTERVIEWED_OR_BEYOND:
            g["interviewed"] += 1

    out = []
    for g in groups.values():
        g["interview_rate"] = round(100 * g["interviewed"] / g["applied"], 1) if g["applied"] else 0.0
        out.append(g)
    out.sort(key=lambda x: x["optimized"], reverse=True)
    return out


def score_band_conversion(tracker: dict | None = None) -> list[dict]:
    """Buckets entries by last_score range, reporting what fraction in each
    band reached Applied or beyond — answers "is a 90+ score actually worth
    more than a 65?"."""
    entries = _entries(tracker)
    out = []
    for lo, hi in _SCORE_BANDS:
        total = 0
        applied = 0
        for entry in entries:
            score = entry.get("last_score")
            if score is None or not (lo <= score <= hi):
                continue
            total += 1
            if entry.get("status", "") in _APPLIED_OR_BEYOND:
                applied += 1
        rate = round(100 * applied / total, 1) if total else 0.0
        out.append({"band": f"{lo}-{hi}", "total": total, "applied": applied, "applied_rate": rate})
    return out


def top_missing_keywords(statuses=("rejected",), top_n: int = 10, tracker: dict | None = None) -> list[dict]:
    """Frequency-ranks missing_keywords across entries in the given status set
    — default 'rejected', to surface which gaps are actually costing offers
    rather than just appearing often across all postings (see
    digest.presentation.compute_skill_gaps for the latter, per-run version)."""
    wanted = {s.lower() for s in statuses}
    counts: dict[str, int] = {}
    for entry in _entries(tracker):
        if entry.get("status", "") not in wanted:
            continue
        for kw in entry.get("missing_keywords") or []:
            key = (kw or "").strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"skill": skill, "count": count} for skill, count in ranked]


def application_summary(tracker: dict | None = None) -> dict:
    """Total applications sent and interviews reached across the whole
    tracker, plus the resulting interview rate — the headline numbers for
    the weekly report."""
    applied = 0
    interviewed = 0
    for entry in _entries(tracker):
        status = entry.get("status", "")
        if status in _APPLIED_OR_BEYOND:
            applied += 1
        if status in _INTERVIEWED_OR_BEYOND:
            interviewed += 1
    interview_rate = round(100 * interviewed / applied, 1) if applied else 0.0
    return {"applied": applied, "interviewed": interviewed, "interview_rate": interview_rate}


def company_intelligence(top_n: int = 10, tracker: dict | None = None) -> list[dict]:
    """Per-company average match score, applications sent, interviews, the
    resulting interview rate, and the most recent application date — ranked
    by interview rate (ties broken by application volume) to surface the
    most-responsive companies first."""
    groups: dict[str, dict] = {}
    for entry in _entries(tracker):
        company = entry.get("company") or "Unknown"
        g = groups.setdefault(company, {
            "company": company, "scores": [], "applied": 0, "interviewed": 0, "last_applied": "",
        })
        score = entry.get("last_score")
        if score is not None:
            g["scores"].append(score)
        status = entry.get("status", "")
        if status in _APPLIED_OR_BEYOND:
            g["applied"] += 1
            updated = entry.get("status_updated_at", "") or ""
            if updated > g["last_applied"]:
                g["last_applied"] = updated
        if status in _INTERVIEWED_OR_BEYOND:
            g["interviewed"] += 1

    out = []
    for g in groups.values():
        avg_score = round(sum(g["scores"]) / len(g["scores"]), 1) if g["scores"] else 0.0
        interview_rate = round(100 * g["interviewed"] / g["applied"], 1) if g["applied"] else 0.0
        out.append({
            "company": g["company"],
            "avg_score": avg_score,
            "applied": g["applied"],
            "interviewed": g["interviewed"],
            "interview_rate": interview_rate,
            "last_applied": g["last_applied"],
        })
    out.sort(key=lambda x: (x["interview_rate"], x["applied"]), reverse=True)
    return out[:top_n]
