"""
tests/test_webapp.py — Unit and integration tests for FastAPI routes and instant matcher.
"""

import pytest
from fastapi.testclient import TestClient
from webapp.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Job Scout" in response.text
    assert "Find Your Next Role" in response.text


def test_runs_page_renders(client):
    response = client.get("/runs")
    assert response.status_code == 200


def test_api_stats(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_runs" in data
    assert "total_jobs_scraped" in data


def test_api_instant_match_validation(client):
    # Too short text should fail 400
    resp = client.post("/api/match/instant", json={"resume_text": "too short"})
    assert resp.status_code == 400
    assert "at least 50 characters" in resp.json().get("error", "")


def test_api_instant_match_success(client, sample_resume_text):
    resp = client.post("/api/match/instant", json={
        "resume_text": sample_resume_text,
        "title": "Backend Engineer",
        "location": "San Francisco",
        "remote_only": True,
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data.get("ok") is True
    assert "session_id" in data

    session_id = data["session_id"]
    # Check results endpoint
    res_resp = client.get(f"/api/match/results/{session_id}")
    assert res_resp.status_code == 200


def test_api_traces_endpoint(client):
    resp = client.get("/api/traces")
    assert resp.status_code == 200
    assert "traces" in resp.json()


def test_api_resume_upload_txt(client):
    raw_content = b"Alex Morgan\nSenior Product Manager with 8+ years experience building SaaS platforms.\nSkills: Python, SQL, Agile."
    resp = client.post(
        "/api/resume/upload",
        files={"file": ("resume.txt", raw_content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "Alex Morgan" in data["text"]
    assert data["char_count"] > 30


def test_api_resume_fetch_cloud_url_invalid(client):
    resp = client.post("/api/resume/fetch-url", json={"url": "not-a-valid-url"})
    assert resp.status_code == 400


def test_instant_results_html_page_renders_with_tailored_pack(client):
    """Ensure /match/{session_id} renders cleanly without Jinja2 template errors."""
    from webapp.run_manager import run_manager
    session_id = "test_sess_render_123"
    with run_manager._lock:
        run_manager._sessions[session_id] = {
            "session_id": session_id,
            "status": "completed",
            "results": {
                "profile": {
                    "name": "Malini Sharma",
                    "title": "Localization Project Manager",
                    "location": "Pune, India",
                    "years_experience": 6,
                    "search_terms": ["Localization PM", "Subtitling Lead"],
                    "target_companies": ["Netflix", "Crunchyroll"],
                },
                "total_matches": 1,
                "total_scraped": 15,
                "pathways": [
                    {
                        "id": "track_a",
                        "role_type": "core",
                        "title": "Localization Project Manager",
                        "track_label": "Track A: Core Trajectory",
                        "potential_score": 98,
                        "tagline": "Direct media localization management",
                        "target_companies": ["Netflix", "Crunchyroll"],
                    }
                ],
                "active_pathways": [
                    {
                        "id": "track_a",
                        "role_type": "core",
                        "title": "Localization Project Manager",
                        "track_label": "Track A: Core Trajectory",
                        "potential_score": 98,
                    }
                ],
                "matches": [
                    {
                        "id": "netflix_loc_1",
                        "title": "Localization Project Manager",
                        "company": "Netflix",
                        "location": "Pune, India",
                        "source": "seed_catalog",
                        "match_score": 98,
                        "seniority_fit": "target",
                        "industry_fit": "core",
                        "track_id": "track_a",
                        "track_label": "Track A: Core Trajectory",
                        "track_title": "Localization Project Manager",
                        "track_role_type": "core",
                        "recommendation": "Superb fit for subtitling lead role.",
                        "tailored_pack": {
                            "optimized_summary": "Experienced Localization PM with deep subtitling QC experience.",
                            "cover_note_variants": [
                                {"angle": "delivery", "text": "I specialize in high-velocity multi-language subtitling delivery."},
                                {"angle": "leadership", "text": "I lead cross-functional dubbing and subtitling operations."}
                            ],
                            "screening_answers": [
                                {"question": "How do you handle subtitle QC deadlines?", "answer": "I coordinate closely with translators and use automated conformity checks."}
                            ]
                        }
                    }
                ]
            }
        }

    resp = client.get(f"/match/{session_id}")
    assert resp.status_code == 200
    assert "Malini Sharma" in resp.text
    assert "Localization Project Manager" in resp.text
    assert "Fast-Apply Application Pack for Netflix" in resp.text
    assert "Track A: Core Trajectory" in resp.text


def test_preview_tailored_resume_page(client):
    """Ensure /resume/preview/{session_id}/{job_idx} renders clean ATS printable view."""
    from webapp.run_manager import run_manager
    session_id = "test_sess_preview_456"
    with run_manager._lock:
        run_manager._sessions[session_id] = {
            "session_id": session_id,
            "status": "completed",
            "resume_text": "Malini Sharma\nLocalization Project Manager in Pune\nExperience:\n- Led subtitle QC for Netflix Originals.\n- Managed multi-language dubbing teams.",
            "results": {
                "profile": {
                    "name": "Malini Sharma",
                    "title": "Localization Project Manager",
                    "location": "Pune, India",
                },
                "matches": [
                    {
                        "id": "netflix_loc_1",
                        "title": "Localization Project Manager",
                        "company": "Netflix",
                        "tailored_pack": {
                            "optimized_summary": "Seasoned Localization Manager with Subtitling & Dubbing expertise.",
                            "optimized_competencies": ["Subtitling QC", "Vendor Management", "EZTitles"],
                        }
                    }
                ]
            }
        }

    resp = client.get(f"/resume/preview/{session_id}/1")
    assert resp.status_code == 200
    assert "Malini Sharma" in resp.text
    assert "Seasoned Localization Manager with Subtitling &amp; Dubbing expertise." in resp.text or "Seasoned Localization Manager" in resp.text
    assert "Subtitling QC" in resp.text
    assert "Save as PDF / Print" in resp.text


def test_download_tailored_docx_endpoint(client):
    """Ensure /api/resume/download/{session_id}/{job_idx} generates valid .docx file."""
    from webapp.run_manager import run_manager
    session_id = "test_sess_docx_789"
    with run_manager._lock:
        run_manager._sessions[session_id] = {
            "session_id": session_id,
            "status": "completed",
            "resume_text": "Malini Sharma\nLocalization Lead\nExperience:\n- Coordinated subtitle delivery.",
            "results": {
                "profile": {
                    "name": "Malini Sharma",
                    "title": "Localization Lead",
                    "location": "Pune",
                },
                "matches": [
                    {
                        "id": "crunchyroll_loc_1",
                        "title": "Media Localization Lead",
                        "company": "Crunchyroll",
                        "tailored_pack": {
                            "optimized_summary": "Anime & Media Localization Specialist.",
                            "optimized_competencies": ["Anime Subtitling", "SRT Conformity"],
                        }
                    }
                ]
            }
        }

    resp = client.get(f"/api/resume/download/{session_id}/1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert len(resp.content) > 1000  # valid docx binary content


def test_instant_match_to_resume_preview_full_e2e(client, mocker):
    """
    True end-to-end test:
    1. Triggers real instant match session from full CV text.
    2. Waits for worker thread to complete and write session state.
    3. Fetches /resume/preview/{session_id}/1 and verifies experience, bullets, and domain terms are present.
    """
    from webapp.run_manager import run_manager
    import time

    mocker.patch(
        "core.llm.LLMClient.generate_json",
        return_value={
            "title": "Localization Project Manager",
            "name": "Malini Sharma",
            "years_experience": 6,
            "location": "Pune, India",
            "search_terms": ["Localization Project Manager"],
            "roles": {"deluxe": ["deluxe media"], "iyuno": ["iyuno"]},
            "optimized_summary": "Localization & Subtitling Lead with 6+ years managing multi-language OTT releases, dubbing pipelines, and subtitle QC for Netflix Originals.",
            "optimized_competencies": ["Subtitling Quality Control", "Vendor Management", "EZTitles", "OTT Media Operations", "Timecode QC"],
            "optimized_bullets": {},
            "cover_note": "Dear Hiring Team at Netflix...",
            "cover_note_variants": [{"angle": "domain-fit", "text": "Dear Hiring Team..."}],
            "screening_answers": [],
            "pathways": [
                {
                    "id": "track_a",
                    "role_type": "core",
                    "title": "Localization Project Manager",
                    "track_label": "Track A: Core Trajectory",
                    "potential_score": 98,
                    "tagline": "Direct management of multi-language media...",
                    "target_companies": ["Netflix", "Crunchyroll"],
                    "search_queries": ["Localization Project Manager"],
                    "target_industries": ["Media & Streaming"],
                    "key_transferable_skills": ["Subtitling QC", "Vendor Management"],
                }
            ]
        }
    )

    cv_text = """
    Malini Sharma
    Localization Project Manager
    Pune, India | malini.sharma@example.com | +91 9876543210
    
    Professional Summary:
    Localization and Subtitling Lead with 6+ years managing multi-language OTT releases, dubbing pipelines, and subtitle QC.
    
    Work Experience:
    Senior Localization Lead | Deluxe Media (Jan 2021 – Present)
    - Directed subtitle quality control across 40+ languages for major OTT streaming originals.
    - Reduced subtitle delivery turnaround time by 35% using automated QC conformance scripts.
    - Managed 15+ external translation vendor studios and negotiated SLAs.

    Subtitling QC Coordinator | Iyuno (Jun 2018 – Dec 2020)
    - Performed framerate, sync, and reading speed verification on 500+ anime and film assets.
    - Supervised localization QA linguists and maintained terminology glossaries in EZTitles.

    Education:
    Bachelor of Arts in English & Media Studies — Pune University (2018)

    Certifications:
    Certified Localization Professional (CLP)
    """

    session_id = run_manager.start_instant_session(
        resume_text=cv_text,
        title_override="Localization Project Manager",
        location_override="Pune, India",
    )

    # Wait for worker thread to finish (max 6s)
    for _ in range(60):
        time.sleep(0.1)
        sess = run_manager.get_session(session_id)
        if sess and sess.get("status") in ("completed", "failed"):
            break

    sess = run_manager.get_session(session_id)
    assert sess is not None, "Session was not created"
    assert sess.get("status") == "completed", f"Session failed: {sess.get('error')}"
    assert sess.get("resume_text") == cv_text, "Raw resume text was not preserved in session state"

    # Test preview route
    resp = client.get(f"/resume/preview/{session_id}/1")
    assert resp.status_code == 200
    html = resp.text

    # Assert candidate identity and contact info
    assert "Malini Sharma" in html
    assert "malini.sharma@example.com" in html
    assert "Pune, India" in html

    # Assert real work history and company sections are present
    assert "Deluxe Media" in html or "Professional Experience" in html
    assert "Iyuno" in html or "Directed subtitle quality control" in html or "Reduced subtitle delivery turnaround" in html
    assert "35%" in html  # Preserved metric
    assert "Pune University" in html
    assert "Save as PDF / Print" in html


def test_candidate_profile_page_renders(client):
    resp = client.get("/candidate")
    assert resp.status_code == 200
    assert "Candidate Profile & Hub" in resp.text
    assert "Candidate Match Sessions History" in resp.text

    # Alias /profile
    resp_alias = client.get("/profile")
    assert resp_alias.status_code == 200


def test_api_candidate_profile_json(client):
    resp = client.get("/api/candidate/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "name" in data
    assert "title" in data


def test_home_page_clean_isolation_without_session(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # No active session -> should not render personalized active matches feed
    assert "Your Active Matches" not in resp.text


def test_api_upload_batch_file_success(client):
    """Ensure /api/resume/upload-batch-file saves file to data/uploads and returns valid path."""
    content = b"John Doe\nSenior Backend Engineer\nSan Francisco, CA\n8 years Python and FastAPI experience."
    files = {"file": ("primary_resume.txt", content, "text/plain")}
    resp = client.post("/api/resume/upload-batch-file", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "primary_resume.txt" in data.get("filename")
    assert "data/uploads" in data.get("saved_path")
    assert data.get("char_count") > 30


def test_api_upload_batch_file_empty(client):
    """Ensure /api/resume/upload-batch-file rejects empty payloads."""
    files = {"file": ("empty.txt", b"", "text/plain")}
    resp = client.post("/api/resume/upload-batch-file", files=files)
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("ok") is False


def test_api_candidate_location_update(client, tmp_path, mocker):
    """Ensure /api/candidate/locations persists updated location preferences."""
    test_yaml = tmp_path / "config.yaml"
    test_yaml.write_text("name: Malini Sharma\nlocation: Old City\ntarget_location_country: india\n")
    mocker.patch("candidate_profile.loader.DEFAULT_PROFILE_PATH", test_yaml)

    payload = {
        "location": "Pune, India",
        "target_location_country": "india",
        "search_locations": ["Pune, India", "Bangalore, India", "Remote"],
        "blocked_locations": ["Hyderabad"]
    }
    resp = client.post("/api/candidate/locations", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("location") == "Pune, India"
    assert "Bangalore, India" in data.get("search_locations")
    assert "Hyderabad" in data.get("blocked_locations")


def test_api_candidate_switch_success(client):
    """Ensure /api/candidate/switch activates selected candidate."""
    resp = client.post("/api/candidate/switch", json={"candidate_id": "malini_mukherjee"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True

    # Candidate profile page should show Malini Mukherjee and her scored jobs table
    page_resp = client.get("/candidate")
    assert page_resp.status_code == 200
    assert "Malini Mukherjee" in page_resp.text
    assert "Personalized Scored Matches for" in page_resp.text
    assert "Candidate Profiles" in page_resp.text


def test_api_candidate_switch_invalid(client):
    """Ensure /api/candidate/switch returns 404 for nonexistent candidates."""
    resp = client.post("/api/candidate/switch", json={"candidate_id": "nonexistent_candidate_xyz"})
    assert resp.status_code == 404
    assert resp.json().get("ok") is False


def test_api_candidate_base_location_update(client, tmp_path, mocker):
    """Ensure /api/candidate/base-location updates base location."""
    test_yaml = tmp_path / "config.yaml"
    test_yaml.write_text("name: Malini\nlocation: Kolkata\ncontext: PM\n")
    mocker.patch("candidate_profile.loader.DEFAULT_PROFILE_PATH", test_yaml)

    resp = client.post("/api/candidate/base-location", json={"location": "Bangalore, India"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("location") == "Bangalore, India"


def test_api_candidate_upload_resume(client, tmp_path):
    """Ensure /api/candidate/upload-resume processes uploaded resume without polluting repository state."""
    resume_content = b"Pooja Mehta\nSenior Product Manager\nBangalore, India\n6 years experience in B2B SaaS roadmaps, analytics, and agile delivery."
    files = {"file": ("pooja_resume.txt", resume_content, "text/plain")}
    resp = client.post("/api/candidate/upload-resume", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "name" in data

    # Clean up uploaded test profile to keep only Malini's real profile
    from pathlib import Path
    import shutil
    cand_yaml = Path("candidate_profile/profiles/pooja_mehta.yaml")
    if cand_yaml.exists():
        cand_yaml.unlink()
    # Restore Malini
    shutil.copyfile("candidate_profile/profiles/malini_mukherjee.yaml", "candidate_profile/config.yaml")


def test_api_candidate_delete_profile(client):
    """Ensure /api/candidate/delete removes a candidate profile."""
    resp = client.post("/api/candidate/delete", json={"candidate_id": "nonexistent_cand"})
    assert resp.status_code == 404
    assert resp.json().get("ok") is False


def test_api_admin_purge_data(client):
    """Ensure /api/admin/purge-data purges run records."""
    resp = client.post("/api/admin/purge-data", json={"target": "sessions"})
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


def test_download_candidate_tailored_pdf(client):
    """Ensure /api/candidate/download-tailored-pdf returns valid PDF bytes."""
    resp = client.get("/api/candidate/download-tailored-pdf/0")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")







