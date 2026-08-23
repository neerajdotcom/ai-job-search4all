import os
import logging
from typing import List, Dict
import httpx

logger = logging.getLogger(__name__)

# Default endpoint – can be overridden via env var for future changes
DEFAULT_API_URL = os.getenv("JOBGETHER_API_URL", "https://jobgether.com/api/v1/jobs")
DEFAULT_TIMEOUT = int(os.getenv("JOBGETHER_API_TIMEOUT", "15"))


def discover_api_endpoint() -> str:
    """Return the JobGether API endpoint.

    The function respects the ``JOBGETHER_API_URL`` environment variable; if not
    set it falls back to the known public endpoint. No authentication is added –
    callers must handle any auth/CORS requirements themselves.
    """
    return DEFAULT_API_URL.rstrip("/")


def fetch_jobs_via_api(profile: "Profile") -> List[Dict]:
    """Fetch job listings from JobGether's public JSON API.

    Parameters
    ----------
    profile:
        ``candidate_profile.loader.Profile`` – only ``search_terms`` and
        ``location`` are used to build the query.

    Returns
    -------
    List[Dict]
        A list of dictionaries matching the project's internal job schema.
        If the request fails the function returns an empty list and logs a
        warning; the hybrid scraper will then fall back to the browser based
        approach.
    """
    endpoint = discover_api_endpoint()
    params = {
        "q": ",".join(profile.search_terms or []),
        "location": profile.location or "",
    }
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(endpoint, params=params, headers={"User-Agent": "JobGetherScraper/1.0"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("JobGether API request failed: %s", exc)
        return []

    jobs: List[Dict] = []
    for item in data.get("results", []):
        jobs.append({
            "title": item.get("title", "").strip(),
            "company": item.get("company", {}).get("name", "").strip(),
            "location": item.get("location", "").strip(),
            "apply_url": item.get("apply_url", "").strip(),
            "posted_at": None,  # API does not guarantee a parsable timestamp
            "source": "jobgether_api",
        })
    logger.info("JobGether API returned %d jobs", len(jobs))
    return jobs
