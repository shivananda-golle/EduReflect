"""
Single entry point for all LLM calls.

Uses an OpenAI-compatible chat completions API (Groq free tier by default), enforces the
global daily call budget, and falls back to the next configured model when one is rate-limited.
"""
import logging
import time
from typing import Dict, List, Optional

import requests

from app.services.usage_limits import LimitExceeded, consume
from app.utils.config import (
    DAILY_LLM_CALL_LIMIT,
    LLM_API_KEY,
    LLM_API_URL,
    LLM_MAX_RETRY_WAIT,
    LLM_MODELS,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


def _model_options(model: str) -> dict:
    """Keep reasoning models from spending the token budget on hidden thinking."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low", "include_reasoning": False}
    if model.startswith("qwen/qwen3"):
        return {"reasoning_effort": "none"}
    return {}


def chat(
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    response_format: Optional[dict] = None,
) -> str:
    """
    Return the assistant message content. Raises LimitExceeded when the demo budget or provider quota is exhausted.
    Pass response_format={"type": "json_object"} to require valid JSON output.
    """
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY (or GROQ_API_KEY) is not set")

    consume(
        "llm:global",
        DAILY_LLM_CALL_LIMIT,
        "The demo has reached its free daily AI limit. Please try again tomorrow.",
    )

    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    for attempt in range(2):
        shortest_wait = None
        for model in LLM_MODELS:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                **_model_options(model),
            }
            if response_format:
                payload["response_format"] = response_format
            response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429:
                wait = _retry_after_seconds(response)
                shortest_wait = wait if shortest_wait is None else min(shortest_wait, wait)
                logger.warning("LLM model %s is rate-limited (retry after %.1fs); trying the next model", model, wait)
                continue
            response.raise_for_status()
            return (response.json()["choices"][0]["message"].get("content") or "").strip()

        # Every model is rate-limited. Per-minute token limits reset within seconds, so wait once;
        # longer waits (e.g. an exhausted daily quota) fail fast with a friendly message.
        if attempt == 0 and shortest_wait is not None and shortest_wait <= LLM_MAX_RETRY_WAIT:
            time.sleep(shortest_wait)
            continue
        break

    raise LimitExceeded("The AI service is busy right now. Please try again in a minute.")


def _retry_after_seconds(response: requests.Response) -> float:
    """Seconds until the provider accepts requests again, from Retry-After (default: too long to wait)."""
    try:
        return max(0.0, float(response.headers.get("retry-after", "")))
    except ValueError:
        return float("inf")
