"""jobs.apple.com — no public JSON API, but the server-rendered search page embeds
the full result set as React Router hydration data. Parsing that is far more stable
than scraping the DOM and needs no browser.
"""

from __future__ import annotations

import json
import re

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request

SEARCH_URL = "https://jobs.apple.com/en-us/search"
_HYDRATION = re.compile(r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\((\".*?\")\);", re.S)
PAGE_SIZE = 20


def parse_apple_html(html: str) -> tuple[list[dict], int]:
    m = _HYDRATION.search(html)
    if not m:
        raise ValueError("Apple hydration data not found (page layout changed?)")
    state = json.loads(json.loads(m.group(1)))
    search = (state.get("loaderData") or {}).get("search") or {}
    return search.get("searchResults") or [], int(search.get("totalRecords") or 0)


class AppleAdapter(BaseAdapter):
    source = "apple"

    def __init__(self, config):
        super().__init__(config)
        self.location = config.get("location", "united-states-USA")

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            page = 1
            while (page - 1) * PAGE_SIZE < self.max_results:
                params = {"search": query, "location": self.location, "sort": "newest", "page": page}
                try:
                    res = await request(self.client, "GET", SEARCH_URL, params=params)
                    results, total = parse_apple_html(res.text)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                for r in results:
                    pos_id = r.get("positionId") or r.get("id")
                    locs = [
                        ", ".join(x for x in (loc.get("name"), loc.get("countryName")) if x)
                        for loc in r.get("locations") or []
                    ]
                    team = r.get("team") or {}
                    jobs.append(
                        self.make_job(
                            job_id=pos_id,
                            title=r.get("postingTitle", ""),
                            location="; ".join(locs),
                            url=f"https://jobs.apple.com/en-us/details/{pos_id}/{r.get('transformedPostingTitle', '')}",
                            description=r.get("jobSummary", ""),
                            posted_date=r.get("postDateInGMT") or r.get("postingDate"),
                            department=team.get("teamName"),
                        )
                    )
                if len(results) < PAGE_SIZE or page * PAGE_SIZE >= total:
                    break
                page += 1
        return jobs
