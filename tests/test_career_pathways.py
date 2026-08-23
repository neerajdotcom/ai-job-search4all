"""
tests/test_career_pathways.py — Comprehensive unit tests for Career Divergence & Multi-Track Matching.
"""

from fastapi.testclient import TestClient
from candidate_profile.career_pathways import (
    _heuristic_pathway_decomposition,
    decompose_career_pathways,
)
from webapp.app import app

client = TestClient(app)


def test_heuristic_pathway_localization():
    """Localization & Subtitling resume should produce 3 media pathways."""
    text = """
    Malini Sharma
    Localization Project Manager / Subtitling Lead
    Pune, India
    6+ years experience in Subtitling, Dubbing, EZTitles, SRT/VTT, and OTT Media operations for anime and streaming movies.
    """
    pathways = _heuristic_pathway_decomposition(text, "Localization Project Manager")
    assert len(pathways) == 3
    track_ids = [p["id"] for p in pathways]
    assert track_ids == ["track_a", "track_b", "track_c"]
    assert "Localization" in pathways[0]["title"]
    assert any("Netflix" in c or "Crunchyroll" in c for c in pathways[0]["target_companies"])
    assert pathways[0]["potential_score"] >= 90


def test_heuristic_pathway_software_engineering():
    """Fullstack / React developer should produce Full Stack, Cloud/DevOps, and Design Systems tracks."""
    text = "Senior React Developer with 5 years experience in TypeScript, Python, and Docker."
    pathways = _heuristic_pathway_decomposition(text, "Frontend Engineer")
    assert len(pathways) == 3
    assert any("Full Stack" in p["title"] or "DevOps" in p["title"] or "Design Systems" in p["title"] for p in pathways)


def test_heuristic_pathway_qa():
    """QA candidate should produce SDET, Release Ops, and Performance tracks."""
    text = "Senior QA Automation Engineer with Selenium, Cypress, and CI/CD experience."
    pathways = _heuristic_pathway_decomposition(text, "Senior QA Engineer")
    assert len(pathways) == 3
    assert any("SDET" in p["title"] or "QA" in p["title"] for p in pathways)


def test_decompose_career_pathways_empty_string():
    """Empty resume should return clean empty pathways without crashing or hallucinating."""
    result = decompose_career_pathways("")
    assert isinstance(result, dict)
    assert result.get("pathways", []) == []


def test_synthetic_gibberish_resumes_produce_zero_pathways_and_zero_seeds():
    """Synthetic/unrecognized profiles (Vrindula, Garbuncle, Pflumert) should yield 0 pathways and 0 seed jobs."""
    from candidate_profile.loader import create_profile_from_text
    from storage.seed_catalog import get_seed_jobs_for_profile

    synthetic_resumes = [
        "Vrindula Boppsworth - Principal Data Snorb Scientist & Blibbet Modelling Lead. Quorple Regression.",
        "Garbuncle Twizzby - Creative Zorp Director & Brand Flibulation Strategist. Snorb Motion Design.",
        "Pflumert J. Snorkelton - Chief Quorple Operations Officer & Deputy Director, Strategic Snorb Affairs.",
    ]
    for cv in synthetic_resumes:
        prof = create_profile_from_text(cv)
        pw = decompose_career_pathways(cv, prof.title)
        seeds = get_seed_jobs_for_profile(prof)
        assert len(pw.get("pathways", [])) == 0, f"Hallucinated pathways for synthetic CV: {cv}"
        assert len(seeds) == 0, f"Hydrated seed jobs for synthetic CV: {cv}"


def test_api_career_pathways_endpoint():
    """POST /api/career/pathways should return structured pathways."""
    resp = client.post("/api/career/pathways", json={
        "resume_text": "Experienced Localization Manager in Pune specializing in anime subtitling, dubbing, and streaming delivery.",
        "title": "Localization Project Manager",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["pathways"]) == 3
    assert data["pathways"][0]["id"] == "track_a"


def test_api_career_pathways_empty():
    """POST /api/career/pathways with short text should return 400 validation error."""
    resp = client.post("/api/career/pathways", json={"resume_text": "too short"})
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


def test_api_instant_match_with_selected_tracks():
    """POST /api/match/instant with selected_tracks should accept and start session."""
    resp = client.post("/api/match/instant", json={
        "resume_text": "Senior Localization Project Manager with 6 years experience in Pune.",
        "title": "Localization Project Manager",
        "location": "Pune, India",
        "selected_tracks": ["track_a", "track_b"],
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert "session_id" in data


def test_instant_match_worker_e2e_single_resume(mocker):
    """End-to-end test of the worker loop with a single resume (no secondary) ensuring no UnboundLocalError."""
    import time
    from candidate_profile.loader import Profile
    from webapp.run_manager import run_manager

    # Mock profile extraction, scrapers, and LLM for instantaneous deterministic test execution
    from core.llm import default_llm
    mocker.patch.object(
        default_llm,
        "generate",
        return_value="{}",
    )
    mocker.patch(
        "candidate_profile.loader.create_profile_from_text",
        return_value=Profile(
            name="Malini Sharma",
            title="Localization Project Manager",
            years_experience=6,
            context="Localization expert in Pune",
            location="Pune, India",
            target_location_country="india",
            search_terms=["Localization Project Manager", "Media Localization Lead"],
            target_companies=["Netflix", "Crunchyroll"],
        )
    )
    mocker.patch(
        "scraper.job_scraper.scrape_all_jobs",
        return_value=[
            {
                "id": "netflix_loc_pm_test",
                "title": "Localization Project Manager (Subtitling & Dubbing)",
                "company": "Netflix",
                "location": "Pune, India",
                "source": "adzuna",
                "target_company": True,
                "jd_text": (
                    "Netflix is seeking an experienced Localization Project Manager in Pune to lead subtitle "
                    "and dubbing operations for international web series, anime, and feature films. In this role, "
                    "you will coordinate with cross-functional creative teams, translation vendors, and dubbing "
                    "studios across multiple territories. You will manage subtitling quality control, SRT and VTT "
                    "asset delivery, timecode conformity using EZTitles and translation management systems. "
                    "You must have at least 5 years of experience in entertainment media localization, dubbing "
                    "management, vendor supervision, and multi-language streaming workflows. Strong communication "
                    "skills, deep familiarity with anime subtitle guidelines, and audio post-production workflows "
                    "are essential for success in this role."
                ),
            }
        ]
    )
    mocker.patch(
        "scorer.match_scorer.score_job",
        return_value={
            "id": "netflix_loc_pm_test",
            "title": "Localization Project Manager (Subtitling & Dubbing)",
            "company": "Netflix",
            "location": "Pune, India",
            "source": "seed_catalog",
            "target_company": True,
            "jd_text": "Lead subtitling and dubbing operations for Netflix Originals anime and films using EZTitles.",
            "match_score": 95,
            "seniority_fit": "target",
            "industry_fit": "core",
            "recommendation": "Outstanding fit for subtitling lead role.",
        }
    )
    mocker.patch(
        "optimizer.resume_optimizer.call_llm",
        return_value={
            "optimized_summary": "Experienced Localization Manager with Subtitling and OTT expertise.",
            "optimized_competencies": ["Subtitling QC", "Vendor Management", "EZTitles"],
            "optimized_bullets": {},
        }
    )

    session_id = run_manager.start_instant_session(
        resume_text="Malini Sharma\nLocalization Project Manager\n6+ years in Subtitling, Dubbing, and OTT operations in Pune, India.",
        title_override="Localization Project Manager",
        location_override="Pune",
        selected_tracks=["track_a"],
        pathways=[{
            "id": "track_a",
            "role_type": "core",
            "title": "Localization Project Manager",
            "track_label": "Track A: Core Trajectory",
            "potential_score": 98,
            "tagline": "Direct management of multi-language media...",
            "target_companies": ["Netflix", "Crunchyroll"],
            "search_queries": ["Localization Project Manager"],
            "target_industries": ["Media & Streaming"],
            "key_transferable_skills": ["Subtitling QC", "Vendor Management"]
        }]
    )
    # Wait up to 5s for worker completion
    for _ in range(50):
        session = run_manager.get_session(session_id)
        if session and session.get("status") in ("completed", "failed"):
            break
        time.sleep(0.1)

    session = run_manager.get_session(session_id)
    assert session is not None
    assert session.get("status") == "completed", f"Session failed with error: {session.get('error')}"
    res = session.get("results")
    assert res is not None
    assert "matches" in res
    assert len(res["matches"]) > 0
    # verify track metadata attached to scored match
    first_match = res["matches"][0]
    assert "track_id" in first_match
    assert first_match["track_id"] == "track_a"

