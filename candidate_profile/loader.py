"""
candidate_profile/loader.py — loads candidate_profile/config.yaml into a Profile object.

This is the single generalization seam: every module reads the candidate's
name/title/location/search terms/resume paths/role list from a Profile
instance instead of hardcoding them. One user = one profile file.
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = Path(__file__).parent / "config.yaml"
EXAMPLE_PROFILE_PATH = Path(__file__).parent / "config.example.yaml"

# Generic default archetypes — a candidate's writing-style/tailoring framing
# bias. Sensible for most delivery/PM-style roles; override in config.yaml
# under `archetypes:` if your target roles need different framings.
_DEFAULT_ARCHETYPES = {
    "process-discipline": "planning, governance, predictable on-time delivery",
    "hands-on-execution": "day-to-day operational delivery, execution speed, direct ownership",
    "cross-functional-leadership": "coordinating across teams/functions, systems thinking, stakeholder alignment",
}

# Generic default industry bands (best -> worst), replacing the gaming-
# specific 5-tier rubric. `points` must sum to <= the INDUSTRY category max
# (35) enforced in scorer/match_scorer.py's prompt; the scorer only uses the
# top band's value as the max, so keep the highest band at 35 unless you
# also update the prompt's stated max.
_DEFAULT_INDUSTRY_BANDS = [
    {"value": "core", "label": "Core industry match", "points": 35,
     "hint": "the role's industry is the same as, or a near-exact match for, your target industry"},
    {"value": "adjacent", "label": "Adjacent industry", "points": 18,
     "hint": "a related/neighboring industry — see adjacent_industries below"},
    {"value": "unrelated", "label": "Unrelated industry", "points": 6,
     "hint": "a different industry with no meaningful overlap"},
]

# Generic defaults for the other two merit-rubric bands (skills, role level).
# Each entry is {label, points}; scorer/match_scorer.py sums them into the
# max-100 rubric. Override in config.yaml for a more granular breakdown
# (e.g. splitting "skills" into several weighted sub-areas).
_DEFAULT_SKILL_AREAS = [
    {"label": "Skills and tools relevant to the target role, as shown in the resume", "points": 40},
]

_DEFAULT_ROLE_LEVEL_BANDS = [
    {"label": "Role is at or near the candidate's target seniority/title", "points": 25},
    {"label": "Role is a step below the candidate's target seniority/title but on the same track", "points": 15},
]


@dataclass
class Profile:
    # --- identity, used to template every LLM prompt ---
    name: str
    title: str
    years_experience: int
    context: str  # short factual paragraph the LLM can quote for screening Qs

    # --- location targeting ---
    location: str                      # human-readable, e.g. "Bangalore, India"
    target_location_country: str       # e.g. "india" — matched against job location text
    target_location_aliases: list[str] = field(default_factory=list)  # e.g. ["remote"]
    blocked_locations: list[str] = field(default_factory=list)  # hard-excluded countries/cities
    # Optional. Cities/regions to search job boards in — LinkedIn's guest
    # search is per-location, so each entry becomes a separate search pass.
    # Leave empty to fall back to searching just `location`. Example:
    # ["Kolkata, India", "Mumbai, India", "Pune, India"] to cast a wider net
    # for a candidate open to multiple cities within their target country.
    search_locations: list[str] = field(default_factory=list)

    # --- search & scoring calibration ---
    search_terms: list[str] = field(default_factory=list)
    target_companies: list[str] = field(default_factory=list)  # presentation-only highlight
    experience_exclude_years: int = 10   # auto-exclude roles requiring >= this many years
    adjacent_industries: list[str] = field(default_factory=list)
    industry_bands: list[dict] = field(default_factory=lambda: list(_DEFAULT_INDUSTRY_BANDS))
    skill_areas: list[dict] = field(default_factory=lambda: list(_DEFAULT_SKILL_AREAS))
    role_level_bands: list[dict] = field(default_factory=lambda: list(_DEFAULT_ROLE_LEVEL_BANDS))
    archetypes: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_ARCHETYPES))

    # --- resume files ---
    resume_path: str = "profile/resume.docx"
    secondary_resume_path: Optional[str] = None
    primary_track_label: str = "Primary"
    secondary_track_label: str = "Secondary Resume Match"

    # --- role/company map for DOCX bullet patching (optimizer.patch_docx) ---
    # role_key -> list of keywords used to locate that employer's heading in
    # the resume DOCX. Order matters (first match wins) — put more specific
    # keywords first if two employer names could overlap.
    roles: dict[str, list[str]] = field(default_factory=dict)

    # --- writing-style preferences, folded into every optimize prompt ---
    writing_style: dict = field(default_factory=lambda: {
        "no_spaced_dashes": True,
        "capitalize_role_titles": True,
        "avoid_ai_buzzwords": True,
    })

    # --- misc ---
    adzuna_country_code: str = "us"  # Adzuna's ISO-ish country slug, e.g. "in", "gb", "us"
    excluded_companies: list[str] = field(default_factory=list)  # e.g. your current employer

    @property
    def industry_summary(self) -> str:
        """Short phrase for prompts, e.g. 'gaming and iGaming'."""
        if self.adjacent_industries:
            return " and ".join(self.adjacent_industries[:2])
        return "your target industry"

    @property
    def resume_slug(self) -> str:
        """Filesystem-safe stem for generated resume filenames."""
        return "".join(c for c in self.name if c.isalnum()) or "Candidate"

    @property
    def effective_search_locations(self) -> list[str]:
        """List of cities/regions to search each job board in — falls back
        to `[location]` when `search_locations` is empty, so old profiles
        without the field still work unchanged. Scrapers iterate over this
        list, one search per entry."""
        return self.search_locations or [self.location]


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def create_profile_from_dict(raw: dict) -> Profile:
    """Instantiate a Profile object from a raw dictionary with sensible defaults."""
    industry_bands = raw.get("industry_bands") or list(_DEFAULT_INDUSTRY_BANDS)
    skill_areas = raw.get("skill_areas") or list(_DEFAULT_SKILL_AREAS)
    role_level_bands = raw.get("role_level_bands") or list(_DEFAULT_ROLE_LEVEL_BANDS)
    archetypes = raw.get("archetypes") or dict(_DEFAULT_ARCHETYPES)

    years = raw.get("years_experience", 5)
    try:
        years = int(years)
    except (ValueError, TypeError):
        years = 5

    return Profile(
        name=raw.get("name", "Candidate"),
        title=raw.get("title", "Professional"),
        years_experience=years,
        context=raw.get("context", ""),
        location=raw.get("location", "Remote"),
        target_location_country=raw.get("target_location_country", "remote"),
        target_location_aliases=raw.get("target_location_aliases", ["remote"]) or ["remote"],
        blocked_locations=raw.get("blocked_locations", []) or [],
        search_locations=raw.get("search_locations", []) or [],
        search_terms=raw.get("search_terms", []) or [],
        target_companies=raw.get("target_companies", []) or [],
        experience_exclude_years=int(raw.get("experience_exclude_years", max(years + 5, 10))),
        adjacent_industries=raw.get("adjacent_industries", []) or [],
        industry_bands=industry_bands,
        skill_areas=skill_areas,
        role_level_bands=role_level_bands,
        archetypes=archetypes,
        resume_path=raw.get("resume_path", "candidate_profile/sample_resume.docx"),
        secondary_resume_path=raw.get("secondary_resume_path") or None,
        primary_track_label=raw.get("primary_track_label", "Primary"),
        secondary_track_label=raw.get("secondary_track_label", "Secondary Resume Match"),
        roles=raw.get("roles", {}) or {},
        writing_style=raw.get("writing_style") or {
            "no_spaced_dashes": True,
            "capitalize_role_titles": True,
            "avoid_ai_buzzwords": True,
        },
        adzuna_country_code=raw.get("adzuna_country_code", "us"),
        excluded_companies=raw.get("excluded_companies", []) or [],
    )


def extract_name_from_filename(filename: str) -> Optional[str]:
    """Extract candidate name from file name if text-level extraction fails."""
    if not filename:
        return None
    stem = Path(filename).stem
    # Remove common filler words
    stem = re.sub(r"(?i)\b(resume|cv|curriculum_vitae|profile|latest|updated|final|doc|docx|pdf|\d{4}|v\d+)\b", " ", stem)
    # Convert camelCase / PascalCase to spaces: "NeerajBanerjee" -> "Neeraj Banerjee"
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    # Replace delimiters with space
    stem = re.sub(r"[-_.]+", " ", stem).strip()
    # Clean non-alphanumeric except spaces
    stem = re.sub(r"[^\w\s\.\-']", "", stem)
    stem = re.sub(r"\d+", "", stem).strip()
    words = [w.capitalize() for w in stem.split() if len(w) > 1 and w.lower() not in {"resume", "cv", "pdf", "docx"}]
    if 1 <= len(words) <= 4:
        candidate_name = " ".join(words)
        if len(candidate_name) >= 2:
            return candidate_name
    return None


def extract_candidate_name(resume_text: str, filename: Optional[str] = None) -> str:
    """
    Intelligently extract the candidate's name from raw resume text.
    Handles headers, compound contact lines, pipes, bullets, emails, and filename fallback.
    """
    if not resume_text or not resume_text.strip():
        if filename:
            fn_name = extract_name_from_filename(filename)
            if fn_name:
                return fn_name
        return "Candidate"

    lines = [line.strip() for line in resume_text.strip().split("\n") if line.strip()]
    if not lines:
        if filename:
            fn_name = extract_name_from_filename(filename)
            if fn_name:
                return fn_name
        return "Candidate"

    # Ignored boilerplate headers
    ignore_phrases = {
        "resume", "curriculum vitae", "cv", "professional summary", "summary",
        "profile", "bio", "contact", "about me", "personal details", "work experience",
        "experience", "skills", "education", "projects", "confidential"
    }

    # Clean candidate name candidate line
    for line in lines[:8]:
        clean = line.strip()
        clean_lower = clean.lower()

        # Skip section headers or contact rows
        if clean_lower in ignore_phrases or clean_lower.startswith(("http", "www", "email:", "phone:", "tel:", "mobile:", "contact:", "address:")):
            continue

        # Strip email addresses, URLs, and phone numbers first
        clean = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "", clean).strip()
        clean = re.sub(r"https?://\S+|www\.\S+|linkedin\.com/\S+|github\.com/\S+", "", clean).strip()
        clean = re.sub(r"\(?\+?\d{1,3}\)?[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", "", clean).strip()

        # Split on primary delimiters: "John Doe | Senior Engineer" or "Jane Doe - Senior Dev" or "Pooja Patel, PMP"
        for delimiter in ["|", "•", "—", "–", " - ", ",", "/", "\t"]:
            if delimiter in clean:
                tokens = [t.strip() for t in clean.split(delimiter) if t.strip()]
                if tokens:
                    clean = tokens[0]
                break

        # Remove trailing parentheses e.g. "Malini Sharma (PMP)"
        clean = re.sub(r"\(.*?\)", "", clean).strip()

        # Clean remaining punctuation except hyphens/periods/apostrophes in names (supports Unicode letters e.g. Alex Müller, J. Doe, O'Connor)
        clean = re.sub(r"[^\w\s\.\-']", "", clean).strip()
        clean = re.sub(r"\d+", "", clean).strip()

        # Validation: A valid name is usually 1 to 4 words, between 2 and 40 characters
        words = [w for w in clean.split() if w]
        if 1 <= len(words) <= 4 and 2 <= len(clean) <= 40:
            if clean.lower() not in ignore_phrases:
                title_words = {"senior", "lead", "junior", "staff", "principal", "manager", "engineer", "developer", "director", "architect", "designer", "consultant", "analyst", "specialist", "coordinator"}
                # If not all words in the line are purely title words
                if not all(w.lower() in title_words for w in words):
                    return re.sub(r"\s+", " ", clean).strip()

    if filename:
        fn_name = extract_name_from_filename(filename)
        if fn_name:
            return fn_name

    return "Candidate"


def create_profile_from_text(
    resume_text: str,
    location_override: Optional[str] = None,
    country_override: Optional[str] = None,
    title_override: Optional[str] = None,
    name_override: Optional[str] = None,
    filename: Optional[str] = None,
    llm=None,
) -> Profile:
    """
    Extract a Profile on the fly from raw resume text.
    Enables zero-friction instant matching when a user pastes their resume.
    """
    from core.llm import default_llm
    from setup_profile import EXTRACTION_PROMPT, build_context_block

    client = llm or default_llm
    prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:8000])

    extracted = None
    try:
        extracted = client.generate_json(prompt, temperature=0.1)
    except Exception as exc:
        logger.warning("LLM profile extraction failed (%s), using local heuristic parser", exc)

    if not extracted or not isinstance(extracted, dict) or not extracted.get("title"):
        # Deterministic local heuristic parser fallback (zero-key)
        lines = [line.strip() for line in resume_text.strip().split("\n") if line.strip()]
        detected_name = name_override.strip() if name_override and name_override.strip() else extract_candidate_name(resume_text, filename=filename)

        # Extract title from early lines, skipping section headers
        section_headers = {"professional summary", "summary", "skills summary", "skills", "experience", "work experience", "education", "academics", "contact", "curriculum vitae", "resume"}
        detected_title = title_override or ""
        
        if not detected_title:
            for line in lines[:15]:
                clean_l = line.strip().lower()
                if clean_l in section_headers:
                    continue
                # If pipe separated line with employer and title (e.g., Company | Title | Dates)
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    for part in parts:
                        if any(t in part.lower() for t in ["manager", "coordinator", "lead", "producer", "engineer", "director", "specialist", "analyst", "scrum master", "consultant"]):
                            detected_title = part
                            break
                    if detected_title:
                        break
                
                # Check for direct title line or opening summary phrase
                if any(t in clean_l for t in [
                    "localization project manager", "senior project coordinator", "project coordinator",
                    "technical program manager", "program manager", "project manager", "delivery manager",
                    "game producer", "producer", "scrum master", "sdet", "qa lead", "software engineer"
                ]):
                    if len(line) < 70 and "@" not in line and not line.lower().startswith("m:"):
                        detected_title = line
                        break
                elif any(t in clean_l for t in ["project management", "product management", "quality engineering", "software engineering"]):
                    if "project management" in clean_l:
                        detected_title = "Project Manager"
                        break
                    elif "product management" in clean_l:
                        detected_title = "Product Manager"
                        break

        if not detected_title:
            detected_title = "Professional"
        else:
            detected_title = re.sub(r"\s+", " ", detected_title).strip()

        # Extract experience years
        exp_m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience", resume_text, re.I)
        years = int(exp_m.group(1)) if exp_m else 10

        # Extract search terms strictly based on substantive domain phrases
        clean_title = re.sub(r"[^a-zA-Z0-9\s–-]", "", detected_title).strip() or "Candidate"
        clean_title = re.sub(r"\s+", " ", clean_title).strip()
        search_terms = [clean_title]
        if "senior" not in clean_title.lower() and "lead" not in clean_title.lower():
            search_terms.append(f"Senior {clean_title}")

        title_l = clean_title.lower()
        res_lower = resume_text.lower()

        # Strict whole-word domain triggers (avoiding partial matches like 'testing' -> QA)
        if re.search(r"\b(gaming|igaming|casino|slot\s+game|game\s+producer|game\s+production)\b", res_lower):
            search_terms.extend([
                "Game Producer",
                "Project Manager - Gaming",
                "Senior Project Coordinator",
                "Agile Delivery Manager",
            ])
        if re.search(r"\b(localization|subtitling|dubbing|transcreation|translation\s+management|lqa)\b", res_lower):
            search_terms.extend([
                "Localization Project Manager",
                "Senior Subtitling Manager",
                "Content Localization Lead",
                "OTT Content Operations Lead",
            ])
        if re.search(r"\b(quality\s+assurance|test\s+automation|sdet|qa\s+lead|qa\s+manager|automation\s+framework)\b", res_lower):
            search_terms.extend(["Senior QA Lead", "Lead SDET", "Quality Engineering Manager"])
        if re.search(r"\b(product\s+manager|product\s+management|product\s+owner|prd|roadmap\s+strategy)\b", res_lower):
            search_terms.extend(["Senior Product Manager", "Product Lead", "Technical Product Manager"])
        if re.search(r"\b(software\s+engineer|backend\s+developer|frontend\s+developer|full\s*stack\s+engineer|golang\s+developer)\b", res_lower):
            search_terms.extend(["Senior Software Engineer", "Backend Developer", "Full Stack Engineer"])
        if re.search(r"\b(data\s+scientist|machine\s+learning\s+engineer|ai\s+researcher|deep\s+learning\s+scientist)\b", res_lower):
            search_terms.extend(["Lead Machine Learning Engineer", "Staff Data Scientist", "Senior Data Engineer"])
        if re.search(r"\b(creative\s+director|art\s+director|ui/ux\s+designer|product\s+designer|brand\s+designer)\b", res_lower):
            search_terms.extend(["Executive Creative Director", "Principal Product Designer", "Head of Design"])

        extracted = {
            "name": detected_name or "Candidate",
            "title": clean_title,
            "years_experience": years,
            "location": location_override or "Worldwide (Remote)",
            "target_location_country": country_override or "remote",
            "search_terms": list(dict.fromkeys(search_terms)),
            "adjacent_industries": ["media", "entertainment", "streaming", "ott", "localization", "tech", "saas", "software"],
            "roles": {},
        }

    # Apply overrides if user provided them in the UI
    if name_override and name_override.strip():
        extracted["name"] = name_override.strip()
    elif not extracted.get("name") or extracted.get("name") == "Candidate":
        extracted["name"] = extract_candidate_name(resume_text)

    if title_override and title_override.strip():
        extracted["title"] = title_override.strip()
        if title_override.strip() not in extracted.get("search_terms", []):
            extracted["search_terms"] = [title_override.strip()] + extracted.get("search_terms", [])
    if location_override and location_override.strip():
        extracted["location"] = location_override.strip()
    if country_override and country_override.strip():
        extracted["target_location_country"] = country_override.strip().lower()

    if not extracted.get("name"):
        extracted["name"] = "Candidate"
    if not extracted.get("title"):
        extracted["title"] = "Professional"
    if not extracted.get("location"):
        extracted["location"] = "Worldwide (Remote)"
    if not extracted.get("target_location_country"):
        extracted["target_location_country"] = "remote"

    context = build_context_block(extracted)
    extracted["context"] = context

    return create_profile_from_dict(extracted)


def load_profile(path: Optional[str] = None) -> Profile:
    """
    Load profile/config.yaml (or the given path) into a Profile.

    Raises FileNotFoundError with a clear message if no profile exists yet —
    callers should catch this and point the user at `setup_profile.py`.
    """
    profile_path = Path(path) if path else DEFAULT_PROFILE_PATH
    if not profile_path.exists():
        raise FileNotFoundError(
            f"No profile found at '{profile_path}'. Run "
            f"'python setup_profile.py --resume your_resume.docx' first, "
            f"or copy profile/config.example.yaml to profile/config.yaml "
            f"and fill it in by hand."
        )

    raw = _read_yaml(profile_path)
    required = ["name", "title", "years_experience", "context", "location", "target_location_country"]
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise ValueError(
            f"profile at '{profile_path}' is missing required field(s): {', '.join(missing)}"
        )

    profile = create_profile_from_dict(raw)
    logger.info(
        "Loaded profile for '%s' (%s, %d yrs) from '%s'",
        profile.name, profile.title, profile.years_experience, profile_path,
    )
    return profile


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else str(EXAMPLE_PROFILE_PATH)
    p = load_profile(path)
    print(f"name={p.name!r} title={p.title!r} years={p.years_experience} "
          f"location={p.location!r} target_country={p.target_location_country!r}")
    print(f"search_terms={p.search_terms}")
    print(f"roles={list(p.roles.keys())}")
