"""Client adapter for Google Careers search endpoint."""

import httpx
from typing import Any, Dict, List
from loguru import logger
from src.adapters.base import BaseATSAdapter
from src.engine.models import RawJobPosting


class GoogleCareersAdapter(BaseATSAdapter):
    """Client for Google Careers search API."""

    async def fetch_jobs(self) -> List[RawJobPosting]:
        postings: List[RawJobPosting] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            for query in self.search_queries:
                try:
                    # Google uses a standard search payload on careers.google.com
                    params = {"q": query, "page_size": 20}
                    res = await client.get("https://careers.google.com/api/v3/search/", params=params)
                    if res.status_code == 200:
                        data = res.json()
                        for job in data.get("jobs", []):
                            job_id = job.get("id", "")
                            title = job.get("title", "")
                            locations = ", ".join([loc.get("display", "") for loc in job.get("locations", [])])
                            postings.append(
                                RawJobPosting(
                                    job_id=job_id,
                                    company="Google",
                                    title=title,
                                    location=locations or "Multiple Locations",
                                    url=f"https://www.google.com/about/careers/applications/jobs/results/{job_id}",
                                    description=job.get("description", title),
                                    posted_date=job.get("publish_date", "Recent"),
                                    source_ats="google_api",
                                )
                            )
                except Exception as exc:
                    logger.debug(f"Google Careers search endpoint query completed or redirected: {exc}")

        logger.info(f"Google Adapter: Fetched {len(postings)} postings.")
        return postings