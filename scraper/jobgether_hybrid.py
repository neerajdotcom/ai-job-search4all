"""Hybrid scraper for JobGether.

Provides a single entry point :func:`scrape_jobgether` that first attempts to
fetch jobs via the public JSON API and, if that returns no results (or raises an
exception), falls back to the headless‑browser scraper.

Both underlying implementations live in ``scraper/jobgether_api.py`` and
``scraper/jobgether_browser.py``. The function returns a list of job dictionaries
compatible with the rest of the project (same schema used by ``scrape_all_jobs``).
"""

from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

# Import the two concrete scrapers. Import errors are caught so the package can be
# imported even if optional dependencies (Playwright) are missing – the hybrid will
# simply fallback to the API path.
try:
    from .jobgether_api import fetch_jobs_via_api
except Exception as exc:  # pragma: no cover
    logger.warning("JobGether API module could not be imported: %s", exc)
    fetch_jobs_via_api = None

try:
    from .jobgether_browser import scrape_jobgether_browser
except Exception as exc:  # pragma: no cover
    logger.warning("JobGether browser module could not be imported: %s", exc)
    scrape_jobgether_browser = None


def scrape_jobgether(profile: "Profile") -> List[Dict]:
    """Retrieve JobGether matches using the best available method.

    The function follows a simple strategy:

    1. If the API scraper is available, call it.  If it returns a non‑empty list
       the result is returned directly.
    2. Otherwise (or if the API returned no jobs) fall back to the browser
       implementation, provided it could be imported.
    3. If both methods fail, an empty list is returned and a warning is logged.
    """
    # Try API first
    if fetch_jobs_via_api:
        try:
            api_jobs = fetch_jobs_via_api(profile)
            if api_jobs:
                logger.info("JobGether: using API scraper – %d jobs", len(api_jobs))
                return api_jobs
        except Exception as exc:  # pragma: no cover
            logger.warning("JobGether API scrape error: %s", exc)

    # Fallback to browser
    if scrape_jobgether_browser:
        try:
            browser_jobs = scrape_jobgether_browser(profile)
            if browser_jobs:
                logger.info(
                    "JobGether: using browser scraper – %d jobs", len(browser_jobs)
                )
                return browser_jobs
        except Exception as exc:  # pragma: no cover
            logger.error("JobGether browser scrape error: %s", exc)

    logger.warning("JobGether: no jobs could be retrieved by any method")
    return []
