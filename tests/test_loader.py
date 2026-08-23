"""
tests/test_loader.py — Unit tests for candidate profile loading, schema validation, and on-the-fly profiling.
"""

import pytest
from candidate_profile.loader import (
    Profile,
    create_profile_from_dict,
    create_profile_from_text,
    load_profile,
    EXAMPLE_PROFILE_PATH,
)


def test_load_example_profile():
    """Verify loading the shipped example profile configuration."""
    profile = load_profile(str(EXAMPLE_PROFILE_PATH))
    assert isinstance(profile, Profile)
    assert profile.name != ""
    assert profile.title != ""
    assert profile.years_experience > 0
    assert len(profile.search_terms) > 0
    assert isinstance(profile.roles, dict)


def test_create_profile_from_dict_defaults():
    """Verify fallback defaults when creating a profile from minimal data."""
    raw = {
        "name": "Jane Smith",
        "title": "Data Scientist",
        "years_experience": "6",
        "location": "New York, NY",
        "target_location_country": "united states",
    }
    p = create_profile_from_dict(raw)
    assert p.name == "Jane Smith"
    assert p.title == "Data Scientist"
    assert p.years_experience == 6
    assert p.experience_exclude_years >= 11
    assert "remote" in p.target_location_aliases
    assert len(p.industry_bands) >= 3


def test_create_profile_from_text_mocked(sample_resume_text):
    """Test on-the-fly profile generation with a mock LLM."""
    class MockLLM:
        def generate_json(self, prompt, temperature=0.1):
            return {
                "name": "John Doe",
                "title": "Senior Backend Engineer",
                "years_experience": 8,
                "location": "San Francisco, CA",
                "target_location_country": "united states",
                "search_terms": ["Senior Backend Engineer", "Lead Developer"],
                "adjacent_industries": ["fintech"],
                "roles": {"acme_corp": ["acme corp"], "beta_tech": ["beta tech"]},
            }

    mock_llm = MockLLM()
    p = create_profile_from_text(
        sample_resume_text,
        name_override="Jonathan Doe",
        title_override="Lead Systems Architect",
        location_override="Remote, Global",
        country_override="remote",
        llm=mock_llm,
    )
    assert p.name == "Jonathan Doe"            # name override applied
    assert p.title == "Lead Systems Architect"  # title override applied
    assert p.location == "Remote, Global"       # location override applied
    assert p.years_experience == 8
    assert "acme_corp" in p.roles


def test_extract_candidate_name_heuristics():
    """Verify smart candidate name extraction across complex resume header formats."""
    from candidate_profile.loader import extract_candidate_name

    cases = [
        ("Malini Sharma | Senior Project Lead | Pune, India | malini@email.com", "Malini Sharma"),
        ("John Doe\nSenior Backend Engineer\nSan Francisco, CA", "John Doe"),
        ("Jane Doe - Senior React Developer, Pune, India - jane@email.com", "Jane Doe"),
        ("CURRICULUM VITAE\nAlex Müller\nMachine Learning Lead", "Alex Müller"),
        ("RESUME\nDr. Sarah O'Connor (PhD)\nBioinformatics Lead", "Dr. Sarah O'Connor"),
        ("Pooja Patel, PMP\nTechnical Project Manager", "Pooja Patel"),
        ("Vrindula Boppsworth - Principal Data Scientist", "Vrindula Boppsworth"),
        ("", "Candidate"),
        ("   \n\n  ", "Candidate"),
    ]
    for text, expected in cases:
        extracted = extract_candidate_name(text)
        assert extracted == expected, f"Failed for '{text}': got '{extracted}', expected '{expected}'"

    # Test filename fallbacks
    assert extract_candidate_name("", filename="NeerajBanerjee_Resume.pdf") == "Neeraj Banerjee"
    assert extract_candidate_name("", filename="Neeraj_Banerjee_CV.docx") == "Neeraj Banerjee"
    assert extract_candidate_name("", filename="john-doe-resume-2024.pdf") == "John Doe"
    assert extract_candidate_name("Pooja Patel\nEngineer", filename="NeerajBanerjee_Resume.pdf") == "Pooja Patel"
