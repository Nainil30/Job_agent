"""Client adapter for Apple Jobs search endpoint."""

import httpx
from typing import Any, Dict, List
from loguru import logger
from src.adapters.base import BaseATSAdapter
from src.engine.models import RawJobPosting


class AppleJobsAdapter(BaseATSAdapter):
    """Client for Apple Jobs search endpoint."""

    async def fetch_jobs(self) -> List[RawJobPosting]:
        postings: List[RawJobPosting] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            for query in self.search_queries:
                try:
                    payload = {"query": query, "filters": {"range": "20"}}
                    res = await client.post(self.base_url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        for item in data.get("searchResults", []):
                            job_id = item.get("id", "")
                            title = item.get("postingTitle", "")
                            location = item.get("locations", [{}])[0].get("name", "Cupertino, CA") if item.get("locations") else "Cupertino, CA"
                            postings.append(
                                RawJobPosting(
                                    job_id=job_id,
                                    company="Apple",
                                    title=title,
                                    location=location,
                                    url=f"https://jobs.apple.com/en-us/details/{job_id}",
                                    description=item.get("jobSummary", title),
                                    posted_date=item.get("postDateInGmt", "Recent"),
                                    source_ats="apple_api",
                                )
                            )
                except Exception as exc:
                    logger.debug(f"Apple Jobs endpoint query note: {exc}")

        logger.info(f"Apple Adapter: Fetched {len(postings)} postings.")
        return postings