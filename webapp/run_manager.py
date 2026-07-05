"""
webapp/run_manager.py — background execution of the pipeline for the dashboard.

The pipeline (scraper/scorer/optimizer) is synchronous blocking I/O with its
own time.sleep()-based throttles, so it's run in a single dedicated daemon
thread rather than on FastAPI's event loop. Only one run is ever allowed at a
time — the pipeline's shared rate-limit/quota flags and outputs/ directory
aren't safe for concurrent runs.
"""

import os
import threading
from datetime import datetime, timezone

from storage.run_store import run_id_for


def _idle_state() -> dict:
    return {
        "active": False,
        "stage": "idle",
        "current": 0,
        "total": 0,
        "title": None,
        "company": None,
        "dry_run": None,
        "started_at": None,
        "run_id": None,
        "finished": False,
        "error": None,
        "result_run_id": None,
    }


class RunManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict = _idle_state()

    def start_run(self, dry_run: bool, resume_path: str, no_dedup: bool = False,
                   enable_crawl4ai: bool = False) -> bool:
        """Start a pipeline run in a background thread. Returns False (and does
        not start anything) if a run is already active."""
        with self._lock:
            if self._state.get("active"):
                return False
            # Assign a run_id at start (not just at the end) so the in-progress
            # run is identifiable on the /runs page. The final snapshot is named
            # from RunSummary.started_at (created a moment later inside
            # main.run()), so this provisional id can differ from the eventual
            # result_run_id by ~1s — cosmetic only, since the in-progress row is
            # non-linking and is replaced the instant the run finishes.
            started_dt = datetime.now(timezone.utc)
            self._state = {
                **_idle_state(),
                "active": True,
                "stage": "starting",
                "dry_run": dry_run,
                "started_at": started_dt.isoformat(),
                "run_id": run_id_for(started_dt),
            }
            self._thread = threading.Thread(
                target=self._run_worker,
                args=(dry_run, resume_path, no_dedup, enable_crawl4ai),
                daemon=True,
            )
            self._thread.start()
            return True

    def _progress_callback(self, update: dict):
        with self._lock:
            self._state.update(update)

    def _run_worker(self, dry_run: bool, resume_path: str, no_dedup: bool = False,
                     enable_crawl4ai: bool = False):
        try:
            # Per-run, not sticky: explicitly set both branches so a previous
            # run's checkbox state never leaks into this one.
            os.environ["ENABLE_CRAWL4AI"] = "true" if enable_crawl4ai else "false"
            from main import run as pipeline_run
            summary = pipeline_run(
                resume_path=resume_path,
                dry_run=dry_run,
                source="webapp",
                progress_callback=self._progress_callback,
                no_dedup=no_dedup,
            )
            result_run_id = run_id_for(summary.started_at)
            with self._lock:
                self._state.update({
                    "active": False, "finished": True, "stage": "done",
                    "result_run_id": result_run_id,
                })
        except Exception as exc:
            with self._lock:
                self._state.update({"active": False, "finished": True, "error": str(exc)})

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._state)


run_manager = RunManager()
