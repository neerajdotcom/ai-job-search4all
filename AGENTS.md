# AGENTS.md — Project Overview & Agent Guidelines

## What This Is

A deploy-your-own AI job-search pipeline. Fork it, add your resume and free
API keys, and get a daily digest of scored job matches with tailored
Fast-Apply packs (cover note + screening Q&A + tailored resume PDF).

**Two execution modes:**

- **API mode** (`main.py`) — uses Groq (scoring) + Gemini (resume tailoring).
  Needs free-tier keys; runs on a cron via GitHub Actions.
- **Native mode** (zero keys) — scoring and tailoring are done by the AI
  agent's own reasoning, not external LLM calls. Entry points are the
  `/setup-native`, `/scrape-native`, and `/apply-native` skills in
  `.agents/skills/`. The same deterministic building blocks (scraper, DOCX
  patch, PDF render, tracker, run snapshots) run via `native/cli.py`.

**First-time setup:** `/setup-native path/to/your_resume.docx`
**Daily job search:** `/scrape-native`
**Tailor for a specific job:** `/apply-native <url-or-paste>`

---

# AGENTS.md — Agent Guidelines & Automated Verification Rules

## 🛡️ Mandatory Testing Rule
Whenever ANY code in this repository is added, modified, refactored, or deleted:
1. **Always invoke and execute the `regression-and-edge-tester` skill** ([`.agent/skills/regression-and-edge-tester/SKILL.md`](file:///.agent/skills/regression-and-edge-tester/SKILL.md)).
2. Execute the full test suite: `.venv/bin/pytest tests/ -v`.
3. Execute the edge-case & negative test suite: `.venv/bin/pytest tests/test_edge_and_negative.py -v`.
4. Ensure 100% passing tests with zero regressions before presenting any solution to the user.

## 🎯 Domain-Agnostic Matching Standard
- Never hardcode exclusions for specific job domains (e.g. QA, Testing, SDET, Software Engineering, Product).
- Ensure the scraper and match scorer dynamically support candidates from any professional background.
- Maintain the high-density seed catalog (`storage/seed_catalog.py`) so offline or network-isolated runs always return valid, scored recommendations.
