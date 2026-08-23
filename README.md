# 🚀 Job Scout: Observable AI Job Search & Recommendation Agent

An open-for-all, observable AI job-matching agent. Anyone can paste their résumé or upload a file, instantly scrape live job boards (LinkedIn, Remotive, Greenhouse, Lever, Ashby, Workable, Adzuna), evaluate fit (0–100%), review honest skill gap explanations, and receive tailored Fast-Apply packs with direct 1-click links to job portals.

> **The human applies. The agent never auto-submits.** Every recommendation is grounded against verified résumé facts with strict anti-fabrication guardrails.

---

## 🌟 Key Features

* **⚡ Instant Open-For-All Matcher**: Paste your résumé text or drop a `.docx`/`.pdf` in the web UI. On-the-fly profiling immediately searches active openings.
* **🌐 Multi-Source Zero-Key Sourcing**:
  * **LinkedIn Guest API**: Public unauthenticated guest job search (zero keys required).
  * **Remotive API**: High-quality remote tech, product, engineering, and management listings (zero keys required).
  * **Direct Employer ATS Feeds**: Live Greenhouse, Lever, Ashby, and Workable open positions.
  * **Adzuna**: High-volume syndicated aggregator (free tier).
* **🧠 Universal Multi-Model Engine**: Pluggable support for **Groq** (free fast scoring), **Google Gemini** (free tailoring), **OpenAI**, **Anthropic**, and **Ollama** (local offline models).
* **🛡️ Strict Anti-Fabrication & Grounding Validator**: Validates that all metrics (percentages, dollar amounts, multipliers), companies, and career claims in tailored materials exist in the candidate's ground-truth CV.
* **🔎 Dynamic Query Reformulation**: If a niche search yields few initial matches, the agent dynamically broadens queries to find adjacent roles.
* **📊 Deep Observability & Tracing**: Step-by-step trace tree with latency, token usage, and cost estimations. Seamlessly connects to **Comet Opik** or logs local JSON traces.
* **🧪 100% Offline Automated Test Suite**: Comprehensive `pytest` test suite running without API keys or network calls.
* **✉️ Direct Portal Redirects & Sharing**: 1-click apply links to original portals, Fast-Apply copy-to-clipboard packs, and email digest sharing.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
git clone https://github.com/neerajdotcom/ai-job-search4all.git
cd ai-job-search4all
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run Offline Tests
```bash
make test
# or: pytest tests/ -v
```

### 3. Launch the Web Portal
```bash
make app
# or: python -m webapp
```
Open **`http://127.0.0.1:8000/`** in your browser:
1. Paste your résumé into the text area.
2. Select your target location or check *Include Remote / Worldwide roles*.
3. Click **⚡ Find My Matches & Tailor Applications**.
4. Watch the live progress stream and browse your tailored recommendations!

---

## 💻 CLI & Batch Pipeline Modes

For unattended daily runs (e.g. GitHub Actions cron or local batch execution):

```bash
# 1. Onboarding: generate profile from resume
python setup_profile.py --resume path/to/your_resume.docx

# 2. Dry-run pipeline
python main.py --dry-run

# 3. Live pipeline execution
python main.py
```

### Zero-Key Claude-Native Mode
If running inside Claude Code / AGY:
```bash
/setup-native path/to/resume.docx
/scrape-native
/apply-native https://example.com/job/posting
```

---

## 📁 Repository Structure

```
├── core/                       # Universal AI engine & Opik/local tracer
│   ├── llm.py                  # Multi-provider client (Groq, Gemini, OpenAI, Ollama, Anthropic)
│   └── tracer.py               # Observability span manager & trace logger
├── scraper/                    # Sourcing adapters
│   ├── remotive_scraper.py     # Zero-key remote job feed (Remotive)
│   ├── linkedin_guest_scraper.py # Zero-key LinkedIn guest scraper
│   ├── ats_scraper.py          # Direct Greenhouse, Lever, Ashby, Workable feeds
│   └── job_scraper.py          # Multi-board orchestrator & location/role tagger
├── scorer/                     # Fit evaluation & quality gates
│   ├── match_scorer.py         # 100-point merit rubric scoring & reviewer pass
│   ├── fabrication_validator.py # Grounding & anti-hallucination validation
│   └── query_reformulator.py   # Dynamic search query expansion loop
├── optimizer/                  # Tailoring & document generation
│   └── resume_optimizer.py     # DOCX paragraph patching & LibreOffice PDF render
├── webapp/                     # Modern FastAPI web dashboard & instant match portal
│   ├── app.py                  # REST API & SSE live streaming
│   ├── run_manager.py          # Async session runner & queue manager
│   ├── templates/              # Jinja2 responsive templates (home, instant_results, kanban)
│   └── static/                 # Styles, charts, and SSE client scripts
├── tests/                      # Automated offline pytest suite
│   ├── conftest.py             # Shared fixtures & mock data
│   ├── test_loader.py          # Profile loader tests
│   ├── test_llm.py             # LLM client & routing tests
│   ├── test_scrapers.py        # Scraper parsing tests
│   ├── test_scorer.py          # Fit scoring & rubric tests
│   ├── test_fabrication_validator.py # Grounding validation tests
│   ├── test_optimizer.py       # DOCX XML patching tests
│   ├── test_tracer.py          # Observability trace tests
│   └── test_webapp.py          # Web API & endpoint tests
├── Makefile                    # Developer shortcuts (test, app, run, dry-run)
└── pyproject.toml              # Standard Python project definition
```

---

## 🔒 Privacy & Grounding Guarantees

* **No Automated Submissions**: The agent will never apply on your behalf or risk your job-board accounts. Fast-Apply packs are structured copy-paste materials.
* **No Fabricated Facts**: Strict preservation of verified quantifiable metrics (percentages, dollar amounts, multipliers).
* **Data Ownership**: No candidate data is retained on external servers; local traces are stored directly in `data/traces/`.

---

