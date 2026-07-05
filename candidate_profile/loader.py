"""
candidate_profile/loader.py — loads candidate_profile/config.yaml into a Profile object.

This is the single generalization seam: every module reads the candidate's
name/title/location/search terms/resume paths/role list from a Profile
instance instead of hardcoding them. One user = one profile file.
"""

import logging
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


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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

    industry_bands = raw.get("industry_bands") or list(_DEFAULT_INDUSTRY_BANDS)
    skill_areas = raw.get("skill_areas") or list(_DEFAULT_SKILL_AREAS)
    role_level_bands = raw.get("role_level_bands") or list(_DEFAULT_ROLE_LEVEL_BANDS)
    archetypes = raw.get("archetypes") or dict(_DEFAULT_ARCHETYPES)

    profile = Profile(
        name=raw["name"],
        title=raw["title"],
        years_experience=int(raw["years_experience"]),
        context=raw["context"],
        location=raw["location"],
        target_location_country=raw["target_location_country"],
        target_location_aliases=raw.get("target_location_aliases", []) or [],
        blocked_locations=raw.get("blocked_locations", []) or [],
        search_terms=raw.get("search_terms", []) or [],
        target_companies=raw.get("target_companies", []) or [],
        experience_exclude_years=int(raw.get("experience_exclude_years", 10)),
        adjacent_industries=raw.get("adjacent_industries", []) or [],
        industry_bands=industry_bands,
        skill_areas=skill_areas,
        role_level_bands=role_level_bands,
        archetypes=archetypes,
        resume_path=raw.get("resume_path", "profile/resume.docx"),
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
