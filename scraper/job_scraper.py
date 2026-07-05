import logging
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse

import requests
from dotenv import load_dotenv

from scraper.ats_scraper import _strip_html

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Sources that return an employer's *current* live open-positions list — an old
# post date doesn't mean a closed role, so they're exempt from STALE_DAYS
# freshness filtering. Everything else (Adzuna, crawl4ai web boards) is a
# syndicated/crawled listing and IS freshness-checked.
_LIVE_BOARD_SOURCES = {"greenhouse", "lever", "ashby", "workable"}

# QA / testing roles — filtered at the title level so they don't burn scoring
# quota. Word-boundary regex so "qa" doesn't match "equation", etc.
_QA_TITLE_PATTERNS = [
    re.compile(r"\bqa\b", re.IGNORECASE),
    re.compile(r"\bsdet\b", re.IGNORECASE),
    re.compile(r"\bquality\s+(assurance|engineer|engineering|lead|manager|analyst|control|specialist|coordinator)\b", re.IGNORECASE),
    re.compile(r"\b(test|testing)\s+(engineer|engineering|lead|manager|analyst|specialist|coordinator|architect|automation)\b", re.IGNORECASE),
    re.compile(r"\b(automation|manual|performance|game|software|qa)\s+tester\b", re.IGNORECASE),
    re.compile(r"\btester\b", re.IGNORECASE),
]


def _is_qa_role(title: str) -> bool:
    if not title:
        return False
    return any(pat.search(title) for pat in _QA_TITLE_PATTERNS)


def _whole_token_match(name: str, aliases: list[str]) -> bool:
    """Whole-token substring match on a normalized name — short aliases
    ('Push', 'L&W') don't false-match unrelated words inside a longer name."""
    if not name or not aliases:
        return False
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    return any(
        re.search(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])", normalized)
        for alias in aliases
    )


def _target_role_patterns(profile) -> list:
    """Word-boundary regexes derived from the candidate's own search_terms —
    lets downstream aggregation (skill-gap report, training recs) tell an
    on-track title from an unrelated one that just shares vocabulary with the
    resume. ATS feeds return a company's *entire* job board, unfiltered by
    title (unlike Adzuna, queried per search_terms), so this tag matters most
    for ATS-sourced jobs."""
    patterns = []
    for term in profile.search_terms:
        # Allow "Program"/"Programme" to match interchangeably, since many
        # JDs use the British spelling regardless of the term's own spelling.
        escaped = re.escape(term.strip()).replace(r"Program", r"Program(me)?")
        patterns.append(re.compile(r"\b" + escaped + r"\b", re.IGNORECASE))
    return patterns


def _is_target_role(title: str, profile) -> bool:
    if not title:
        return False
    return any(pat.search(title) for pat in _target_role_patterns(profile))


def _is_target_company(company: str, profile) -> bool:
    """True if the company is on the candidate's own curated target list —
    used only to highlight the job in the digest/dashboard, never to score
    or rank it. Whole-token match so short aliases don't false-match."""
    return _whole_token_match(company, profile.target_companies)


RESULTS_PER_TERM = 50  # Adzuna API's max results_per_page

STALE_DAYS = 7

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def _is_fresh(posted_at) -> bool:
    if posted_at is None:
        return True
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posted_at) <= timedelta(days=STALE_DAYS)


def _is_excluded_company(company: str, profile) -> bool:
    lower = (company or "").lower()
    return any(ex.lower() in lower for ex in profile.excluded_companies)


# Generic world-country/city recognition list used to detect an EXPLICIT
# signal that a posting is in some country other than the candidate's target
# (profile.target_location_country) — not tied to any one target country, so
# it works whichever country a profile picks. Same permissive-by-default
# philosophy the original India-only version used: only a recognized signal
# flags "not my target location"; ambiguous/empty/"Remote" text still counts
# as matching the target.
_KNOWN_COUNTRIES = {
    "india", "pakistan", "bangladesh", "china", "spain", "japan",
    "united states", "usa", "u.s.", "u.s.a", "brazil", "canada", "mexico",
    "singapore", "united kingdom", "uk", "germany", "france", "philippines",
    "vietnam", "indonesia", "poland", "ireland", "australia", "south korea",
    "korea", "netherlands",
}

# City -> country, so a target country's own cities are never mistaken for a
# different country (e.g. if target_location_country is "germany", "berlin"
# must NOT count as an out-of-target signal).
_CITY_COUNTRY_MAP = {
    "karachi": "pakistan", "lahore": "pakistan", "islamabad": "pakistan",
    "rawalpindi": "pakistan", "faisalabad": "pakistan", "multan": "pakistan",
    "peshawar": "pakistan", "quetta": "pakistan", "hyderabad sindh": "pakistan",
    "dhaka": "bangladesh", "chittagong": "bangladesh", "khulna": "bangladesh",
    "rajshahi": "bangladesh", "sylhet": "bangladesh",
    "shanghai": "china", "beijing": "china", "shenzhen": "china",
    "barcelona": "spain", "madrid": "spain",
    "tokyo": "japan", "osaka": "japan",
    "san francisco": "united states", "san mateo": "united states",
    "new york": "united states", "los angeles": "united states",
    "seattle": "united states", "austin": "united states",
    "porto alegre": "brazil", "sao paulo": "brazil", "são paulo": "brazil",
    "rio de janeiro": "brazil",
    "toronto": "canada", "vancouver": "canada", "montreal": "canada",
    "singapore": "singapore",
    "london": "united kingdom", "manchester": "united kingdom",
    "berlin": "germany", "munich": "germany",
    "paris": "france",
    "manila": "philippines",
    "ho chi minh": "vietnam", "hanoi": "vietnam",
    "jakarta": "indonesia",
    "warsaw": "poland",
    "dublin": "ireland",
    "sydney": "australia", "melbourne": "australia",
    "seoul": "south korea", "pangyo": "south korea",
    "amsterdam": "netherlands",
}


def _is_blocked_location(area, location: str, profile) -> bool:
    """
    True if the job matches one of profile.blocked_locations — a hard
    exclude (e.g. countries the candidate legally can't work from), checked
    against every element of Adzuna's `area` list plus the display string.
    Empty by default: no hard blocking unless the profile configures one.
    """
    blocked = [b.lower() for b in profile.blocked_locations]
    if not blocked:
        return False
    for element in (area or []):
        if str(element).strip().lower() in blocked:
            return True
    loc = (location or "").lower()
    return any(b in loc for b in blocked)


def _is_target_location(area, location: str, profile) -> bool:
    """
    True unless the job carries a recognized EXPLICIT signal for a country
    other than profile.target_location_country. Ambiguous, empty, or
    remote-with-no-country location text still counts as the target location
    — permissive-by-default, whichever country is the target.
    """
    target = profile.target_location_country.strip().lower()
    aliases = {a.strip().lower() for a in profile.target_location_aliases}
    other_countries = _KNOWN_COUNTRIES - {target}

    for element in (area or []):
        val = str(element).strip().lower()
        if val == target or val in aliases:
            return True
        if val in other_countries:
            return False
    loc = (location or "").lower()
    if target in loc or any(a in loc for a in aliases):
        return True
    if any(c in loc for c in other_countries):
        return True
    # A city belonging to a different country than the target is a signal;
    # a city belonging to the target country (or unmapped) is not.
    for city, country in _CITY_COUNTRY_MAP.items():
        if city in loc and country != target:
            return False
    return True


def _text_mentions_non_target(text: str, profile) -> bool:
    """Same widened detector as _is_target_location (inverted), applied to
    the full JD/page text the way _text_mentions_blocked_location checks the
    full text for the hard-blocked locations."""
    if not text:
        return False
    target = profile.target_location_country.strip().lower()
    other_countries = _KNOWN_COUNTRIES - {target}
    head = text[:3000].lower()
    if any(c in head for c in other_countries):
        return True
    return any(city in head for city, country in _CITY_COUNTRY_MAP.items() if country != target)


def _clean_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return url


def _parse_date(raw):
    if not raw:
        return None
    try:
        # Adzuna returns ISO 8601, e.g. "2026-06-18T10:30:00Z"
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Adzuna — free job search API
# ---------------------------------------------------------------------------

def scrape_adzuna(profile) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()

    if not app_id or not app_key:
        logger.warning("ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping Adzuna")
        return []

    logger.info("Scraping Adzuna %s job API", profile.adzuna_country_code)
    url = ADZUNA_BASE.format(country=profile.adzuna_country_code)

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for term in profile.search_terms:
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": RESULTS_PER_TERM,
            "what": term,
            "max_days_old": STALE_DAYS,
            "sort_by": "date",
            "content-type": "application/json",
        }
        try:
            logger.info("  Searching Adzuna: '%s'", term)
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", []):
                apply_url = item.get("redirect_url", "")
                key = _clean_url(apply_url)
                if key in seen_urls:
                    continue
                seen_urls.add(key)

                company = (item.get("company", {}) or {}).get("display_name", "").strip()
                loc_obj = item.get("location", {}) or {}
                location = loc_obj.get("display_name", profile.location)
                area = loc_obj.get("area", []) or []

                # Hard-block only what profile.blocked_locations names; allow
                # everything else (target location, remote, multi-country).
                if _is_blocked_location(area, location, profile):
                    logger.info("  Blocking job in %s: %s",
                                location, (item.get("title") or "").strip()[:40])
                    continue

                all_jobs.append({
                    "title": (item.get("title") or "").strip(),
                    "company": company,
                    "location": location,
                    "jd_text": _strip_html(item.get("description", "")),
                    "apply_url": apply_url,
                    "source": "adzuna",
                    "posted_at": _parse_date(item.get("created")),
                })

        except requests.HTTPError as exc:
            logger.error("  Adzuna HTTP error for '%s': %s", term, exc)
        except Exception as exc:
            logger.error("  Adzuna failed for '%s': %s", term, exc)

    logger.info("Adzuna: fetched %d raw entries across all search terms", len(all_jobs))
    return all_jobs


# ---------------------------------------------------------------------------
# Full description fetch — Adzuna's search API truncates "description" to
# ~500 chars, which routinely omits experience/seniority requirements stated
# later in the real posting. Adzuna's own detail page (the apply_url) has the
# full text, no anti-bot issues since it's Adzuna's own domain.
# ---------------------------------------------------------------------------

_FETCH_TIMEOUT = 10
_MAX_DESC_CHARS = 6000  # generous bound that stays well before "similar jobs" filler


def fetch_full_description(apply_url: str):
    """Best-effort fetch of the full job text from Adzuna's detail page.
    Returns None on any failure so callers can fail open (no false rejections)."""
    if not apply_url:
        return None
    try:
        resp = requests.get(apply_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        return _strip_html(resp.text)[:_MAX_DESC_CHARS]
    except Exception as exc:
        logger.warning("Could not fetch full description from %s: %s", apply_url, exc)
        return None


def check_job_live(job: dict) -> bool:
    """Re-verify a posting is still reachable right before it's surfaced in the
    digest — catches a job that was fresh at scrape time but has since been
    filled/removed (the STALE_DAYS window is a one-time scrape-time check and
    never re-confirms an in-window posting is still open).

    Fail-open by design: returns False ONLY on an unambiguous dead signal
    (HTTP 404/410). A 200, a redirect, a timeout, or any other error all return
    True — a flaky check must never drop a real match. Intended for the small
    qualifying set only, not the full scraped list.

    ATS-sourced jobs (greenhouse/lever/ashby) come straight from each
    employer's live open-positions board, so an entry existing there already
    means it's open — they're treated as live without a network call. Only
    Adzuna's and LinkedIn's syndicated/crawled listings actually go stale
    between scrape and digest."""
    if job.get("source") not in ("adzuna", "linkedin"):
        return True
    url = job.get("apply_url", "")
    if not url:
        return True
    try:
        resp = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"},
            timeout=_FETCH_TIMEOUT, allow_redirects=True,
        )
    except Exception as exc:
        logger.warning("Liveness check could not reach %s: %s — assuming live", url, exc)
        return True
    if resp.status_code in (404, 410):
        logger.info("Liveness: %s returned %d — flagging as closed", url, resp.status_code)
        return False
    return True


def _text_mentions_blocked_location(text: str, profile) -> bool:
    """Check the rendered page text (not the API's structured location field)
    for a location in profile.blocked_locations. The page typically has
    ~1300-1400 chars of tracking/script boilerplate before the title+location
    line, so the window needs to extend past that — but stays well short of
    the "similar jobs" section that starts around 3400+ chars, to avoid
    picking up an unrelated posting's location."""
    blocked = [b.lower() for b in profile.blocked_locations]
    if not text or not blocked:
        return False
    head = text[:3000].lower()
    return any(b in head for b in blocked)


# ---------------------------------------------------------------------------
# Dedup utility
# ---------------------------------------------------------------------------

def _normalize_for_dedup(text: str) -> str:
    """Strip punctuation/casing/extra-whitespace differences so 'Epic Games' vs
    'Epic Games, Inc.' or 'Senior Producer' vs 'Senior  Producer' still match
    across sources that format the same job differently."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _dedup(jobs: list[dict]) -> list[dict]:
    """De-dupes across ALL sources combined (Adzuna + every ATS feed), not
    per-source — callers should pass every source's jobs in one list. The
    first occurrence of a duplicate wins, so callers should order their input
    with the richer/more-accurate source first (full JD + verified location)
    ahead of syndicated sources (truncated JD, mislabel-prone location)."""
    seen_urls: set[str] = set()
    seen_title_company: set[str] = set()
    unique = []
    for job in jobs:
        url_key = _clean_url(job["apply_url"])
        tc_key = (_normalize_for_dedup(job.get("title", "")) + "|" +
                  _normalize_for_dedup(job.get("company", "")))
        # Skip if we've seen this URL OR this exact title+company already
        if (url_key and url_key in seen_urls) or (tc_key != "|" and tc_key in seen_title_company):
            continue
        if url_key:
            seen_urls.add(url_key)
        if tc_key != "|":
            seen_title_company.add(tc_key)
        unique.append(job)
    return unique


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def scrape_all_jobs(profile) -> list[dict]:
    """
    Scrape jobs from Adzuna (free API, country from profile.adzuna_country_code)
    plus, optionally, direct employer ATS feeds (Greenhouse, Lever, Ashby,
    Workable — see ats_scraper.py). Returns deduplicated jobs posted within
    the last 7 days, excluding profile.excluded_companies.
    """
    raw = scrape_adzuna(profile)
    logger.info("Adzuna raw jobs: %d", len(raw))

    # Zero-key job source — LinkedIn's public guest endpoints, no API key
    # required. On by default so the pipeline produces real matches even
    # with no Adzuna/ATS credentials configured at all; set
    # ENABLE_LINKEDIN_SCRAPE=false to disable (e.g. ToS-averse deployments).
    if os.getenv("ENABLE_LINKEDIN_SCRAPE", "true").lower() == "true":
        from scraper.linkedin_guest_scraper import scrape_linkedin_guest
        try:
            linkedin_jobs = scrape_linkedin_guest(profile)
        except Exception as exc:
            logger.error("LinkedIn guest scraping failed: %s", exc)
            linkedin_jobs = []
        logger.info("LinkedIn (guest) raw jobs: %d", len(linkedin_jobs))
    else:
        linkedin_jobs = []

    # ATS company boards are a hand-picked list of specific employers'
    # Greenhouse/Lever/Ashby/Workable slugs (see scraper/ats_scraper.py) —
    # they don't generalize to an arbitrary profile's target companies, so
    # this source is opt-in (default off) until you edit ats_scraper.py's
    # company lists to your own targets. See README "Deploy your own copy".
    if os.getenv("ENABLE_ATS_SCRAPING", "false").lower() == "true":
        from scraper.ats_scraper import scrape_all_ats_jobs
        try:
            ats_jobs = scrape_all_ats_jobs()
        except Exception as exc:
            logger.error("ATS scraping failed: %s", exc)
            ats_jobs = []
        logger.info("ATS (Greenhouse/Lever/Ashby/Workable) raw jobs: %d", len(ats_jobs))
    else:
        ats_jobs = []

    # Optional crawl4ai web-board sources (Naukri/Indeed/Foundit/Instahyre/
    # Wellfound). Gated behind ENABLE_CRAWL4AI and fully fail-open — a blocked
    # CI IP or missing browser just yields nothing, never breaks the run.
    if os.getenv("ENABLE_CRAWL4AI", "false").lower() == "true":
        try:
            from scraper.crawl4ai_scraper import scrape_crawl4ai_jobs
            crawl_jobs = scrape_crawl4ai_jobs()
        except Exception as exc:
            logger.error("crawl4ai scraping failed: %s", exc)
            crawl_jobs = []
        logger.info("crawl4ai web-board raw jobs: %d", len(crawl_jobs))
    else:
        crawl_jobs = []

    # ATS jobs go first: if the same posting somehow exists in both (e.g.
    # Adzuna's crawler syndicates a posting that's also on the company's own
    # Greenhouse/Lever/Ashby board), _dedup keeps the *first* occurrence — and
    # the ATS copy has the full JD text and a trustworthy location field,
    # while Adzuna's copy is truncated to ~500 chars and has mislabeled
    # location data before. Keeping Adzuna first would silently keep the
    # worse copy on any future overlap.
    combined = _dedup(ats_jobs + crawl_jobs + raw + linkedin_jobs)

    # The 7-day freshness window only makes sense for syndicated/crawled
    # listings (Adzuna, crawl4ai web boards): an old timestamp can mean a
    # stale/closed posting. Greenhouse/Lever/Ashby/Workable jobs are pulled
    # live from the employer's current open-positions list — if it's in the
    # response, it's open right now, no matter when it was first posted.
    # Applying the same 7-day rule to them was throwing away ~95% of genuinely
    # live roles.
    filtered = [
        job for job in combined
        if (job.get("source") in _LIVE_BOARD_SOURCES or _is_fresh(job["posted_at"]))
        and not _is_excluded_company(job["company"], profile)
    ]

    logger.info(
        "Total after dedup: %d | After freshness+exclusion filter: %d (dropped %d)",
        len(combined), len(filtered), len(combined) - len(filtered),
    )

    # Re-verify location against the real detail page text — but only for
    # Adzuna jobs. Adzuna's own structured `location` field can be wrong —
    # e.g. a job actually based in Lahore, Pakistan was labeled
    # `area: ['India'], display_name: 'India'` by Adzuna itself, which no
    # field-level check could ever catch. Greenhouse/Lever jobs don't need
    # this: their location field comes straight from the employer (no
    # syndication mislabeling), and we already have their full JD text from
    # the same API call, so we just check that in-memory instead of an extra
    # network fetch — important given there can be 600+ ATS jobs per run.
    verified = []
    blocked = 0
    for job in filtered:
        if job.get("source") == "adzuna":
            full_text = fetch_full_description(job.get("apply_url", ""))
            job["_full_text"] = full_text
            is_blocked = bool(full_text and _text_mentions_blocked_location(full_text, profile))
            is_target = _is_target_location(None, job.get("location", ""), profile) and not (
                full_text and _text_mentions_non_target(full_text, profile)
            )
        elif job.get("source") == "linkedin":
            # Same lazy-fetch pattern as Adzuna: the guest search endpoint
            # only returns title/company/location/date, not the description.
            from scraper.linkedin_guest_scraper import fetch_job_detail
            full_text = fetch_job_detail(job.get("_linkedin_id", "")) if job.get("_linkedin_id") else None
            job["jd_text"] = full_text or ""
            job["_full_text"] = full_text
            is_blocked = bool(full_text and _text_mentions_blocked_location(full_text, profile))
            is_target = _is_target_location(None, job.get("location", ""), profile) and not (
                full_text and _text_mentions_non_target(full_text, profile)
            )
        else:
            # ATS sources give a trustworthy location field directly from the
            # employer plus the full JD text in the same call — check both,
            # no extra fetch needed.
            job["_full_text"] = job.get("jd_text", "")
            is_blocked = (
                _is_blocked_location(None, job.get("location", ""), profile)
                or _text_mentions_blocked_location(job.get("jd_text", ""), profile)
            )
            is_target = _is_target_location(None, job.get("location", ""), profile) and not (
                _text_mentions_non_target(job.get("jd_text", ""), profile)
            )

        if is_blocked:
            blocked += 1
            logger.info("  Blocking job (location check) — blocked location: %s @ %s",
                        job.get("title", "")[:40], job.get("company", ""))
            continue

        # Tag, don't drop: QA/testing roles and out-of-target-location roles
        # still get scraped/scored, just routed into separate digest sections
        # later.
        job["is_qa_role"] = _is_qa_role(job.get("title", ""))
        job["is_target_location"] = is_target
        job["is_target_role"] = _is_target_role(job.get("title", ""), profile)
        job["target_company"] = _is_target_company(job.get("company", ""), profile)
        verified.append(job)

    if blocked:
        logger.info("Location re-check: blocked %d additional job(s)", blocked)

    return verified


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from candidate_profile.loader import load_profile, EXAMPLE_PROFILE_PATH

    profile = load_profile(sys.argv[1] if len(sys.argv) > 1 else str(EXAMPLE_PROFILE_PATH))
    jobs = scrape_all_jobs(profile)
    print(f"\nFound {len(jobs)} qualifying jobs:\n")
    for j in jobs:
        ts = j["posted_at"].isoformat() if j["posted_at"] else "unknown"
        print(f"  [{j['source'].upper():8}] {j['title']} @ {j['company']} ({j['location']}) — {ts}")
        print(f"           {j['apply_url']}\n")
