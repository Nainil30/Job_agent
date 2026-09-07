"""Direct API adapter for Amazon Jobs search endpoint."""

import httpx
from typing import Any, Dict, List
from loguru import logger
from src.adapters.base import BaseATSAdapter
from src.engine.models import RawJobPosting


class AmazonAdapter(BaseATSAdapter):
    """Client for amazon.jobs REST API."""

    async def fetch_jobs(self) -> List[RawJobPosting]:
        postings: List[RawJobPosting] = []
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            for query in self.search_queries:
                params = {
                    "base_query": query,
                    "city": "Austin",
                    "result_limit": 25,
                    "sort": "recent",
                }
                try:
                    res = await client.get(self.base_url, params=params)
                    if res.status_code != 200:
                        logger.warning(f"Amazon API returned status {res.status_code} for query '{query}'")
                        continue

                    data = res.json()
                    jobs = data.get("jobs", [])
                    for j in jobs:
                        job_id = j.get("id_icims") or j.get("job_path", "")
                        title = j.get("title", "")
                        loc = f"{j.get('city', '')}, {j.get('state', '')} {j.get('country_code', '')}".strip()
                        job_url = f"https://www.amazon.jobs{j.get('job_path', '')}"
                        description = j.get("description_short", "") or j.get("basic_qualifications", "")

                        postings.append(
                            RawJobPosting(
                                job_id=str(job_id),
                                company="Amazon",
                                title=title,
                                location=loc,
                                url=job_url,
                                description=f"{description} {j.get('preferred_qualifications', '')}",
                                posted_date=j.get("posted_date", "Recent"),
                                source_ats="amazon_api",
                            )
                        )
                except Exception as exc:
                    logger.error(f"Error querying Amazon Jobs API on '{query}': {exc}")

        logger.info(f"Amazon Adapter: Fetched {len(postings)} postings.")
        return postings