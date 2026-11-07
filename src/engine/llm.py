"""Provider-agnostic LLM client — every option has a free tier or runs locally.

    gemini      Google AI Studio free tier (native JSON-schema output)
    groq        Groq free tier (OpenAI-compatible)
    openrouter  OpenRouter ":free" models (OpenAI-compatible)
    ollama      Local model, fully offline (OpenAI-compatible)

Plain httpx — no vendor SDKs — so swapping providers is one env var.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import httpx
from loguru import logger

from src.net import request

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "fit_score": {"type": "INTEGER"},
        "summary": {"type": "STRING"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "gaps": {"type": "ARRAY", "items": {"type": "STRING"}},
        "resume_bullets": {"type": "ARRAY", "items": {"type": "STRING"}},
        "years_required": {"type": "INTEGER", "nullable": True},
    },
    "required": ["fit_score", "summary", "strengths", "gaps", "resume_bullets"],
}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse_json(text: str) -> dict[str, Any]:
    text = _FENCE.sub("", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class RateLimiter:
    """Spaces calls to stay under a free tier's requests-per-minute limit."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / max(rpm, 1)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class LLMClient:
    name = "llm"

    def __init__(self, model: str, rpm: int = 8):
        self.model = model
        self.limiter = RateLimiter(rpm)

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"

    async def complete_json(self, system: str, prompt: str) -> dict[str, Any]:
        await self.limiter.wait()
        async with httpx.AsyncClient(timeout=90) as client:
            return await self._call(client, system, prompt)

    async def _call(self, client: httpx.AsyncClient, system: str, prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class GeminiClient(LLMClient):
    name = "gemini"

    def __init__(self, api_key: str, model: str, rpm: int = 8):
        super().__init__(model, rpm)
        self.api_key = api_key

    async def _call(self, client, system, prompt):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": VERDICT_SCHEMA,
            },
        }
        res = await request(client, "POST", url, json=body, headers={"x-goog-api-key": self.api_key}, attempts=4)
        parts = res.json()["candidates"][0]["content"]["parts"]
        return parse_json("".join(p.get("text", "") for p in parts))


class OpenAICompatClient(LLMClient):
    def __init__(self, name: str, base_url: str, api_key: str, model: str, rpm: int = 8, json_mode: bool = True):
        super().__init__(model, rpm)
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.json_mode = json_mode

    async def _call(self, client, system, prompt):
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        res = await request(client, "POST", f"{self.base_url}/chat/completions", json=body, headers=headers, attempts=4)
        return parse_json(res.json()["choices"][0]["message"]["content"])


def get_llm(provider: str = "auto", rpm: int = 8) -> LLMClient | None:
    """Build the configured client, or None to run heuristic-only."""
    env = os.getenv
    builders = {
        "gemini": lambda: (
            env("GEMINI_API_KEY")
            and GeminiClient(env("GEMINI_API_KEY"), env("GEMINI_MODEL") or "gemini-2.5-flash", rpm)
        ),
        "groq": lambda: (
            env("GROQ_API_KEY")
            and OpenAICompatClient(
                "groq",
                "https://api.groq.com/openai/v1",
                env("GROQ_API_KEY"),
                env("GROQ_MODEL") or "llama-3.3-70b-versatile",
                rpm,
            )
        ),
        "openrouter": lambda: (
            env("OPENROUTER_API_KEY")
            and OpenAICompatClient(
                "openrouter",
                "https://openrouter.ai/api/v1",
                env("OPENROUTER_API_KEY"),
                env("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free",
                rpm,
            )
        ),
        "ollama": lambda: OpenAICompatClient(
            "ollama",
            f"{(env('OLLAMA_BASE_URL') or 'http://localhost:11434').rstrip('/')}/v1",
            "ollama",
            env("OLLAMA_MODEL") or "llama3.1",
            rpm,
        ),
    }
    provider = (provider or "auto").lower()
    if provider == "none":
        return None
    if provider == "auto":
        for name in ("gemini", "groq", "openrouter"):
            client = builders[name]()
            if client:
                logger.info(f"LLM provider: {client.label}")
                return client
        logger.info("No LLM key configured - using the free heuristic scorer only")
        return None
    if provider not in builders:
        logger.warning(f"Unknown LLM_PROVIDER '{provider}' - heuristic only")
        return None
    client = builders[provider]()
    if not client:
        logger.warning(f"LLM_PROVIDER={provider} but its API key is missing - heuristic only")
        return None
    logger.info(f"LLM provider: {client.label}")
    return client
