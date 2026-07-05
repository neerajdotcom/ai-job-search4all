"""
digest/presentation.py — shared score/badge color logic.

Pure functions with no email/SMTP concerns, used by both the HTML email
digest and the webapp dashboard so the two presentations can't drift apart
(e.g. a new industry_fit value only handled in one place).
"""

_SENIORITY_COLORS = {
    "good":  ("#065f46", "#d1fae5"),
    "under": ("#92400e", "#fef3c7"),
    "over":  ("#1e3a5f", "#dbeafe"),
}

_DEFAULT_COLORS = ("#374151", "#f3f4f6")

# Rank-based palette for industry bands (best -> worst), independent of what
# values/labels a profile's industry_bands actually use — a 3-band profile
# gets green/amber/red, a 5-band profile spreads across the same ramp.
_INDUSTRY_RANK_COLORS = [
    ("#065f46", "#d1fae5"),  # best
    ("#1e3a5f", "#dbeafe"),
    ("#92400e", "#fef3c7"),
    ("#7f1d1d", "#fee2e2"),  # worst
]


def score_color(score: int) -> str:
    if score >= 80:
        return "#1a7f4b"   # green
    return "#b45309"       # amber (only called for >= 65)


def score_bg(score: int) -> str:
    if score >= 80:
        return "#d1fae5"
    return "#fef3c7"


def seniority_badge_colors(fit: str) -> tuple[str, str]:
    """Returns (foreground, background) hex colors for a seniority-fit badge."""
    return _SENIORITY_COLORS.get(fit, _DEFAULT_COLORS)


def industry_badge_colors(fit: str, industry_bands: list[dict] | None = None) -> tuple[str, str]:
    """Returns (foreground, background) hex colors for an industry-fit badge,
    ranked by the fit value's position in profile.industry_bands (best first).
    Falls back to a neutral color for an unrecognized value or when no bands
    are supplied (e.g. an older run snapshot rendered without a profile)."""
    if not industry_bands:
        return _DEFAULT_COLORS
    values = [b.get("value") for b in industry_bands]
    if fit not in values:
        return _DEFAULT_COLORS
    rank = values.index(fit)
    palette_idx = min(rank, len(_INDUSTRY_RANK_COLORS) - 1)
    return _INDUSTRY_RANK_COLORS[palette_idx]


def industry_label(fit: str, industry_bands: list[dict] | None = None) -> str:
    """Human-readable label for an industry_fit value, looked up from
    profile.industry_bands (e.g. 'core' -> 'Core industry match'). Falls back
    to a title-cased version of the raw value if no bands are supplied or the
    value isn't recognized."""
    if not fit:
        return ""
    if industry_bands:
        for band in industry_bands:
            if band.get("value") == fit:
                return band.get("label", fit)
    return fit.replace("_", " ").title()


def compute_skill_gaps(jobs: list[dict], top_n: int = 10) -> list[dict]:
    """Frequency-rank each job's missing_keywords across a run — zero extra
    LLM calls, since missing_keywords is already produced by Groq scoring.
    Surfaces which skills would have moved the needle on the most postings."""
    counts: dict[str, int] = {}
    for job in jobs:
        for kw in job.get("missing_keywords", []) or []:
            key = (kw or "").strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"skill": skill, "count": count} for skill, count in ranked]
