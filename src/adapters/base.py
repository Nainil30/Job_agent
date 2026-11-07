"""Base class every job source implements."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx
from loguru import logger

from src.engine.models import RawJobPosting
from src.net import make_client
from src.utils import parse_posted


class BaseAdapter(ABC):
    """A job source. Subclasses implement `fetch_jobs` and optionally `enrich`.

    Ingestion is two-phase on purpose:
      1. `fetch_jobs` pulls the cheap listing (title / location / link) for every query.
      2. `enrich` fetches the full description, but only for jobs that survive the
         free title + location filter — usually <10% of listings.
    """

    source: ClassVar[str] = "base"
    ingestion_tier: ClassVar[str] = "api"  # api | browser | aggregator
    client_headers: ClassVar[dict[str, str]] = {}

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.company_name: str = config.get("name", "Unknown")
        self.tier: str = config.get("tier", "Secondary")
        self.url: str = (config.get("url") or "").rstrip("/")
        self.queries: list[str] = list(config.get("queries") or [])
        self.max_results: int = int(config.get("max_results_per_query", 60))
        self.errors: list[str] = []
        self.client: httpx.AsyncClient | None = None

    # -- identity -----------------------------------------------------------------
    @property
    def label(self) -> str:
        return f"{self.company_name} ({self.source})"

    def make_job(self, **kw: Any) -> RawJobPosting:
        kw.setdefault("company", self.company_name)
        kw.setdefault("company_tier", self.tier)
        kw.setdefault("source_ats", self.source)
        kw["job_id"] = str(kw.get("job_id") or kw.get("url"))
        if kw.get("posted_at") is None:
            kw["posted_at"] = parse_posted(kw.get("posted_date"))
        if kw.get("posted_date") is not None:
            kw["posted_date"] = str(kw["posted_date"])
        return RawJobPosting(**kw)

    def record_error(self, context: str, exc: Exception | str) -> None:
        msg = f"{context}: {exc}"
        self.errors.append(msg[:300])
        logger.warning(f"[{self.label}] {msg}")

    # -- lifecycle ----------------------------------------------------------------
    async def run(self) -> list[RawJobPosting]:
        """Fetch listings, de-duplicated by job_id. Raises if every query failed."""
        self.errors = []
        async with make_client(headers=self.client_headers) as client:
            self.client = client
            jobs = await self.fetch_jobs()
        unique: dict[str, RawJobPosting] = {}
        for j in jobs:
            unique.setdefault(j.job_id, j)
        if not unique and self.errors:
            raise RuntimeError("; ".join(self.errors[:3]))
        return list(unique.values())

    async def enrich_many(self, jobs: list[RawJobPosting], concurrency: int = 4) -> list[RawJobPosting]:
        """Fetch full descriptions for the given jobs; failures keep the listing version."""
        if not jobs:
            return jobs
        sem = asyncio.Semaphore(concurrency)

        async def one(job: RawJobPosting) -> RawJobPosting:
            async with sem:
                try:
                    return await self.enrich(job)
                except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
                    logger.debug(f"[{self.label}] enrich failed for {job.job_id}: {exc}")
                    return job

        async with make_client(headers=self.client_headers) as client:
            self.client = client
            return list(await asyncio.gather(*(one(j) for j in jobs)))

    @abstractmethod
    async def fetch_jobs(self) -> list[RawJobPosting]:
        """Return normalized listings for all configured queries."""

    async def enrich(self, job: RawJobPosting) -> RawJobPosting:
        """Return the job with a full description. Default: no-op."""
        return job
