"""
tests/test_tracer.py — Unit tests for the Observability Tracer.
"""

import pytest
from pathlib import Path
from core.tracer import Tracer, Span, list_local_traces


def test_span_lifecycle():
    span = Span(name="scrape_step", inputs={"provider": "remotive"})
    assert span.status == "running"
    assert span.name == "scrape_step"
    assert span.inputs.get("provider") == "remotive"

    span.complete(outputs={"count": 15}, metrics={"duration": 1.2})
    assert span.status == "completed"
    assert span.outputs.get("count") == 15
    assert span.duration_seconds >= 0.0


def test_tracer_context_and_save():
    tracer = Tracer(session_name="test_session")
    with tracer.span("test_span_1", inputs={"key": "val"}) as s:
        s.complete(outputs={"result": "ok"})

    assert len(tracer.spans) == 1
    assert tracer.spans[0].name == "test_span_1"

    saved_path = tracer.save()
    assert Path(saved_path).exists()
    assert str(tracer.trace_id) in str(saved_path)

    # Clean up test trace
    Path(saved_path).unlink(missing_ok=True)
