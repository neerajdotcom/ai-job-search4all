import os
import logging
import asyncio
from typing import List, Dict

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# Configurable values – can be overridden via environment variables
DEFAULT_TIMEOUT = int(os.getenv("JOBGETHER_BROWSER_TIMEOUT", "30"))  # seconds
SCROLL_PAUSE = float(os.getenv("JOBGETHER_SCROLL_PAUSE", "1.0"))   # seconds between scroll steps
MAX_SCROLL_ATTEMPTS = int(os.getenv("JOBGETHER_MAX_SCROLL_ATTEMPTS", "20"))


def _extract_job_data(element) -> Dict:
    """Extract a job dictionary from a Playwright element.

    The function attempts to pull the most common fields using a set of fallback
    selectors. If a selector is missing we return an empty string for that field.
    """
    try:
        title = element.query_selector("h2, .job-title, .title")
        title_text = title.inner_text().strip() if title else ""
    except Exception:
        title_text = ""
    try:
        company = element.query_selector(".company, .company-name")
        company_text = company.inner_text().strip() if company else ""
    except Exception:
        company_text = ""
    try:
        location = element.query_selector(".location, .job-location")
        location_text = location.inner_text().strip() if location else ""
    except Exception:
        location_text = ""
    try:
        link_el = element.query_selector("a[href]")
        apply_url = link_el.get_attribute("href").strip() if link_el else ""
    except Exception:
        apply_url = ""
    return {
        "title": title_text,
        "company": company_text,
        "location": location_text,
        "apply_url": apply_url,
        "posted_at": None,
        "source": "jobgether_browser",
    }


async def _scrape_async(profile) -> List[Dict]:
    """Core async implementation that drives Playwright.

    The function loads the JobGether matches page, scrolls to the bottom to load
    all lazy‑loaded results, then extracts job cards using CSS selectors.
    """
    url = f"https://jobgether.com/talent/matches?utm_source=brevo&utm_campaign=Email%20to%20prospect%20-%20Flow%20prospect%20-%20Active%20version&utm_medium=email&utm_id=499"
    jobs: List[Dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="JobGetherScraper/1.0")
        page = await context.new_page()
        try:
            await page.goto(url, timeout=DEFAULT_TIMEOUT * 1000)
        except PlaywrightTimeoutError:
            logger.warning("Page load timed out for %s", url)
            await browser.close()
            return []

        # Scroll loop – keep scrolling until no new content appears or limit reached
        previous_height = None
        for attempt in range(MAX_SCROLL_ATTEMPTS):
            current_height = await page.evaluate("() => document.body.scrollHeight")
            if previous_height == current_height:
                break
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_PAUSE)
            previous_height = current_height

        # After scrolling, collect all job card elements
        elements = await page.query_selector_all("article[data-job-id]")
        if not elements:
            elements = await page.query_selector_all(".job-card, .result-item, .listing")
        logger.info("Found %d job elements on the page", len(elements))
        for el in elements:
            job = _extract_job_data(el)
            if job["title"]:
                jobs.append(job)

        await browser.close()
    return jobs


def scrape_jobgether_browser(profile) -> List[Dict]:
    """Public wrapper that runs the async Playwright scraper.

    This function is deliberately synchronous so it can be called from the
    existing codebase without requiring the caller to be async-aware.
    """
    try:
        return asyncio.run(_scrape_async(profile))
    except Exception as exc:
        logger.error("JobGether browser scrape failed: %s", exc)
        return []
