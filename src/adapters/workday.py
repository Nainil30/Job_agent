"""Workday CXS adapter (Nvidia, Intel, Applied Materials, Micron, Cisco, HPE, ...).

Every Workday career site is backed by the same JSON API:
    POST https://{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs      -> listings
    GET  https://{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}     -> full JD
To add a company, open its careers page, copy the tenant + site name from the URL.
"""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text, parse_posted

PAGE_SIZE = 20  # Workday rejects larger pages


class WorkdayAdapter(BaseAdapter):
    source = "workday"
    client_headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(self, config):
        super().__init__(config)
        self.site_url = (config.get("site_url") or "").rstrip("/")
        self.cxs_root = self.url[: -len("/jobs")] if self.url.endswith("/jobs") else self.url

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            offset = 0
            while offset < self.max_results:
                payload = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": query}
                try:
                    res = await request(self.client, "POST", self.url, json=payload)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                data = res.json()
                postings = data.get("jobPostings") or []
                for item in postings:
                    path = item.get("externalPath", "")
                    if not path:
                        continue
                    req_id = path.rsplit("_", 1)[-1] if "_" in path else path
                    jobs.append(
                        self.make_job(
                            job_id=req_id,
                            title=item.get("title", ""),
                            location=item.get("locationsText", ""),
                            url=f"{self.site_url}{path}" if self.site_url else f"{self.cxs_root}{path}",
                            description="",
                            posted_date=item.get("postedOn"),
                        )
                    )
                total = data.get("total") or 0
                offset += PAGE_SIZE
                if not postings or offset >= total:
                    break
        return jobs

    async def enrich(self, job: RawJobPosting) -> RawJobPosting:
        if not self.site_url or not job.url.startswith(self.site_url):
            return job
        path = job.url[len(self.site_url) :]
        res = await request(self.client, "GET", f"{self.cxs_root}{path}")
        info = res.json().get("jobPostingInfo", {})
        locs = [info.get("location", "")] + list(info.get("additionalLocations") or [])
        return job.model_copy(
            update={
                "description": html_to_text(info.get("jobDescription")),
                "location": "; ".join(x for x in locs if x) or job.location,
                "posted_at": parse_posted(info.get("startDate")) or job.posted_at,
            }
        )
