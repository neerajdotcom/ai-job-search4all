"""
core/tracer.py — Observability, trace logging, and LLMOps integration.

Supports:
- Comet Opik tracing (when OPIK_API_KEY is configured)
- Local zero-key JSON trace recording (data/traces/<trace_id>.json)

Allows users and developers to see inside the agent's reasoning:
- Step-by-step span tree (Extraction -> Scrape -> Prefilter -> Score -> Tailor -> Validate)
- Latency per node
- Token counts & estimated cost
- Inputs, prompts, outputs, and validation receipts
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TRACES_DIR = Path(__file__).parent.parent / "data" / "traces"


class Span:
    """Represents a single execution step in the pipeline trace tree."""

    def __init__(self, name: str, parent_id: Optional[str] = None, inputs: Optional[Dict[str, Any]] = None):
        self.span_id = f"span_{int(time.time() * 1000)}_{os.urandom(3).hex()}"
        self.name = name
        self.parent_id = parent_id
        self.inputs = inputs or {}
        self.outputs: Dict[str, Any] = {}
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None
        self.duration_seconds: float = 0.0
        self.status = "running"
        self.error: Optional[str] = None
        self.metrics: Dict[str, Any] = {}

    def complete(self, outputs: Optional[Dict[str, Any]] = None, metrics: Optional[Dict[str, Any]] = None):
        self.finished_at = datetime.now(timezone.utc).isoformat()
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at)
        self.duration_seconds = round((end - start).total_seconds(), 3)
        self.status = "completed"
        if outputs:
            self.outputs = outputs
        if metrics:
            self.metrics.update(metrics)

    def fail(self, error: Exception):
        self.finished_at = datetime.now(timezone.utc).isoformat()
        self.status = "failed"
        self.error = str(error)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metrics": self.metrics,
            "error": self.error,
        }


class Tracer:
    """Agent Observability Tracer supporting Opik and local structured logging."""

    def __init__(self, trace_id: Optional[str] = None, session_name: str = "job-search-pipeline"):
        self.trace_id = trace_id or f"trace_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{os.urandom(3).hex()}"
        self.session_name = session_name
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.spans: List[Span] = []
        self._current_span: Optional[Span] = None
        self._opik_client = None
        self._init_opik()

    def _init_opik(self):
        opik_key = os.getenv("OPIK_API_KEY", "").strip()
        if opik_key:
            try:
                import opik
                self._opik_client = opik.Opik(project_name=os.getenv("OPIK_PROJECT_NAME", "job-scout"))
                logger.info("Opik tracing initialized for project: %s", os.getenv("OPIK_PROJECT_NAME", "job-scout"))
            except Exception as exc:
                logger.warning("Failed to initialize Opik tracing: %s (falling back to local traces)", exc)
                self._opik_client = None

    @contextmanager
    def span(self, name: str, inputs: Optional[Dict[str, Any]] = None):
        """Context manager for tracing an execution span."""
        parent_id = self._current_span.span_id if self._current_span else None
        span = Span(name=name, parent_id=parent_id, inputs=inputs)
        self.spans.append(span)
        previous_span = self._current_span
        self._current_span = span

        t0 = time.time()
        try:
            yield span
            if span.status == "running":
                span.complete()
        except Exception as exc:
            span.fail(exc)
            raise
        finally:
            self._current_span = previous_span
            logger.debug("Span '%s' completed in %.2fs (status=%s)", name, time.time() - t0, span.status)

    def log_event(self, name: str, data: Dict[str, Any]):
        """Record an instantaneous event or metric."""
        with self.span(name, inputs=data) as s:
            s.complete(outputs=data)

    def save(self) -> Path:
        """Persist trace tree to local JSON database with automatic retention pruning."""
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        path = TRACES_DIR / f"{self.trace_id}.json"
        trace_data = {
            "trace_id": self.trace_id,
            "session_name": self.session_name,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_spans": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)

        # Auto-retention: prune oldest traces if count exceeds 10
        try:
            all_traces = sorted(TRACES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if len(all_traces) > 10:
                for old_trace in all_traces[10:]:
                    old_trace.unlink(missing_ok=True)
        except Exception:
            pass

        return path


def trace_function(name: Optional[str] = None):
    """Decorator to automatically trace a function execution."""
    def decorator(fn: Callable):
        span_name = name or fn.__name__
        def wrapper(*args, **kwargs):
            tracer = getattr(args[0], "tracer", None) if args else None
            if tracer and isinstance(tracer, Tracer):
                with tracer.span(span_name, inputs={"args": str(args)[:200], "kwargs": str(kwargs)[:200]}):
                    return fn(*args, **kwargs)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def list_local_traces() -> List[Dict[str, Any]]:
    """List all saved local traces."""
    if not TRACES_DIR.exists():
        return []
    traces = []
    for f in sorted(TRACES_DIR.glob("*.json"), reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                traces.append({
                    "trace_id": data.get("trace_id"),
                    "session_name": data.get("session_name"),
                    "started_at": data.get("started_at"),
                    "total_spans": data.get("total_spans", 0),
                    "file_path": str(f),
                })
        except Exception:
            continue
    return traces
