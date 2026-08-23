"""
storage/seed_catalog.py — High-density, multi-industry curated job catalog.

Serves as:
1. Resilient offline / zero-network fallback when outbound web scraping is blocked (e.g. sandbox, corporate firewalls, rate limits).
2. Domain-diverse seed postings across QA, Engineering, Product, Cloud, AI/ML, Data, and Operations.
"""

from datetime import datetime, timezone
import re

SEED_JOBS = [
    # --------------------------------------------------------------------------
    # LOCALIZATION PROJECT MANAGEMENT, SUBTITLING & MEDIA CONTENT (OTT/Anime/Movies)
    # --------------------------------------------------------------------------
    {
        "title": "Localization Project Manager (Subtitling & Dubbing)",
        "company": "Netflix",
        "location": "Mumbai / Pune, India (Remote Eligible)",
        "apply_url": "https://jobs.netflix.com/search?q=localization",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Netflix is looking for an experienced Localization Project Manager to oversee subtitling, dubbing, and audio description across our global slate of original films, series, and anime.
Responsibilities:
- Manage end-to-end localization lifecycles for high-priority theatrical releases, OTT web series, and international episodic content.
- Coordinate linguists, subtitling vendors, translation studios, and dubbing directors to ensure cultural authenticity and linguistic excellence.
- Supervise Localization Quality Assurance (LQA) and subtitle timing QC (framerate, character limits, reading speeds, sync).
- Manage localization schedules, master asset delivery pipelines, and post-production vendor SLAs.
- Partner with Creative Dubbing leads, Content Operations, and Mastering engineers to troubleshoot asset workflows.
Requirements:
- 5+ years of experience in Localization Project Management, Subtitling, Dubbing, or Post-Production Media Operations.
- Deep familiarity with subtitling tools (EZTitles, Subtitle Edit, Swift), translation management systems (TMS), and cloud subtitling platforms.
- Background managing subtitle assets for streaming OTT platforms, movies, anime, or gaming narratives.
- Exceptional project management, cross-cultural communication, and vendor management skills.
        """.strip(),
    },
    {
        "title": "Senior Media Localization Lead (Anime & OTT Content)",
        "company": "Crunchyroll (Sony Pictures Entertainment)",
        "location": "Worldwide (Remote) / Pune, India",
        "apply_url": "https://boards.greenhouse.io/crunchyroll",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Crunchyroll is hiring a Senior Media Localization Lead to direct subtitling and dubbing operations for our rapidly expanding global anime catalog.
Key Responsibilities:
- Oversee Japanese-to-English / Multi-Language subtitling, simulcast localization pipelines, and dubbing project schedules.
- Ensure fidelity to character voice, cultural nuances, terminology glossaries, and original IP narrative intent.
- Lead localization quality assurance (LQA) reviews across subtitle files (SRT, VTT, TTML, PAC, STL).
- Manage external language service providers (LSPs), freelance subtitlers, and QC proofreaders.
- Collaborate with Video Operations to resolve caption encoding, burnt-in subtitle rendering, and sync issues.
Requirements:
- 4-8 years experience in Anime/Film/TV Subtitling, Media Localization, or Entertainment Translation Project Management.
- Strong understanding of anime pop culture, Japanese cultural tropes, and media localization best practices.
- Proficiency with subtitling standards, timecoding conventions, and translation project management.
        """.strip(),
    },
    {
        "title": "Content Localization Project Manager (Subtitling & Post-Production)",
        "company": "Deluxe Media",
        "location": "Pune / Mumbai, India",
        "apply_url": "https://careers.bydeluxe.com/search-jobs",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Deluxe Media Pune is hiring a Localization Project Manager for our global digital distribution and subtitling operations.
Responsibilities:
- Drive project execution for feature films, episodic streaming shows, and broadcast localization across 40+ languages.
- Coordinate subtitle creation, translation, proofreading, conform editing, and quality control.
- Track project milestones, client deliverables, dub cards, and technical metadata.
- Serve as the primary liaison between major Hollywood / OTT studio clients and internal production hubs.
Requirements:
- 4+ years in Localization Project Management, Subtitling, Audio/Video Post-Production, or Translation Management.
- Hands-on experience with subtitling software, caption formats (DFXP, WebVTT, SCC), and media delivery specifications.
- Strong organizational ability, attention to detail, and ability to manage tight broadcast deadlines.
        """.strip(),
    },
    {
        "title": "OTT Subtitling & Operations Lead",
        "company": "Iyuno",
        "location": "Pune / Mumbai, India (Hybrid)",
        "apply_url": "https://iyuno.com/careers",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Iyuno is the global leader in media localization and entertainment technology services. We are seeking an experienced OTT Subtitling & Operations Lead to oversee high-throughput localization workflows for premium streaming content.
Key Responsibilities:
- Lead and manage end-to-end subtitle creation, translation QC, caption conform editing, and timed text deliverables for leading global streaming platforms including Netflix, Disney+, and Amazon Prime Video.
- Monitor linguistic quality assurance (LQA) scores, translator turnaround times, glossary compliance, and subtitle consistency across multiple regional language pairs.
- Coordinate with post-production supervisors, dubbing studios, and digital supply chain teams to resolve subtitle timing discrepancies, format mismatches (WebVTT, DFXP, TTML, SRT), and metadata errors.
- Track production schedules and milestone delivery across simultaneous multi-episode television series and feature film releases.
Requirements:
- 4-8 years of experience in Media Localization, Subtitling Operations, Audio-Visual Translation, or Post-Production Project Management.
- Hands-on proficiency with professional subtitling software (e.g. EZTitles, Subtitle Edit, Swift) and media asset management systems.
- Strong organizational, vendor management, and cross-functional communication skills with a proven track record meeting strict OTT delivery deadlines.
        """.strip(),
    },
    {
        "title": "Subtitling & Translation Quality Manager",
        "company": "TransPerfect Media",
        "location": "Worldwide (Remote) / India",
        "apply_url": "https://www.transperfect.com/careers",
        "source": "remotive",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
TransPerfect Media is seeking a Remote Subtitling & Translation Quality Manager to drive quality standards across global localization pipelines for film, television, and digital streaming clients.
Key Responsibilities:
- Oversee linguistic quality control, terminology management, and translation consistency for multi-lingual subtitling and dubbing projects.
- Manage external language service vendors, freelance subtitlers, and in-house proofreaders to ensure compliance with client-specific style guides and international delivery specifications.
- Develop and enforce standardized Quality Assurance (QA) checklists, linguistic evaluation scorecards, and error classification rubrics.
- Facilitate root cause analysis on subtitle rejection reports and implement corrective training programs for translation teams.
- Collaborate with project managers and client account directors to provide real-time updates on high-profile entertainment media releases.
Requirements:
- 5+ years of experience in Subtitling Quality Management, Translation QC, or Localization Project Coordination within entertainment media.
- In-depth understanding of subtitling standards, timed text formats, subtitle frame rates, line length constraints, and reading speed metrics.
- Familiarity with Translation Memory (TM) systems, TMS platforms, and subtitle QA automation tools.
        """.strip(),
    },
    {
        "title": "Localization Project Manager - Prime Video Media",
        "company": "Amazon Studios",
        "location": "Worldwide (Remote) / India",
        "apply_url": "https://amazon.jobs/en/search?base_query=Localization",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Amazon Prime Video is seeking a talented Localization Project Manager to support international title launches, subtitling, and dubbing operations across global streaming markets.
Key Responsibilities:
- Manage the end-to-end localization delivery lifecycle for Amazon Original movies, series, and licensed catalog titles across Asian and international language pairs.
- Partner with post-production operations, audio localization leads, mastering facilities, and creative directors to ensure on-time delivery of localized audio, subtitles, and metadata assets.
- Supervise external localization vendors, dubbing partners, and QC agencies, managing SLA performance, capacity planning, and deliverable handoffs.
- Identify operational bottlenecks across digital ingestion pipelines and champion workflow automation and continuous process improvements.
- Ensure strict adherence to Amazon content security protocols and quality benchmarks across all media localization assets.
Requirements:
- 5+ years of progressive project management experience in Subtitling, Dubbing, or Media Localization Operations for television, film, or OTT platforms.
- Deep expertise in media supply chain workflows, localized asset distribution, and captioning standards.
- Exceptional stakeholder management, data-driven analytical skills, and ability to navigate fast-paced media delivery cycles.
        """.strip(),
    },
    # --------------------------------------------------------------------------
    # QA / TEST AUTOMATION / SDET ROLES (Pune, Bangalore, Remote, Global)
    # --------------------------------------------------------------------------
    {
        "title": "Lead QA Engineer / SDET Lead",
        "company": "Cognizant",
        "location": "Pune, India",
        "apply_url": "https://careers.cognizant.com/global/en/c/technology-engineering-jobs",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
We are seeking an experienced Lead QA Engineer / SDET Lead to join our Pune engineering hub.
Key Responsibilities:
- Architect and maintain enterprise-grade test automation frameworks using Selenium, Playwright, Cypress, and Python/Java.
- Lead end-to-end quality assurance across web, mobile, and API microservices.
- Design performance, stress, and security testing pipelines using JMeter and Postman.
- Integrate automated regression suites into CI/CD pipelines (Jenkins, GitHub Actions, GitLab).
- Collaborate with Product Managers and Engineering leads on sprint planning, test strategy, and release sign-offs.
Requirements:
- 6+ years of hands-on experience in Software Quality Assurance, Test Automation, and SDET leadership.
- Strong proficiency in API testing (REST/GraphQL), SQL queries, and CI/CD integration.
- Proven experience mentoring QA engineers and establishing zero-defect testing standards.
        """.strip(),
    },
    {
        "title": "Senior Quality Assurance Analyst",
        "company": "Barclays",
        "location": "Pune, India",
        "apply_url": "https://search.jobs.barclays/search-jobs",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Barclays Pune is hiring a Senior QA Analyst for our Banking Platform Technology team.
Responsibilities:
- Create detailed, comprehensive, and well-structured test plans and test cases for financial workflows.
- Execute manual and automated test suites for trading, compliance, and payment settlement systems.
- Identify, record, document thoroughly, and track software bugs using JIRA.
- Perform thorough regression testing when bugs are resolved.
- Develop and apply testing processes for new and existing products.
Requirements:
- 4-8 years of experience in Software Quality Assurance and functional testing.
- Strong knowledge of software QA methodologies, tools, and processes.
- Experience with Agile/Scrum development process.
- Hands-on experience with automated testing tools (Selenium WebDriver, RestAssured) is a plus.
        """.strip(),
    },
    {
        "title": "Staff SDET - Platform Quality",
        "company": "Postman",
        "location": "Bangalore, India (Remote Eligible)",
        "apply_url": "https://www.postman.com/company/careers/open-positions/",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Postman is looking for a Staff SDET to elevate quality engineering across our developer API platform.
What you'll do:
- Design, architect, and implement scalable test automation frameworks for high-concurrency cloud systems.
- Drive reliability testing, chaos engineering, and contract testing across 100+ microservices.
- Evangelize quality-first engineering practices and partner with platform teams to reduce flaky tests.
- Build monitoring, observability dashboards, and synthetic testing alerts in Datadog.
Requirements:
- 8+ years experience in Software Development in Test (SDET), test automation architecture, and distributed systems.
- Deep expertise in JavaScript/TypeScript, Go, or Python.
- Proven track record of architecting CI/CD quality gates for enterprise SaaS.
        """.strip(),
    },
    {
        "title": "QA Automation Engineer (Mobile & Web)",
        "company": "Swiggy",
        "location": "Pune / Bangalore, India",
        "apply_url": "https://careers.swiggy.com/",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Join Swiggy's consumer tech engineering team in building robust delivery experiences.
Requirements:
- 3-6 years experience in automated mobile (Appium) and web (Playwright/Selenium) testing.
- Strong proficiency in Java or Python and BDD frameworks (Cucumber).
- Experience with performance testing tools (Gatling, Locust) and cloud device farms (BrowserStack).
        """.strip(),
    },
    {
        "title": "Senior Test Automation Architect",
        "company": "Turing",
        "location": "Worldwide (Remote)",
        "apply_url": "https://www.turing.com/jobs",
        "source": "remotive",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Turing is looking for a Senior Test Automation Architect for a high-growth US client.
Requirements:
- 7+ years of experience leading QA automation and CI/CD quality engineering.
- Deep expertise in Cypress, Playwright, Python, AWS, Docker, and Kubernetes.
- Excellent English communication skills and experience in remote-first teams.
        """.strip(),
    },

    # --------------------------------------------------------------------------
    # SOFTWARE ENGINEERING / FULLSTACK / BACKEND / DEVOPS
    # --------------------------------------------------------------------------
    {
        "title": "Senior Backend Engineer (Python / Distributed Systems)",
        "company": "Razorpay",
        "location": "Pune / Bangalore, India (Hybrid)",
        "apply_url": "https://razorpay.com/jobs/",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Razorpay is looking for a Senior Backend Engineer to build resilient financial checkout and payment infrastructure.
Responsibilities:
- Build high-throughput microservices handling millions of daily transactions with sub-50ms latency.
- Design database schemas and data access layers using PostgreSQL, Redis, and Apache Kafka.
- Implement robust telemetry, metrics, and distributed tracing using OpenTelemetry.
Requirements:
- 5+ years of experience building scalable backend services in Python, Go, or Java.
- Strong expertise in concurrency, relational databases, distributed caching, and microservices architecture.
        """.strip(),
    },
    {
        "title": "Full Stack Engineer (React / Node / TypeScript)",
        "company": "Notion",
        "location": "Worldwide (Remote)",
        "apply_url": "https://www.notion.so/careers",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Notion is hiring a Full Stack Engineer to craft collaborative workspace features used by millions worldwide.
What you will do:
- Build highly responsive, beautiful UI workflows using modern React, TypeScript, and CSS styling.
- Develop reliable backend APIs and synchronization services on Node.js and PostgreSQL.
- Partner with product designers and product managers to iterate rapidly on user feedback.
Requirements:
- 4+ years full stack engineering experience building modern web applications.
- Strong mastery of TypeScript, modern React, state management, and API design.
        """.strip(),
    },
    {
        "title": "Senior Cloud & DevOps Engineer",
        "company": "Canonical",
        "location": "Worldwide (Remote)",
        "apply_url": "https://canonical.com/careers",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Canonical is hiring Senior DevOps Engineers to build open-source cloud infrastructure.
Responsibilities:
- Automate Kubernetes cluster deployments across AWS, GCP, and Azure using Terraform.
- Maintain high-availability CI/CD pipelines, Prometheus monitoring, and zero-downtime releases.
- Troubleshoot Linux kernel, networking, and security configurations.
Requirements:
- 5+ years Linux systems administration, cloud infrastructure, and Kubernetes orchestration experience.
        """.strip(),
    },

    # --------------------------------------------------------------------------
    # PRODUCT MANAGEMENT & AGILE DELIVERY
    # --------------------------------------------------------------------------
    {
        "title": "Senior Product Manager - Platform & Core Experience",
        "company": "Stripe",
        "location": "Worldwide (Remote)",
        "apply_url": "https://stripe.com/jobs/search",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Stripe is looking for a Senior Product Manager to lead platform and infrastructure product strategy.
Responsibilities:
- Define product vision, roadmap, and quarterly OKRs for core developer APIs and merchant platforms.
- Synthesize user research, customer feedback, and data telemetry into clear PRDs.
- Work closely with engineering leads and designers to ship high-impact developer products.
Requirements:
- 5+ years of product management experience shipping technical or SaaS platforms.
- Deep analytical rigor, customer empathy, and exceptional stakeholder management skills.
        """.strip(),
    },
    {
        "title": "Technical Product Manager / Delivery Lead",
        "company": "Zomato",
        "location": "Pune / Gurgaon, India",
        "apply_url": "https://www.zomato.com/careers",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Zomato is hiring a Technical Product Manager / Delivery Lead for our logistics and supply chain systems.
Responsibilities:
- Manage cross-functional sprint deliveries across 4 engineering squads using Agile / Scrum methodologies.
- Translate business requirements into detailed user stories, acceptance criteria, and system sequence diagrams.
- Drive on-time delivery, sprint velocity tracking, and risk mitigation.
Requirements:
- 4-8 years experience in Technical Product Management, Agile Delivery, or Project Management.
- Strong technical background and experience working with REST APIs, SQL, and event-driven architecture.
        """.strip(),
    },

    # --------------------------------------------------------------------------
    # DATA SCIENCE, AI & MACHINE LEARNING
    # --------------------------------------------------------------------------
    {
        "title": "Senior Data Scientist / AI Engineer",
        "company": "Datadog",
        "location": "Worldwide (Remote)",
        "apply_url": "https://www.datadoghq.com/careers/",
        "source": "ats",
        "posted_at": datetime.now(timezone.utc),
        "jd_text": """
Datadog is seeking a Senior Data Scientist / AI Engineer to build intelligent observability models.
Responsibilities:
- Develop anomaly detection and predictive models on high-volume time-series metric streams.
- Fine-tune Large Language Models (LLMs) and build RAG pipelines for root cause analysis.
- Deploy machine learning models into production using Python, PyTorch, Ray, and Triton.
Requirements:
- 5+ years experience in applied Machine Learning, NLP, or Data Science.
- Strong software engineering skills in Python and experience with distributed data processing (Spark).
        """.strip(),
    },
]


def get_seed_jobs_for_profile(profile, limit: int = 25) -> list:
    """Return relevant jobs from the seed catalog matching profile terms & location."""
    search_keywords = [t.lower() for t in (profile.search_terms or [profile.title or ""])]
    if profile.title:
        search_keywords.append(profile.title.lower())

    # Candidate domain focus detectors (strict whole-word matching)
    search_blob = " ".join(search_keywords)
    is_qa_candidate = bool(re.search(r"\b(qa|sdet|quality\s+assurance|test\s+automation)\b", search_blob))
    is_loc_candidate = bool(re.search(r"\b(localiz|subtitl|dubbing|translat|media\s+ops|lqa)\b", search_blob))
    is_gaming_candidate = bool(re.search(r"\b(gaming|igaming|slot|casino|game\s+producer)\b", search_blob))
    is_pm_candidate = bool(re.search(r"\b(product\s+manager|project\s+manager|program\s+manager|delivery\s+manager)\b", search_blob))
    is_dev_candidate = bool(re.search(r"\b(software\s+engineer|backend|frontend|fullstack|developer)\b", search_blob))

    ranked_jobs = []
    for j in SEED_JOBS:
        title_lower = j["title"].lower()
        jd_lower = j["jd_text"].lower()

        score = 0
        for kw in search_keywords:
            if not kw or len(kw) < 3 or kw in ("candidate", "professional"):
                continue
            if kw in title_lower:
                score += 15
            elif kw in jd_lower:
                score += 5

        # Domain alignments
        if is_loc_candidate and any(term in title_lower or term in jd_lower for term in ["localiz", "subtitl", "dubbing", "translat", "media", "anime", "ott"]):
            score += 20

        if is_qa_candidate and ("qa" in title_lower or "sdet" in title_lower or "quality" in title_lower or "test automation" in title_lower):
            score += 20

        if is_gaming_candidate and ("game" in title_lower or "gaming" in title_lower or "slot" in title_lower or "casino" in title_lower):
            score += 20

        if is_pm_candidate and ("project manager" in title_lower or "program manager" in title_lower or "delivery manager" in title_lower or "producer" in title_lower):
            score += 15

        if is_dev_candidate and ("engineer" in title_lower or "developer" in title_lower or "backend" in title_lower or "frontend" in title_lower):
            score += 15

        # Location matching only contributes if there is already positive domain relevance
        if score > 0:
            loc_lower = j["location"].lower()
            target_loc = (profile.location or "").lower()
            if target_loc and any(part in loc_lower for part in target_loc.split(",") if len(part.strip()) > 2):
                score += 8
            elif "remote" in loc_lower or "worldwide" in loc_lower:
                score += 5

        if score >= 10:
            ranked_jobs.append((score, j))

    ranked_jobs.sort(key=lambda x: x[0], reverse=True)
    return [job for _, job in ranked_jobs[:limit]]
