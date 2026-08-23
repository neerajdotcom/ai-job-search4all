# 🚨 MANDATORY RULE: Automated Verification on Every Code Change

**TRIGGER**: Whenever ANY code is added, modified, refactored, or removed in this codebase (`*.py`, `*.html`, `*.js`, `*.css`, or config files).

**ACTION**:
You MUST unconditionally invoke and execute the `regression-and-edge-tester` skill:
1. Run `.venv/bin/pytest tests/ -v` (Full 59+ test regression suite).
2. Run `.venv/bin/pytest tests/test_edge_and_negative.py -v` (Edge cases, corrupt uploads, boundary limits, security defenses).
3. Run `.venv/bin/pytest tests/test_webapp.py -v` (Webapp routes, file uploads, cloud link fetchers).
4. Verify multi-domain profile matching (QA, Engineering, Product tracks) produces active jobs and scores > 0%.

**NO EXCEPTIONS**: Never claim a task is completed or respond to the user without executing and verifying this test suite.
