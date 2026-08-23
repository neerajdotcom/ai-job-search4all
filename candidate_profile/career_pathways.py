"""
candidate_profile/career_pathways.py — AI Career Divergence & Multi-Track Persona Analyzer.

Deconstructs any candidate's resume into 2-3 distinct, viable career pathways:
1. Core Direct Trajectory: Proven primary title and immediate progression.
2. Adjacent Industry Pivot: Domain experience applied to product, operations, or cross-industry verticals.
3. Specialized Functional Niche: Tool mastery and technical depth applied to specialist roles.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CAREER_PATHWAY_PROMPT = """You are an elite Executive Career Strategist and Talent Architect.
Analyze the candidate's resume below and identify 2 to 3 DISTINCT, HIGH-FIT CAREER DIVERGENCE PATHWAYS.

Do not just output 3 variations of the exact same job title. Decompose their transferable skills, domain exposure, and technical competencies into:
- Track A (Core Trajectory): Their primary, most natural career progression.
- Track B (Adjacent Pivot): A viable domain/industry pivot where their experience (e.g. streaming, fintech, SaaS, operations) directly applies.
- Track C (Specialized Niche): A focused technical or functional specialization based on their hands-on tool proficiencies or methodology.

Resume Content:
\"\"\"
{resume_text}
\"\"\"

Respond with valid JSON only in this exact schema:
{{
  "candidate_name": "string",
  "experience_years": number,
  "pathways": [
    {{
      "id": "track_a",
      "role_type": "core",
      "title": "Primary Direct Job Title",
      "track_label": "Track A: Core Trajectory",
      "potential_score": 95,
      "tagline": "Direct progression in primary domain",
      "target_companies": ["Company1", "Company2", "Company3"],
      "search_queries": ["Query 1", "Query 2", "Query 3"],
      "target_industries": ["Industry1", "Industry2"],
      "key_transferable_skills": ["Skill1", "Skill2", "Skill3"]
    }},
    {{
      "id": "track_b",
      "role_type": "pivot",
      "title": "Adjacent Pivot Job Title",
      "track_label": "Track B: Industry Pivot",
      "potential_score": 88,
      "tagline": "Applying domain mastery to operations/product",
      "target_companies": ["Company4", "Company5"],
      "search_queries": ["Query 4", "Query 5"],
      "target_industries": ["Industry3", "Industry4"],
      "key_transferable_skills": ["Skill4", "Skill5"]
    }},
    {{
      "id": "track_c",
      "role_type": "niche",
      "title": "Specialized Functional Title",
      "track_label": "Track C: Specialized Niche",
      "potential_score": 82,
      "tagline": "High-impact specialization based on technical tools and methodology",
      "target_companies": ["Company6", "Company7"],
      "search_queries": ["Query 6", "Query 7"],
      "target_industries": ["Industry5"],
      "key_transferable_skills": ["Skill6", "Skill7"]
    }}
  ]
}}
"""


def _heuristic_pathway_decomposition(resume_text: str, detected_title: str = "") -> List[Dict[str, Any]]:
    """Zero-key, deterministic heuristic fallback for discovering career divergence tracks."""
    text_lower = (resume_text or "").lower()
    title_lower = detected_title.lower() if detected_title else ""
    full_blob = f"{title_lower} {text_lower}"

    # 1. iGaming, Game Production & Slot Lifecycle PMO
    if re.search(r"\b(gaming|igaming|casino|slot\s+game|game\s+producer|game\s+production|arrise|pragmatic\s+play)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Game Producer / iGaming Delivery Lead",
                "track_label": "Track A: Core Trajectory (Gaming / PMO)",
                "potential_score": 98,
                "tagline": "End-to-end 2D/3D slot lifecycle, Art/Math/Dev cross-functional coordination, and release delivery",
                "target_companies": ["Pragmatic Play", "Evolution", "Playtech", "Aristocrat", "Light & Wonder", "Moon Active"],
                "search_queries": ["Game Producer", "iGaming Project Manager", "Senior Project Coordinator PMO", "Agile Delivery Manager"],
                "target_industries": ["iGaming", "Gaming & Entertainment", "Casino & Slot Systems"],
                "key_transferable_skills": ["Slot Asset Pipeline", "Math/Art/Dev Handoff", "Sprint Burndown & JIRA", "PMO Governance & RAID"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Media Localization & OTT Content Lead",
                "track_label": "Track B: Divergent Trajectory (Localization / OTT)",
                "potential_score": 95,
                "tagline": "Multi-language OTT mastering, theatrical localization, subtitling QC & streaming distribution",
                "target_companies": ["Netflix", "Crunchyroll", "Deluxe Media", "Visual Data", "Iyuno", "Amazon Studios"],
                "search_queries": ["Localization Project Manager", "OTT Content Operations Lead", "Media Operations Manager"],
                "target_industries": ["Media & Streaming", "Entertainment", "Language Services"],
                "key_transferable_skills": ["Subtitling & Dubbing QC", "Vendor SLA Management", "TMS/EZTitles", "Content Mastering"],
            },
            {
                "id": "track_c",
                "role_type": "niche",
                "title": "Technical Program Manager / PMO Lead",
                "track_label": "Track C: Specialized Enterprise PMO",
                "potential_score": 90,
                "tagline": "Cross-functional governance, stakeholder alignment, risk mitigation, and executive telemetry",
                "target_companies": ["Swiggy", "Postman", "Barclays", "Cognizant", "PwC"],
                "search_queries": ["Technical Program Manager", "PMO Lead", "Senior Delivery Manager"],
                "target_industries": ["Enterprise Tech", "SaaS & Fintech", "Consulting"],
                "key_transferable_skills": ["Executive Dashboards", "Cross-Functional Alignment", "Risk & Dependency Mapping", "Process Improvement"],
            },
        ]

    # 2. Media, Localization, Subtitling & Content Operations
    if re.search(r"\b(localization|subtitling|dubbing|transcreation|lqa|translation\s+management|eztitles|subtitles)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Localization Project Manager",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 98,
                "tagline": "Direct management of multi-language media & localization lifecycles",
                "target_companies": ["Netflix", "Crunchyroll", "Sony Pictures", "Amazon Studios"],
                "search_queries": ["Localization Project Manager", "Senior Media Localization Lead", "Subtitling Project Manager"],
                "target_industries": ["Media & Streaming", "Entertainment", "Anime & Gaming"],
                "key_transferable_skills": ["Subtitling QC", "Vendor Management", "EZTitles/TMS", "Localization QA"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "OTT Content Operations Lead",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 91,
                "tagline": "Digital streaming distribution, asset delivery & media workflow management",
                "target_companies": ["Amazon Prime Video", "Disney+", "YouTube", "Warner Bros"],
                "search_queries": ["OTT Content Operations Lead", "Digital Asset Coordinator", "Media Operations Manager"],
                "target_industries": ["OTT Platforms", "Digital Streaming", "Broadcasting"],
                "key_transferable_skills": ["Asset Ingestion", "Delivery SLAs", "Metadata Management", "Workflow Automation"],
            },
            {
                "id": "track_c",
                "role_type": "niche",
                "title": "Subtitling Quality & LQA Lead",
                "track_label": "Track C: Specialized Niche",
                "potential_score": 85,
                "tagline": "Linguistic excellence, caption timecoding & localization quality control",
                "target_companies": ["Deluxe Media", "Iyuno", "TransPerfect", "Keywords Studios"],
                "search_queries": ["Subtitling Quality Manager", "LQA Specialist", "Translation Quality Lead"],
                "target_industries": ["Language Services", "Post-Production", "Subtitling Studios"],
                "key_transferable_skills": ["Timecode Sync", "SRT/VTT/TTML", "LQA Auditing", "Glossary Compliance"],
            },
        ]

    # 3. Data Science, Machine Learning & AI Engineering
    if re.search(r"\b(data\s+scientist|machine\s+learning\s+engineer|deep\s+learning\s+engineer|nlp\s+engineer|computer\s+vision\s+engineer|pytorch|tensorflow|scikit-learn|data\s+science\s+lead)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Lead Machine Learning Scientist",
                "track_label": "Track A: Core Trajectory (Data & AI)",
                "potential_score": 97,
                "tagline": "Predictive modeling, distributed neural architectures, and real-time inference",
                "target_companies": ["Google", "Meta", "Datadog", "OpenAI", "Anthropic"],
                "search_queries": ["Lead Machine Learning Engineer", "Staff Data Scientist", "AI Research Scientist"],
                "target_industries": ["Artificial Intelligence", "High-Scale Tech", "Fintech"],
                "key_transferable_skills": ["PyTorch/TensorFlow", "MLOps Pipelines", "Statistical Modeling", "Distributed Training"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Staff Data & Analytics Engineer",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 90,
                "tagline": "Real-time stream processing, distributed data warehousing, and ETL infrastructure",
                "target_companies": ["Snowflake", "Databricks", "Stripe", "Uber"],
                "search_queries": ["Staff Data Engineer", "Analytics Platform Lead", "Data Architect"],
                "target_industries": ["Cloud Infrastructure", "Data Platforms", "Enterprise SaaS"],
                "key_transferable_skills": ["Spark / Kafka", "Data Lakehouse", "SQL & dbt", "High-Throughput Streaming"],
            },
        ]

    # 4. Software Engineering / Web / Fullstack
    if re.search(r"\b(software\s+engineer|full\s*stack\s+engineer|full\s*stack\s+developer|backend\s+developer|backend\s+engineer|frontend\s+developer|frontend\s+engineer|golang\s+developer|python\s+developer|java\s+developer|microservices\s+architect)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Senior Full Stack Engineer",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 96,
                "tagline": "End-to-end product feature development and scalable web architecture",
                "target_companies": ["Stripe", "Notion", "Figma", "Razorpay"],
                "search_queries": ["Senior Full Stack Engineer", "Staff Software Engineer", "Senior Web Developer"],
                "target_industries": ["SaaS & Cloud", "Developer Tools", "Fintech"],
                "key_transferable_skills": ["React/TypeScript", "Node/Python", "API Design", "PostgreSQL"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Cloud & DevOps Solutions Engineer",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 89,
                "tagline": "Infrastructure reliability, Docker/K8s automation, and CI/CD pipelines",
                "target_companies": ["Datadog", "Canonical", "GitLab", "Cloudflare"],
                "search_queries": ["Cloud DevOps Engineer", "Platform Engineer", "Site Reliability Specialist"],
                "target_industries": ["Cloud Infrastructure", "Enterprise Platforms", "Cybersecurity"],
                "key_transferable_skills": ["Kubernetes/Docker", "CI/CD Automation", "Terraform", "Monitoring & Telemetry"],
            },
            {
                "id": "track_c",
                "role_type": "niche",
                "title": "UI/UX Design Systems Engineer",
                "track_label": "Track C: Specialized Niche",
                "potential_score": 84,
                "tagline": "High-craft component libraries, accessibility, and interactive web motion",
                "target_companies": ["Vercel", "Linear", "Supabase", "Automattic"],
                "search_queries": ["Design Systems Engineer", "Frontend Architect", "UI Component Specialist"],
                "target_industries": ["Product Design Tech", "Modern Web SaaS"],
                "key_transferable_skills": ["Component Architecture", "Design Systems", "Web Performance", "Accessibility"],
            },
        ]

    # 5. Cloud, DevOps & Platform Engineering
    if re.search(r"\b(cloud\s+engineer|devops\s+engineer|platform\s+engineer|sre\s+lead|site\s+reliability\s+engineer|infrastructure\s+architect)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Principal Cloud & DevOps Solutions Engineer",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 96,
                "tagline": "Infrastructure reliability, Docker/K8s automation, and CI/CD pipelines",
                "target_companies": ["Datadog", "Canonical", "GitLab", "Cloudflare"],
                "search_queries": ["Cloud DevOps Engineer", "Platform Engineer", "Site Reliability Specialist"],
                "target_industries": ["Cloud Infrastructure", "Enterprise Platforms", "Cybersecurity"],
                "key_transferable_skills": ["Kubernetes/Docker", "CI/CD Automation", "Terraform", "Monitoring & Telemetry"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Staff Platform & Systems Architect",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 90,
                "tagline": "High-scale distributed systems, multi-cloud networking, and infrastructure as code",
                "target_companies": ["AWS", "Google Cloud", "Stripe", "HashiCorp"],
                "search_queries": ["Platform Architect", "Infrastructure Lead", "Principal Systems Engineer"],
                "target_industries": ["Cloud Platforms", "Enterprise SaaS"],
                "key_transferable_skills": ["Multi-Cloud Architecture", "Kubernetes Mesh", "IaC / Terraform", "Observability"],
            },
        ]

    # 5. QA / SDET / Quality Engineering
    if re.search(r"\b(qa\s+lead|qa\s+engineer|senior\s+qa|sdet|selenium|cypress|playwright|test\s+automation|quality\s+assurance|automation\s+architect)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Lead SDET / QA Automation Architect",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 97,
                "tagline": "Enterprise test automation frameworks and zero-defect quality systems",
                "target_companies": ["Cognizant", "Postman", "Swiggy", "Barclays"],
                "search_queries": ["Lead SDET", "Lead QA Engineer", "QA Automation Architect"],
                "target_industries": ["Enterprise Tech", "API Platforms", "Fintech"],
                "key_transferable_skills": ["Selenium/Playwright", "API Testing", "CI/CD Quality Gates", "Python/Java"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Release & Delivery Operations Manager",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 88,
                "tagline": "Cross-functional release orchestration, sprint delivery, and risk governance",
                "target_companies": ["Amazon", "Turing", "Infosys", "Wipro"],
                "search_queries": ["Release Manager", "Delivery Operations Lead", "Technical Program Lead"],
                "target_industries": ["Enterprise Delivery", "E-Commerce", "SaaS"],
                "key_transferable_skills": ["Sprint Governance", "Release Management", "JIRA/Agile", "Risk Mitigation"],
            },
            {
                "id": "track_c",
                "role_type": "niche",
                "title": "Performance & Security QA Specialist",
                "track_label": "Track C: Specialized Niche",
                "potential_score": 83,
                "tagline": "High-concurrency load testing, chaos resilience, and vulnerability assessment",
                "target_companies": ["Datadog", "Razorpay", "Zomato"],
                "search_queries": ["Performance Test Engineer", "Security QA Specialist", "Chaos Engineer"],
                "target_industries": ["High-Scale Fintech", "Cloud Platforms"],
                "key_transferable_skills": ["JMeter/Locust", "Load Testing", "API Security", "Observability"],
            },
        ]

    # 6. Product Management & Strategy
    if re.search(r"\b(product\s+manager|product\s+management|product\s+owner|roadmap\s+strategy|user\s+stories|prd)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Senior Product Manager",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 96,
                "tagline": "Product discovery, roadmap leadership, and user-centric feature delivery",
                "target_companies": ["Stripe", "Zomato", "Swiggy", "Notion"],
                "search_queries": ["Senior Product Manager", "Group Product Manager", "Product Lead"],
                "target_industries": ["Consumer Apps", "SaaS & Marketplace", "Fintech"],
                "key_transferable_skills": ["Product Roadmap", "PRD Authoring", "User Research", "Agile Leadership"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Technical Delivery & Agile Program Lead",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 90,
                "tagline": "Engineering alignment, squad velocity, and cross-team program delivery",
                "target_companies": ["Cognizant", "Barclays", "Deloitte"],
                "search_queries": ["Agile Delivery Lead", "Technical Program Manager", "Scrum Master Lead"],
                "target_industries": ["Enterprise Consulting", "Banking Technology"],
                "key_transferable_skills": ["Sprint Velocity", "Dependency Management", "Stakeholder Alignment"],
            },
        ]

    # 7. Creative Direction, UI/UX & Brand Design
    if re.search(r"\b(creative\s+director|art\s+director|ui/ux\s+designer|product\s+designer|brand\s+designer|graphic\s+designer|figma|typography\s+lead)\b", full_blob):
        return [
            {
                "id": "track_a",
                "role_type": "core",
                "title": "Executive Creative Director",
                "track_label": "Track A: Core Trajectory",
                "potential_score": 96,
                "tagline": "Brand identity systems, visual storytelling, and multi-channel campaign direction",
                "target_companies": ["Pentagram", "Wieden+Kennedy", "Apple", "Airbnb"],
                "search_queries": ["Executive Creative Director", "Head of Design", "Brand Design Director"],
                "target_industries": ["Design Studios", "Brand Consulting", "Consumer Tech"],
                "key_transferable_skills": ["Brand Strategy", "Creative Direction", "Typography & Layout", "Campaign Leadership"],
            },
            {
                "id": "track_b",
                "role_type": "pivot",
                "title": "Principal Product & UX Designer",
                "track_label": "Track B: Industry Pivot",
                "potential_score": 89,
                "tagline": "Design systems, user experience architecture, and digital interaction",
                "target_companies": ["Figma", "Linear", "Vercel", "Stripe"],
                "search_queries": ["Principal Product Designer", "Staff UI/UX Designer", "Design Systems Lead"],
                "target_industries": ["Product Tech", "Modern SaaS"],
                "key_transferable_skills": ["Figma / Systems", "Interaction Design", "User Research", "Prototyping"],
            },
        ]

    # 8. Unrecognized / Synthetic Domain -> Return Empty List (Never hallucinate fake tracks)
    return []


def decompose_career_pathways(resume_text: str, detected_title: str = "", llm=None) -> Dict[str, Any]:
    """
    Analyzes any resume and returns structured career divergence tracks.
    Attempts LLM decomposition first, seamlessly falling back to heuristic parsing.
    """
    if not resume_text or not resume_text.strip():
        return {
            "candidate_name": "Candidate",
            "experience_years": 0,
            "pathways": [],
        }

    from core.llm import default_llm
    client = llm or default_llm

    prompt = CAREER_PATHWAY_PROMPT.format(resume_text=resume_text[:6000])
    try:
        data = client.generate_json(prompt, temperature=0.2)
        if data and isinstance(data, dict) and data.get("pathways"):
            return data
    except Exception as exc:
        logger.info("LLM pathway decomposition bypassed (%s), applying heuristic engine", exc)

    # Heuristic Fallback
    pathways = _heuristic_pathway_decomposition(resume_text, detected_title)
    from candidate_profile.loader import extract_candidate_name
    candidate_name = extract_candidate_name(resume_text)

    exp_m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience", resume_text, re.I)
    years = int(exp_m.group(1)) if exp_m else 5

    return {
        "candidate_name": candidate_name,
        "experience_years": years,
        "pathways": pathways,
    }
