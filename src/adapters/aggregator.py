"""Tier 3 — aggregator safety net via python-jobspy (LinkedIn, Indeed, Glassdoor, Google Jobs).

Why this exists: some employers (Tesla) put their career site behind bot protection
that blocks even real headless browsers, and others have no usable endpoint. Their
roles are still syndicated to Indeed / LinkedIn, which JobSpy reads for free.
Aggregator results are lower priority than direct-ATS results: when the same role
is found both ways, the direct listing wins (see pipeline de-duplication).
"""

from __future__ import annotations

import asyncio
import math
import random
from typing import Any

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.utils import normalize_company, stable_hash

_LOCKS: dict[int, asyncio.Lock] = {}


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v)
    return None if s in {"nan", "NaT", "None"} else v


class JobSpyAdapter(BaseAdapter):
    source = "jobspy"
    ingestion_tier = "aggregator"

    def __init__(self, search: dict[str, Any], settings: dict[str, Any], known_tiers: dict[str, str] | None = None):
        term = search.get("term", "")
        super().__init__({"name": f"JobSpy: {term}", "tier": "Aggregator", "queries": [term]})
        self.search = search
        self.sites = settings.get("sites", ["indeed", "linkedin"])
        self.hours_old = int(search.get("hours_old", settings.get("hours_old", 72)))
        self.results_wanted = int(search.get("results_wanted", settings.get("results_wanted", 30)))
        self.company_filter = [normalize_company(c) for c in search.get("companies") or []]
        self.known_tiers = {normalize_company(k): v for k, v in (known_tiers or {}).items()}

    @property
    def label(self) -> str:
        return self.company_name

    async def run(self) -> list[RawJobPosting]:
        self.errors = []
        # LinkedIn returns 429 when searches run in parallel: run aggregator searches one at a
        # time with a short pause (other source tiers keep running concurrently meanwhile).
        lock = _LOCKS.setdefault(id(asyncio.get_running_loop()), asyncio.Lock())
        async with lock:
            jobs = await self.fetch_jobs()
            await asyncio.sleep(2 + random.random() * 2)
        if not jobs and self.errors:
            raise RuntimeError("; ".join(self.errors[:3]))
        return list({j.job_id: j for j in jobs}.values())

    def _scrape(self):
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("python-jobspy not installed: pip install python-jobspy") from exc
        return scrape_jobs(
            site_name=self.sites,
            search_term=self.search.get("term", ""),
            location=self.search.get("location", "United States"),
            results_wanted=self.results_wanted,
            hours_old=self.hours_old,
            country_indeed="USA",
            verbose=0,
        )

    def _keep(self, company: str) -> bool:
        if not self.company_filter:
            return True
        norm = normalize_company(company)
        return any(norm == c or norm.startswith(c + " ") for c in self.company_filter)

    async def fetch_jobs(self) -> list[RawJobPosting]:
        try:
            df = await asyncio.to_thread(self._scrape)
        except Exception as exc:
            self.record_error("scrape", exc)
            return []
        jobs = []
        for row in df.to_dict("records"):
            company = _clean(row.get("company")) or ""
            if not company or not self._keep(company):
                continue
            url = _clean(row.get("job_url_direct")) or _clean(row.get("job_url")) or ""
            site = _clean(row.get("site")) or "aggregator"
            tier = self.known_tiers.get(normalize_company(company), "Aggregator")
            jobs.append(
                self.make_job(
                    job_id=_clean(row.get("id")) or stable_hash(url)[:16],
                    company=company,
                    company_tier=tier,
                    title=_clean(row.get("title")) or "",
                    location=_clean(row.get("location")) or "",
                    url=url,
                    description=_clean(row.get("description")) or "",
                    posted_date=_clean(row.get("date_posted")),
                    source_ats=f"jobspy:{site}",
                )
            )
        return jobs
