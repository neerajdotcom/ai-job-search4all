"""
ats_scraper.py — Direct employer ATS feeds (Greenhouse, Lever, Ashby)

Why this exists: Adzuna is a syndicated aggregator, which means its listings
can be stale (a job that's been live for weeks before Adzuna's crawler picks
it up) or have location data the aggregator itself mislabels. Greenhouse,
Lever, and Ashby are public, unauthenticated, official APIs that gaming
companies expose specifically so applicants can browse their own open roles
directly — no ToS risk, no scraping, and the data comes straight from the
source with no syndication lag. Bonus: all three APIs return the full job
description in the same response, unlike Adzuna's 500-char snippet, so no
second fetch is needed to check experience requirements or location text.

Company list was validated by probing each slug against the public API and
confirming it returns real job postings (see project notes for the discovery
run). Add a slug here only after confirming it 200s with jobs.
"""

import logging
import re
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 10

# Greenhouse: company_name comes from the API response itself, so no display
# name mapping is needed — just the board token (usually lowercase company name).
GREENHOUSE_COMPANIES = [
    "scopely", "krafton", "roblox", "epicgames", "riotgames", "wildlifestudios",
    "dreamgames",
]

# Lever: the posting API doesn't include a display name, so map slug -> name.
LEVER_COMPANIES = {
    "jamcity": "Jam City",
}

# Ashby: same shape of public, unauthenticated job-board API as Greenhouse/Lever.
# Voodoo's Ashby board (126 jobs at last check) is far more complete than their
# Lever board (34) — Lever looks like a stale/secondary listing — so Voodoo
# lives here instead of in LEVER_COMPANIES to avoid scraping the smaller, less
# current duplicate.
ASHBY_COMPANIES = {
    "badrobotgames": "Bad Robot Games",
    "joyteractive": "Joyteractive",
    "voodoo": "Voodoo",
    "moonactive": "Moon Active",
}

# Workable: public widget API, same "official board the employer exposes for
# applicants" shape as the three above. Slug -> display name. Evolution/Playtech/
# Kindred confirmed correct (account name matches) on a network-enabled probe,
# though each had 0 open postings at probe time — kept anyway since this is a
# live open-positions API that will surface jobs the moment any are posted.
WORKABLE_COMPANIES: dict[str, str] = {
    "evolution": "Evolution",
    "playtech": "Playtech",
    "kindred": "Kindred",
}

# Unverified gaming/iGaming slugs to probe on a network-enabled run, then move
# the ones that resolve into the dicts above. Greenhouse: api .../boards/{slug}/jobs;
# Lever: api.lever.co/v0/postings/{slug}; Ashby: .../job-board/{slug};
# Workable: apply.workable.com/api/v1/widget/accounts/{slug}. The slugs below
# were probed and 404'd under these exact guesses — they may use a different
# careers platform (Workday, SuccessFactors, custom) not supported by this
# scraper, or a different slug than guessed; not worth re-guessing blindly.
CANDIDATE_SLUGS = {
    "greenhouse": ["zynga", "playtika", "niantic", "rovio", "sciplay", "lightandwonder"],
    "lever": ["miniclip", "tiltingpoint", "socialpoint"],
    "ashby": ["applovin"],
    "workable": ["betsson", "betway", "pragmaticplay"],
}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def scrape_greenhouse() -> list:
    jobs = []
    for slug in GREENHOUSE_COMPANIES:
        try:
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                params={"content": "true"},
                timeout=_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("  Greenhouse fetch failed for '%s': %s", slug, exc)
            continue

        for item in data.get("jobs", []):
            posted_at = None
            try:
                # first_published reflects the original posting date, not the
                # last metadata touch — closer to the real "is this fresh" signal.
                raw_date = item.get("first_published") or item.get("updated_at")
                if raw_date:
                    posted_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except Exception:
                pass

            jobs.append({
                "title": (item.get("title") or "").strip(),
                "company": item.get("company_name", slug).strip(),
                "location": (item.get("location") or {}).get("name", "") or "",
                "jd_text": _strip_html(item.get("content", "")),
                "apply_url": item.get("absolute_url", ""),
                "source": "greenhouse",
                "posted_at": posted_at,
            })

        logger.info("  Greenhouse '%s': fetched %d jobs", slug, len(data.get("jobs", [])))

    return jobs


def scrape_lever() -> list:
    jobs = []
    for slug, display_name in LEVER_COMPANIES.items():
        try:
            resp = requests.get(
                f"https://api.lever.co/v0/postings/{slug}",
                params={"mode": "json"},
                timeout=_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("  Lever fetch failed for '%s': %s", slug, exc)
            continue

        for item in data:
            posted_at = None
            created_ms = item.get("createdAt")
            if created_ms:
                try:
                    posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
                except Exception:
                    pass

            categories = item.get("categories", {}) or {}
            jd_text = " ".join(filter(None, [
                item.get("descriptionPlain", ""),
                item.get("additionalPlain", ""),
            ]))

            jobs.append({
                "title": (item.get("text") or "").strip(),
                "company": display_name,
                "location": categories.get("location", "") or item.get("workplaceType", "") or "",
                "jd_text": jd_text,
                "apply_url": item.get("hostedUrl", ""),
                "source": "lever",
                "posted_at": posted_at,
            })

        logger.info("  Lever '%s': fetched %d jobs", slug, len(data))

    return jobs


def scrape_ashby() -> list:
    jobs = []
    for slug, display_name in ASHBY_COMPANIES.items():
        try:
            resp = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                timeout=_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("  Ashby fetch failed for '%s': %s", slug, exc)
            continue

        for item in data.get("jobs", []):
            posted_at = None
            raw_date = item.get("publishedAt")
            if raw_date:
                try:
                    posted_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            jobs.append({
                "title": (item.get("title") or "").strip(),
                "company": display_name,
                "location": item.get("location", "") or "",
                "jd_text": item.get("descriptionPlain", "") or "",
                "apply_url": item.get("jobUrl", ""),
                "source": "ashby",
                "posted_at": posted_at,
            })

        logger.info("  Ashby '%s': fetched %d jobs", slug, len(data.get("jobs", [])))

    return jobs


def scrape_workable() -> list:
    jobs = []
    for slug, display_name in WORKABLE_COMPANIES.items():
        try:
            resp = requests.get(
                f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
                params={"details": "true"},
                timeout=_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("  Workable fetch failed for '%s': %s", slug, exc)
            continue

        for item in data.get("jobs", []):
            posted_at = None
            raw_date = item.get("published_on") or item.get("created_at")
            if raw_date:
                try:
                    posted_at = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                except Exception:
                    pass

            # Workable splits location across city/country fields.
            loc = item.get("location", {}) or {}
            location = ", ".join(filter(None, [
                loc.get("city", ""), loc.get("region", ""), loc.get("country", ""),
            ])) or ("Remote" if loc.get("telecommuting") else "")

            jobs.append({
                "title": (item.get("title") or "").strip(),
                "company": data.get("name", display_name) or display_name,
                "location": location,
                "jd_text": _strip_html(item.get("description", "") or ""),
                "apply_url": item.get("url") or item.get("application_url", ""),
                "source": "workable",
                "posted_at": posted_at,
            })

        logger.info("  Workable '%s': fetched %d jobs", slug, len(data.get("jobs", [])))

    return jobs


def scrape_all_ats_jobs() -> list:
    logger.info("Scraping direct employer ATS feeds (Greenhouse + Lever + Ashby + Workable)")
    return scrape_greenhouse() + scrape_lever() + scrape_ashby() + scrape_workable()
