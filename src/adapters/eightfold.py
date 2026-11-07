"""Eightfold AI career sites (Qualcomm, Microsoft, and many other enterprises).

GET {site}/api/pcsx/search?domain=...&query=...&location=...&start=N   -> listings (10 / page)
GET {site}/api/pcsx/position_details?position_id=...&domain=...       -> full JD
"""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text

PAGE_SIZE = 10


class EightfoldAdapter(BaseAdapter):
    source = "eightfold"

    def __init__(self, config):
        super().__init__(config)
        self.domain = config.get("domain", "")
        self.location = config.get("location", "")

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            start = 0
            while start < self.max_results:
                params = {"domain": self.domain, "query": query, "location": self.location, "start": start}
                try:
                    res = await request(self.client, "GET", f"{self.url}/api/pcsx/search", params=params)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                data = (res.json() or {}).get("data") or {}
                positions = data.get("positions") or []
                for p in positions:
                    locs = p.get("standardizedLocations") or p.get("locations") or []
                    jobs.append(
                        self.make_job(
                            job_id=p.get("displayJobId") or p.get("id"),
                            title=p.get("name", ""),
                            location="; ".join(locs),
                            url=f"{self.url}{p.get('positionUrl', '')}",
                            posted_date=p.get("postedTs"),
                            department=p.get("department"),
                            description="",
                        )
                    )
                start += PAGE_SIZE
                if len(positions) < PAGE_SIZE or start >= (data.get("count") or 0):
                    break
        return jobs

    async def enrich(self, job: RawJobPosting) -> RawJobPosting:
        position_id = job.url.rstrip("/").rsplit("/", 1)[-1]
        params = {"position_id": position_id, "domain": self.domain, "hl": "en"}
        res = await request(self.client, "GET", f"{self.url}/api/pcsx/position_details", params=params)
        data = (res.json() or {}).get("data") or {}
        desc = html_to_text(data.get("jobDescription"))
        return job.model_copy(update={"description": desc or job.description, "url": data.get("publicUrl") or job.url})
