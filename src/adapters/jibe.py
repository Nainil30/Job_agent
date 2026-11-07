"""iCIMS Jibe career sites (AMD). Listings already contain the full description.

GET {site}/api/jobs?keywords=...&page=N&limit=50
"""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text

PAGE_SIZE = 50


class JibeAdapter(BaseAdapter):
    source = "jibe"

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            page = 1
            while (page - 1) * PAGE_SIZE < self.max_results:
                params = {
                    "keywords": query,
                    "page": page,
                    "limit": PAGE_SIZE,
                    "sortBy": "posted_date",
                    "descending": "true",
                }
                try:
                    res = await request(self.client, "GET", f"{self.url}/api/jobs", params=params)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                data = res.json()
                items = data.get("jobs") or []
                for wrapper in items:
                    d = wrapper.get("data", wrapper)
                    slug = d.get("slug") or d.get("req_id")
                    desc = "\n\n".join(
                        html_to_text(d.get(k))
                        for k in ("description", "responsibilities", "qualifications")
                        if d.get(k)
                    )
                    jobs.append(
                        self.make_job(
                            job_id=d.get("req_id") or slug,
                            title=d.get("title", ""),
                            location=d.get("full_location") or d.get("location_name", ""),
                            url=f"{self.url}/careers-home/jobs/{slug}?lang=en-us",
                            description=desc,
                            posted_date=d.get("posted_date"),
                            department=(d.get("category") or [None])[0]
                            if isinstance(d.get("category"), list)
                            else None,
                        )
                    )
                if len(items) < PAGE_SIZE or page * PAGE_SIZE >= (data.get("totalCount") or 0):
                    break
                page += 1
        return jobs
