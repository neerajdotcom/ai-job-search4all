"""
tests/test_llm.py — Unit tests for the Universal LLM provider client.
"""

import pytest
from core.llm import LLMClient, clean_json_response


def test_clean_json_response_with_fences():
    raw = "```json\n{\"match_score\": 85, \"recommendation\": \"Strong match\"}\n```"
    cleaned = clean_json_response(raw)
    assert cleaned == '{"match_score": 85, "recommendation": "Strong match"}'


def test_clean_json_response_with_preamble():
    raw = "Here is the resulting JSON:\n\n{\"status\": \"ok\", \"count\": 3}\n\nHope this helps!"
    cleaned = clean_json_response(raw)
    assert cleaned == '{"status": "ok", "count": 3}'


def test_clean_json_response_empty():
    assert clean_json_response("") == "{}"
    assert clean_json_response(None) == "{}"


def test_llm_client_routing_and_fallback(monkeypatch):
    """Test LLM client fallback and error handling without real API keys."""
    client = LLMClient(provider="groq")
    assert client.provider == "groq"
    assert "llama" in client.model

    # Mock _call_groq
    monkeypatch.setattr(client, "_call_groq", lambda p, m, s, t: '{"score": 90}')
    res = client.generate_json("test prompt")
    assert isinstance(res, dict)
    assert res.get("score") == 90


def test_llm_quota_circuit_breaker(monkeypatch):
    client = LLMClient(provider="groq")

    def raise_quota_error(p, m, s, t):
        raise RuntimeError("Daily request limit / tokens per day exceeded")

    monkeypatch.setattr(client, "_call_groq", raise_quota_error)
    res = client.generate("test prompt", max_retries=1)
    assert res is None
    assert client.quota_exhausted["groq"] is True
