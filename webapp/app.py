"""
webapp/app.py — FastAPI dashboard for the job-search pipeline.

Local-only (binds to 127.0.0.1), single-user, no auth layer. Server-rendered
Jinja2 pages are primary; the small set of /api/* JSON endpoints exist only
for things that need polling/async JS (live run progress, Chart.js data).
"""

import io
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests

from digest.presentation import (
    score_color, score_bg, seniority_badge_colors, industry_badge_colors,
    industry_label,
)
from storage import run_store, tracker_store
from webapp.run_manager import run_manager

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


def _default_resume() -> str:
    """Best-effort default for the trigger form's resume-path field. Falls
    back to a placeholder if no profile exists yet — the form field is still
    editable, and main.run() derives the real default from the profile
    regardless of what's shown here."""
    try:
        from candidate_profile.loader import load_profile
        return load_profile().resume_path
    except Exception:
        return "candidate_profile/resume.docx"


DEFAULT_RESUME = _default_resume()

app = FastAPI(title="Job Search Dashboard")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["score_color"] = score_color
templates.env.globals["score_bg"] = score_bg
templates.env.globals["seniority_badge_colors"] = seniority_badge_colors
templates.env.globals["industry_badge_colors"] = industry_badge_colors
templates.env.globals["industry_label"] = industry_label


def _safe_url(url) -> str:
    """Only http(s):// links are rendered as hrefs — blocks javascript:/data:/etc."""
    if not url or not isinstance(url, str):
        return "#"
    if url.startswith(("http://", "https://")):
        return url
    return "#"


templates.env.filters["safe_url"] = _safe_url


class TriggerRequest(BaseModel):
    dry_run: bool = True
    resume_path: str = DEFAULT_RESUME
    resume_secondary_path: Optional[str] = None
    no_dedup: bool = False
    enable_crawl4ai: bool = False


class TrackerStatusRequest(BaseModel):
    run_id: str
    job_index: int
    status: str


class TrackerFieldsRequest(BaseModel):
    run_id: str
    job_index: int
    recruiter_name: str = ""
    notes: str = ""
    follow_up_date: str = ""


class TrackerStatusByKeyRequest(BaseModel):
    key: str
    status: str


# ---------------------------------------------------------------------------
# Server-rendered pages
# ---------------------------------------------------------------------------

@app.get("/")
def home(request: Request, session_id: Optional[str] = None):
    stats = run_store.compute_stats()
    active_session_id = session_id or request.cookies.get("job_scout_session_id")
    session_data = run_manager.get_session(active_session_id) if active_session_id else None

    # Only surface personalized matches if the active candidate has a completed match session
    session_jobs = []
    if session_data and session_data.get("status") == "completed":
        session_jobs = session_data.get("results", {}).get("matches", [])

    # User-centric application pipeline metrics from CRM Kanban store
    board = tracker_store.kanban_board()
    columns = board.get("columns", [])
    col_counts = {col["status"]: len(col.get("entries", [])) for col in columns}

    tracker_kpis = {
        "qualifying": col_counts.get("qualifying", 0) or len(session_jobs) or stats.get("total_jobs_qualifying", 0),
        "optimized": col_counts.get("optimized", 0),
        "applied": col_counts.get("applied", 0),
        "interviewing": col_counts.get("interview_scheduled", 0) + col_counts.get("interview_complete", 0),
        "offers": col_counts.get("offer", 0),
    }

    return templates.TemplateResponse(request, "home.html", {
        "stats": stats,
        "tracker_kpis": tracker_kpis,
        "active_session": session_data,
        "active_session_id": active_session_id,
        "recent_jobs": session_jobs,
    })


def get_available_candidate_profiles(current_profile_name: str = "") -> list[dict]:
    """Scan candidate_profile/profiles/*.yaml and return candidate list with active status."""
    import yaml
    from pathlib import Path

    profiles_dir = Path("candidate_profile/profiles")
    profiles_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for p in sorted(profiles_dir.glob("*.yaml")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            c_name = data.get("name", p.stem.replace("_", " ").title())
            results.append({
                "id": p.stem,
                "name": c_name,
                "title": data.get("title", "Specialist"),
                "location": data.get("location", "Remote"),
                "years_experience": data.get("years_experience", 5),
                "is_active": (c_name.strip().lower() == current_profile_name.strip().lower()),
                "search_terms": data.get("search_terms", [])[:3],
            })
        except Exception:
            continue
    return results


def get_candidate_matched_jobs(profile) -> list[dict]:
    """Retrieve or score matching jobs for a candidate from seed catalog / historical runs."""
    from storage.seed_catalog import SEED_JOBS

    if not profile:
        return []

    search_terms_lower = [t.lower() for t in (profile.search_terms or [])]
    target_title_lower = (profile.title or "").lower()
    adj_industries_lower = [i.lower() for i in (profile.adjacent_industries or [])]

    matched_jobs = []
    for idx, raw_job in enumerate(SEED_JOBS):
        job_title = raw_job.get("title", "")
        job_title_lower = job_title.lower()
        job_text = (raw_job.get("jd_text", "") + " " + job_title).lower()
        company = raw_job.get("company", "")

        score = 0
        matched_skills = []
        has_relevance = False

        # Exact / Strong Title match
        for term in search_terms_lower:
            if term in job_title_lower:
                score += 40
                matched_skills.append(term.title())
                has_relevance = True
                break
            else:
                words = [w for w in term.split() if len(w) > 3]
                matched_words = [w for w in words if w in job_title_lower]
                if len(matched_words) >= 2 or (len(words) == 1 and len(matched_words) == 1):
                    score += 30
                    matched_skills.append(term.title())
                    has_relevance = True
                    break

        if not has_relevance:
            target_words = [w for w in target_title_lower.split() if len(w) > 3]
            matched_target = [w for w in target_words if w in job_title_lower]
            if len(matched_target) >= 2 or (len(target_words) == 1 and len(matched_target) == 1):
                score += 30
                has_relevance = True

        # Check industry overlap
        for ind in adj_industries_lower:
            if ind in job_title_lower:
                score += 25
                matched_skills.append(ind.title())
                has_relevance = True
                break
            elif ind in job_text:
                score += 15
                matched_skills.append(ind.title())
                break

        if not has_relevance:
            continue

        # Target company match bonus
        for co in (profile.target_companies or []):
            if co.lower() in company.lower():
                score += 15
                break

        score += 20
        score = min(98, max(50, score))

        if score >= 60:
            matched_jobs.append({
                "job_index": idx,
                "title": job_title,
                "company": company,
                "location": raw_job.get("location", "Remote"),
                "apply_url": raw_job.get("apply_url", "#"),
                "source": raw_job.get("source", "Direct ATS"),
                "score": score,
                "decision": "QUALIFYING",
                "matched_skills": list(dict.fromkeys(matched_skills))[:3],
                "fit_reason": f"Matches candidate background in {profile.title} ({', '.join(profile.search_terms[:2])})."
            })

    matched_jobs.sort(key=lambda j: j["score"], reverse=True)
    return matched_jobs


@app.get("/candidate")
@app.get("/profile")
def candidate_profile_page(request: Request):
    from candidate_profile.loader import load_profile
    try:
        profile = load_profile()
        profile_dict = {
            "name": profile.name,
            "title": profile.title,
            "years_experience": profile.years_experience,
            "location": profile.location,
            "target_location_country": profile.target_location_country,
            "search_terms": profile.search_terms,
            "target_companies": profile.target_companies,
            "search_locations": profile.search_locations,
            "blocked_locations": profile.blocked_locations,
            "adjacent_industries": profile.adjacent_industries,
            "roles": list(profile.roles.keys()),
            "resume_path": profile.resume_path,
        }
    except Exception:
        profile_dict = None
        profile = None

    # Available candidates for 1-click switching
    current_name = profile_dict.get("name", "") if profile_dict else ""
    available_candidates = get_available_candidate_profiles(current_name)

    # Candidate scored jobs table
    candidate_jobs = get_candidate_matched_jobs(profile)

    # Retrieve candidate match session history
    session_history = []
    for sid, sess in list(run_manager._sessions.items())[::-1]:
        if sess.get("status") == "completed":
            results = sess.get("results", {})
            session_history.append({
                "session_id": sid,
                "created_at": sess.get("started_at", ""),
                "target_title": sess.get("title") or (sess.get("profile") or {}).get("title", "Multi-Track"),
                "total_scraped": results.get("total_scraped", 0),
                "total_matches": results.get("total_matches", 0),
                "pathways_count": len(results.get("pathways", [])),
            })

    return templates.TemplateResponse(request, "candidate_profile.html", {
        "profile": profile_dict,
        "available_candidates": available_candidates,
        "candidate_jobs": candidate_jobs,
        "session_history": session_history,
    })


class CandidateSwitchRequest(BaseModel):
    candidate_id: str


@app.post("/api/candidate/switch")
def api_candidate_switch(payload: CandidateSwitchRequest):
    """Switch the active candidate profile to another preset or uploaded candidate."""
    import shutil
    from pathlib import Path

    profiles_dir = Path("candidate_profile/profiles")
    target = profiles_dir / f"{payload.candidate_id}.yaml"
    if not target.exists():
        return JSONResponse(status_code=404, content={"ok": False, "error": f"Profile '{payload.candidate_id}' not found."})

    try:
        shutil.copyfile(target, "candidate_profile/config.yaml")
        run_manager._sessions.clear()
        return {"ok": True, "message": f"Successfully activated profile for {payload.candidate_id}."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class CandidateDeleteRequest(BaseModel):
    candidate_id: str


@app.post("/api/candidate/delete")
def api_delete_candidate(payload: CandidateDeleteRequest):
    """Admin endpoint to remove a candidate profile and switch to default if active."""
    import shutil
    from pathlib import Path

    profiles_dir = Path("candidate_profile/profiles")
    target = profiles_dir / f"{payload.candidate_id}.yaml"
    if not target.exists():
        return JSONResponse(status_code=404, content={"ok": False, "error": f"Profile '{payload.candidate_id}' not found."})

    try:
        target.unlink(missing_ok=True)
        # If deleted candidate was active, fall back to malini_mukherjee if available
        fallback = profiles_dir / "malini_mukherjee.yaml"
        if fallback.exists():
            shutil.copyfile(fallback, "candidate_profile/config.yaml")
        run_manager._sessions.clear()
        return {"ok": True, "message": f"Candidate profile '{payload.candidate_id}' deleted successfully."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class AdminDataPurgeRequest(BaseModel):
    target: str = "runs"  # "runs", "sessions", or "all"


@app.post("/api/admin/purge-data")
def api_admin_purge_data(payload: AdminDataPurgeRequest):
    """Admin endpoint to purge historical runs, telemetry traces, or active sessions."""
    try:
        deleted_items = 0
        if payload.target in ["sessions", "all"]:
            deleted_items += len(run_manager._sessions)
            run_manager._sessions.clear()

        if payload.target in ["runs", "all"]:
            from storage.run_store import RunStore
            store = RunStore()
            # Clear runs in store if method exists
            if hasattr(store, "clear_all"):
                store.clear_all()

        if payload.target in ["traces", "all"]:
            from core.tracer import TRACES_DIR
            if TRACES_DIR.exists():
                for trace_file in TRACES_DIR.glob("*.json"):
                    trace_file.unlink(missing_ok=True)
                    deleted_items += 1

        if payload.target in ["outputs", "all"]:
            outputs_dir = Path(__file__).parent.parent / "outputs"
            if outputs_dir.exists():
                for out_file in outputs_dir.iterdir():
                    if out_file.is_file() and out_file.name != ".gitkeep":
                        out_file.unlink(missing_ok=True)
                        deleted_items += 1

        return {"ok": True, "message": f"Purged {payload.target} data successfully."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.get("/api/candidate/profile")
def api_candidate_profile():
    from candidate_profile.loader import load_profile
    try:
        profile = load_profile()
        return {
            "ok": True,
            "name": profile.name,
            "title": profile.title,
            "years_experience": profile.years_experience,
            "location": profile.location,
            "target_location_country": profile.target_location_country,
            "search_terms": profile.search_terms,
            "target_companies": profile.target_companies,
            "search_locations": profile.search_locations,
            "blocked_locations": profile.blocked_locations,
            "adjacent_industries": profile.adjacent_industries,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class CandidateBaseLocationRequest(BaseModel):
    location: str
    target_location_country: Optional[str] = None


@app.post("/api/candidate/base-location")
def api_update_candidate_base_location(payload: CandidateBaseLocationRequest):
    """Update candidate primary base location and country in 1 click."""
    from candidate_profile.loader import DEFAULT_PROFILE_PATH
    import yaml

    try:
        profile_path = DEFAULT_PROFILE_PATH
        config_data = {}
        if profile_path.exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        config_data["location"] = payload.location.strip()
        if payload.target_location_country:
            config_data["target_location_country"] = payload.target_location_country.strip().lower()
        elif "india" in payload.location.lower():
            config_data["target_location_country"] = "india"
        elif "remote" in payload.location.lower() or "worldwide" in payload.location.lower():
            config_data["target_location_country"] = "worldwide"
        elif any(us_loc in payload.location.lower() for us_loc in ["san francisco", "new york", "ca", "ny", "usa", "united states"]):
            config_data["target_location_country"] = "united states"
        elif "london" in payload.location.lower() or "uk" in payload.location.lower():
            config_data["target_location_country"] = "united kingdom"

        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False)

        return {
            "ok": True,
            "location": config_data.get("location"),
            "target_location_country": config_data.get("target_location_country"),
            "message": f"Primary location updated to {config_data.get('location')}."
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.post("/api/candidate/upload-resume")
def api_upload_candidate_resume(file: UploadFile = File(...)):
    """Upload a candidate resume from the Candidate Hub, extract profile, and activate."""
    import re
    import shutil
    import yaml
    from candidate_profile.loader import create_profile_from_text

    if not file or not file.filename:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No file uploaded."})

    try:
        file_bytes = file.file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Uploaded file is empty."})

        resume_text = extract_text_from_file_bytes(file.filename, file_bytes)
        if not resume_text or len(resume_text.strip()) < 30:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Could not extract readable text from file."})

        # Save uploaded resume file to data/uploads
        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
        saved_file_path = upload_dir / safe_filename
        with open(saved_file_path, "wb") as f:
            f.write(file_bytes)

        # Create Profile
        profile = create_profile_from_text(resume_text=resume_text, filename=file.filename)
        cand_name = profile.name or "Uploaded Candidate"
        cand_slug = re.sub(r'[^a-z0-9_]', '_', cand_name.lower()).strip('_') or "uploaded_candidate"

        # Build clean profile dict
        profile_data = {
            "name": cand_name,
            "title": profile.title or "Professional",
            "years_experience": profile.years_experience or 5,
            "context": f"{cand_name} is a {profile.title} with {profile.years_experience} years experience.",
            "location": profile.location or "Remote",
            "target_location_country": profile.target_location_country or "india",
            "target_location_aliases": ["remote", "worldwide", (profile.location or "remote").lower()],
            "search_locations": profile.search_locations or ["Remote", profile.location or "India"],
            "blocked_locations": profile.blocked_locations or [],
            "search_terms": profile.search_terms or [profile.title or "Specialist"],
            "target_companies": profile.target_companies or [],
            "adjacent_industries": profile.adjacent_industries or [],
            "resume_path": str(saved_file_path),
        }

        # Save to candidate_profile/profiles/<slug>.yaml
        profiles_dir = Path("candidate_profile/profiles")
        profiles_dir.mkdir(parents=True, exist_ok=True)
        with open(profiles_dir / f"{cand_slug}.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(profile_data, f, sort_keys=False)

        # Copy to config.yaml to activate
        shutil.copyfile(profiles_dir / f"{cand_slug}.yaml", "candidate_profile/config.yaml")
        run_manager._sessions.clear()

        return {
            "ok": True,
            "candidate_id": cand_slug,
            "name": cand_name,
            "title": profile.title,
            "location": profile.location,
            "message": f"Successfully created and activated profile for {cand_name}."
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class CandidateLocationUpdateRequest(BaseModel):
    location: Optional[str] = None
    target_location_country: Optional[str] = None
    search_locations: Optional[List[str]] = None
    blocked_locations: Optional[List[str]] = None


@app.post("/api/candidate/locations")
def api_update_candidate_locations(payload: CandidateLocationUpdateRequest):
    """Update candidate target locations, target country, and search cities."""
    from candidate_profile.loader import DEFAULT_PROFILE_PATH
    import yaml

    try:
        profile_path = DEFAULT_PROFILE_PATH
        config_data = {}
        if profile_path.exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        if payload.location is not None:
            config_data["location"] = payload.location.strip()
        if payload.target_location_country is not None:
            config_data["target_location_country"] = payload.target_location_country.strip().lower()
        if payload.search_locations is not None:
            config_data["search_locations"] = [loc.strip() for loc in payload.search_locations if loc.strip()]
        if payload.blocked_locations is not None:
            config_data["blocked_locations"] = [loc.strip() for loc in payload.blocked_locations if loc.strip()]

        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False)

        return {
            "ok": True,
            "location": config_data.get("location"),
            "target_location_country": config_data.get("target_location_country"),
            "search_locations": config_data.get("search_locations", []),
            "blocked_locations": config_data.get("blocked_locations", []),
            "message": "Candidate location preferences successfully updated and saved."
        }
    except Exception as exc:
        logger.warning("Failed to update candidate location preferences: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Failed to save location preferences: {exc}"})


@app.get("/runs")
def runs_page(request: Request, page: int = 1, page_size: int = 25):
    all_runs = run_store.list_runs()
    page = max(page, 1)
    page_size = max(page_size, 1)
    start = (page - 1) * page_size
    page_runs = all_runs[start:start + page_size]
    total_pages = max(1, (len(all_runs) + page_size - 1) // page_size)
    # Surface the currently-running webapp-triggered run (if any) so /runs shows
    # live state, not just completed snapshots. Only shown on the first page,
    # where a freshly-completed run's snapshot would also land.
    status = run_manager.get_status()
    active_run = status if status.get("active") and page == 1 else None
    return templates.TemplateResponse(request, "runs.html", {
        "runs": page_runs, "page": page, "active_run": active_run,
        "page_size": page_size, "total": len(all_runs), "total_pages": total_pages,
    })


@app.get("/runs/{run_id}")
def run_detail(request: Request, run_id: str):
    run = run_store.load_run(run_id)
    if run is None:
        return templates.TemplateResponse(
            request, "run_detail.html", {"run": None, "run_id": run_id},
            status_code=404,
        )
    return templates.TemplateResponse(request, "run_detail.html", {"run": run, "run_id": run_id})


@app.get("/runs/{run_id}/jobs/{job_index}")
def job_detail(request: Request, run_id: str, job_index: int):
    run = run_store.load_run(run_id)
    if run is None or job_index < 0 or job_index >= len(run.get("jobs", [])):
        return templates.TemplateResponse(
            request, "job_detail.html", {"run": None, "job": None,
                                          "run_id": run_id, "job_index": job_index},
            status_code=404,
        )

    job = run["jobs"][job_index]
    ats_path = job.get("ats_output")
    review_path = job.get("review_output")
    tracker_entry = tracker_store.load_tracker().get(tracker_store.entry_key(job), {})

    return templates.TemplateResponse(request, "job_detail.html", {
        "run": run, "run_id": run_id, "job": job, "job_index": job_index,
        "tracker_recruiter_name": tracker_entry.get("recruiter_name", ""),
        "tracker_notes": tracker_entry.get("notes", ""),
        "tracker_follow_up_date": tracker_entry.get("follow_up_date", ""),
        "ats_available": bool(ats_path) and Path(ats_path).exists(),
        "review_available": bool(review_path) and Path(review_path).exists(),
        "ats_generated": bool(ats_path),
        "review_generated": bool(review_path),
        "tracker_status": tracker_store.get_status(job),
        "tracker_statuses": sorted(tracker_store.VALID_STATUSES),
    })


@app.get("/trigger")
def trigger_page(request: Request):
    return templates.TemplateResponse(request, "trigger.html", {
        "default_resume": DEFAULT_RESUME,
    })


@app.get("/kanban")
def kanban_page(request: Request):
    board = tracker_store.kanban_board()
    return templates.TemplateResponse(request, "kanban.html", {"board": board})


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.post("/api/runs/trigger")
def api_trigger_run(payload: TriggerRequest):
    started = run_manager.start_run(
        dry_run=payload.dry_run,
        resume_path=payload.resume_path,
        resume_secondary_path=payload.resume_secondary_path,
        no_dedup=payload.no_dedup,
        enable_crawl4ai=payload.enable_crawl4ai,
    )
    if not started:
        return JSONResponse(status_code=409, content={
            "status": "error", "message": "A run is already in progress",
        })
    return JSONResponse(status_code=202, content={"status": "started"})


@app.post("/api/tracker/status")
def api_set_tracker_status(payload: TrackerStatusRequest):
    """Set a posting's application status (new/applied/rejected/…) from the
    job-detail page. Writes data/tracker.json, which commits/pushes like the
    run snapshots do."""
    run = run_store.load_run(payload.run_id)
    if run is None or payload.job_index < 0 or payload.job_index >= len(run.get("jobs", [])):
        return JSONResponse(status_code=404, content={"ok": False, "reason": "Run or job not found"})

    job = run["jobs"][payload.job_index]
    key = tracker_store.entry_key(job)
    if not key:
        return JSONResponse(status_code=400, content={"ok": False, "reason": "Job has no stable key"})

    # The job may not be in the tracker yet (e.g. viewing a CI snapshot locally
    # before any local run touched the tracker) — seed it, then set the status.
    tracker = tracker_store.load_tracker()
    if key not in tracker:
        tracker_store.mark_seen([{**job, "qualifying": job.get("qualifying", False)}], tracker)

    if not tracker_store.set_status(key, payload.status):
        return JSONResponse(status_code=400, content={
            "ok": False, "reason": f"Unknown status '{payload.status}'",
        })
    return JSONResponse(status_code=200, content={"ok": True, "status": payload.status.lower()})


@app.post("/api/tracker/fields")
def api_set_tracker_fields(payload: TrackerFieldsRequest):
    """Set manual bookkeeping fields (recruiter name/notes/follow-up date) on
    a posting from the job-detail page. Same seed-if-missing pattern as
    /api/tracker/status."""
    run = run_store.load_run(payload.run_id)
    if run is None or payload.job_index < 0 or payload.job_index >= len(run.get("jobs", [])):
        return JSONResponse(status_code=404, content={"ok": False, "reason": "Run or job not found"})

    job = run["jobs"][payload.job_index]
    key = tracker_store.entry_key(job)
    if not key:
        return JSONResponse(status_code=400, content={"ok": False, "reason": "Job has no stable key"})

    tracker = tracker_store.load_tracker()
    if key not in tracker:
        tracker_store.mark_seen([{**job, "qualifying": job.get("qualifying", False)}], tracker)

    tracker_store.set_fields(
        key,
        recruiter_name=payload.recruiter_name,
        notes=payload.notes,
        follow_up_date=payload.follow_up_date,
    )
    return JSONResponse(status_code=200, content={"ok": True})


@app.post("/api/tracker/status_by_key")
def api_set_tracker_status_by_key(payload: TrackerStatusByKeyRequest):
    """Set a posting's application status from the Kanban board, which already
    has the tracker key on the dragged card — no run_id/job_index lookup
    needed, unlike /api/tracker/status."""
    if not tracker_store.set_status(payload.key, payload.status):
        return JSONResponse(status_code=400, content={
            "ok": False, "reason": "Unknown status, missing key, or invalid backward move",
        })
    return JSONResponse(status_code=200, content={"ok": True, "status": payload.status.lower()})


@app.get("/api/runs/status")
def api_run_status():
    return run_manager.get_status()


@app.get("/api/stats")
def api_stats():
    return run_store.compute_stats()


@app.get("/api/runs")
def api_runs(page: int = 1, page_size: int = 25):
    all_runs = run_store.list_runs()
    page = max(page, 1)
    page_size = max(page_size, 1)
    start = (page - 1) * page_size
    return {
        "runs": all_runs[start:start + page_size],
        "page": page, "page_size": page_size, "total": len(all_runs),
    }


@app.get("/downloads/{run_id}/{job_index}/{kind}")
def download_resume(run_id: str, job_index: int, kind: str):
    if kind not in ("ats", "review"):
        return JSONResponse(status_code=404, content={"available": False, "reason": "Unknown file kind"})

    run = run_store.load_run(run_id)
    if run is None or job_index < 0 or job_index >= len(run.get("jobs", [])):
        return JSONResponse(status_code=404, content={"available": False, "reason": "Run or job not found"})

    job = run["jobs"][job_index]
    field = "ats_output" if kind == "ats" else "review_output"
    path_str = job.get(field)

    if not path_str:
        return JSONResponse(status_code=404, content={
            "available": False,
            "reason": "Not generated for this job (dry run or optimize cap reached)",
        })

    path = Path(path_str)
    if not path.exists():
        return JSONResponse(status_code=404, content={
            "available": False,
            "reason": "File not generated on this machine (likely a CI-run snapshot) — "
                      "check the GitHub Actions run artifact if within its 7-day retention.",
        })

    return FileResponse(path, filename=path.name)


# ---------------------------------------------------------------------------
# Resume File & Cloud Import Endpoints (.pdf, .docx, .txt, Google Drive, Dropbox)
# ---------------------------------------------------------------------------

def extract_text_from_file_bytes(filename: str, data: bytes) -> str:
    """Extract clean raw text from PDF, DOCX, TXT, or MD file bytes."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text.strip()
    elif lower.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text.strip()
    else:
        return data.decode("utf-8", errors="ignore").strip()


def normalize_cloud_url(url: str) -> str:
    """Convert Google Drive / Dropbox share links to direct download URLs."""
    url = url.strip()
    gd_m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=)([a-zA-Z0-9_-]+)", url)
    if gd_m:
        file_id = gd_m.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    if "dropbox.com" in url:
        return re.sub(r"[?&]dl=0", "", url) + ("&dl=1" if "?" in url else "?dl=1")
    return url


class CloudResumeRequest(BaseModel):
    url: str


@app.post("/api/resume/upload")
async def api_upload_resume(file: UploadFile = File(...)):
    """Upload and extract text from a local device .pdf, .docx, or .txt file."""
    try:
        content = await file.read()
        if not content:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Uploaded file is empty."})

        extracted_text = extract_text_from_file_bytes(file.filename or "resume.txt", content)
        if not extracted_text or len(extracted_text.strip()) < 40:
            return JSONResponse(status_code=422, content={
                "ok": False,
                "error": "Could not extract readable text. If this is a scanned PDF image, please use a searchable text PDF or .docx.",
            })

        return {
            "ok": True,
            "filename": file.filename,
            "char_count": len(extracted_text),
            "text": extracted_text,
        }
    except Exception as exc:
        logger.warning("Resume file parsing error: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Failed to parse resume: {exc}"})


@app.post("/api/resume/upload-batch-file")
async def api_upload_batch_file(file: UploadFile = File(...)):
    """Upload and save a local device .docx, .pdf, or .txt file for batch pipeline scouting."""
    try:
        content = await file.read()
        if not content:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Uploaded file is empty."})

        extracted_text = extract_text_from_file_bytes(file.filename or "resume.txt", content)
        if not extracted_text or len(extracted_text.strip()) < 30:
            return JSONResponse(status_code=422, content={
                "ok": False,
                "error": "Could not extract readable text. Please use a valid .docx, .pdf, or .txt file.",
            })

        uploads_dir = Path("data/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename or "uploaded_resume.docx")
        dest_path = uploads_dir / clean_name
        with open(dest_path, "wb") as f:
            f.write(content)

        return {
            "ok": True,
            "filename": file.filename,
            "saved_path": str(dest_path),
            "size_bytes": len(content),
            "char_count": len(extracted_text),
        }
    except Exception as exc:
        logger.warning("Batch resume upload error: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Failed to upload resume: {exc}"})



@app.post("/api/resume/fetch-url")
def api_fetch_cloud_resume(payload: CloudResumeRequest):
    """Import and extract text from a public Google Drive, Dropbox, or web URL."""
    url = payload.url.strip()
    if not url or not url.startswith(("http://", "https://")):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Please provide a valid HTTP/HTTPS cloud link."})

    direct_url = normalize_cloud_url(url)
    try:
        resp = requests.get(
            direct_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=15,
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=400, content={
                "ok": False,
                "error": f"Could not download file (HTTP {resp.status_code}). Ensure public link sharing is enabled.",
            })

        content = resp.content
        filename = "cloud_resume.txt"
        if "application/pdf" in resp.headers.get("Content-Type", "") or ".pdf" in url.lower():
            filename = "cloud_resume.pdf"
        elif "wordprocessingml" in resp.headers.get("Content-Type", "") or ".docx" in url.lower():
            filename = "cloud_resume.docx"

        extracted_text = extract_text_from_file_bytes(filename, content)
        if not extracted_text or len(extracted_text.strip()) < 40:
            return JSONResponse(status_code=422, content={
                "ok": False,
                "error": "Could not extract text from cloud file. Please ensure the file contains searchable text or download and paste directly.",
            })

        return {
            "ok": True,
            "filename": filename,
            "char_count": len(extracted_text),
            "text": extracted_text,
        }
    except Exception as exc:
        logger.warning("Cloud resume fetch error: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Failed to import from cloud: {exc}"})


# ---------------------------------------------------------------------------
# Instant Match & Career Divergence Endpoints (Paste Resume -> Pathways -> Matches)
# ---------------------------------------------------------------------------

class CareerPathwaysRequest(BaseModel):
    resume_text: str
    title: str = ""


@app.post("/api/career/pathways")
def api_get_career_pathways(payload: CareerPathwaysRequest):
    """Analyze a resume and return 2-3 discovered career divergence pathways."""
    if not payload.resume_text or len(payload.resume_text.strip()) < 30:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Resume text too short for career analysis."})

    from candidate_profile.career_pathways import decompose_career_pathways
    try:
        data = decompose_career_pathways(payload.resume_text, detected_title=payload.title)
        return {"ok": True, **data}
    except Exception as exc:
        logger.warning("Career pathway decomposition failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class InstantMatchRequest(BaseModel):
    resume_text: str
    resume_secondary_text: Optional[str] = None
    name: str = ""
    title: str = ""
    location: str = ""
    country: str = ""
    remote_only: bool = False
    selected_tracks: Optional[List[str]] = None
    pathways: Optional[List[Dict[str, Any]]] = None


class ShareDigestRequest(BaseModel):
    session_id: str
    recipient_email: str


@app.post("/api/match/instant")
def api_start_instant_match(payload: InstantMatchRequest):
    """Start an on-the-fly match session from pasted resume text across chosen career tracks."""
    if not payload.resume_text or len(payload.resume_text.strip()) < 50:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Resume text must be at least 50 characters long."},
        )

    session_id = run_manager.start_instant_session(
        resume_text=payload.resume_text,
        resume_secondary_text=payload.resume_secondary_text,
        name_override=payload.name,
        title_override=payload.title,
        location_override=payload.location,
        country_override=payload.country,
        remote_only=payload.remote_only,
        selected_tracks=payload.selected_tracks,
        pathways=payload.pathways,
    )
    return JSONResponse(status_code=202, content={"ok": True, "session_id": session_id})


@app.get("/api/match/stream/{session_id}")
async def api_stream_instant_match(session_id: str):
    """Server-Sent Events (SSE) stream for live match session progress."""
    from fastapi.responses import StreamingResponse
    import json
    import asyncio

    q = run_manager.get_session_queue(session_id)
    if not q:
        return JSONResponse(status_code=404, content={"error": "Session not found"})

    async def event_generator():
        while True:
            try:
                # Check for new event in queue (non-blocking)
                if not q.empty():
                    event = q.get_nowait()
                    data_str = json.dumps(event, default=str)
                    yield f"data: {data_str}\n\n"
                    if event.get("stage") in ("done", "error"):
                        break
                else:
                    session = run_manager.get_session(session_id)
                    if session and session.get("status") in ("completed", "failed"):
                        yield f"data: {json.dumps({'stage': 'done', 'percent': 100})}\n\n"
                        break
                    await asyncio.sleep(0.5)
            except Exception as exc:
                logger.error("SSE stream error for %s: %s", session_id, exc)
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/match/results/{session_id}")
def api_get_instant_results(session_id: str):
    session = run_manager.get_session(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return session


@app.get("/match/{session_id}")
def instant_results_page(request: Request, session_id: str):
    session = run_manager.get_session(session_id)
    if not session:
        return templates.TemplateResponse(request, "instant_results.html", {
            "session_id": session_id,
            "session": {"status": "not_found"},
            "results": None,
        })
    return templates.TemplateResponse(request, "instant_results.html", {
        "session_id": session_id,
        "session": session,
        "results": session.get("results"),
    })


@app.get("/resume/preview/{session_id}/{job_idx}")
def preview_tailored_resume(request: Request, session_id: str, job_idx: int):
    """Render a clean, ATS-compliant, printable HTML/PDF view of the tailored resume."""
    session = run_manager.get_session(session_id)
    if not session or not session.get("results"):
        return JSONResponse(status_code=404, content={"error": "Session or results not found"})

    results = session["results"]
    matches = results.get("matches", [])
    if job_idx < 1 or job_idx > len(matches):
        return JSONResponse(status_code=404, content={"error": "Job match index out of range"})

    job = matches[job_idx - 1]
    from optimizer.resume_generator import assemble_tailored_resume_data

    resume_text = session.get("resume_text", "")
    profile_dict = results.get("profile", {})
    tailored_pack = job.get("tailored_pack")

    resume_data = assemble_tailored_resume_data(
        resume_text=resume_text,
        profile_dict=profile_dict,
        tailored_pack=tailored_pack,
        job=job,
    )

    return templates.TemplateResponse(request, "resume_preview.html", {
        "session_id": session_id,
        "job_idx": job_idx,
        "resume": resume_data,
        "job": job,
    })


@app.get("/api/resume/download/{session_id}/{job_idx}")
def download_tailored_docx_file(session_id: str, job_idx: int):
    """Generate and return an ATS-compliant tailored DOCX file for the matched role."""
    session = run_manager.get_session(session_id)
    if not session or not session.get("results"):
        return JSONResponse(status_code=404, content={"error": "Session or results not found"})

    results = session["results"]
    matches = results.get("matches", [])
    if job_idx < 1 or job_idx > len(matches):
        return JSONResponse(status_code=404, content={"error": "Job match index out of range"})

    job = matches[job_idx - 1]
    from optimizer.resume_generator import assemble_tailored_resume_data, generate_tailored_docx

    resume_text = session.get("resume_text", "")
    profile_dict = results.get("profile", {})
    tailored_pack = job.get("tailored_pack")

    resume_data = assemble_tailored_resume_data(
        resume_text=resume_text,
        profile_dict=profile_dict,
        tailored_pack=tailored_pack,
        job=job,
    )

    docx_stream = generate_tailored_docx(resume_data)
    safe_company = "".join(c for c in job.get("company", "Company") if c.isalnum() or c in " _-").strip()
    safe_name = "".join(c for c in profile_dict.get("name", "Resume") if c.isalnum() or c in " _-").strip()
    filename = f"{safe_name}_Tailored_{safe_company}.docx"

    from fastapi.responses import Response
    return Response(
        content=docx_stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/resume/download-pdf/{session_id}/{job_idx}")
def download_tailored_pdf_file(session_id: str, job_idx: int):
    """Generate and return an ATS-compliant tailored PDF file for the matched role."""
    session = run_manager.get_session(session_id)
    if not session or not session.get("results"):
        return JSONResponse(status_code=404, content={"error": "Session or results not found"})

    results = session["results"]
    matches = results.get("matches", [])
    if job_idx < 1 or job_idx > len(matches):
        return JSONResponse(status_code=404, content={"error": "Job match index out of range"})

    job = matches[job_idx - 1]
    from optimizer.resume_generator import assemble_tailored_resume_data, generate_tailored_pdf

    resume_text = session.get("resume_text", "")
    profile_dict = results.get("profile", {})
    tailored_pack = job.get("tailored_pack")

    resume_data = assemble_tailored_resume_data(
        resume_text=resume_text,
        profile_dict=profile_dict,
        tailored_pack=tailored_pack,
        job=job,
    )

    pdf_stream = generate_tailored_pdf(resume_data)
    safe_company = "".join(c for c in job.get("company", "Company") if c.isalnum() or c in " _-").strip()
    safe_name = "".join(c for c in profile_dict.get("name", "Resume") if c.isalnum() or c in " _-").strip()
    filename = f"{safe_name}_Tailored_{safe_company}.pdf"

    from fastapi.responses import Response
    return Response(
        content=pdf_stream.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/candidate/download-tailored-pdf/{job_index}")
def download_candidate_tailored_pdf(job_index: int):
    """Generate tailored PDF résumé directly from Candidate Hub for any matched job."""
    from pathlib import Path
    from candidate_profile.loader import load_profile
    from storage.seed_catalog import SEED_JOBS
    from optimizer.resume_generator import assemble_tailored_resume_data, generate_tailored_pdf

    try:
        profile = load_profile()
    except Exception as exc:
        return JSONResponse(status_code=404, content={"error": f"Profile load error: {exc}"})

    if job_index < 0 or job_index >= len(SEED_JOBS):
        return JSONResponse(status_code=404, content={"error": "Job index out of range"})

    job = SEED_JOBS[job_index]
    profile_dict = {
        "name": profile.name,
        "title": profile.title,
        "location": profile.location,
        "years_experience": profile.years_experience,
        "search_terms": profile.search_terms,
        "target_companies": profile.target_companies,
    }

    # Extract full resume text from profile's base resume file if available
    full_resume_text = ""
    if profile.resume_path and Path(profile.resume_path).exists():
        try:
            p_path = Path(profile.resume_path)
            if p_path.suffix.lower() == ".docx":
                from docx import Document
                doc = Document(str(p_path))
                full_resume_text = "\n".join(p.text for p in doc.paragraphs if p.text)
            elif p_path.suffix.lower() == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(p_path))
                full_resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                full_resume_text = p_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            full_resume_text = ""

    if not full_resume_text or len(full_resume_text.strip()) < 50:
        full_resume_text = profile.context or f"{profile.name} - {profile.title} with {profile.years_experience} years experience in {profile.location}."

    resume_data = assemble_tailored_resume_data(
        resume_text=full_resume_text,
        profile_dict=profile_dict,
        tailored_pack=None,
        job=job,
    )

    pdf_stream = generate_tailored_pdf(resume_data)
    safe_company = "".join(c for c in job.get("company", "Company") if c.isalnum() or c in " _-").strip()
    safe_name = "".join(c for c in profile.name if c.isalnum() or c in " _-").strip()
    filename = f"{safe_name}_Tailored_{safe_company}.pdf"

    from fastapi.responses import Response
    return Response(
        content=pdf_stream.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@app.post("/api/match/share")
def api_share_matches(payload: ShareDigestRequest):
    """Email the tailored HTML digest with match cards and apply links."""
    session = run_manager.get_session(payload.session_id)
    if not session or not session.get("results"):
        return JSONResponse(status_code=404, content={"ok": False, "error": "Results not found for session"})

    recipient = payload.recipient_email.strip()
    if not recipient or "@" not in recipient:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid email address"})

    try:
        from digest.email_digest import _build_html, send_digest
        from candidate_profile.loader import create_profile_from_dict
        from datetime import datetime, timezone

        results = session["results"]
        profile = create_profile_from_dict(results.get("profile", {}))
        matches = results.get("matches", [])
        date_str = datetime.now(timezone.utc).strftime("%d %b %Y")

        html_content = _build_html(
            primary=matches,
            outside_target_location=[],
            qa_roles=[],
            date_str=date_str,
            profile=profile,
            skill_gaps=results.get("skill_gaps", []),
            training_recs=[],
        )

        import os, smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        user = os.getenv("GMAIL_USER")
        pw = os.getenv("GMAIL_APP_PASSWORD")
        if not user or not pw:
            return JSONResponse(status_code=500, content={"ok": False, "error": "Server SMTP credentials not configured."})

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your Job Scout Matches & Fast-Apply Pack ({date_str})"
        msg["From"] = user
        msg["To"] = recipient
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, pw)
            smtp.sendmail(user, recipient, msg.as_bytes())

        return JSONResponse(status_code=200, content={"ok": True, "message": f"Digest sent to {recipient}"})

    except Exception as exc:
        logger.exception("Failed to share matches: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.get("/api/traces")
def api_traces():
    from core.tracer import list_local_traces
    return {"traces": list_local_traces()}

