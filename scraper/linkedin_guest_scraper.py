"""
Zero-key job source: LinkedIn's public, unauthenticated `jobs-guest` search
endpoints. No API key, no login, works for any country/city out of the box —
this is what lets the pipeline run with zero third-party keys at all (Adzuna
becomes optional, not required).

Technique adapted from `.agents/skills/linkedin-search` in
github.com/MadsLorentzen/ai-job-search (MIT), which itself credits
github.com/mikkelkrogsholm/skills for the job-search CLI pattern. Same
retry-with-backoff + HTML-regex-parsing approach, ported from their
TypeScript CLI to Python so it shares a runtime with the rest of this repo.

Personal use only: automated access to LinkedIn is against their Terms of
Service. Keep volume low (this module fetches a handful of pages per run,
same order of magnitude as a person manually paging through search results).
"""

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ai-job-search4all/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_MAX_RETRIES = 4
_RESULTS_PER_PAGE = 10
_MAX_PAGES_PER_TERM = 2  # keep volume low — see module docstring
_REQUEST_TIMEOUT = 15


def _get_with_retry(url: str) -> str | None:
    """GET with exponential backoff on 429/5xx. Returns None (fail-open) on
    exhausted retries or a 4xx that isn't 429 — a blocked/rate-limited request
    here should never break the rest of the scrape."""
    delay = 0.5
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                logger.warning("LinkedIn guest request failed: %s", exc)
                return None
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == _MAX_RETRIES:
                logger.warning("LinkedIn guest request exhausted retries: HTTP %d", resp.status_code)
                return None
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
            continue
        if not resp.ok:
            logger.warning("LinkedIn guest request failed: HTTP %d", resp.status_code)
            return None
        return resp.text
    return None


def _decode_entities(text: str) -> str:
    return (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    )


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


_CARD_PATTERN = re.compile(
    r'<div class="base-card[^"]*"[^>]*data-entity-urn="urn:li:jobPosting:(\d+)"[\s\S]*?'
    r'<h3 class="base-search-card__title">([\s\S]*?)</h3>[\s\S]*?'
    r'<h4 class="base-search-card__subtitle">[\s\S]*?<a[^>]*>([\s\S]*?)</a>[\s\S]*?'
    r'<span class="job-search-card__location">([\s\S]*?)</span>',
    re.MULTILINE,
)
_DATE_PATTERN = re.compile(r'<time[^>]+datetime="([^"]+)"')


def _parse_search_html(html: str) -> list[dict]:
    jobs = []
    for match in _CARD_PATTERN.finditer(html):
        job_id, title, company, location = match.groups()
        # LinkedIn repeats data-entity-urn on both the wrapping <div> and a
        # <time> element that appears *before* it in source order, so scan a
        # window spanning both sides of the match rather than assuming the
        # date always follows.
        window_start = max(0, match.start() - 1000)
        card_html = html[window_start:match.start() + 1000]
        date_match = _DATE_PATTERN.search(card_html)
        jobs.append({
            "title": _decode_entities(_strip_tags(title)),
            "company": _decode_entities(_strip_tags(company)),
            "location": _decode_entities(_strip_tags(location)),
            "apply_url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "source": "linkedin",
            "posted_at": _parse_date(date_match.group(1)) if date_match else None,
            "_linkedin_id": job_id,
        })
    return jobs


def _parse_date(raw: str):
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_job_detail(job_id: str) -> str | None:
    """Full description text for a single job — a second request, so callers
    should only call this for jobs that already passed the cheap card-level
    filters (title/company/location), not the whole result set."""
    url = f"{BASE_URL}/jobPosting/{job_id}"
    html = _get_with_retry(url)
    if not html:
        return None
    desc_match = re.search(
        r'<div class="show-more-less-html__markup[^"]*">([\s\S]*?)</div>', html
    )
    if not desc_match:
        return None
    return _decode_entities(_strip_tags(desc_match.group(1)))


def search_jobs(query: str, location: str, max_pages: int = _MAX_PAGES_PER_TERM) -> list[dict]:
    """Search LinkedIn's public guest job listings for one query+location
    pair. Returns the standard job dict shape used across scraper/ (minus
    jd_text, which is filled in lazily via fetch_job_detail for jobs that
    survive the cheap filters — see scraper/job_scraper.py)."""
    all_jobs: list[dict] = []
    for page in range(max_pages):
        params = {
            "keywords": query,
            "location": location,
            "start": page * _RESULTS_PER_PAGE,
        }
        url = f"{BASE_URL}/seeMoreJobPostings/search?{urlencode(params)}"
        html = _get_with_retry(url)
        if not html:
            break
        page_jobs = _parse_search_html(html)
        if not page_jobs:
            break
        all_jobs.extend(page_jobs)
    return all_jobs


def scrape_linkedin_guest(profile) -> list[dict]:
    """Zero-key job source for scraper.job_scraper.scrape_all_jobs. Searches
    profile.search_terms against profile.location (falling back to
    target_location_country), dedup happens in the caller like every other
    source. jd_text is left empty here — job_scraper.py fetches full
    descriptions lazily, same pattern as Adzuna's fetch_full_description."""
    location = profile.location or profile.target_location_country
    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    for term in profile.search_terms:
        try:
            logger.info("  Searching LinkedIn (guest): '%s' in '%s'", term, location)
            results = search_jobs(term, location)
        except Exception as exc:
            logger.error("  LinkedIn guest search failed for '%s': %s", term, exc)
            continue
        for job in results:
            job_id = job.get("_linkedin_id")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            job["jd_text"] = ""  # filled in lazily by job_scraper's full-text recheck
            all_jobs.append(job)

    logger.info("LinkedIn (guest): fetched %d raw entries across all search terms", len(all_jobs))
    return all_jobs


if __name__ == "__main__":
    import sys
    from candidate_profile.loader import load_profile, EXAMPLE_PROFILE_PATH

    profile = load_profile(sys.argv[1] if len(sys.argv) > 1 else str(EXAMPLE_PROFILE_PATH))
    jobs = scrape_linkedin_guest(profile)
    print(f"\nFound {len(jobs)} raw LinkedIn (guest) postings:\n")
    for j in jobs:
        print(f"  {j['title']} @ {j['company']} ({j['location']})")
        print(f"    {j['apply_url']}\n")
