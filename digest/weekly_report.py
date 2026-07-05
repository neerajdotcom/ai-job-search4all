"""
digest/weekly_report.py — Friday-only markdown career report.

No LLM call: every figure here is a deterministic aggregation already
available from storage.run_store, storage.tracker_store, and digest.analytics
— consistent with the project's existing zero-cost-aggregation pattern for
skill gaps (digest.presentation.compute_skill_gaps). Written to
data/weekly_report_<date>.md (git-committed, like data/runs/ and
data/tracker.json) and surfaced in the Friday digest email.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from digest import analytics
from storage import run_store, tracker_store

REPORTS_DIR = Path(__file__).parent.parent / "data"


def is_report_day(today: datetime | None = None) -> bool:
    """True if `today` (any tz, defaults to now in UTC) falls on a Friday in
    IST — matches the existing 9:30 AM IST / 04:00 UTC weekday run schedule."""
    today = today or datetime.now(timezone.utc)
    ist = today.astimezone(timezone.utc) + timedelta(hours=5, minutes=30)
    return ist.weekday() == 4  # Monday=0 ... Friday=4


def _within_last_days(iso_str: str, now: datetime, days: int) -> bool:
    if not iso_str:
        return False
    try:
        when = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).days < days


def _runs_in_last_days(now: datetime, days: int = 7) -> list[dict]:
    out = []
    for r in run_store.list_runs():
        if _within_last_days(r.get("started_at", ""), now, days):
            out.append(r)
    return out


def build_weekly_report(today: datetime | None = None) -> tuple[str, Path]:
    """Aggregate this week's runs + the full cross-run tracker into a
    markdown report, write it to data/weekly_report_<date>.md, and return
    (markdown_text, path)."""
    now = today or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    runs = _runs_in_last_days(now, days=7)
    tracker = tracker_store.load_tracker()
    live_entries = [e for e in tracker.values() if not e.get("ghost_flagged")]

    total_scraped = sum(r.get("total_scraped", 0) for r in runs)
    total_qualifying = sum(r.get("total_qualifying", 0) for r in runs)

    discovered_this_week_by_source: dict[str, int] = {}
    for entry in live_entries:
        if not _within_last_days(entry.get("first_seen", ""), now, days=7):
            continue
        src = entry.get("source") or "unknown"
        discovered_this_week_by_source[src] = discovered_this_week_by_source.get(src, 0) + 1

    app_summary = analytics.application_summary(tracker)
    resume_perf = analytics.resume_performance(tracker)
    companies = analytics.company_intelligence(top_n=10, tracker=tracker)
    missing = analytics.top_missing_keywords(statuses=("rejected",), tracker=tracker)

    lines = [f"# Weekly Career Report — {date_str}", ""]

    lines += ["## This week", f"- Runs: {len(runs)}",
              f"- Jobs discovered: {total_scraped}",
              f"- Jobs qualified: {total_qualifying}", ""]

    lines += ["## Jobs discovered this week, by source"]
    if discovered_this_week_by_source:
        for src, count in sorted(discovered_this_week_by_source.items(), key=lambda x: -x[1]):
            lines.append(f"- {src}: {count}")
    else:
        lines.append("- (no new postings recorded this week)")
    lines.append("")

    lines += ["## Applications (all-time)",
              f"- Applications sent: {app_summary['applied']}",
              f"- Interviews: {app_summary['interviewed']}",
              f"- Interview rate: {app_summary['interview_rate']}%", ""]

    lines += ["## Resume performance by framing"]
    if resume_perf:
        for g in resume_perf:
            lines.append(
                f"- {g['archetype']}: {g['optimized']} optimized, "
                f"{g['applied']} applied, {g['interviewed']} interviewed "
                f"({g['interview_rate']}% interview rate)"
            )
    else:
        lines.append("- (no optimized resumes recorded yet)")
    lines.append("")

    lines += ["## Most responsive companies"]
    if companies:
        for c in companies:
            lines.append(
                f"- {c['company']}: avg score {c['avg_score']}%, "
                f"{c['applied']} applied, {c['interviewed']} interviewed "
                f"({c['interview_rate']}% interview rate)"
            )
    else:
        lines.append("- (no applications recorded yet)")
    lines.append("")

    lines += ["## Top missing keywords in rejections"]
    if missing:
        for m in missing:
            lines.append(f"- {m['skill']} (×{m['count']})")
    else:
        lines.append("- (no rejections recorded yet)")
    lines.append("")

    lines += ["## Recommended actions"]
    actions = []
    if missing:
        actions.append(
            f"Close the recurring gap on **{missing[0]['skill']}** — it's the most "
            "common missing keyword across rejected applications."
        )
    no_response = [c for c in companies if c.get("applied") and not c.get("interviewed")]
    if no_response:
        names = ", ".join(c["company"] for c in no_response[:3])
        actions.append(f"Follow up on applications with no response yet: {names}.")
    if not actions:
        actions.append("No specific action flagged this week — keep applying and re-run "
                        "once more application data accumulates.")
    lines.extend(f"- {a}" for a in actions)

    markdown = "\n".join(lines) + "\n"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"weekly_report_{date_str}.md"
    path.write_text(markdown, encoding="utf-8")
    return markdown, path
