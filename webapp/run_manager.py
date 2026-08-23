"""
webapp/run_manager.py — background execution of pipeline and instant match sessions.

Supports:
1. Standard batch pipeline runs (for CLI / GitHub Actions / local dashboard).
2. Instant On-The-Fly Match Sessions for the open-for-all web portal (paste resume, get matches).
3. SSE (Server-Sent Events) live progress streaming for interactive web clients.
"""

import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from storage.run_store import run_id_for

logger = logging.getLogger(__name__)


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
        self._thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = _idle_state()

        # Instant Match Session storage
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_queues: Dict[str, queue.Queue] = {}

    # -----------------------------------------------------------------------
    # Standard Pipeline Run (for dashboard)
    # -----------------------------------------------------------------------

    def start_run(
        self,
        dry_run: bool,
        resume_path: str,
        resume_secondary_path: Optional[str] = None,
        no_dedup: bool = False,
        enable_crawl4ai: bool = False,
    ) -> bool:
        with self._lock:
            if self._state.get("active"):
                return False
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
                args=(dry_run, resume_path, resume_secondary_path, no_dedup, enable_crawl4ai),
                daemon=True,
            )
            self._thread.start()
            return True

    def _progress_callback(self, update: dict):
        with self._lock:
            self._state.update(update)

    def _run_worker(
        self,
        dry_run: bool,
        resume_path: str,
        resume_secondary_path: Optional[str] = None,
        no_dedup: bool = False,
        enable_crawl4ai: bool = False,
    ):
        try:
            os.environ["ENABLE_CRAWL4AI"] = "true" if enable_crawl4ai else "false"
            from main import run as pipeline_run

            summary = pipeline_run(
                resume_path=resume_path,
                resume_secondary_path=resume_secondary_path,
                dry_run=dry_run,
                source="webapp",
                progress_callback=self._progress_callback,
                no_dedup=no_dedup,
            )
            result_run_id = run_id_for(summary.started_at)
            with self._lock:
                self._state.update({
                    "active": False,
                    "finished": True,
                    "stage": "done",
                    "result_run_id": result_run_id,
                })
        except Exception as exc:
            with self._lock:
                self._state.update({"active": False, "finished": True, "error": str(exc)})

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._state)

    # -----------------------------------------------------------------------
    # Instant On-The-Fly Matching (Paste CV & Match)
    # -----------------------------------------------------------------------

    def start_instant_session(
        self,
        resume_text: str,
        resume_secondary_text: Optional[str] = None,
        name_override: Optional[str] = None,
        title_override: Optional[str] = None,
        location_override: Optional[str] = None,
        country_override: Optional[str] = None,
        remote_only: bool = False,
        selected_tracks: Optional[List[str]] = None,
        pathways: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        event_q: queue.Queue = queue.Queue()
        with self._lock:
            self._session_queues[session_id] = event_q
            self._sessions[session_id] = {
                "session_id": session_id,
                "resume_text": resume_text,
                "resume_secondary_text": resume_secondary_text,
                "status": "starting",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "profile": None,
                "results": None,
                "error": None,
            }

        worker = threading.Thread(
            target=self._instant_match_worker,
            args=(session_id, resume_text, resume_secondary_text, name_override, title_override, location_override, country_override, remote_only, selected_tracks, pathways, event_q),
            daemon=True,
        )
        worker.start()
        return session_id

    def _instant_match_worker(
        self,
        session_id: str,
        resume_text: str,
        resume_secondary_text: Optional[str],
        name_override: Optional[str],
        title_override: Optional[str],
        location_override: Optional[str],
        country_override: Optional[str],
        remote_only: bool,
        selected_tracks: Optional[List[str]],
        pathways: Optional[List[Dict[str, Any]]],
        event_q: queue.Queue,
    ):
        from candidate_profile.career_pathways import decompose_career_pathways
        from candidate_profile.loader import create_profile_from_text
        from core.tracer import Tracer
        from optimizer.resume_optimizer import call_llm
        from scorer.fabrication_validator import validate_tailored_package
        from scorer.match_scorer import is_ghost_job, prefilter_jobs, score_job
        from scraper.job_scraper import check_job_live, scrape_all_jobs

        tracer = Tracer(trace_id=session_id, session_name="instant-match-session")

        def emit(stage: str, message: str, percent: int, extra: Optional[Dict] = None):
            payload = {
                "session_id": session_id,
                "stage": stage,
                "message": message,
                "percent": percent,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if extra:
                payload.update(extra)
            event_q.put(payload)

        try:
            # 1. Career Divergence Analysis & Profile Extraction
            emit("extracting", "Analyzing career divergence pathways and grounding factual background...", 10)
            if not pathways:
                pw_data = decompose_career_pathways(resume_text, detected_title=title_override or "")
                pathways = pw_data.get("pathways", [])

            active_pathways = [p for p in pathways if p.get("id") in selected_tracks] if selected_tracks else pathways
            if not active_pathways:
                active_pathways = pathways

            with tracer.span("profile_extraction"):
                profile = create_profile_from_text(
                    resume_text=resume_text,
                    name_override=name_override,
                    title_override=title_override,
                    location_override=location_override,
                    country_override=country_override,
                )
                if remote_only:
                    profile.target_location_aliases.append("remote")

                # Merge search queries and target companies from all active career tracks
                for p in active_pathways:
                    for q in p.get("search_queries", []):
                        if q not in profile.search_terms:
                            profile.search_terms.append(q)
                    for co in p.get("target_companies", []):
                        if co not in profile.target_companies:
                            profile.target_companies.append(co)

                profile_sec = None
                if resume_secondary_text and len(resume_secondary_text.strip()) >= 50:
                    try:
                        profile_sec = create_profile_from_text(
                            resume_text=resume_secondary_text,
                            location_override=location_override,
                            country_override=country_override,
                        )
                        if remote_only:
                            profile_sec.target_location_aliases.append("remote")
                        for t in profile_sec.search_terms:
                            if t not in profile.search_terms:
                                profile.search_terms.append(t)
                    except Exception as exc:
                        logger.warning("Could not parse secondary resume: %s", exc)

            track_names = ", ".join([p.get("title", "") for p in active_pathways[:3]])
            emit("scouting", f"Searching job boards across {len(active_pathways)} career pathways ({track_names}) in {profile.location}...", 25)

            # 2. Multi-Source Scraping
            with tracer.span("scraping"):
                jobs = scrape_all_jobs(profile)

            # Resilient fallback: if network is restricted / 403 blocked, load cached snapshot jobs
            if not jobs:
                logger.info("Scraper returned 0 jobs (likely network restriction). Loading recent cached jobs...")
                from storage.run_store import list_runs, load_run
                for r in list_runs():
                    full_r = load_run(r["run_id"])
                    if full_r and full_r.get("jobs"):
                        jobs.extend(full_r["jobs"])
                        if len(jobs) >= 40:
                            break

            # 3. Keyword Prefilter across all candidate jobs
            pool = jobs
            with tracer.span("prefilter"):
                candidates = prefilter_jobs(pool, resume_text, profile, top_n=35)
                if profile_sec:
                    sec_candidates = prefilter_jobs(pool, resume_secondary_text, profile_sec, top_n=20)
                    for sj in sec_candidates:
                        if sj not in candidates:
                            candidates.append(sj)

            all_scored: List[Dict[str, Any]] = []
            total_cand = len(candidates)

            # 4. Scoring
            for idx, job in enumerate(candidates, start=1):
                pct = 45 + int((idx / max(total_cand, 1)) * 35)
                emit("scoring", f"Evaluating fit {idx}/{total_cand}: {job.get('title')} @ {job.get('company')}", pct)

                ghost_flagged, _ = is_ghost_job(job, {})
                if ghost_flagged:
                    continue

                with tracer.span("score_job", inputs={"title": job.get("title"), "company": job.get("company")}):
                    scored_primary = score_job(job, resume_text, profile)
                    scored_primary["resume_track"] = "primary"

                    if profile_sec and resume_secondary_text:
                        scored_sec = score_job(job, resume_secondary_text, profile_sec)
                        scored_sec["resume_track"] = "secondary"
                        # Select best-fitting track
                        if (scored_sec.get("match_score", 0) > scored_primary.get("match_score", 0)):
                            scored = scored_sec
                        else:
                            scored = scored_primary
                    else:
                        scored = scored_primary
                # Tag job with matching career pathway
                best_track = active_pathways[0] if active_pathways else None
                best_track_score = 0
                title_l = (job.get("title") or "").lower()
                jd_l = (job.get("jd_text") or "").lower()
                comp_l = (job.get("company") or "").lower()

                for p in active_pathways:
                    p_score = 0
                    for q in p.get("search_queries", []):
                        if q.lower() in title_l:
                            p_score += 15
                        elif q.lower() in jd_l:
                            p_score += 5
                    for ind in p.get("target_industries", []):
                        if ind.lower() in jd_l or ind.lower() in title_l:
                            p_score += 8
                    for co in p.get("target_companies", []):
                        if co.lower() in comp_l:
                            p_score += 20
                    if p_score > best_track_score:
                        best_track_score = p_score
                        best_track = p

                if best_track:
                    scored["track_id"] = best_track.get("id", "track_a")
                    scored["track_title"] = best_track.get("title", "")
                    scored["track_label"] = best_track.get("track_label", "Track A")
                    scored["track_role_type"] = best_track.get("role_type", "core")

                all_scored.append(scored)

            try:
                if all_scored:
                    from storage.tracker_store import mark_seen
                    mark_seen(all_scored, resume_text=resume_text)
            except Exception as exc:
                logger.warning("Failed to record tracker seen jobs: %s", exc)

            # Filter qualifying matches (>= 50%)
            all_scored.sort(key=lambda j: j.get("match_score", 0), reverse=True)
            scored_matches = [j for j in all_scored if j.get("match_score", 0) >= 50]

            # 5. Tailor Fast-Apply Packs for top matches
            emit("tailoring", "Generating tailored Fast-Apply packs and validating grounding...", 85)
            for job in scored_matches[:10]:
                use_resume = resume_secondary_text if (job.get("resume_track") == "secondary" and resume_secondary_text) else resume_text
                use_profile = profile_sec if (job.get("resume_track") == "secondary" and profile_sec) else profile

                try:
                    tailor_pack = call_llm(
                        resume_text=use_resume,
                        jd=job.get("jd_text", ""),
                        profile=use_profile,
                        company=job.get("company", ""),
                        title=job.get("title", ""),
                    )
                    val = validate_tailored_package(
                        source_resume_text=use_resume,
                        tailored_summary=tailor_pack.get("optimized_summary", ""),
                        tailored_competencies=tailor_pack.get("optimized_competencies", []),
                        tailored_bullets=tailor_pack.get("optimized_bullets", {}),
                        profile=use_profile,
                    )
                    job["tailored_pack"] = tailor_pack
                    job["grounding_score"] = val.get("grounding_score", 1.0)
                    job["validation_warnings"] = val.get("warnings", [])
                except Exception as exc:
                    logger.warning("Tailoring failed for %s: %s", job.get("title"), exc)

                try:
                    job["is_live"] = check_job_live(job)
                except Exception:
                    job["is_live"] = True

            # Compute skill gaps
            from digest.presentation import compute_skill_gaps
            skill_gaps = compute_skill_gaps(scored_matches)

            results_payload = {
                "profile": {
                    "name": profile.name,
                    "title": profile.title,
                    "location": profile.location,
                    "years_experience": profile.years_experience,
                    "search_terms": profile.search_terms,
                    "target_companies": profile.target_companies,
                },
                "secondary_profile": {
                    "name": profile_sec.name,
                    "title": profile_sec.title,
                } if profile_sec else None,
                "pathways": pathways,
                "active_pathways": active_pathways,
                "total_scraped": len(jobs),
                "total_matches": len(scored_matches),
                "matches": scored_matches,
                "skill_gaps": skill_gaps,
            }

            tracer_path = tracer.save()

            with self._lock:
                self._sessions[session_id].update({
                    "status": "completed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "resume_text": resume_text,
                    "resume_secondary_text": resume_secondary_text,
                    "profile": results_payload["profile"],
                    "results": results_payload,
                    "trace_file": str(tracer_path),
                })

            emit("done", f"Found {len(scored_matches)} top recommendations ready to apply!", 100, {"results": results_payload})

        except Exception as exc:
            logger.exception("Instant match session '%s' failed: %s", session_id, exc)
            with self._lock:
                self._sessions[session_id].update({
                    "status": "failed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                })
            emit("error", f"Error during matching: {exc}", 100, {"error": str(exc)})

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._sessions.get(session_id)

    def get_session_queue(self, session_id: str) -> Optional[queue.Queue]:
        with self._lock:
            return self._session_queues.get(session_id)


run_manager = RunManager()
