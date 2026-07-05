"""
setup_profile.py — one-time onboarding: turn your resume into a working
candidate_profile/config.yaml.

Usage:
    python setup_profile.py --resume path/to/your_resume.docx
    python setup_profile.py --resume path/to/your_resume.pdf

Makes ONE Gemini call (your own free-tier GEMINI_API_KEY — the same client
the pipeline already uses for resume optimization) to extract a first-draft
profile from your resume text. This is a DRAFT, not gospel: review every
field it writes before your first real run, exactly like the pipeline's own
"never fabricate" rule for tailored resumes. Fix anything wrong by hand in
candidate_profile/config.yaml.
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).parent / "candidate_profile"
CONFIG_PATH = PROFILE_DIR / "config.yaml"


def _extract_docx_text(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "Reading a PDF resume requires pypdf. Install it with: pip install pypdf"
        )
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_resume_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(p)
    if suffix == ".docx":
        return _extract_docx_text(p)
    raise ValueError(f"Unsupported resume format '{suffix}' — use .docx or .pdf")


EXTRACTION_PROMPT = """You are helping a job seeker set up an automated job-search tool. \
Read their resume below and extract a structured profile as JSON. Never invent \
anything not stated or clearly implied by the resume — leave a field as an empty \
string/list if you can't determine it confidently.

Resume:
{resume_text}

Return ONLY a JSON object with exactly these keys:
- name (string, full name)
- title (string, current or most recent job title, generalized to a standard
  form suitable for job search, e.g. "Product Manager" not "Sr. PM II")
- years_experience (integer, total years of relevant professional experience)
- location (string, "City, Country" - their current location)
- target_location_country (string, lowercase country name matching `location`,
  e.g. "india", "united states", "united kingdom" - used to match job postings)
- search_terms (list of 4-8 strings - job titles to search for, based on their
  actual title and career trajectory; include close variants, e.g. for a
  "Product Manager" include "Senior Product Manager", "Associate Product
  Manager", "Product Owner")
- adjacent_industries (list of 1-3 strings - the industries their experience
  is in or closely adjacent to, e.g. "fintech", "e-commerce", "healthcare")
- roles (object - one entry per employer in their work history, in the same
  order as the resume, oldest experience last; each key is a short lowercase
  slug like "acme_corp" and each value is a list of 1-2 lowercase keyword
  strings that would appear in that employer's name on the page, e.g.
  {{"acme_corp": ["acme corp", "acme"]}} - used to locate that employer's
  bullet points in the resume DOCX later, so the keywords must be exact
  substrings of how the company name appears in the resume text above)
No preamble, no markdown, just the JSON object.
"""


def call_gemini_extraction(resume_text: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your .env file first (see "
            ".env.example). This reuses the same free-tier Gemini call the "
            "pipeline uses for resume optimization — no new cost."
        )
    from google import genai
    client = genai.Client(api_key=api_key)
    prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:8000])
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = (response.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def build_context_block(extracted: dict) -> str:
    """A short factual paragraph the LLM can quote verbatim for screening
    answers — mirrors the shape the pipeline's optimize prompts expect."""
    name = extracted.get("name", "")
    title = extracted.get("title", "")
    years = extracted.get("years_experience", "")
    location = extracted.get("location", "")
    industries = ", ".join(extracted.get("adjacent_industries", []))
    return (
        "Candidate facts (use these; do NOT invent others):\n"
        f"- Name: {name}\n"
        f"- Current role: {title}\n"
        f"- {years} years experience across {industries}\n"
        "- Notice period: [fill in]\n"
        f"- Current location: {location}\n"
        "- Do NOT state a specific salary figure — use the placeholder '[expected CTC]'\n"
    )


def build_config(extracted: dict, resume_dest_name: str) -> dict:
    years = extracted.get("years_experience") or 5
    try:
        years = int(years)
    except (TypeError, ValueError):
        years = 5
    return {
        "name": extracted.get("name", ""),
        "title": extracted.get("title", ""),
        "years_experience": years,
        "context": build_context_block(extracted),
        "location": extracted.get("location", ""),
        "target_location_country": extracted.get("target_location_country", ""),
        "target_location_aliases": ["remote"],
        "blocked_locations": [],
        "search_terms": extracted.get("search_terms", []) or [],
        "target_companies": [],
        "experience_exclude_years": max(years + 5, 10),
        "adjacent_industries": extracted.get("adjacent_industries", []) or [],
        "resume_path": f"candidate_profile/{resume_dest_name}",
        "secondary_resume_path": None,
        "primary_track_label": "Primary",
        "secondary_track_label": "Secondary Resume Match",
        "roles": extracted.get("roles", {}) or {},
        "writing_style": {
            "no_spaced_dashes": True,
            "capitalize_role_titles": True,
            "avoid_ai_buzzwords": True,
        },
        "adzuna_country_code": "us",
        "excluded_companies": [],
    }


def write_config(config: dict) -> Path:
    import yaml
    PROFILE_DIR.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True, width=100)
    return CONFIG_PATH


def main():
    parser = argparse.ArgumentParser(
        description="Turn your resume into a candidate_profile/config.yaml (one-time setup)."
    )
    parser.add_argument("--resume", required=True, help="Path to your resume (.docx or .pdf)")
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing candidate_profile/config.yaml",
    )
    args = parser.parse_args()

    if CONFIG_PATH.exists() and not args.force:
        logger.error(
            "%s already exists. Pass --force to overwrite, or edit it by hand.",
            CONFIG_PATH,
        )
        sys.exit(1)

    resume_path = Path(args.resume)
    logger.info("Reading resume: %s", resume_path)
    try:
        resume_text = load_resume_text(args.resume)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if len(resume_text.strip()) < 100:
        logger.error(
            "Extracted only %d characters from the resume — the file may be "
            "image-based or empty. A text-based .docx works best.",
            len(resume_text),
        )
        sys.exit(1)

    logger.info("Extracting profile via Gemini (one free-tier call)...")
    try:
        extracted = call_gemini_extraction(resume_text)
    except Exception as exc:
        logger.error("Profile extraction failed: %s", exc)
        sys.exit(1)

    PROFILE_DIR.mkdir(exist_ok=True)
    resume_dest_name = f"resume{resume_path.suffix.lower()}"
    resume_dest = PROFILE_DIR / resume_dest_name
    shutil.copy2(resume_path, resume_dest)
    logger.info("Copied resume to %s", resume_dest)

    config = build_config(extracted, resume_dest_name)
    config_path = write_config(config)
    logger.info("Wrote %s", config_path)

    print()
    print("=" * 70)
    print("Draft profile written. REVIEW THESE BEFORE YOUR FIRST RUN:")
    print("=" * 70)
    print(f"  name:                    {extracted.get('name')}")
    print(f"  title:                   {extracted.get('title')}")
    print(f"  years_experience:        {extracted.get('years_experience')}")
    print(f"  location:                {extracted.get('location')}")
    print(f"  target_location_country: {extracted.get('target_location_country')}")
    print(f"  search_terms:            {extracted.get('search_terms')}")
    print(f"  adjacent_industries:     {extracted.get('adjacent_industries')}")
    print(f"  roles (for resume patching): {list((extracted.get('roles') or {}).keys())}")
    print()
    print(f"Edit {CONFIG_PATH} to fix anything above, add your own target_companies,")
    print("fill in the notice-period placeholder in 'context', and set adzuna_country_code")
    print("and excluded_companies (e.g. your current employer). Then run:")
    print("  python main.py --dry-run")
    print("=" * 70)


if __name__ == "__main__":
    main()
