"""
scraper/remotive_scraper.py — Zero-key scraper adapter for Remotive Remote Jobs.

Public API: https://remotive.com/api/remote-jobs
No API key, no login required. Provides high-quality, verified remote roles
in Software Development, Product, Design, QA, Management, Sales, Marketing, etc.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"
_REQUEST_TIMEOUT = 15


def _strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
}


def scrape_remotive(profile, limit_per_term: int = 15) -> List[Dict[str, Any]]:
    """
    Fetch remote job listings from Remotive matching the candidate's search_terms.
    Returns normalized job dictionaries.
    """
    search_terms = list(profile.search_terms or [profile.title])
    generic_titles = {"project manager", "senior project manager", "program manager", "delivery manager", "operations manager", "lead", "director"}
    if getattr(profile, "adjacent_industries", None):
        for term in list(profile.search_terms or []):
            if term.lower().strip() in generic_titles:
                for ind in profile.adjacent_industries[:2]:
                    combined_query = f"{term} {ind}"
                    if combined_query not in search_terms:
                        search_terms.append(combined_query)

    all_jobs: List[Dict[str, Any]] = []
    seen_urls = set()

    for term in search_terms[:8]:
        params = {"search": term, "limit": limit_per_term}
        try:
            resp = requests.get(REMOTIVE_API_URL, params=params, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Remotive API returned HTTP %d for query '%s'", resp.status_code, term)
                continue
            data = resp.json()
            jobs_list = data.get("jobs", [])
            logger.info("Remotive API returned %d jobs for query '%s'", len(jobs_list), term)

            for item in jobs_list:
                apply_url = item.get("url", "")
                if not apply_url or apply_url in seen_urls:
                    continue
                seen_urls.add(apply_url)

                title = (item.get("title") or "").strip()
                company = (item.get("company_name") or "").strip()
                location = (item.get("candidate_required_location") or "Worldwide (Remote)").strip()
                raw_desc = item.get("description", "")
                jd_text = _strip_html(raw_desc)
                pub_date_str = item.get("publication_date")

                posted_at = None
                if pub_date_str:
                    try:
                        # Format: "2024-05-01T12:00:00"
                        posted_at = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    except Exception:
                        posted_at = None

                job_dict = {
                    "title": title,
                    "company": company,
                    "location": f"Remote ({location})" if "remote" not in location.lower() else location,
                    "apply_url": apply_url,
                    "jd_text": jd_text,
                    "source": "remotive",
                    "posted_at": posted_at,
                    "is_target_location": True,  # Remotive is remote-first
                }
                all_jobs.append(job_dict)

        except Exception as exc:
            logger.warning("Failed Remotive request for '%s': %s", term, exc)
            continue

    logger.info("Total Remotive unique jobs scraped: %d", len(all_jobs))
    return all_jobs
