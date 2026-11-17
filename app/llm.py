"""
Thin wrapper around the Groq API (OpenAI-compatible chat completions).

Kept separate from the agent nodes so that:
  1. Every node measures latency + tokens + cost the same way.
  2. Tests can monkeypatch/replace `LLMClient.complete` with a fake and
     never touch the network.

Groq is used instead of a paid API — free tier, OpenAI-compatible endpoint.
Default model is openai/gpt-oss-120b (Groq deprecated llama-3.3-70b-versatile
and llama-3.1-8b-instant in June 2026; gpt-oss-120b is their recommended
migration target — same free tier, faster inference, 131k context).
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

import httpx
from langsmith import traceable

from app.cache import Cache

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# LLM response cache TTL — identical (system, prompt) pairs within this
# window skip the network call entirely. Reduces cost and latency for
# repeated or near-identical triage/action calls within the same session.
LLM_CACHE_TTL_SECONDS = int(os.getenv("LLM_CACHE_TTL_SECONDS", "300"))  # 5 minutes

_llm_cache = Cache(namespace="agentops-llm")

# Groq's free tier has no per-token billing for most models, so cost
# tracking defaults to $0. If you're on a paid Groq plan or swap models,
# update these to reflect real pricing — it only affects dashboard numbers.
# PRICE_PER_1M_INPUT_USD = 0.0
# PRICE_PER_1M_OUTPUT_USD = 0.0
# Estimated standard API pricing for openai/gpt-oss-120b.
# These are estimates, not a representation of your actual Groq bill.
PRICE_PER_1M_INPUT_USD = 0.15
PRICE_PER_1M_OUTPUT_USD = 0.60

@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * PRICE_PER_1M_INPUT_USD
            + self.output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT_USD
        )


class LLMClient:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.api_key = os.getenv("GROQ_API_KEY")

    @traceable(name="groq_llm_call", run_type="llm")
    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
                "and add it to your .env file, or inject a fake LLMClient in tests."
            )

        # ── Cache lookup ───────────────────────────────────────────
        cache_key = hashlib.sha256(
            f"{self.model}:{system}:{prompt}:{max_tokens}:{temperature}".encode()
        ).hexdigest()[:32]
        cached = _llm_cache.get_json(cache_key)
        if cached:
            return LLMResult(**cached)

        start = time.perf_counter()
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        latency_ms = (time.perf_counter() - start) * 1000

        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        result = LLMResult(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
        )

        # ── Cache result ───────────────────────────────────────────
        _llm_cache.set_json(
            cache_key,
            {
                "text": result.text,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
            },
            ttl_seconds=LLM_CACHE_TTL_SECONDS,
        )

        return result
