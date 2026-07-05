import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from digest.presentation import (
    score_color as _score_color,
    score_bg as _score_bg,
    seniority_badge_colors,
    industry_badge_colors,
    industry_label,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
# Each resume is ~13KB, so attaching all of them (capped by main.py's
# AI_OPTIMIZE_LIMIT=15 anyway) is well under any email size limit — there's no
# reason to silently drop tailored resumes the optimizer already spent quota
# generating.
TOP_ATTACH_COUNT = 15


# ---------------------------------------------------------------------------
# HTML building
# ---------------------------------------------------------------------------

def _missing_keywords_cell(keywords: list) -> str:
    if not keywords:
        return '<span style="color:#6b7280;">—</span>'
    pills = "".join(
        f'<span style="display:inline-block;background:#e5e7eb;border-radius:4px;'
        f'padding:1px 6px;margin:1px;font-size:12px;">{kw}</span>'
        for kw in keywords[:5]
    )
    return pills


def _seniority_badge(fit: str) -> str:
    fg, bg = seniority_badge_colors(fit)
    return (
        f'<span style="background:{bg};color:{fg};border-radius:4px;'
        f'padding:2px 8px;font-size:12px;font-weight:600;">{fit.upper()}</span>'
    )


def _industry_badge(fit: str, industry_bands: list[dict] | None = None) -> str:
    fg, bg = industry_badge_colors(fit, industry_bands)
    label = (industry_label(fit, industry_bands) or fit).upper()
    return (
        f'<span style="background:{bg};color:{fg};border-radius:4px;'
        f'padding:2px 8px;font-size:12px;font-weight:600;">{label}</span>'
    )


def _skill_gap_section(skill_gaps: list) -> str:
    if not skill_gaps:
        return ""
    pills = "".join(
        f'<span style="display:inline-block;background:#fef3c7;color:#92400e;'
        f'border-radius:4px;padding:3px 10px;margin:3px;font-size:13px;font-weight:600;">'
        f'{g["skill"]} <span style="opacity:0.65;">&times;{g["count"]}</span></span>'
        for g in skill_gaps
    )
    return f"""
    <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
      Skill Gaps This Run
    </h2>
    <p style="color:#6b7280;font-size:13px;margin:0 0 12px;">
      Keywords most often missing across this run's scored jobs — recurring gaps
      here are worth closing before your next batch of applications.
    </p>
    <div>{pills}</div>
    """


def _training_section(training_recs: list) -> str:
    if not training_recs:
        return ""
    items = "".join(
        f"""
        <div style="margin-bottom:10px;padding:12px 16px;background:#f0f9ff;
                    border-left:4px solid #0284c7;border-radius:4px;">
          <span style="font-weight:600;color:#0c4a6e;">{r.get("recommendation","")}</span>
          {f'<span style="color:#6b7280;font-size:12px;margin-left:8px;">closes: {r.get("skill","")}</span>' if r.get("skill") else ""}
          {f'<p style="margin:6px 0 0;color:#374151;font-size:13px;">{r.get("why","")}</p>' if r.get("why") else ""}
        </div>"""
        for r in training_recs
    )
    return f"""
    <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
      Recommended Training
    </h2>
    <p style="color:#6b7280;font-size:13px;margin:0 0 12px;">
      Courses / certifications that would close the most-recurring skill gaps above.
    </p>
    {items}
    """


def _weekly_report_section(weekly_report_md: str | None) -> str:
    """Render the markdown weekly report (digest.weekly_report.build_weekly_report
    — Friday-only, no LLM call) as a simple HTML block. Markdown is converted
    with a minimal hand-rolled pass (## headings, - bullets) rather than a
    dependency, since the report's own structure is fixed and small."""
    if not weekly_report_md:
        return ""

    html_lines = []
    in_list = False
    for line in weekly_report_md.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<h3 style="font-size:14px;font-weight:700;color:#111827;margin:16px 0 6px;">'
                f'{stripped[3:]}</h3>'
            )
        elif stripped.startswith("# "):
            continue  # top-level title — the section heading below covers it
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append('<ul style="margin:0 0 4px;padding-left:20px;color:#374151;font-size:13px;">')
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<p style="margin:4px 0;color:#374151;font-size:13px;">{stripped}</p>')
    if in_list:
        html_lines.append("</ul>")

    return f"""
    <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
      📊 Weekly Career Report
    </h2>
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px 16px;">
      {"".join(html_lines)}
    </div>
    """


def _build_table(jobs: list[dict], industry_bands: list[dict] | None = None, show_resume_col: bool = True) -> str:
    # Which jobs actually get a resume attached to this email (top N by score
    # that have a generated resume) vs. generated-but-not-attached vs. none —
    # so the table can tell you where to find each one instead of leaving
    # you to guess from the Fast-Apply Packs section below.
    attached_keys = set()
    if show_resume_col:
        with_resume = [j for j in jobs if j.get("ats_output")]
        attached_keys = {
            (j.get("title"), j.get("company"))
            for j in sorted(with_resume, key=lambda j: j.get("match_score", 0), reverse=True)[:TOP_ATTACH_COUNT]
        }

    resume_th = (
        '<th style="padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb;'
        'color:#374151;">Resume</th>'
    ) if show_resume_col else ""

    rows = []
    for job in jobs:
        score = job.get("match_score", 0)
        fg = _score_color(score)
        bg = _score_bg(score)
        missing = job.get("missing_keywords", [])
        apply_url = job.get("apply_url", "#")
        source = job.get("source", "").capitalize()

        resume_td = ""
        if show_resume_col:
            key = (job.get("title"), job.get("company"))
            if key in attached_keys:
                resume_badge = ('<span style="color:#065f46;font-size:12px;font-weight:600;">'
                                 '📎 Attached</span>')
            elif job.get("ats_output"):
                resume_badge = ('<span style="color:#92400e;font-size:12px;font-weight:600;">'
                                 '📄 See Fast-Apply Pack ↓</span>')
            else:
                resume_badge = '<span style="color:#9ca3af;font-size:12px;">— Base resume only</span>'
            resume_td = (
                '<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">'
                f'{resume_badge}</td>'
            )

        closed_note = (
            '<div style="font-size:11px;color:#b45309;font-weight:600;margin-top:2px;">'
            '⚠ Link may be closed — verify before applying</div>'
        ) if job.get("live") is False else ""

        # Target-company highlight: a job whose company is on the curated list
        # gets a soft amber row tint + a ⭐ marker. Visual only — no effect on
        # score, qualification, or ordering (see scraper._is_target_company).
        is_target = bool(job.get("target_company"))
        tr_style = ' style="background:#fffbeb;"' if is_target else ""
        star = '⭐ ' if is_target else ""
        target_tag = (
            '<div style="font-size:11px;color:#b45309;font-weight:600;margin-top:2px;">'
            '⭐ On your target-company list</div>'
        ) if is_target else ""

        rows.append(f"""
        <tr{tr_style}>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">
            <div style="font-weight:600;color:#111827;">{star}{job.get("company","")}</div>
            <div style="font-size:12px;color:#6b7280;">{job.get("location","")}</div>
            {target_tag}
            {closed_note}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#374151;">
            {job.get("title","")}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
            <span style="background:{bg};color:{fg};font-weight:700;border-radius:6px;
                         padding:4px 10px;font-size:14px;">{score}%</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
            {_seniority_badge(job.get("seniority_fit","—"))}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
            {_industry_badge(job.get("industry_fit","—"), industry_bands)}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">
            {_missing_keywords_cell(missing)}
          </td>
          {resume_td}
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
            <a href="{apply_url}"
               style="background:#2563eb;color:#fff;text-decoration:none;
                      border-radius:5px;padding:5px 12px;font-size:13px;font-weight:600;">
              Apply →
            </a>
            <div style="font-size:11px;color:#9ca3af;margin-top:3px;">{source}</div>
          </td>
        </tr>""")

    return f"""
    <table style="width:100%;border-collapse:collapse;font-family:system-ui,sans-serif;font-size:14px;">
      <thead>
        <tr style="background:#f9fafb;">
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #e5e7eb;color:#374151;">Company</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #e5e7eb;color:#374151;">Role</th>
          <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb;color:#374151;">Score</th>
          <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb;color:#374151;">Seniority</th>
          <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb;color:#374151;">Industry</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #e5e7eb;color:#374151;">Missing Keywords</th>
          {resume_th}
          <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb;color:#374151;">Apply</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def _build_section(jobs: list[dict], heading: str, industry_bands: list[dict] | None = None,
                    subheading: str | None = None, show_resume_col: bool = True) -> str:
    if not jobs:
        return ""
    sub_html = (
        f'<p style="color:#6b7280;font-size:13px;margin:0 0 12px;">{subheading}</p>'
        if subheading else ""
    )
    return f"""
    <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
      {heading} <span style="color:#9ca3af;font-weight:500;">({len(jobs)})</span>
    </h2>
    {sub_html}
    {_build_table(jobs, industry_bands, show_resume_col=show_resume_col)}
    """


def _build_primary_section(jobs: list[dict], industry_bands: list[dict] | None = None,
                            track_label: str | None = None) -> tuple[str, str]:
    """Build (table_html, fast_apply_html) for one primary-track job list —
    table + recommendation blurbs folded into the first, Fast-Apply Packs
    into the second. Returns ("", "") for an empty list. track_label (e.g.
    profile.secondary_track_label) adds a heading above the table and tags
    the Fast-Apply heading so a dual-resume digest reads as two distinct
    groups; omit it for a single-track day so the layout is unchanged."""
    if not jobs:
        return "", ""

    track_heading = (
        f'<h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">'
        f'{track_label} Match <span style="color:#9ca3af;font-weight:500;">({len(jobs)})</span></h2>'
    ) if track_label else ""
    table_html = track_heading + _build_table(jobs, industry_bands, show_resume_col=True)

    # Per-job recommendation blurbs
    rec_items = []
    for job in jobs:
        rec = job.get("recommendation", "")
        if rec:
            rec_items.append(f"""
            <div style="margin-bottom:12px;padding:12px 16px;background:#f9fafb;
                        border-left:4px solid #2563eb;border-radius:4px;">
              <span style="font-weight:600;color:#111827;">
                {"⭐ " if job.get("target_company") else ""}{job.get("title","")} @ {job.get("company","")}
              </span>
              <span style="color:#6b7280;font-size:12px;margin-left:8px;">
                {job.get("match_score",0)}%
              </span>
              <p style="margin:6px 0 0;color:#374151;font-size:13px;">{rec}</p>
            </div>""")

    if rec_items:
        rec_heading = f"Recommendations — {track_label}" if track_label else "Recommendations"
        table_html += f"""
        <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
          {rec_heading}
        </h2>
        {"".join(rec_items)}
        """

    # Fast-Apply Packs — cover note + screening answers per job
    pack_items = []
    for job in jobs:
        cover = job.get("cover_note")
        variants = job.get("cover_note_variants") or []
        answers = job.get("screening_answers") or []
        if not cover and not variants and not answers:
            continue

        qa_html = ""
        for qa in answers:
            q = qa.get("question", "") if isinstance(qa, dict) else ""
            a = qa.get("answer", "") if isinstance(qa, dict) else ""
            if q or a:
                qa_html += (
                    f'<div style="margin:8px 0;">'
                    f'<div style="font-weight:600;color:#374151;font-size:13px;">{q}</div>'
                    f'<div style="color:#4b5563;font-size:13px;">{a}</div>'
                    f'</div>'
                )

        cover_html = ""
        valid_variants = [v for v in variants if isinstance(v, dict) and v.get("text")]
        if valid_variants:
            cover_html = ('<div style="font-weight:600;color:#374151;font-size:13px;margin-bottom:4px;">'
                          'Cover note variants (pick one to paste)</div>')
            for v in valid_variants:
                angle = (v.get("angle", "") or "").replace("-", " ").title()
                cover_html += (
                    f'<div style="margin-bottom:8px;">'
                    f'<div style="font-size:12px;font-weight:600;color:#0c4a6e;margin-bottom:2px;">{angle}</div>'
                    f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:4px;'
                    f'padding:10px 12px;color:#374151;font-size:13px;white-space:pre-wrap;">{v.get("text","")}</div>'
                    f'</div>'
                )
            cover_html += '<div style="margin-bottom:12px;"></div>'
        elif cover:
            cover_html = (
                '<div style="font-weight:600;color:#374151;font-size:13px;margin-bottom:4px;">'
                'Cover note (ready to paste)</div>'
                f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:4px;'
                f'padding:10px 12px;color:#374151;font-size:13px;white-space:pre-wrap;'
                f'margin-bottom:12px;">{cover}</div>'
            )

        archetype = job.get("chosen_archetype")
        archetype_tag = (
            f'<span style="font-size:11px;color:#6b7280;font-weight:500;margin-left:8px;">'
            f'framing: {archetype}</span>'
        ) if archetype else ""

        apply_url = job.get("apply_url", "#")
        pack_items.append(f"""
        <div style="margin-bottom:20px;padding:16px;background:#f9fafb;
                    border:1px solid #e5e7eb;border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="font-weight:700;color:#111827;font-size:14px;">
              {"⭐ " if job.get("target_company") else ""}{job.get("title","")} @ {job.get("company","")}{archetype_tag}
            </span>
            <a href="{apply_url}"
               style="background:#2563eb;color:#fff;text-decoration:none;border-radius:5px;
                      padding:6px 14px;font-size:13px;font-weight:600;">Step 1 — Open job page →</a>
          </div>
          {cover_html}
          {('<div style="font-weight:600;color:#374151;font-size:13px;margin-bottom:2px;">'
            'Screening answers</div>' + qa_html) if qa_html else ''}
        </div>""")

    fast_apply_heading = "⚡ Fast-Apply Packs" + (f" — {track_label}" if track_label else "")
    fast_apply_html = f"""
    <h2 style="font-size:16px;font-weight:700;color:#111827;margin:32px 0 12px;">
      {fast_apply_heading}
    </h2>
    <p style="color:#6b7280;font-size:13px;margin:0 0 16px;">
      <strong>These don't auto-submit anything</strong> — that's intentional, since
      auto-applying violates job-board terms and risks your real accounts getting flagged.
      For each job below: (1) click "Open job page" to go to the real listing, (2) attach the
      tailored resume from above (it's already attached to this email), (3) paste the cover
      note and screening answers into the application form, then submit it yourself.
    </p>
    {"".join(pack_items)}
    """ if pack_items else ""

    return table_html, fast_apply_html


def _build_html(primary: list[dict], outside_target_location: list[dict], qa_roles: list[dict],
                 date_str: str, profile, skill_gaps: list | None = None,
                 training_recs: list | None = None, weekly_report: str | None = None) -> str:
    n = len(primary) + len(outside_target_location) + len(qa_roles)
    title = f"Job Digest — {date_str} — {n} match{'es' if n != 1 else ''} found"
    industry_bands = profile.industry_bands

    if n == 0:
        body_content = """
        <p style="font-size:16px;color:#374151;padding:24px 0;">
          No matches above 60% today. The pipeline ran successfully — check back next run.
        </p>
        """ + _skill_gap_section(skill_gaps) + _training_section(training_recs) + _weekly_report_section(weekly_report)
    else:
        # Primary jobs are segregated by which resume's keywords surfaced
        # them (main.py tags a job "secondary" only when profile has a
        # secondary_resume_path configured and ranked it there). On a
        # single-resume profile secondary_jobs is empty and the layout is
        # byte-identical to a single-track digest.
        primary_jobs = [j for j in primary if j.get("resume_track") != "secondary"]
        secondary_jobs = [j for j in primary if j.get("resume_track") == "secondary"]

        if secondary_jobs:
            primary_table, primary_fast_apply = _build_primary_section(
                primary_jobs, industry_bands, profile.primary_track_label)
            secondary_table, secondary_fast_apply = _build_primary_section(
                secondary_jobs, industry_bands, profile.secondary_track_label)
            primary_table = primary_table + secondary_table
            fast_apply_section = primary_fast_apply + secondary_fast_apply
        else:
            primary_table, fast_apply_section = _build_primary_section(primary, industry_bands)

        outside_location_section = _build_section(
            outside_target_location, f"Outside {profile.location}", industry_bands,
            subheading=f"Same target roles, but located outside {profile.location} — informational "
                       "only, no tailored resume generated.",
            show_resume_col=False,
        )
        qa_section = _build_section(
            qa_roles, "QA / Testing Roles", industry_bands,
            subheading="QA/testing-titled roles (any location) — informational only, "
                       "no tailored resume generated.",
            show_resume_col=False,
        )

        body_content = (
            primary_table + outside_location_section + qa_section
            + _skill_gap_section(skill_gaps) + _training_section(training_recs)
            + _weekly_report_section(weekly_report) + fast_apply_section
        )

    feedback_to = os.getenv("DIGEST_RECIPIENT", "").strip()
    feedback_subject = quote(f"Job Digest Feedback — {date_str}")
    feedback_body = quote(
        "Note any issues with today's digest (e.g. wrong location, bad match, "
        "missing tailored resume, irrelevant role) — paste this into your next "
        "Claude Code session so it can investigate and fix:\n\n- "
    )
    feedback_mailto = f"mailto:{feedback_to}?subject={feedback_subject}&body={feedback_body}"
    excluded_note = (
        f" · {', '.join(profile.excluded_companies)} excluded" if profile.excluded_companies else ""
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:system-ui,sans-serif;">
  <div style="max-width:900px;margin:32px auto;background:#fff;border-radius:10px;
              box-shadow:0 1px 4px rgba(0,0,0,0.08);overflow:hidden;">

    <!-- Header -->
    <div style="background:#1e3a5f;padding:24px 32px;display:flex;justify-content:space-between;align-items:flex-start;">
      <div>
        <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">{title}</h1>
        <p style="margin:6px 0 0;color:#93c5fd;font-size:13px;">
          {profile.name} · Job Search Pipeline · Auto-generated
        </p>
      </div>
      <a href="{feedback_mailto}"
         style="background:#fff;color:#1e3a5f;text-decoration:none;border-radius:6px;
                padding:8px 14px;font-size:12px;font-weight:700;white-space:nowrap;margin-left:16px;">
        💬 Leave Feedback
      </a>
    </div>

    <!-- Body -->
    <div style="padding:24px 32px;">
      {body_content}
    </div>

    <!-- Footer -->
    <div style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;
                font-size:12px;color:#9ca3af;text-align:center;">
      Generated by job-search-agent at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
      · Scores &lt; 60% filtered out{excluded_note}
    </div>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _collect_attachments(jobs: list[dict]) -> list[Path]:
    """Return the submittable resume paths (PDF, or DOCX if PDF render failed)
    for the top jobs by score that have an output file."""
    top = sorted(jobs, key=lambda j: j.get("match_score", 0), reverse=True)
    paths = []
    for job in top:
        ats = job.get("ats_output")
        if ats:
            p = Path(ats)
            if p.exists():
                paths.append(p)
        if len(paths) >= TOP_ATTACH_COUNT:
            break
    return paths


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_digest(primary: list[dict], profile, outside_target_location: list[dict] | None = None,
                 qa_roles: list[dict] | None = None, skill_gaps: list | None = None,
                 training_recs: list | None = None, weekly_report: str | None = None) -> bool:
    """
    Build and send the digest email.
    Returns True on success, False on failure.
    """
    outside_target_location = outside_target_location or []
    qa_roles = qa_roles or []

    gmail_user = os.getenv("GMAIL_USER", "").strip()
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    recipient = os.getenv("DIGEST_RECIPIENT", "").strip()

    if not gmail_user or not gmail_password:
        logger.error("GMAIL_USER or GMAIL_APP_PASSWORD not set — cannot send digest")
        return False
    if not recipient:
        logger.error("DIGEST_RECIPIENT not set — cannot send digest")
        return False

    date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
    n = len(primary) + len(outside_target_location) + len(qa_roles)
    subject = f"Job Digest — {date_str} — {n} match{'es' if n != 1 else ''} found"

    html_body = _build_html(primary, outside_target_location, qa_roles, date_str, profile,
                            skill_gaps=skill_gaps, training_recs=training_recs,
                            weekly_report=weekly_report)
    attachments = _collect_attachments(primary)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for path in attachments:
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)

    if attachments:
        logger.info("Attaching %d resume file(s): %s", len(attachments), [p.name for p in attachments])

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, recipient, msg.as_bytes())

        logger.info(
            "Digest sent to %s at %s — %d job(s), %d attachment(s)",
            recipient,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            n,
            len(attachments),
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail authentication failed — check GMAIL_USER and GMAIL_APP_PASSWORD")
    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending digest: %s", exc)
    except OSError as exc:
        logger.error("Network error while sending digest: %s", exc)

    return False


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from datetime import timezone
    from candidate_profile.loader import load_profile, EXAMPLE_PROFILE_PATH

    profile = load_profile(sys.argv[1] if len(sys.argv) > 1 else str(EXAMPLE_PROFILE_PATH))

    dummy_jobs = [
        {
            "title": "Delivery Manager",
            "company": "Nazara Technologies",
            "location": "Mumbai, India",
            "match_score": 88,
            "seniority_fit": "good",
            "industry_fit": "core",
            "missing_keywords": ["OKRs", "PMP"],
            "matched_keywords": ["Agile", "Jira", "Sprint Planning", "Stakeholder Management"],
            "recommendation": "Strong fit — highlight iGaming compliance experience in the summary.",
            "apply_url": "https://example.com/jobs/1",
            "source": "linkedin",
            "ats_output": None,
            "review_output": None,
            "posted_at": datetime.now(timezone.utc),
        },
        {
            "title": "Program Manager",
            "company": "Mobile Premier League",
            "location": "Bangalore, India",
            "match_score": 74,
            "seniority_fit": "good",
            "industry_fit": "core",
            "missing_keywords": ["Python", "SQL", "Data Analysis"],
            "matched_keywords": ["Delivery", "Agile", "Mobile"],
            "recommendation": "Good match but JD skews technical — emphasise cross-functional delivery track record.",
            "apply_url": "https://example.com/jobs/2",
            "source": "naukri",
            "ats_output": None,
            "review_output": None,
            "posted_at": datetime.now(timezone.utc),
        },
        {
            "title": "Associate Producer",
            "company": "Example Studios",
            "location": "Pune, India",
            "match_score": 67,
            "seniority_fit": "under",
            "industry_fit": "core",
            "missing_keywords": ["Perforce", "Shotgrid", "Console"],
            "matched_keywords": ["Production", "Milestone tracking", "Agile"],
            "recommendation": "Title is a step down but AAA pedigree is an exact fit — worth applying.",
            "apply_url": "https://example.com/jobs/3",
            "source": "indeed",
            "ats_output": None,
            "review_output": None,
            "posted_at": datetime.now(timezone.utc),
        },
    ]

    dummy_outside_india = [{
        "title": "Senior Producer",
        "company": "Wildlife Studios",
        "location": "Porto Alegre, Brazil",
        "match_score": 71,
        "seniority_fit": "good",
        "industry_fit": "core",
        "missing_keywords": ["Unity", "F2P"],
        "matched_keywords": ["Production", "Agile", "Live Ops"],
        "recommendation": "",
        "apply_url": "https://example.com/jobs/4",
        "source": "greenhouse",
        "ats_output": None,
        "review_output": None,
        "posted_at": datetime.now(timezone.utc),
    }]

    dummy_qa_roles = [{
        "title": "QA Director",
        "company": "Scopely",
        "location": "Remote",
        "match_score": 65,
        "seniority_fit": "good",
        "industry_fit": "core",
        "missing_keywords": ["Test Automation"],
        "matched_keywords": ["Agile", "Live Ops"],
        "recommendation": "",
        "apply_url": "https://example.com/jobs/5",
        "source": "greenhouse",
        "ats_output": None,
        "review_output": None,
        "posted_at": datetime.now(timezone.utc),
    }]

    success = send_digest(dummy_jobs, profile, dummy_outside_india, dummy_qa_roles)
    if not success:
        # Fallback: write the HTML locally for visual inspection without sending
        date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
        html = _build_html(dummy_jobs, dummy_outside_india, dummy_qa_roles, date_str, profile)
        out = Path("outputs/digest_preview.html")
        out.parent.mkdir(exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Email send skipped (env vars not set). HTML preview written to {out}")
