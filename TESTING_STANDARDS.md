# 🧪 TESTING_STANDARDS.md — AI Edge-Case & Negative Testing Architecture

This document establishes the testing standards for `ai-job-search4all`, synthesizing patterns from top AI test generation frameworks (`ai-test-engineer`, `AI-Test-Case-Generator`, `TestGen AI`, `testzeus-hercules`).

---

## 🎯 Core Testing Principles

1. **Zero Unhandled Exceptions**: No unexpected input (null, 0-byte file, malformed JSON, network drop) should ever cause an uncaught 500 or crash the pipeline.
2. **Deterministic & Isolated**: Unit tests must never make real outbound HTTP requests or consume paid LLM API credits. All external I/O is mocked with boundary conditions.
3. **Aggressive Edge-Case & Negative Scenarios**: Every module must be tested against 4 distinct test classes:
   - **Happy Path / Functional**: Standard operational flows with well-formed inputs.
   - **Boundary Conditions**: Null values, zero lengths, maximum payload sizes, Unicode/emojis, whitespace-only.
   - **Negative / Malformed Inputs**: Corrupt file bytes, invalid JSON, spoofed URLs, prompt injection payloads.
   - **Resilience / Fault Injection**: Network timeouts, HTTP 403/429/500 status codes, LLM quota exhaustion, socket drops.

---

## 📊 Negative & Edge-Case Testing Matrix

| Subsystem | Target Hotspots | Edge Cases & Negative Scenarios Tested |
|---|---|---|
| **File Parsing (`/api/resume/upload`)** | `extract_text_from_file_bytes` | 0-byte files, corrupt `.docx` zip headers, unsearchable scanned PDFs, binary garbage, non-UTF8 bytes, `.exe` disguised as `.pdf`. |
| **Cloud Import (`/api/resume/fetch-url`)** | `normalize_cloud_url`, `api_fetch_cloud_resume` | Invalid protocols (`file://`, `ftp://`), private Drive links (HTTP 403), connection timeouts, DNS failure, empty responses. |
| **Profile Grounding & Extraction** | `create_profile_from_text`, `loader.py` | Empty string, whitespace-only, emoji-only resumes, prompt injection attempts (`Ignore previous instructions...`), missing experience years. |
| **Scraper Resiliency** | `scraper/job_scraper.py` | Total network failure (all endpoints 403/500), empty HTML responses, rate limit blocks (429), malformed JSON payloads, circular redirects. |
| **Scorer & Fabrication Validator** | `match_scorer.py`, `fabrication_validator.py` | Empty JD text, 100% fabricated metrics, 0% match thresholds, negative numbers in metrics, unicode quotation marks and math symbols. |
| **Webapp Security & State** | `webapp/app.py`, `storage/tracker_store.py` | Path traversal attempts in download routes, XSS in form inputs, invalid session IDs, non-existent run IDs, invalid tracker state transitions. |
| **SSE Telemetry Streaming** | `/api/match/stream/{session_id}` | Client disconnect midway, non-existent session ID, empty event queue, worker thread exception propagation. |

---

## 🛠️ Test Execution Commands

```bash
# Run complete test suite (Unit + Edge Cases + Negative Tests)
pytest tests/ -v

# Run edge-case and negative tests specifically
pytest tests/test_edge_and_negative.py -v
```
