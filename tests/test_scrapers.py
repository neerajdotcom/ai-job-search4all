"""
tests/test_scrapers.py — Unit tests for job board scrapers and deduplication logic.
"""

import pytest
from scraper.job_scraper import _clean_url, _dedup, _is_qa_role, _normalize_for_dedup
from scraper.remotive_scraper import _strip_html, scrape_remotive


def test_url_cleaning():
    url1 = "https://boards.greenhouse.io/acme/jobs/12345?gh_src=linkedin&utm_source=feed"
    assert _clean_url(url1) == "https://boards.greenhouse.io/acme/jobs/12345"

    url2 = "https://www.adzuna.com/land/ad/99999?se=xyz&utm_medium=email"
    assert _clean_url(url2) == "https://www.adzuna.com/land/ad/99999"


def test_deduplication():
    jobs = [
        {"title": "Senior Backend Engineer", "company": "Stripe", "apply_url": "https://stripe.com/jobs/1?src=1", "source": "greenhouse"},
        {"title": "Senior Backend Engineer", "company": "Stripe", "apply_url": "https://stripe.com/jobs/1?src=2", "source": "adzuna"},  # dup URL
        {"title": "Senior Backend Engineer ", "company": "Stripe", "apply_url": "https://other.com/jobs/2", "source": "linkedin"},      # dup title+company
        {"title": "Staff Engineer", "company": "Stripe", "apply_url": "https://stripe.com/jobs/3", "source": "greenhouse"},
    ]
    unique = _dedup(jobs)
    assert len(unique) == 2
    assert unique[0]["source"] == "greenhouse"
    assert unique[1]["title"] == "Staff Engineer"


def test_qa_role_detection():
    assert _is_qa_role("QA Lead Engineer") is True
    assert _is_qa_role("Senior SDET - Automation") is True
    assert _is_qa_role("Quality Assurance Analyst") is True
    assert _is_qa_role("Software Tester") is True
    assert _is_qa_role("Senior Backend Developer") is False
    assert _is_qa_role("Product Manager") is False


def test_remotive_html_stripping():
    html_raw = "<p>We are hiring a <strong>Senior Engineer</strong> with &amp; Python experience.<br>Apply now!</p>"
    clean = _strip_html(html_raw)
    assert clean == "We are hiring a Senior Engineer with & Python experience. Apply now!"


def test_remotive_scraper_mocked(monkeypatch, sample_profile):
    """Test Remotive scraper with mocked network response."""
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Senior Python Developer",
                        "company_name": "RemotiveCo",
                        "candidate_required_location": "USA Only",
                        "url": "https://remotive.com/job/999",
                        "description": "<p>Build great APIs</p>",
                        "publication_date": "2026-08-01T12:00:00",
                    }
                ]
            }

    import requests
    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResponse())

    results = scrape_remotive(sample_profile)
    assert len(results) >= 1
    assert results[0]["company"] == "RemotiveCo"
    assert results[0]["source"] == "remotive"
    assert "Remote" in results[0]["location"]


def test_freshness_and_repost_filter():
    from datetime import datetime, timezone, timedelta
    from scraper.job_scraper import _is_fresh_or_reposted

    now = datetime.now(timezone.utc)

    # 1. Fresh job (< 5 days)
    fresh_job = {"posted_at": now - timedelta(days=2), "source": "linkedin", "title": "Dev"}
    assert _is_fresh_or_reposted(fresh_job) is True

    # 2. Stale job (> 5 days) without repost indicator
    stale_job = {"posted_at": now - timedelta(days=8), "source": "linkedin", "title": "Dev", "jd_text": "Normal JD"}
    assert _is_fresh_or_reposted(stale_job) is False

    # 3. Old job but marked reposted via metadata
    reposted_meta = {"posted_at": now - timedelta(days=12), "source": "linkedin", "is_reposted": True}
    assert _is_fresh_or_reposted(reposted_meta) is True

    # 4. Old job but contains repost text indicator
    reposted_text = {"posted_at": now - timedelta(days=15), "source": "linkedin", "title": "Senior Dev - Reposted", "jd_text": "Actively hiring"}
    assert _is_fresh_or_reposted(reposted_text) is True

    # 5. Direct ATS live feed source
    ats_job = {"posted_at": now - timedelta(days=30), "source": "greenhouse", "title": "Staff Engineer"}
    assert _is_fresh_or_reposted(ats_job) is True


def test_disqualified_job_cross_run_skipping(tmp_path, monkeypatch):
    import json
    from storage.tracker_store import filter_unscored, mark_seen, get_resume_hash

    tracker_file = tmp_path / "tracker.json"
    monkeypatch.setattr("storage.tracker_store.TRACKER_PATH", tracker_file)

    resume_text = "John Doe 10 years Senior Backend Engineer Python Go Docker"
    jobs = [
        {"title": "Backend Dev", "company": "Acme", "apply_url": "https://acme.com/job/1", "match_score": 90, "qualifying": True},
        {"title": "Unrelated Receptionist", "company": "Beta", "apply_url": "https://beta.com/job/2", "match_score": 25, "qualifying": False, "off_target_skipped": True},
    ]

    # First run scores and marks jobs seen
    mark_seen(jobs, resume_text=resume_text)

    # Next run with same resume should skip the disqualified job
    new_batch = [
        {"title": "Backend Dev", "company": "Acme", "apply_url": "https://acme.com/job/1"},
        {"title": "Unrelated Receptionist", "company": "Beta", "apply_url": "https://beta.com/job/2"},
        {"title": "Fresh Python Role", "company": "Gamma", "apply_url": "https://gamma.com/job/3"},
    ]

    unscored = filter_unscored(new_batch, resume_text=resume_text)
    assert len(unscored) == 1
    assert unscored[0]["company"] == "Gamma"


def test_target_role_patterns_domain_matching(sample_profile):
    from scraper.job_scraper import _is_target_role

    # Matches explicit search terms
    assert _is_target_role("Senior Backend Engineer", sample_profile) is True
    assert _is_target_role("Staff Software Engineer", sample_profile) is True
    assert _is_target_role("Distributed Systems Engineer", sample_profile) is True

    # Reject completely off-target roles
    assert _is_target_role("Technical Program Manager, Cloud Silicon", sample_profile) is False
    assert _is_target_role("Head Chef", sample_profile) is False
    assert _is_target_role("Commercial Airline Captain", sample_profile) is False


def test_dynamic_ats_company_probe_mocked(monkeypatch):
    from scraper.ats_scraper import _probe_dynamic_target_company

    class MockGreenhouseResp:
        status_code = 200
        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Senior Game Producer",
                        "company_name": "Pragmatic Play",
                        "location": {"name": "Pune, India"},
                        "content": "Lead iGaming slot game production cycles.",
                        "absolute_url": "https://boards.greenhouse.io/pragmaticplay/jobs/101",
                    }
                ]
            }

    import requests
    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockGreenhouseResp())

    results = _probe_dynamic_target_company("Pragmatic Play")
    assert len(results) >= 1
    assert results[0]["company"] == "Pragmatic Play"
    assert results[0]["title"] == "Senior Game Producer"
    assert results[0]["source"] == "greenhouse"


