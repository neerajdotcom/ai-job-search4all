"""
tests/test_adversarial_matrix.py — Exhaustive Adversarial & Edge-Case Stress Testing Suite.
"""
import pytest
from unittest.mock import patch
from candidate_profile.loader import create_profile_from_text
from candidate_profile.career_pathways import decompose_career_pathways
from storage.seed_catalog import get_seed_jobs_for_profile
from scorer.match_scorer import _score_job_deterministic

# Auto-patch LLM calls in this module so heuristic tests execute in milliseconds
@pytest.fixture(autouse=True)
def mock_llm():
    with patch('core.llm.LLMClient.generate_json', return_value=None),          patch('core.llm.LLMClient.generate', return_value=''):
        yield

NETFLIX_LOC_PM = {
    "title": "Localization Project Manager (Subtitling & Dubbing)",
    "company": "Netflix",
    "jd_text": "Oversee subtitling, dubbing, and audio description across movies, series, and anime. EZTitles, TMS, LQA.",
}

COGNIZANT_LEAD_QA = {
    "title": "Lead QA Engineer / SDET Lead",
    "company": "Cognizant",
    "jd_text": "Enterprise test automation frameworks, Selenium, Playwright, CI/CD quality gates, Python/Java.",
}

SWIGGY_BACKEND = {
    "title": "Senior Software Engineer (Backend / Distributed Systems)",
    "company": "Swiggy",
    "jd_text": "Golang, Java, Python, high concurrency microservices, PostgreSQL, Kafka, distributed caching.",
}

GIBBERISH_RESUMES = [
    (
        "Blorwick Fentangle",
        """Blorwick T. Fentangle
        Senior Glumper & Wazzle Strategist
        8 years experience orchestrating high-velocity wazzle pipelines across distributed snorb ecosystems.
        Core Skills: Flibber Analysis, Quorple Design, Snorb Management, Zizzle Ops, Grumpton Scripting, Plinket Testing.
        Head of Grumpton Wazzlification at ZORBLEX GLOBAL SNORB SOLUTIONS.
        """,
    ),
    (
        "Vrindula Boppsworth",
        """Vrindula Boppsworth
        Principal Data Snorb Scientist & Blibbet Modelling Lead
        9 years building predictive blibbet models and real-time snorb inference pipelines.
        Skills: Quorple Regression, Snorb Trees, Flibbernet, Wazzle Clustering, Dortberry Spark, Flurbian Kafka.
        Ph.D. Computational Snorb Science, Plonk Institute of Advanced Wazzlery.
        """,
    ),
    (
        "Garbuncle Twizzby",
        """Garbuncle Twizzby
        Creative Zorp Director & Brand Flibulation Strategist
        12 years directing brand identities and integrated zorp campaigns across Zorpmouth.
        Core Disciplines: Zorp Direction, Brand Flibulation, Quorple Typography, Snorb Motion Design, Grumpton Campaigns.
        Executive Creative Zorper at TWIZZBY CREATIVE STUDIO.
        """,
    ),
    (
        "Pflumert Snorkelton",
        """Pflumert J. Snorkelton
        Chief Quorple Operations Officer & Deputy Director, Strategic Snorb Affairs
        22 years across the Snorb sector. Wumbleby Dortberry Consolidation reform.
        National Snorb Regulatory Commission. FICQO since 2016.
        """,
    ),
    (
        "Xanthopaw Glorp",
        """Xanthopaw V. Glorp
        Supreme High Flurn Collector & Splinge Coordinator
        15 years cataloging rare flurn specimens across the outer Grumble belt.
        Master of Flurnology, Grand Splinge Academy of Plonkershire.
        """,
    ),
]

@pytest.mark.parametrize("name, cv_text", GIBBERISH_RESUMES)
def test_pure_gibberish_resumes_zero_pathways_and_zero_seeds(name, cv_text):
    prof = create_profile_from_text(cv_text)
    pw = decompose_career_pathways(cv_text, prof.title)
    seeds = get_seed_jobs_for_profile(prof)

    assert len(pw.get("pathways", [])) == 0, f"Failed for {name}: Hallucinated pathways: {pw.get('pathways')}"
    assert len(seeds) == 0, f"Failed for {name}: Hydrated {len(seeds)} seed jobs"

    for sample_job in [NETFLIX_LOC_PM, COGNIZANT_LEAD_QA, SWIGGY_BACKEND]:
        res = _score_job_deterministic(sample_job, cv_text, prof)
        assert res["match_score"] <= 25, f"Failed for {name} on {sample_job['title']}: score was {res['match_score']} %"
        assert res["industry_fit"] == "unrelated"

KEYWORD_STUFFED_GIBBERISH = [
    (
        "Agile Scrum Snorb Master",
        """Zorblaxian Q. Vunder
        Lead Scrum Snorb Master & Agile Wazzle Delivery Coach
        7 years facilitating sprint retrospectives for distributed flibber pods in Grumpton.
        JIRA, Confluence, Kanban, Snorb CI/CD, Quorple Sprint Planning.
        """,
    ),
    (
        "Python Scripting Glumper",
        """Plonko M. Fizzle
        Senior Grumpton Scripting Glumper
        6 years writing automated dortberry scripts using Pythonic syntax for high-scale snorb extraction.
        Docker, Linux, Git, Quorple CLI, Flurbian Bash.
        """,
    ),
    (
        "DevOps Cloud Flibber",
        """Krelthor the Cloud Snorb
        Principal Cloud Infrastructure Flibber
        10 years deploying distributed wazzle clusters to Horbix Cloud with Kubernetes-style flurb pods.
        Terraform, Ansible, AWS-Zorp, Snorb Telemetry, CloudWatch.
        """,
    ),
]

@pytest.mark.parametrize("name, cv_text", KEYWORD_STUFFED_GIBBERISH)
def test_keyword_stuffed_gibberish_zero_pathways_and_zero_seeds(name, cv_text):
    prof = create_profile_from_text(cv_text)
    pw = decompose_career_pathways(cv_text, prof.title)
    seeds = get_seed_jobs_for_profile(prof)

    assert len(pw.get("pathways", [])) == 0, f"Failed for {name}: Hallucinated pathways"
    assert len(seeds) == 0, f"Failed for {name}: Hydrated {len(seeds)} seed jobs"

    for sample_job in [NETFLIX_LOC_PM, COGNIZANT_LEAD_QA, SWIGGY_BACKEND]:
        res = _score_job_deterministic(sample_job, cv_text, prof)
        assert res["match_score"] <= 25, f"Failed for {name} on {sample_job['title']}: score was {res['match_score']} %"

NON_TECH_PROFESSIONS = [
    (
        "Equine Veterinarian",
        """Dr. Alistair Finch, DVM
        Board-Certified Equine Surgeon & Large Animal Veterinarian
        14 years clinical experience specializing in equine orthopedic surgery, lameness diagnosis, and broodmare reproductive health.
        Equine Arthroscopy, Ultrasound Diagnostics, Digital Radiography, Anesthesia Management.
        Senior Surgeon at Kentucky Equine Hospital (2015 – Present).
        DVM — Cornell University College of Veterinary Medicine.
        """,
    ),
    (
        "French Pastry Chef",
        """Jean-Luc Moreau
        Executive Pastry Chef & Master Chocolatier
        18 years crafting artisan viennoiserie, entremets, chocolate showpieces, and sugar sculptures in Michelin-starred establishments.
        Tempering, Sourdough Fermentation, Laminating, Sugar Casting, Menu Engineering.
        Head of Pastry at Le Grand Gourmet, Paris (2018 – Present).
        CAP Pâtissier — Ferrandi Paris.
        """,
    ),
    (
        "Commercial Airline Pilot",
        """Captain Sarah Jenkins
        Senior Airline Transport Pilot (ATPL) — Boeing 777 / 787 Fleet
        16 years and 11,500+ accident-free flight hours operating international wide-body routes.
        Crew Resource Management (CRM), ETOPS Operations, CAT III ILS Approaches, Flight Safety Auditing.
        Line Captain at Emirates Airlines (2014 – Present).
        FAA / EASA First Class Medical, Type Rated B777/B787.
        """,
    ),
    (
        "High School History Teacher",
        """Marcus Aurelius Vance
        High School AP European History & Social Studies Department Chair
        12 years curriculum development, pedagogical instruction, and academic mentoring for grades 9-12.
        Classroom Management, Common Core Curriculum, Formative Assessment, AP Exam Preparation.
        Master of Education (M.Ed.) — Harvard Graduate School of Education.
        """,
    ),
    (
        "Criminal Defense Attorney",
        """Eleanor Vance, Esq.
        Senior Criminal Defense Trial Attorney & Partner
        15 years lead counsel representing defendants in state and federal jury trials, grand jury proceedings, and appellate litigation.
        Cross-Examination, Evidence Suppression Motions, Plea Negotiations, Constitutional Law.
        Juris Doctor (J.D.) — Columbia Law School. Member of State Bar.
        """,
    ),
]

@pytest.mark.parametrize("name, cv_text", NON_TECH_PROFESSIONS)
def test_real_non_tech_professions_zero_tech_pathways_and_seeds(name, cv_text):
    prof = create_profile_from_text(cv_text)
    pw = decompose_career_pathways(cv_text, prof.title)
    seeds = get_seed_jobs_for_profile(prof)

    assert len(pw.get("pathways", [])) == 0, f"Failed for {name}: Hallucinated pathways for non-tech candidate"
    assert len(seeds) == 0, f"Failed for {name}: Hydrated tech seed jobs for non-tech candidate"

    for sample_job in [NETFLIX_LOC_PM, COGNIZANT_LEAD_QA, SWIGGY_BACKEND]:
        res = _score_job_deterministic(sample_job, cv_text, prof)
        assert res["match_score"] <= 25, f"Failed for {name} on {sample_job['title']}: score was {res['match_score']} %"

MALFORMED_PAYLOADS = [
    (
        "Lorem Ipsum",
        """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
        Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
        """,
    ),
    (
        "Python Code Snippet",
        """import os
        import sys
        def calculate_fibonacci(n):
            a, b = 0, 1
            for _ in range(n):
                yield a
                a, b = b, a + b
        """,
    ),
    (
        "JSON Schema Dump",
        """{
            "": "https://json-schema.org/draft/2020-12/schema",
            "title": "InventoryItem",
            "type": "object",
            "properties": {
                "itemId": {"type": "integer"}
            }
        }""",
    ),
    (
        "SQL Query Dump",
        """SELECT u.user_id, u.email, COUNT(o.order_id) as total_orders
        FROM users u
        WHERE o.created_at >= '2024-01-01'
        GROUP BY u.user_id, u.email;
        """,
    ),
]

@pytest.mark.parametrize("name, cv_text", MALFORMED_PAYLOADS)
def test_malformed_and_noise_payloads(name, cv_text):
    prof = create_profile_from_text(cv_text)
    pw = decompose_career_pathways(cv_text, prof.title)
    seeds = get_seed_jobs_for_profile(prof)

    assert len(pw.get("pathways", [])) == 0, f"Failed for {name}: Hallucinated pathways on noise"
    assert len(seeds) == 0, f"Failed for {name}: Hydrated seeds on noise"

LEGITIMATE_CANDIDATES = [
    (
        "Malini Sharma (Localization & Gaming PM)",
        """Malini Sharma
        Localization Project Manager & Subtitling Lead
        Pune, India | malini@example.com
        6+ years experience managing multi-language OTT releases, dubbing pipelines, and subtitle QC for Netflix Originals.
        Skills: Subtitling QC, Vendor Management, EZTitles, TMS, OTT Media Operations, Dubbing QC.
        Senior Localization Lead at Deluxe Media (2021 – Present).
        Subtitling QC Coordinator at Iyuno (2018 – 2020).
        """,
        NETFLIX_LOC_PM,
        ["Localization Project Manager", "Senior Media Localization Lead", "OTT Content Operations Lead"],
    ),
    (
        "Rohan Gupta (QA / SDET Lead)",
        """Rohan Gupta
        Senior QA Engineer / Lead SDET
        Bangalore, India | rohan.gupta@example.com
        7+ years architecting enterprise test automation frameworks with Selenium, Cypress, and Playwright.
        Skills: Selenium, Playwright, Test Automation, CI/CD Quality Gates, Python, Java, API Testing, JMeter.
        Lead SDET at Cognizant (2020 – Present).
        Automation Engineer at Infosys (2017 – 2020).
        """,
        COGNIZANT_LEAD_QA,
        ["Lead SDET / QA Automation Architect", "Release & Delivery Operations Manager"],
    ),
    (
        "Ananya Roy (Software / Backend Engineer)",
        """Ananya Roy
        Senior Software Engineer (Backend Developer)
        Pune, India | ananya.roy@example.com
        6+ years designing high-throughput distributed microservices in Golang and Python.
        Skills: Golang, Python Developer, FastAPI, PostgreSQL, Kubernetes, Docker, Microservices, Redis, Kafka.
        Senior Backend Developer at Razorpay (2021 – Present).
        Software Engineer at Zomato (2018 – 2021).
        """,
        SWIGGY_BACKEND,
        ["Senior Full Stack Engineer", "Cloud & DevOps Solutions Engineer"],
    ),
]

@pytest.mark.parametrize("name, cv_text, target_job, expected_pathway_titles", LEGITIMATE_CANDIDATES)
def test_legitimate_candidates_produce_grounded_pathways_and_high_scores(name, cv_text, target_job, expected_pathway_titles):
    prof = create_profile_from_text(cv_text)
    pw = decompose_career_pathways(cv_text, prof.title)
    pathways = pw.get("pathways", [])

    assert len(pathways) >= 2, f"Failed for real candidate {name}: produced {len(pathways)} pathways"
    found_titles = [p["title"] for p in pathways]
    assert any(any(exp.lower() in t.lower() for exp in expected_pathway_titles) for t in found_titles), (
        f"Expected one of {expected_pathway_titles}, but got {found_titles}"
    )

    if target_job:
        seeds = get_seed_jobs_for_profile(prof)
        assert len(seeds) > 0, f"Failed for real candidate {name}: 0 seed jobs hydrated"
        res = _score_job_deterministic(target_job, cv_text, prof)
        assert res["match_score"] >= 70, f"Failed for real candidate {name} on {target_job['title']}: score was {res['match_score']} %"
        assert res["industry_fit"] in ("core", "adjacent")
