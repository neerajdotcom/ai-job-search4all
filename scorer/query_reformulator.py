"""
scorer/query_reformulator.py — Dynamic search query expansion and reformulation.

Inspired by observable-job-agent:
If the initial scrape pass returns too few results or 0 qualifying matches (e.g.,
because the candidate's exact title is too niche or company-specific), this module
dynamically queries the LLM to generate broader synonyms, industry variants, and
adjacent titles to perform an automated secondary search pass.
"""

import logging
from typing import List, Optional

from core.llm import default_llm

logger = logging.getLogger(__name__)

REFORMULATION_PROMPT = """You are an expert technical recruiter. A candidate's job search returned too few results with their current search terms: {search_terms}.
Their background is:
- Target Title: {title}
- Total Experience: {years_experience} years
- Summary / Facts: {context}
- Target Industries: {industries}

Generate 4 to 6 broader, standardized, and commonly-posted job title search queries that match their skillset on public job boards (like LinkedIn, Indeed, Greenhouse, Remotive).
Include both exact variants (e.g. "Staff" vs "Senior", "Lead" vs "Manager", "Product Owner" vs "Technical Product Manager") and adjacent industry terminology.

Return ONLY a JSON array of search query strings.
Example: ["Senior Backend Engineer", "Lead Python Developer", "Platform Engineer", "Distributed Systems Engineer"]
"""


def reformulate_search_terms(profile, current_terms: Optional[List[str]] = None, llm=None) -> List[str]:
    """
    Generate alternative and expanded search queries based on candidate profile.
    """
    client = llm or default_llm
    terms = current_terms or profile.search_terms or [profile.title]
    prompt = REFORMULATION_PROMPT.format(
        search_terms=", ".join(terms),
        title=profile.title,
        years_experience=profile.years_experience,
        context=(profile.context or "")[:500],
        industries=", ".join(profile.adjacent_industries or ["Technology"]),
    )

    try:
        data = client.generate_json(prompt, temperature=0.3)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            expanded = [t.strip() for t in data if t.strip() and t.strip().lower() not in [x.lower() for x in terms]]
            logger.info("Reformulated queries for '%s': %s", profile.title, expanded)
            return expanded
        elif isinstance(data, dict) and "search_terms" in data and isinstance(data["search_terms"], list):
            expanded = [t.strip() for t in data["search_terms"] if t.strip()]
            logger.info("Reformulated queries for '%s': %s", profile.title, expanded)
            return expanded
    except Exception as exc:
        logger.warning("Query reformulation failed: %s", exc)

    # Fallback heuristic expansion if LLM is unavailable
    fallback = []
    base = profile.title.strip()
    if "senior" not in base.lower() and profile.years_experience >= 5:
        fallback.append(f"Senior {base}")
    if "lead" not in base.lower() and profile.years_experience >= 7:
        fallback.append(f"Lead {base}")
    if "manager" in base.lower():
        fallback.append(base.replace("Manager", "Director"))
    if "developer" in base.lower():
        fallback.append(base.replace("Developer", "Engineer"))
    if "engineer" in base.lower():
        fallback.append(base.replace("Engineer", "Developer"))
    return [f for f in fallback if f.lower() not in [x.lower() for x in terms]]
