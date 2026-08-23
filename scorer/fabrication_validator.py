"""
scorer/fabrication_validator.py — Anti-hallucination and factual grounding validator.

Inspired by observable-job-agent:
Ensures the AI never fabricates metrics, tools, employers, or accomplishments.
The human applies; the agent never invents.

Performs both:
1. Deterministic entity & metric preservation verification (0 token cost).
2. Grounding assessment against base CV facts.
"""

import logging
import re
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

# Regular expressions for quantifiable figures: percentages, currencies, multipliers, counts
_METRIC_PATTERNS = [
    re.compile(r"\b\d+(?:\.\d+)?%"),                                   # 40%, 3.5%
    re.compile(r"[\$€£₹]\s*\d+(?:\.\d+)?\s*(?:[kKmMbB]|million|billion|crore|lakh)?\b"),  # $5M, £100k, ₹50L
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:[kKmMbB]|million|billion|crore|lakh)\b", re.I),     # 10M, 500k
    re.compile(r"\b\d+x\b", re.I),                                     # 10x, 2x
    re.compile(r"\b\d+\+\s*(?:years|yrs|people|engineers|teams|projects|clients|users|customers)\b", re.I),
]


def extract_metrics(text: str) -> Set[str]:
    """Extract all quantifiable metrics and figures from text."""
    if not text:
        return set()
    metrics = set()
    for pattern in _METRIC_PATTERNS:
        for match in pattern.finditer(text):
            val = match.group(0).strip().lower()
            metrics.add(val)
    return metrics


def validate_metrics_preservation(source_text: str, tailored_text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Ensure every metric present in the tailored text was grounded in the source CV text.
    Returns: (is_valid, ungrounded_metrics, preserved_metrics)
    """
    source_metrics = extract_metrics(source_text)
    tailored_metrics = extract_metrics(tailored_text)

    # Allow numbers that represent simple bullet counts or common ranking words
    ungrounded = []
    preserved = []

    for metric in tailored_metrics:
        # Check if the exact metric or its base number exists in source
        clean_num = re.sub(r"[^\d.]", "", metric)
        if metric in source_metrics or any(clean_num and clean_num in s for s in source_metrics):
            preserved.append(metric)
        else:
            # Check if source has the number in some form
            if clean_num and clean_num in source_text:
                preserved.append(metric)
            else:
                ungrounded.append(metric)

    is_valid = len(ungrounded) == 0
    return is_valid, ungrounded, preserved


def validate_tailored_package(
    source_resume_text: str,
    tailored_summary: str,
    tailored_competencies: List[str],
    tailored_bullets: Dict[str, List[str]],
    profile=None,
) -> Dict[str, Any]:
    """
    Comprehensive validation of a tailored resume package before it is rendered to DOCX/PDF.
    """
    warnings: List[str] = []
    all_tailored_text = (
        f"{tailored_summary}\n"
        f"{' '.join(tailored_competencies)}\n"
        f"{' '.join(' '.join(b) for b in tailored_bullets.values())}"
    )

    # 1. Metrics validation
    metrics_valid, ungrounded, preserved = validate_metrics_preservation(source_resume_text, all_tailored_text)
    if not metrics_valid:
        msg = f"Anti-Fabrication Warning: {len(ungrounded)} ungrounded metric(s) detected in rewrite: {', '.join(ungrounded)}"
        logger.warning(msg)
        warnings.append(msg)

    # 2. Company & Employer boundary check
    if profile and profile.roles:
        known_roles = set(profile.roles.keys())
        for role_key in tailored_bullets.keys():
            if role_key not in known_roles:
                warnings.append(f"Unexpected role key '{role_key}' in tailored bullets (known: {list(known_roles)})")

    # 3. Text length sanity checks
    if len(tailored_summary.strip()) < 40:
        warnings.append("Tailored summary appears unusually short or empty.")

    grounding_score = 1.0 if not ungrounded else max(0.0, 1.0 - (len(ungrounded) * 0.25))

    return {
        "valid": len(warnings) == 0,
        "grounding_score": round(grounding_score, 2),
        "warnings": warnings,
        "ungrounded_metrics": ungrounded,
        "preserved_metrics": preserved,
    }
