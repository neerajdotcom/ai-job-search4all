"""
webapp/app.py — FastAPI dashboard for the job-search pipeline.

Local-only (binds to 127.0.0.1), single-user, no auth layer. Server-rendered
Jinja2 pages are primary; the small set of /api/* JSON endpoints exist only
for things that need polling/async JS (live run progress, Chart.js data).
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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
def home(request: Request):
    stats = run_store.compute_stats()
    return templates.TemplateResponse(request, "home.html", {"stats": stats})


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
        dry_run=payload.dry_run, resume_path=payload.resume_path,
        no_dedup=payload.no_dedup, enable_crawl4ai=payload.enable_crawl4ai,
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
