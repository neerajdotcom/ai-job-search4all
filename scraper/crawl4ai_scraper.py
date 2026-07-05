"""crawl4ai-based scrapers for India-facing job boards.

Adds Naukri, Indeed, Foundit (Monster India), Instahyre and Wellfound as extra
sources for ``scrape_all_jobs()``. Produces the *same* job-dict shape as
``ats_scraper.py`` so the scorer/optimizer/digest need no changes.

Design notes (kept deliberately minimal — see .claude/skills/minimal-code-review):
- **Table-driven.** One ``SITES`` config list + one generic crawl loop, not five
  near-duplicate functions. Adding a board is a new dict entry.
- **Hybrid extraction.** Free per-site CSS selectors first; if a page yields zero
  rows, fall back to one Groq pass over crawl4ai's clean markdown — reusing the
  scorer's existing Groq client / retry / daily-quota state (no new LLM path).
- **Fail-open everywhere.** Any failure (crawl4ai not installed, browser launch,
  a datacenter-IP block, a parse error) returns ``[]`` so the existing
  Adzuna + ATS pipeline is never broken. Gated behind ``ENABLE_CRAWL4AI``.
"""
import asyncio
import json
import logging
import os
from datetime import datetime  # noqa: F401  (kept for parity with other scrapers' posted_at typing)
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# crawl4ai pulls in Playwright and is only installed where a browser is wanted.
# Import under a guard so this module stays importable (and unit-checkable) even
# where crawl4ai isn't present — callers fall open to no crawl4ai jobs.
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
    _CRAWL4AI_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - depends on optional dep
    _CRAWL4AI_AVAILABLE = False
    _IMPORT_ERROR = _exc

# Cap rows kept per (site, term) query — bounds the CI job's runtime and stays
# polite to each board. Listing pages typically show ~20-25 results.
_MAX_RESULTS_PER_QUERY = 25
_PAGE_TIMEOUT_MS = 60000
# Default headless UA is an easy bot tell — present a realistic desktop UA.
_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _browser_config():
    """Headless browser tuned to look less like a bot. Optional proxy via
    CRAWL4AI_PROXY for egress-restricted/proxied environments (unset locally)."""
    kwargs = dict(headless=True, verbose=False, enable_stealth=True, user_agent=_USER_AGENT)
    proxy = os.getenv("CRAWL4AI_PROXY", "").strip()
    if proxy:
        kwargs["proxy"] = proxy
    return BrowserConfig(**kwargs)


def _run_config(strategy):
    """Per-request config with crawl4ai's anti-bot / JS-SPA helpers enabled, so a
    login-gated or JS-rendered board (e.g. Instahyre) has a chance to populate
    its results list before extraction. Still bounded and cache-bypassing."""
    return CrawlerRunConfig(
        extraction_strategy=strategy,
        cache_mode=CacheMode.BYPASS,
        page_timeout=_PAGE_TIMEOUT_MS,
        magic=True,                    # crawl4ai's bundled anti-bot evasion
        simulate_user=True,
        override_navigator=True,
        delay_before_return_html=2.0,  # let late JS render the results
    )

# Per-site config. ``url`` is a template; the search term is slugified with
# ``term_sep`` (hyphens for path-style URLs, '+' for query-string URLs). CSS
# schemas are best-effort — for boards whose markup we can't verify from a
# blocked CI IP, the Groq markdown fallback does the real work.
SITES = [
    {
        "source": "naukri",
        "url": "https://www.naukri.com/{term}-jobs",
        "term_sep": "-",
        "schema": {
            "name": "naukri",
            "baseSelector": "div.srp-jobtuple-wrapper, article.jobTuple",
            "fields": [
                {"name": "title", "selector": "a.title", "type": "text"},
                {"name": "apply_url", "selector": "a.title", "type": "attribute", "attribute": "href"},
                {"name": "company", "selector": "a.comp-name, a.subTitle", "type": "text"},
                {"name": "location", "selector": "span.locWdth, span.loc, li.location", "type": "text"},
                {"name": "jd_text", "selector": "span.job-desc, ul.job-description", "type": "text"},
            ],
        },
    },
    {
        "source": "indeed",
        "url": "https://in.indeed.com/jobs?q={term}&l=India",
        "term_sep": "+",
        "schema": {
            "name": "indeed",
            "baseSelector": "div.job_seen_beacon, div.cardOutline",
            "fields": [
                {"name": "title", "selector": "h2.jobTitle span", "type": "text"},
                {"name": "apply_url", "selector": "a.jcs-JobTitle, h2.jobTitle a", "type": "attribute", "attribute": "href"},
                {"name": "company", "selector": "[data-testid='company-name'], span.companyName", "type": "text"},
                {"name": "location", "selector": "[data-testid='text-location'], div.companyLocation", "type": "text"},
                {"name": "jd_text", "selector": "div.job-snippet, ul[style]", "type": "text"},
            ],
        },
    },
    {
        "source": "foundit",
        "url": "https://www.foundit.in/srp/results?query={term}&locations=india",
        "term_sep": "+",
        "schema": {
            "name": "foundit",
            "baseSelector": "div.srpResultCardContainer, div.cardContainer",
            "fields": [
                {"name": "title", "selector": "div.jobTitle, h3.jobTitle", "type": "text"},
                {"name": "apply_url", "selector": "a", "type": "attribute", "attribute": "href"},
                {"name": "company", "selector": "div.companyName, span.companyName", "type": "text"},
                {"name": "location", "selector": "div.details.location, span.location", "type": "text"},
                {"name": "jd_text", "selector": "div.jobDescription, div.description", "type": "text"},
            ],
        },
    },
    {
        "source": "instahyre",
        "url": "https://www.instahyre.com/search-jobs/?q={term}",
        "term_sep": "+",
        "schema": {
            "name": "instahyre",
            "baseSelector": "div.job-listing, div.opportunity, div.profile, div.search-result, li.job, [class*='job-card'], [class*='jobCard']",
            "fields": [
                {"name": "title", "selector": "a.job-title, a[href*='/job'], h3, h2, [class*='title']", "type": "text"},
                {"name": "apply_url", "selector": "a.job-title, a[href*='/job'], a", "type": "attribute", "attribute": "href"},
                {"name": "company", "selector": "div.company-name, span.company, [class*='company']", "type": "text"},
                {"name": "location", "selector": "div.location, span.location, [class*='location']", "type": "text"},
                {"name": "jd_text", "selector": "div.job-description, [class*='description'], p", "type": "text"},
            ],
        },
    },
    {
        "source": "wellfound",
        "url": "https://wellfound.com/role/r/{term}",
        "term_sep": "-",
        "schema": {
            "name": "wellfound",
            "baseSelector": "div[data-test='JobSearchResult'], div.styles_component__job",
            "fields": [
                {"name": "title", "selector": "a[data-test='job-link'], h2", "type": "text"},
                {"name": "apply_url", "selector": "a[data-test='job-link'], a", "type": "attribute", "attribute": "href"},
                {"name": "company", "selector": "h2.inline, a[data-test='startup-link']", "type": "text"},
                {"name": "location", "selector": "span.location, div.locations", "type": "text"},
                {"name": "jd_text", "selector": "div.description, p", "type": "text"},
            ],
        },
    },
]


def _format_url(site: dict, term: str) -> str:
    slug = site["term_sep"].join(term.lower().split())
    return site["url"].format(term=slug)


def _to_job(row: dict, source: str, base_url: str):
    """Normalize one extracted row into the standard job dict, or None if unusable."""
    if not isinstance(row, dict):
        return None
    title = (row.get("title") or "").strip()
    url = (row.get("apply_url") or row.get("url") or "").strip()
    if not title or not url:
        return None
    if url.startswith("/"):
        url = urljoin(base_url, url)
    return {
        "title": title,
        "company": (row.get("company") or "").strip(),
        "location": (row.get("location") or "").strip(),
        "jd_text": (row.get("jd_text") or row.get("description") or "").strip(),
        "apply_url": url,
        "source": source,
        # Listing pages rarely expose a reliable machine-readable post date;
        # None means _is_fresh() keeps it (it can't be judged stale).
        "posted_at": None,
    }


def _groq_extract(markdown: str, source: str) -> list:
    """Fallback: extract listings from clean markdown via the scorer's Groq client.

    Reuses scorer.match_scorer's throttle + daily-quota short-circuit so these
    extraction calls share the same per-run Groq budget as scoring. Fails open
    to []. Costs a little Groq free-tier quota only when CSS selectors miss.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or not markdown:
        return []
    try:
        from scorer.match_scorer import _generate_with_retry, _daily_quota_exhausted
        from groq import Groq
    except Exception as exc:
        logger.warning("crawl4ai Groq fallback unavailable: %s", exc)
        return []
    if _daily_quota_exhausted[0]:
        return []
    prompt = (
        "You are parsing a job board's search-results page. Extract every real "
        "job posting (ignore ads, filters, navigation, and pagination). Return a "
        'JSON object: {"jobs": [{"title": str, "company": str, "location": str, '
        '"url": str}]}. Use absolute URLs where present. Page text:\n\n'
        + markdown[:12000]
    )
    try:
        raw = _generate_with_retry(Groq(api_key=api_key), prompt)
        if not raw:
            return []
        data = json.loads(raw)
        rows = data.get("jobs", []) if isinstance(data, dict) else []
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        logger.warning("crawl4ai Groq fallback failed for %s: %s", source, exc)
        return []


def _parse_rows(result) -> list:
    if not result or not getattr(result, "success", False):
        return []
    content = getattr(result, "extracted_content", None)
    if not content:
        return []
    try:
        data = json.loads(content)
    except Exception:
        return []
    return data if isinstance(data, list) else []


async def _crawl_site(crawler, site: dict, terms: list) -> list:
    out = []
    strategy = JsonCssExtractionStrategy(site["schema"])
    for term in terms:
        url = _format_url(site, term)
        run_cfg = _run_config(strategy)
        try:
            result = await crawler.arun(url=url, config=run_cfg)
        except Exception as exc:
            logger.warning("crawl4ai %s '%s' fetch failed: %s", site["source"], term, exc)
            continue
        rows = _parse_rows(result)
        if not rows and getattr(result, "markdown", None):
            rows = _groq_extract(str(result.markdown), site["source"])
        for row in rows[:_MAX_RESULTS_PER_QUERY]:
            job = _to_job(row, site["source"], url)
            if job:
                out.append(job)
    return out


async def _run_all() -> list:
    if not _CRAWL4AI_AVAILABLE:
        logger.warning("crawl4ai not installed (%s) — skipping web-board scrape", _IMPORT_ERROR)
        return []
    # Imported here (not at module top) to avoid any import-order coupling and to
    # keep this module importable without the scraper package fully initialized.
    from scraper.job_scraper import SEARCH_TERMS

    jobs = []
    async with AsyncWebCrawler(config=_browser_config()) as crawler:
        for site in SITES:
            try:
                site_jobs = await _crawl_site(crawler, site, SEARCH_TERMS)
            except Exception as exc:
                logger.warning("crawl4ai site %s failed: %s", site["source"], exc)
                continue
            logger.info("crawl4ai %s: %d jobs", site["source"], len(site_jobs))
            jobs.extend(site_jobs)
    return jobs


def scrape_crawl4ai_jobs() -> list:
    """Sync entry point for scrape_all_jobs(). Always returns a list, never raises."""
    if not _CRAWL4AI_AVAILABLE:
        logger.warning("crawl4ai not installed — skipping web-board scrape")
        return []
    try:
        return asyncio.run(_run_all())
    except Exception as exc:
        logger.error("crawl4ai scraping crashed: %s", exc)
        return []


async def _debug_site(source: str):
    """Verbose single-board run for local validation from an open-egress machine
    (CI/sandbox IPs are anti-bot-blocked or network-policy-blocked). Prints, per
    term: success/status, markdown size, CSS rows, Groq-fallback rows, errors and
    a markdown sample — enough to tune selectors against a real fetch."""
    if not _CRAWL4AI_AVAILABLE:
        print("crawl4ai not installed — `pip install crawl4ai && crawl4ai-setup`")
        return
    from scraper.job_scraper import SEARCH_TERMS
    site = next((s for s in SITES if s["source"] == source), None)
    if not site:
        print(f"unknown site '{source}'. Known: {[s['source'] for s in SITES]}")
        return
    strategy = JsonCssExtractionStrategy(site["schema"])
    async with AsyncWebCrawler(config=_browser_config()) as crawler:
        for term in SEARCH_TERMS[:3]:
            url = _format_url(site, term)
            print(f"\n=== {source} | {term} ===\n{url}")
            try:
                result = await crawler.arun(url=url, config=_run_config(strategy))
            except Exception as exc:
                print("  fetch EXCEPTION:", exc)
                continue
            md = str(getattr(result, "markdown", "") or "")
            css_rows = _parse_rows(result)
            print(f"  success={getattr(result, 'success', None)} "
                  f"status={getattr(result, 'status_code', None)} "
                  f"markdown_chars={len(md)} css_rows={len(css_rows)}")
            err = getattr(result, "error_message", None)
            if err:
                print("  error_message:", str(err)[:200])
            for r in css_rows[:3]:
                print("   css·", r)
            if not css_rows and md:
                groq_rows = _groq_extract(md, source)
                print(f"  groq_fallback_rows={len(groq_rows)}")
                for r in groq_rows[:3]:
                    print("   groq·", r)
            print("  markdown sample:", md[:400].replace("\n", " "))


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if len(sys.argv) > 1:
        # Single-board diagnostic run, e.g.: python -m scraper.crawl4ai_scraper instahyre
        asyncio.run(_debug_site(sys.argv[1].lower()))
    else:
        found = scrape_crawl4ai_jobs()
        print(f"\nTotal crawl4ai jobs: {len(found)}")
        for j in found[:10]:
            print(f"  [{j['source']}] {j['title']} | {j['company']} | {j['location']} | {j['apply_url']}")
