---
name: regression-and-edge-tester
description: >-
  Mandatory automated testing and verification skill. Invoked automatically whenever ANY changes are made
  to code (modifying, adding, refactoring, or removing files). Runs full regression pytest suites, edge-case
  validators, negative scenario matrices, and webapp endpoint checks to guarantee zero breakage.
---

# 🛡️ Code Change Verification & Regression Testing Skill

## 🎯 Purpose
This skill MUST be executed whenever any code is modified, added, refactored, or deleted in the codebase. It ensures zero regressions, zero unhandled 500 exceptions, and continuous multi-domain pipeline stability.

---

## ⚡ Execution Protocol

Whenever a file in `main.py`, `scraper/`, `scorer/`, `optimizer/`, `digest/`, `storage/`, `webapp/`, or `candidate_profile/` is changed, execute the following 5-phase verification workflow:

### Phase 1: Fast Static & Syntax Audit
Verify all modified Python files parse cleanly without syntax or import errors:
```bash
.venv/bin/python3 -m py_compile $(find . -name "*.py" -not -path "*/.venv/*")
```

### Phase 2: Full Regression Pytest Suite
Run the complete automated test suite across all 59+ test cases:
```bash
.venv/bin/pytest tests/ -v
```
*Requirement: 100% of tests must pass (0 failures, 0 errors).*

### Phase 3: Edge-Case & Negative Scenario Matrix
Verify boundary conditions, malformed payloads, corruption resilience, and security defenses:
```bash
.venv/bin/pytest tests/test_edge_and_negative.py -v
```
Checks:
- 0-byte and corrupt `.docx` / `.pdf` file upload rejection (`400` / `500` graceful handling).
- Cloud URL spoofing, invalid URL protocols (`file://`, `ftp://`), and remote 404 handling.
- Empty, whitespace, prompt injection, and Unicode emoji resume extraction safety.
- Anti-fabrication metric extraction and severe hallucination score penalties.
- Path traversal blocking on download endpoints (`/downloads/../../etc/passwd`).
- Invalid tracker status transition rejection.

### Phase 4: Multi-Domain Candidate Simulation Check
Run a headless end-to-end matching check to verify that candidates across all domains (QA, Software Engineering, Product, Cloud, AI) match and score properly without dropping to 0 jobs:
```bash
.venv/bin/python3 -c "
from candidate_profile.loader import create_profile_from_text
from scraper.job_scraper import scrape_all_jobs
from scorer.match_scorer import score_job

cv = '''Malini Sharma\nSenior QA Engineer / Test Automation Lead\nPune, India\n7+ yrs experience in Selenium, Python, Postman, CI/CD, and Agile.'''
profile = create_profile_from_text(cv)
jobs = scrape_all_jobs(profile)
assert len(jobs) > 0, 'FAILURE: Scraper returned 0 jobs for QA candidate'
scored = score_job(jobs[0], cv, profile)
assert scored.get('match_score', 0) > 0, 'FAILURE: Job scored 0%'
print('✓ Multi-domain candidate simulation PASSED with', len(jobs), 'jobs')
"
```

### Phase 5: Webapp Live Route Verification
Run webapp API route integration tests:
```bash
.venv/bin/pytest tests/test_webapp.py -v
```

---

## 🛑 Strict Rules

1. **Never Mark a Task Done Without Testing**: Do not inform the user that a feature or fix is complete until all phases of this skill pass with 100% success.
2. **Never Allow Network Leaks in Unit Tests**: External HTTP requests in unit tests must always be mocked or use local test fixtures.
3. **Preserve Zero-Job Immunity**: If an edit modifies scraping or prefiltering, always test with multi-domain resumes (e.g. QA, Engineering, Product) to guarantee no candidate profile ever receives 0 matches due to domain filtering.
