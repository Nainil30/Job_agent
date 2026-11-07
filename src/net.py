"""Shared async HTTP client with polite defaults and retry/backoff."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from loguru import logger

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
RETRY_STATUS = {429, 500, 502, 503, 504}


def make_client(**kwargs: Any) -> httpx.AsyncClient:
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/html;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }
    headers.update(kwargs.pop("headers", {}))
    return httpx.AsyncClient(headers=headers, timeout=kwargs.pop("timeout", 25.0), follow_redirects=True, **kwargs)


async def request(
    client: httpx.AsyncClient, method: str, url: str, *, attempts: int = 3, **kwargs: Any
) -> httpx.Response:
    """Send a request, retrying transient failures (429 / 5xx / network) with jittered backoff.

    Raises httpx.HTTPStatusError for non-retryable or exhausted error responses.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            res = await client.request(method, url, **kwargs)
            if res.status_code in RETRY_STATUS and attempt < attempts:
                try:
                    wait = float(res.headers.get("retry-after", 0) or 0)
                except ValueError:
                    wait = 0
                wait = wait or (2**attempt + random.random())
                logger.debug(f"{res.status_code} from {url} - retrying in {wait:.1f}s")
                await asyncio.sleep(min(wait, 30))
                continue
            res.raise_for_status()
            return res
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < attempts:
                await asyncio.sleep(2**attempt + random.random())
    raise last_exc or RuntimeError(f"request to {url} failed")
