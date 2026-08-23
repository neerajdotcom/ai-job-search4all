"""
tests/conftest.py — Shared test fixtures, mock data, and offline stubs.
"""

import os
import pytest
from pathlib import Path
from candidate_profile.loader import Profile, create_profile_from_dict

# Force dummy API keys so tests don't fail env checks
os.environ["GROQ_API_KEY"] = "test_groq_key"
os.environ["GEMINI_API_KEY"] = "test_gemini_key"
os.environ["ENABLE_LINKEDIN_SCRAPE"] = "false"
os.environ["ENABLE_ATS_SCRAPING"] = "false"
os.environ["ENABLE_REMOTIVE_SCRAPE"] = "false"


@pytest.fixture
def sample_resume_text() -> str:
    return """
John Doe
Senior Backend Engineer
San Francisco, CA | john.doe@example.com

SUMMARY
Experienced Senior Backend Engineer with 8+ years building high-scale distributed systems and RESTful APIs using Python, Go, and PostgreSQL. Reduced latency by 45% and improved throughput by 3x across 10M+ daily active users.

EXPERIENCE
Acme Corp | Senior Software Engineer | 2021 - Present
- Architected microservices processing $5M in monthly transactions with 99.99% uptime.
- Mentored a team of 6 engineers and established CI/CD automated deployment pipelines.
- Reduced API response times by 35% through Redis caching and query optimization.

Beta Tech | Software Engineer | 2017 - 2021
- Developed core data ingestion pipelines handling 500k events/sec.
- Automated deployment infrastructure with Docker and Kubernetes.

SKILLS
Python, Go, PostgreSQL, Redis, Docker, Kubernetes, AWS, Microservices, CI/CD

EDUCATION
B.S. in Computer Science, University of California, Berkeley
"""


@pytest.fixture
def sample_profile() -> Profile:
    return create_profile_from_dict({
        "name": "John Doe",
        "title": "Senior Backend Engineer",
        "years_experience": 8,
        "location": "San Francisco, CA",
        "target_location_country": "united states",
        "target_location_aliases": ["remote", "us"],
        "search_terms": [
            "Senior Backend Engineer",
            "Staff Software Engineer",
            "Lead Python Developer",
            "Distributed Systems Engineer",
        ],
        "adjacent_industries": ["fintech", "saas", "cloud infrastructure"],
        "roles": {
            "acme_corp": ["acme corp", "acme"],
            "beta_tech": ["beta tech", "beta"],
        },
        "resume_path": "candidate_profile/sample_resume.docx",
    })


@pytest.fixture
def sample_job_dict() -> dict:
    return {
        "title": "Senior Backend Engineer",
        "company": "Stripe",
        "location": "San Francisco, CA (Hybrid)",
        "apply_url": "https://stripe.com/jobs/senior-backend-engineer-12345",
        "jd_text": "We are seeking a Senior Backend Engineer to build resilient payment infrastructure. Requirements: 5+ years experience in Python or Go, distributed systems, PostgreSQL, Redis, and high-scale APIs.",
        "source": "greenhouse",
        "posted_at": None,
        "is_target_location": True,
        "is_target_role": True,
        "is_qa_role": False,
    }
