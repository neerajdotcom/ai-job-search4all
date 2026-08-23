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
