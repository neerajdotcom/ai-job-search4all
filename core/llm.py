"""
core/llm.py — Universal multi-provider LLM client.

Supports:
- Groq (default for fast, high-volume scoring)
- Google Gemini (default for resume tailoring & extraction)
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude 3.5 Sonnet, Claude 3.7 Sonnet)
- Ollama (local offline models, e.g. llama3.2, mistral)
- OpenRouter (OpenAI-compatible multi-model routing)

Features:
- Single unified interface: LLMClient.generate()
- Robust JSON extraction with automatic fence stripping
- Per-provider throttle and exponential backoff
- Daily quota circuit breaker (fails open or switches fallback)
- Observability trace hook integration
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Union

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Default model assignments
DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-20241022",
    "ollama": "llama3.2",
    "openrouter": "meta-llama/llama-3.3-70b-instruct",
}

# Per-provider rate-limit throttle (seconds between calls)
PROVIDER_MIN_INTERVAL = {
    "groq": 0.5,
    "gemini": 2.0,
    "openai": 0.2,
    "anthropic": 0.5,
    "ollama": 0.0,
    "openrouter": 0.5,
}


def clean_json_response(raw_text: str) -> str:
    """Strip markdown code fences and extraneous text surrounding a JSON payload."""
    if not raw_text:
        return "{}"
    text = raw_text.strip()
    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # If there's still text before the first '{' or after the last '}', trim it
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        text = text[start : end + 1]
    return text


class LLMClient:
    """Unified client for executing structured prompts across multiple LLM providers."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODELS.get(self.provider, "llama-3.3-70b-versatile"))
        self._last_call_time: Dict[str, float] = {}
        self.quota_exhausted: Dict[str, bool] = {
            "groq": False,
            "gemini": False,
            "openai": False,
            "anthropic": False,
            "ollama": False,
            "openrouter": False,
        }

    def _throttle(self, provider: str):
        interval = PROVIDER_MIN_INTERVAL.get(provider, 0.5)
        last = self._last_call_time.get(provider, 0.0)
        elapsed = time.time() - last
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_call_time[provider] = time.time()

    def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        json_mode: bool = True,
    ) -> Optional[str]:
        """Generate text/JSON with automatic retries and exponential backoff."""
        active_provider = (provider or self.provider).lower()
        active_model = model or self.model or DEFAULT_MODELS.get(active_provider)

        if self.quota_exhausted.get(active_provider, False):
            logger.warning("Quota previously exhausted for provider '%s' — skipping call", active_provider)
            return None

        delay = 1.0
        last_exc = None

        for attempt in range(max_retries + 1):
            self._throttle(active_provider)
            try:
                if active_provider == "groq":
                    return self._call_groq(prompt, active_model, system_prompt, temperature)
                elif active_provider == "gemini":
                    return self._call_gemini(prompt, active_model, system_prompt, temperature)
                elif active_provider == "openai":
                    return self._call_openai(prompt, active_model, system_prompt, temperature)
                elif active_provider == "anthropic":
                    return self._call_anthropic(prompt, active_model, system_prompt, temperature)
                elif active_provider == "ollama":
                    return self._call_ollama(prompt, active_model, system_prompt, temperature)
                elif active_provider == "openrouter":
                    return self._call_openrouter(prompt, active_model, system_prompt, temperature)
                else:
                    raise ValueError(f"Unsupported LLM provider: {active_provider}")
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()

                # Check for missing keys or quota exhaustion vs transient rate-limits
                if "not set" in err_str or "api_key" in err_str or "unauthorized" in err_str or "invalid_api_key" in err_str:
                    logger.warning("%s API key not configured or invalid — skipping remote call", active_provider)
                    self.quota_exhausted[active_provider] = True
                    return None

                if "daily" in err_str or "quota exceeded" in err_str or "insufficient_quota" in err_str:
                    logger.error("Daily quota exhausted for %s: %s", active_provider, exc)
                    self.quota_exhausted[active_provider] = True
                    return None

                if attempt == max_retries:
                    logger.error("%s API failed after %d retries: %s", active_provider, max_retries, exc)
                    return None

                logger.warning("%s call attempt %d failed (%s), retrying in %.1fs...", active_provider, attempt + 1, exc, delay)
                time.sleep(delay)
                delay = min(delay * 2, 10.0)

        return None

    def generate_json(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """Generate and parse structured JSON output."""
        raw = self.generate(
            prompt=prompt,
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            json_mode=True,
        )
        if not raw:
            return None
        cleaned = clean_json_response(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode JSON from %s response: %s (Raw: %r)", provider or self.provider, exc, raw[:200])
            return None

    # -----------------------------------------------------------------------
    # Provider Implementations
    # -----------------------------------------------------------------------

    def _call_groq(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        from groq import Groq
        client = Groq(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _call_gemini(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        from google import genai
        client = genai.Client(api_key=api_key)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
        )
        return response.text or ""

    def _call_openai(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    def _call_ollama(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        url = f"{host.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def _call_openrouter(self, prompt: str, model: str, system_prompt: Optional[str], temperature: float) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/neerajdotcom/ai-job-search4all",
            "X-Title": "AI Job Search Agent",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# Global default client instance
default_llm = LLMClient()
