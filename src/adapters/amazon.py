"""amazon.jobs public search JSON. Listings include the full description."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text

PAGE_SIZE = 50


class AmazonAdapter(BaseAdapter):
    source = "amazon"

    def __init__(self, config):
        super().__init__(config)
        self.url = self.url or "https://www.amazon.jobs/en/search.json"
        self.location = config.get("location", "")

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            offset = 0
            while offset < self.max_results:
                params = {"base_query": query, "result_limit": PAGE_SIZE, "offset": offset, "sort": "recent"}
                if self.location:
                    params["loc_query"] = self.location
                try:
                    res = await request(self.client, "GET", self.url, params=params)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                data = res.json()
                items = data.get("jobs") or []
                for j in items:
                    desc = "\n\n".join(
                        html_to_text(j.get(k))
                        for k in ("description", "basic_qualifications", "preferred_qualifications")
                        if j.get(k)
                    )
                    jobs.append(
                        self.make_job(
                            job_id=j.get("id_icims") or j.get("id"),
                            title=j.get("title", ""),
                            location=j.get("normalized_location") or j.get("location", ""),
                            url=f"https://www.amazon.jobs{j.get('job_path', '')}",
                            description=desc,
                            posted_date=j.get("posted_date"),
                            department=j.get("job_category"),
                        )
                    )
                offset += PAGE_SIZE
                if len(items) < PAGE_SIZE or offset >= (data.get("hits") or 0):
                    break
        return jobs
