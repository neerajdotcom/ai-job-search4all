"""
tests/test_fabrication_validator.py — Unit tests for anti-fabrication and factual grounding validation.
"""

import pytest
from scorer.fabrication_validator import (
    extract_metrics,
    validate_metrics_preservation,
    validate_tailored_package,
)


def test_extract_metrics():
    text = "Improved latency by 45%, managed $5M budget across 10M users with 3x throughput and 10+ engineers."
    metrics = extract_metrics(text)
    assert "45%" in metrics
    assert "$5m" in metrics
    assert "10m" in metrics
    assert "3x" in metrics
    assert "10+ engineers" in metrics


def test_validate_metrics_preservation_clean():
    source = "Reduced cost by 25% and delivered $2M revenue with 5x speedup."
    tailored = "Refactored payment systems, achieving 25% cost reduction and 5x performance boost."
    is_valid, ungrounded, preserved = validate_metrics_preservation(source, tailored)
    assert is_valid is True
    assert len(ungrounded) == 0
    assert "25%" in preserved
    assert "5x" in preserved


def test_validate_metrics_preservation_with_hallucination():
    source = "Reduced cost by 25%."
    tailored = "Achieved 99.9% uptime, reduced cost by 25%, and delivered $50M profit across 100M users."
    is_valid, ungrounded, preserved = validate_metrics_preservation(source, tailored)
    assert is_valid is False
    assert len(ungrounded) >= 2  # $50M and 100M and 99.9% are ungrounded


def test_validate_tailored_package(sample_profile, sample_resume_text):
    tailored_summary = "Senior Backend Engineer with 8+ years experience in distributed systems."
    tailored_comp = ["Python", "Go", "PostgreSQL", "Docker"]
    tailored_bullets = {
        "acme_corp": ["Architected microservices handling $5M in monthly transactions."],
        "beta_tech": ["Developed core pipelines handling 500k events/sec."],
    }

    res = validate_tailored_package(
        source_resume_text=sample_resume_text,
        tailored_summary=tailored_summary,
        tailored_competencies=tailored_comp,
        tailored_bullets=tailored_bullets,
        profile=sample_profile,
    )
    assert res["valid"] is True
    assert res["grounding_score"] == 1.0
    assert len(res["warnings"]) == 0
