"""
tests/test_scorer.py — Unit tests for keyword pre-filtering, ghost-job heuristics, and scoring rubric construction.
"""

import pytest
from scorer.match_scorer import (
    build_scoring_instructions,
    is_ghost_job,
    prefilter_jobs,
    _extract_required_years,
)
from scorer.query_reformulator import reformulate_search_terms


def test_build_scoring_instructions(sample_profile):
    rubric = build_scoring_instructions(sample_profile)
    assert "SKILLS" in rubric
    assert "INDUSTRY" in rubric
    assert "ROLE LEVEL" in rubric
    assert "match_score" in rubric


def test_ghost_job_detection():
    # 1. Short JD text (< 100 words)
    job_short = {"company": "Acme", "title": "Dev", "jd_text": "Join our cool company and code."}
    flagged, reason = is_ghost_job(job_short, {})
    assert flagged is True
    assert "too short" in reason.lower()

    # 2. Placeholder company name
    job_anon = {"company": "Confidential", "title": "Senior Dev", "jd_text": "A " * 150}
    flagged, reason = is_ghost_job(job_anon, {})
    assert flagged is True
    assert "no identifiable company" in reason.lower()

    # 3. Valid normal job
    job_valid = {"company": "Stripe", "title": "Senior Engineer", "jd_text": "A " * 150}
    flagged, reason = is_ghost_job(job_valid, {})
    assert flagged is False


def test_experience_requirement_extraction():
    text1 = "Looking for a candidate with 5+ years of software development experience."
    assert _extract_required_years(text1) == 5

    text2 = "Requirements: 7-10 yrs exp in building distributed backends."
    assert _extract_required_years(text2) == 7  # Takes lower bound of range

    text3 = "No prior experience required."
    assert _extract_required_years(text3) is None


def test_keyword_prefiltering(sample_profile, sample_resume_text):
    jobs = [
        {"title": "Senior Backend Engineer", "company": "Co A", "jd_text": "Python PostgreSQL Redis Docker", "is_target_location": True, "is_qa_role": False},
        {"title": "Executive Assistant", "company": "Co B", "jd_text": "Calendar scheduling travel booking", "is_target_location": True, "is_qa_role": False},
        {"title": "QA Lead", "company": "Co C", "jd_text": "Selenium testing automation", "is_target_location": True, "is_qa_role": True},
    ]
    ranked = prefilter_jobs(jobs, sample_resume_text, sample_profile, top_n=2)
    assert len(ranked) == 2
    assert ranked[0]["title"] == "Senior Backend Engineer"


def test_query_reformulation_fallback(sample_profile):
    """Test heuristic query expansion when LLM is offline."""
    terms = reformulate_search_terms(sample_profile, current_terms=["Senior Backend Engineer"], llm=None)
    assert len(terms) >= 1
    assert any("Engineer" in t or "Developer" in t or "Lead" in t for t in terms)


def test_score_job_mathematical_clamping(sample_profile, sample_resume_text):
    """Verify that unrelated industry or severe domain gap scores are hard-clamped below threshold."""
    from unittest.mock import patch
    from scorer.match_scorer import score_job

    unrelated_job = {
        "title": "Technical Program Manager, Cloud Silicon",
        "company": "Google",
        "location": "Bangalore, India",
        "jd_text": "Lead silicon engineering, ASIC tapeout, hardware validation, cloud accelerators.",
    }

    # Simulate an LLM hallucinating 100% while admitting the domain is unrelated
    mock_hallucinated_scoring = {
        "skills_score": 40,
        "industry_score": 35,
        "role_level_score": 25,
        "match_score": 100,
        "matched_keywords": ["Program Manager", "Agile", "Delivery"],
        "missing_keywords": ["Silicon", "ASIC", "Tapeout", "Cloud Accelerators"],
        "seniority_fit": "good",
        "industry_fit": "unrelated",
        "recommendation": "Strong delivery background in gaming but lacks the cloud silicon technical background required for this role.",
    }

    with patch("core.llm.LLMClient.generate_json", return_value=mock_hallucinated_scoring):
        result = score_job(unrelated_job, sample_resume_text, sample_profile)
        # Assert the math engine clamped the score below qualification threshold (< 40%)
        assert result["match_score"] <= 35
        assert result["industry_fit"] == "unrelated"

