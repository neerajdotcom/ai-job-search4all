import json
import logging
import os
import re

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Scoring runs on Groq (free tier ~30 req/min, thousands/day) — high volume,
# speed matters more than prose quality. Resume optimization stays on Gemini.
GROQ_MODEL = "llama-3.3-70b-versatile"

# Groq free tier is ~30 requests/min → space calls ~2.5s apart to stay safe.
import time as _time
_MIN_INTERVAL = 2.5
_last_call = [0.0]


def _throttle():
    elapsed = _time.time() - _last_call[0]
    if elapsed < _MIN_INTERVAL:
        _time.sleep(_MIN_INTERVAL - elapsed)
    _last_call[0] = _time.time()


# Once Groq reports the daily token cap (TPD) is exhausted, every subsequent
# call in the run will fail the same way — retrying just burns ~30-40s per job
# waiting on backoff before giving up anyway. This flag short-circuits the rest
# of the run the moment that's detected, so e.g. job 20/50 doesn't sit through
# a doomed retry loop on every remaining job.
_daily_quota_exhausted = [False]


def _is_daily_quota_error(msg: str) -> bool:
    low = msg.lower()
    return "tokens per day" in low or "tpd" in low


def _generate_with_retry(client, prompt, max_retries=2):
    """Call Groq chat completion, retrying transient 429/503 with backoff."""
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        except Exception as exc:
            msg = str(exc)
            if _is_daily_quota_error(msg):
                _daily_quota_exhausted[0] = True
                logger.error("Groq daily token quota (TPD) exhausted — skipping Groq for the rest of this run")
                raise
            transient = ("503" in msg or "UNAVAILABLE" in msg
                         or "429" in msg or "rate" in msg.lower())
            if transient and attempt < max_retries:
                wait = 10 * (attempt + 1)
                logger.warning("Groq transient error (attempt %d) — retrying in %ds",
                               attempt + 1, wait)
                _time.sleep(wait)
                continue
            raise


# ---------------------------------------------------------------------------
# Free keyword pre-filter — ranks jobs locally with NO API calls.
# Used to pick the most relevant jobs before spending Gemini quota.
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "are", "our", "will", "this", "that",
    "have", "from", "has", "was", "but", "all", "can", "out", "who", "job", "role",
    "work", "team", "years", "year", "experience", "should", "must", "their", "they",
    "a", "an", "in", "on", "of", "to", "is", "as", "at", "be", "or", "we", "it",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _priority_terms(profile) -> set:
    """High-signal terms for THIS profile's target roles — derived from the
    profile's own search_terms/title/adjacent_industries rather than a fixed
    hardcoded set, so the prefilter's bonus weighting generalizes to any
    candidate instead of being tuned to one person's career."""
    words: set = set()
    for phrase in list(profile.search_terms) + [profile.title] + list(profile.adjacent_industries):
        words |= _tokenize(phrase)
    return words


def _target_title_words(profile) -> set:
    """Words that make a job title look like one of the profile's own search
    terms — used for the title_bonus in prefilter_jobs."""
    words: set = set()
    for phrase in profile.search_terms:
        words |= _tokenize(phrase)
    return words


def _priority_rank(job: dict) -> int:
    """
    Target-location + non-QA jobs get first claim on the scarce Groq scoring
    slots (top_n below), then non-target-location non-QA, then QA/testing
    roles (any location) last — keyword overlap alone shouldn't let a
    better-matching out-of-region/QA posting bump a target-location role out
    of scoring.
    """
    if job.get("is_qa_role"):
        return 2
    if not job.get("is_target_location", True):
        return 1
    return 0


def prefilter_jobs(jobs, resume_text: str, profile, top_n: int = 12) -> list[dict]:
    """
    Rank jobs by cheap keyword overlap (no API calls) and return the top_n.
    Keeps Gemini quota for only the most promising jobs. Target-location +
    non-QA jobs are prioritized into top_n ahead of out-of-region/QA jobs
    regardless of keyword-overlap score (see _priority_rank).
    """
    resume_tokens = _tokenize(resume_text)
    priority_terms = _priority_terms(profile)
    target_title_words = _target_title_words(profile)

    scored = []
    for job in jobs:
        jd_tokens = _tokenize(job.get("jd_text", "") + " " + job.get("title", ""))
        title_tokens = _tokenize(job.get("title", ""))

        overlap = resume_tokens & jd_tokens
        base = len(overlap)
        priority_bonus = 2 * len(jd_tokens & priority_terms)
        title_bonus = 5 * len(title_tokens & target_title_words)

        prefilter_score = base + priority_bonus + title_bonus
        scored.append((prefilter_score, job))

    scored.sort(key=lambda x: (_priority_rank(x[1]), -x[0]))
    top = [job for _, job in scored[:top_n]]

    logger.info(
        "Pre-filter: ranked %d jobs locally, selected top %d for AI scoring",
        len(jobs), len(top),
    )
    return top


# ---------------------------------------------------------------------------
# Ghost-job detection — local, zero-LLM-cost heuristics. Catches likely-fake
# or low-effort postings before they spend a Groq scoring slot, let alone a
# scarce Gemini optimize slot. Flags only — main.py skips scoring for a
# flagged job but never drops it from the run snapshot, so the reason stays
# visible and the user can override by re-running.
# ---------------------------------------------------------------------------

_GHOST_MIN_WORDS = 100
_GHOST_TITLE_RE = re.compile(r"\b(urgent|immediate joiner|walk-?in)\b", re.IGNORECASE)
_GHOST_DUPLICATE_THRESHOLD = 3  # same JD text posted by more than this many distinct companies


def _normalize_jd(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def build_jd_fingerprint_index(jobs: list[dict]) -> dict:
    """Map normalized JD text -> set of distinct companies posting it, built
    once per run so the duplicate-JD check in is_ghost_job is O(n) instead of
    O(n^2) over the prefiltered batch."""
    index: dict[str, set] = {}
    for job in jobs:
        norm = _normalize_jd(job.get("jd_text", ""))
        if not norm:
            continue
        index.setdefault(norm, set()).add(job.get("company", "") or "")
    return index


def is_ghost_job(job: dict, fingerprint_index: dict | None = None) -> tuple[bool, str]:
    """Four free local heuristics: JD too short, no identifiable company,
    urgent/walk-in title language, and identical JD text reposted under many
    different companies (likely a scraped/synthetic listing). Returns
    (flagged, reason) — never drops the job, only flags it for main.py to
    skip scoring/optimize on."""
    jd_text = job.get("jd_text", "") or ""
    word_count = len(jd_text.split())
    # Adzuna's API returns truncated snippets (~60-80 words) by design — the
    # word-count check would false-positive on every Adzuna job, so skip it there.
    if job.get("source") != "adzuna" and word_count < _GHOST_MIN_WORDS:
        return True, f"JD too short ({word_count} words, expected {_GHOST_MIN_WORDS}+)"

    company = (job.get("company") or "").strip()
    if not company or company.lower() in ("unknown", "n/a", "confidential"):
        return True, "No identifiable company name"

    title = job.get("title", "") or ""
    match = _GHOST_TITLE_RE.search(title)
    if match:
        return True, f"Title contains urgency/spam language: '{match.group(0)}'"

    if fingerprint_index is not None:
        norm = _normalize_jd(jd_text)
        companies = fingerprint_index.get(norm, set())
        if len(companies) > _GHOST_DUPLICATE_THRESHOLD:
            return True, f"Identical JD text posted by {len(companies)} different companies"

    return False, ""


def _format_bands(bands: list[dict]) -> str:
    return "; ".join(f"{b['label']} = {b['points']}" for b in bands) + "."


def build_scoring_instructions(profile) -> str:
    """Rubric v2, generalized: SKILLS/INDUSTRY/ROLE LEVEL bands all come from
    the profile (sensible generic defaults, override in config.yaml for a
    more granular breakdown) instead of one candidate's hardcoded rubric."""
    industry_bands_max = max((b["points"] for b in profile.industry_bands), default=35)
    return (
        f"You are a job-resume match scorer for {profile.name} — a {profile.title} with "
        f"{profile.years_experience} years of {profile.industry_summary} experience. Compute "
        "match_score out of 100 by ADDING the points earned in three categories (max 100 total):\n"
        f"SKILLS (max 40): {_format_bands(profile.skill_areas)}\n"
        f"INDUSTRY (max {industry_bands_max}, pick the single best-matching band): "
        f"{_format_bands(profile.industry_bands)}\n"
        f"ROLE LEVEL (max 25, pick one): {_format_bands(profile.role_level_bands)}\n"
        "Judge the role's ACTUAL function and domain, not just shared job-title words — a role that "
        "shares generic vocabulary with the resume but whose core domain is unrelated to the "
        f"candidate's target industry ({profile.industry_summary}) must NOT be inflated by that "
        "vocabulary alone; score its industry band as unrelated. "
        "Respond with valid JSON only, no preamble, no markdown."
    )


PROMPT_TEMPLATE = """{instructions}

Resume:
{resume_text}

Job Description:
Title: {title}
Company: {company}
Location: {location}
Description:
{jd_text}

Return ONLY a JSON object with exactly these keys:
- match_score (integer 0-100 — the SUM of the SKILLS + INDUSTRY + ROLE LEVEL points above)
- matched_keywords (list of strings found in both resume and JD)
- missing_keywords (list of strings required by JD but absent from resume)
- seniority_fit (one of: "under", "good", "over")
- industry_fit (one of: {industry_fit_values})
- recommendation (string, one sentence max)
"""

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        _client = Groq(api_key=api_key)
    return _client


def _fallback(reason: str) -> dict:
    return {
        "match_score": 0,
        "matched_keywords": [],
        "missing_keywords": [],
        "seniority_fit": "unknown",
        "industry_fit": "unknown",
        "recommendation": reason,
    }


# ---------------------------------------------------------------------------
# Experience-gap hard check — local, zero-LLM-cost.
#
# Adzuna's API snippet (jd_text) is truncated to ~500 chars and routinely omits
# the actual experience requirement (e.g. "Minimum 15 years of experience" can
# sit well past that cutoff). An LLM scoring only the snippet has no way to
# catch this, so we extract years-of-experience locally — first from the
# snippet, falling back to fetching Adzuna's own full detail page — and hard-
# cap the score before (or instead of) spending a Groq call.
# ---------------------------------------------------------------------------

# Match both the full word ("years"/"year") and common abbreviations
# ("yrs"/"yr") many JDs use — the original word-only pattern silently missed
# "10-14 yrs" entirely, letting an LLM score the truncated snippet as a match.
# A range ("10-14 years", "10 to 14 yrs") is the real minimum at its LOWER
# bound, so we read group(1); a standalone figure ("15+ years") reads as-is.
_RANGE_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
_SINGLE_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
# Accept the abbreviation "exp" (as a standalone word, so "expand"/"export"
# don't trip it) alongside the full "experien…" stem.
_EXP_WORD_RE = re.compile(r"\bexp\b")


def _near_experience(text: str, start: int, end: int) -> bool:
    """True if 'experience' (or the abbreviation 'exp') sits next to a matched
    years figure — guards against false positives like '5-year warranty'."""
    window = text[max(0, start - 40):end + 15].lower()
    return "experien" in window or _EXP_WORD_RE.search(window) is not None


def _extract_required_years(text: str):
    """Largest required-experience figure stated near 'experience'/'exp'.
    Ranges contribute their lower bound (the true minimum), so a '5-8 years'
    role the candidate already meets isn't mistaken for an 8-year requirement."""
    if not text:
        return None
    candidates = []
    # Ranges first; blank each matched span (same length) so the single-figure
    # scan below can't re-read a range's upper bound as a separate requirement.
    work = text
    for m in _RANGE_YEARS_RE.finditer(text):
        if _near_experience(text, *m.span()):
            candidates.append(int(m.group(1)))
        work = work[:m.start()] + (" " * (m.end() - m.start())) + work[m.end():]
    for m in _SINGLE_YEARS_RE.finditer(work):
        if _near_experience(work, *m.span()):
            candidates.append(int(m.group(1)))
    return max(candidates) if candidates else None


def _experience_override(job: dict, profile):
    """Returns a dict of scoring overrides if the JD needs far more experience
    than the candidate has, or None if there's no detectable mismatch."""
    required = _extract_required_years(job.get("jd_text", ""))
    if required is None:
        # Reuse the full page text the scraper already fetched for the
        # location re-check (avoids fetching the same Adzuna page twice).
        full_text = job.get("_full_text")
        if full_text is None:
            from scraper.job_scraper import fetch_full_description
            full_text = fetch_full_description(job.get("apply_url", ""))
        required = _extract_required_years(full_text or "")

    if required is None:
        return None

    # Rubric v2 auto-excludes roles requiring >= profile.experience_exclude_years.
    # Any such role is almost certainly an auto-reject, so it isn't worth a Groq
    # slot. Rather than hard-drop it, flag it and soft-cap below main.py's
    # SCORE_THRESHOLD (60): it stays visible in the run snapshot / dashboard
    # with a clear reason for the user to judge, but never lands as an inflated
    # false match in the digest.
    if required >= profile.experience_exclude_years:
        return {
            "skip_scoring": True,
            "required_years": required,
            "match_score": 45,
            "seniority_fit": "under",
            "industry_fit": "unrelated",
            "matched_keywords": [],
            "missing_keywords": [f"{required}+ years experience"],
            "recommendation": (
                f"⚠ Requires {required}+ years of experience — you have "
                f"{profile.years_experience}. Auto-excluded per the "
                f"{profile.experience_exclude_years}+ year rule and capped below the match "
                "threshold; Groq scoring skipped to save quota."
            ),
        }
    return None


def score_job(job: dict, resume_text: str, profile) -> dict:
    """
    Score a single job dict against the resume using Groq.
    Returns the original job dict merged with scoring fields.
    """
    override = _experience_override(job, profile)
    if override and override.get("skip_scoring"):
        logger.info(
            "%-40s | %-30s | score: %3d%% | EXPERIENCE GAP: needs %d+ yrs (have %d) — Groq call skipped",
            (job.get("title", ""))[:40], (job.get("company", ""))[:30],
            override["match_score"], override["required_years"], profile.years_experience,
        )
        clean = {k: v for k, v in override.items() if k not in ("skip_scoring", "required_years")}
        return {**job, **clean}

    if _daily_quota_exhausted[0]:
        scoring = _fallback("Groq daily quota exhausted earlier this run — scoring skipped to save time.")
    else:
        industry_fit_values = ", ".join(f'"{b["value"]}"' for b in profile.industry_bands)
        prompt = PROMPT_TEMPLATE.format(
            instructions=build_scoring_instructions(profile),
            resume_text=resume_text,
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            jd_text=job.get("jd_text", ""),
            industry_fit_values=industry_fit_values,
        )

        try:
            client = _get_client()
            raw = (_generate_with_retry(client, prompt) or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            scoring = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Groq response for '%s' @ %s: %s",
                         job.get("title"), job.get("company"), exc)
            scoring = _fallback("Scoring failed — could not parse model response.")
        except Exception as exc:
            logger.error("Groq error for '%s' @ %s: %s",
                         job.get("title"), job.get("company"), exc)
            scoring = _fallback(f"Scoring failed — {exc}")

    score = scoring.get("match_score", 0)
    top_missing = scoring.get("missing_keywords", [])[:3]

    logger.info(
        "%-40s | %-30s | score: %3d%% | missing: %s",
        (job.get("title", ""))[:40],
        (job.get("company", ""))[:30],
        score,
        ", ".join(top_missing) if top_missing else "none",
    )

    return {**job, **scoring}


# ---------------------------------------------------------------------------
# Drafter-reviewer second pass — a cheap sanity-check call that catches
# false-positive qualifications before Gemini optimize quota gets spent on
# them. Deliberately does NOT resend the full resume + JD (that would double
# the Groq token cost per run); it only sends the first pass's own output
# (score, matched/missing keywords, recommendation) plus a short JD excerpt,
# and asks Groq to flag if that score looks inconsistent with its own reasons.
# Only called from main.py for jobs that already cleared SCORE_THRESHOLD, so
# it runs on a small subset of the 50 jobs scored per run, not all of them.
# ---------------------------------------------------------------------------

def build_review_instructions(profile) -> str:
    return (
        f"You are auditing another model's job-match score for {profile.name}, a "
        f"{profile.title} with {profile.years_experience} years of "
        f"{profile.industry_summary} experience. You are given the first pass's "
        "score and its own stated reasons. Check whether the score is actually "
        "consistent with those reasons — e.g. a high score next to several "
        "serious missing requirements, or a 'good' seniority_fit next to language "
        "suggesting otherwise. Also flag a high score that is driven only by "
        "generic vocabulary shared with the resume when the role's real domain/"
        f"function is unrelated to the candidate's target industry "
        f"({profile.industry_summary}) — lower reviewed_score in that case. "
        "Respond with valid JSON only, no preamble, no markdown."
    )

REVIEW_PROMPT_TEMPLATE = """{instructions}

Job: {title} @ {company}
JD excerpt: {jd_excerpt}

First-pass result:
- match_score: {match_score}
- matched_keywords: {matched_keywords}
- missing_keywords: {missing_keywords}
- seniority_fit: {seniority_fit}
- industry_fit: {industry_fit}
- recommendation: {recommendation}

Return ONLY a JSON object with exactly these keys:
- score_adjusted (boolean — true only if the first-pass score is meaningfully wrong)
- reviewed_score (integer 0-100 — same as match_score if score_adjusted is false)
- reviewer_notes (string, one sentence max, empty string if score_adjusted is false)
"""

_JD_EXCERPT_CHARS = 400


def review_score(scored_job: dict, profile) -> dict | None:
    """Second-pass audit of an already-qualifying job's Groq score. Returns
    None (no-op) if the daily quota is exhausted or the call fails — callers
    should keep the first-pass score unchanged in that case (fail open, never
    block a job from being optimized/sent over a reviewer-call hiccup)."""
    if _daily_quota_exhausted[0]:
        return None

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        instructions=build_review_instructions(profile),
        title=scored_job.get("title", ""),
        company=scored_job.get("company", ""),
        jd_excerpt=(scored_job.get("jd_text", "") or "")[:_JD_EXCERPT_CHARS],
        match_score=scored_job.get("match_score", 0),
        matched_keywords=scored_job.get("matched_keywords", []),
        missing_keywords=scored_job.get("missing_keywords", []),
        seniority_fit=scored_job.get("seniority_fit", "unknown"),
        industry_fit=scored_job.get("industry_fit", "unknown"),
        recommendation=scored_job.get("recommendation", ""),
    )

    try:
        client = _get_client()
        raw = (_generate_with_retry(client, prompt) or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        review = json.loads(raw)
    except Exception as exc:
        logger.warning("Reviewer pass failed for '%s' @ %s: %s",
                       scored_job.get("title"), scored_job.get("company"), exc)
        return None

    return {
        "score_adjusted": bool(review.get("score_adjusted", False)),
        "reviewed_score": int(review.get("reviewed_score", scored_job.get("match_score", 0))),
        "reviewer_notes": review.get("reviewer_notes", ""),
    }


# ---------------------------------------------------------------------------
# Skill-gap → training recommendations — ONE Groq call per run (not per job).
# Closes the loop on digest.presentation.compute_skill_gaps, which already
# frequency-ranks the keywords most often missing across a run but doesn't act
# on them. Runs on Groq (already initialized for scoring, abundant per-day
# budget) rather than Gemini, whose per-call throttle/optimize cap is the
# scarcer resource. Fails open: returns [] on any error or exhausted quota, so
# the digest just omits the section — same philosophy as the reviewer pass.
# ---------------------------------------------------------------------------

def build_training_instructions(profile) -> str:
    search_terms_summary = "/".join(profile.search_terms[:3]) if profile.search_terms else profile.title
    return (
        f"You advise {profile.name} — a {profile.title} with "
        f"{profile.years_experience} years of {profile.industry_summary} experience "
        f"targeting {search_terms_summary} roles in {profile.location}. Given the "
        "skills that most often came up as gaps across this batch of job matches, "
        "recommend the highest-leverage, low-cost or free courses/certifications "
        "that would close them. Prefer well-known, widely-accessible options "
        "(Coursera, Udemy, official vendor/industry certs, official docs). Respond "
        "with valid JSON only, no preamble, no markdown."
    )

TRAINING_PROMPT_TEMPLATE = """{instructions}

Recurring skill gaps this run (most frequent first): {skills}

Return ONLY a JSON object with exactly this key:
- recommendations (list of 2-3 objects, each with exactly these keys:
  "skill" (string, which gap it addresses),
  "recommendation" (string, a specific course/cert name or short path),
  "why" (string, one sentence on the payoff for these target roles))
"""


def generate_training_recommendations(skill_gaps: list[dict], profile, max_skills: int = 6) -> list[dict]:
    """Turn the existing skill_gaps list into 2-3 concrete course/cert picks.
    Returns [] on empty input, exhausted quota, or any error (fail open)."""
    if not skill_gaps or _daily_quota_exhausted[0]:
        return []

    skills = [g.get("skill", "") for g in skill_gaps[:max_skills] if g.get("skill")]
    if not skills:
        return []

    prompt = TRAINING_PROMPT_TEMPLATE.format(
        instructions=build_training_instructions(profile), skills=", ".join(skills),
    )

    try:
        client = _get_client()
        raw = (_generate_with_retry(client, prompt) or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("Training-recommendation call failed: %s", exc)
        return []

    recs = data.get("recommendations", []) if isinstance(data, dict) else []
    out = []
    for r in recs:
        if isinstance(r, dict) and (r.get("recommendation") or r.get("skill")):
            out.append({
                "skill": str(r.get("skill", "")),
                "recommendation": str(r.get("recommendation", "")),
                "why": str(r.get("why", "")),
            })
    return out


if __name__ == "__main__":
    import sys
    from datetime import datetime, timezone
    from candidate_profile.loader import load_profile, EXAMPLE_PROFILE_PATH

    profile = load_profile(sys.argv[1] if len(sys.argv) > 1 else str(EXAMPLE_PROFILE_PATH))

    sample_resume = f"""
    {profile.name} | {profile.title} | {profile.location}
    {profile.years_experience} years of experience in {profile.industry_summary}.
    Agile | Scrum | Delivery Management | Stakeholder Management | Jira | Sprint Planning
    """

    sample_job = {
        "title": profile.search_terms[0] if profile.search_terms else profile.title,
        "company": "Example Corp",
        "location": profile.location,
        "jd_text": (
            f"Seeking an experienced {profile.title} with agile software delivery background. "
            "Must have strong Jira, sprint planning, and stakeholder management skills."
        ),
        "apply_url": "https://example.com/jobs/123",
        "source": "adzuna",
        "posted_at": datetime.now(timezone.utc),
    }

    result = score_job(sample_job, sample_resume, profile)
    print("\n--- Score Result ---")
    print(json.dumps({k: v for k, v in result.items() if k != "jd_text"}, indent=2, default=str))
