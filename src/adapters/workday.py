"""Universal Workday CXS API adapter for Nvidia, AMD, Qualcomm, AMAT, etc."""

import httpx
from typing import Any, Dict, List
from loguru import logger
from src.adapters.base import BaseATSAdapter
from src.engine.models import RawJobPosting


class WorkdayAdapter(BaseATSAdapter):
    """Direct JSON client for Workday CXS endpoints."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.site_domain = config.get("site_domain", "")

    async def fetch_jobs(self) -> List[RawJobPosting]:
        postings: List[RawJobPosting] = []
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            for query in self.search_queries:
                payload = {
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": 0,
                    "searchText": query,
                }
                try:
                    res = await client.post(self.base_url, json=payload)
                    if res.status_code != 200:
                        logger.warning(f"Workday request failed for {self.company_name} [{query}]: Status {res.status_code}")
                        continue

                    data = res.json()
                    job_items = data.get("jobPostings", [])
                    for item in job_items:
                        external_path = item.get("externalPath", "")
                        job_id = external_path.split("_")[-1] if "_" in external_path else external_path
                        title = item.get("title", "Unknown Title")
                        locations = item.get("locationsText", "Not specified")
                        apply_url = f"{self.site_domain}{external_path}" if self.site_domain else f"{self.base_url}{external_path}"
                        snippet = item.get("bulletFields", [])
                        desc = " ".join(snippet) if snippet else title

                        postings.append(
                            RawJobPosting(
                                job_id=job_id or external_path,
                                company=self.company_name,
                                title=title,
                                location=locations,
                                url=apply_url,
                                description=f"{title} - Location: {locations}. {desc}",
                                posted_date=item.get("postedOn", "Recent"),
                                source_ats="workday",
                            )
                        )
                except Exception as exc:
                    logger.error(f"Error querying Workday for {self.company_name} on '{query}': {exc}")

        logger.info(f"Workday Adapter [{self.company_name}]: Fetched {len(postings)} total records.")
        return postings