"""Google Careers — the old /api/v3/search endpoint is gone (404), but the results page
ships its data in an `AF_initDataCallback({key: 'ds:1', ...})` block. We parse that
JSON array directly: no browser, full descriptions included.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text

SEARCH_URL = "https://www.google.com/about/careers/applications/jobs/results/"
_DS1 = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);", re.S)
PAGE_SIZE = 20


def _at(seq: Any, *path: int) -> Any:
    for i in path:
        if not isinstance(seq, list) or i >= len(seq):
            return None
        seq = seq[i]
    return seq


def parse_google_html(html: str) -> tuple[list[dict[str, Any]], int]:
    m = _DS1.search(html)
    if not m:
        raise ValueError("Google ds:1 data block not found (page layout changed?)")
    data = json.loads(m.group(1))
    rows = _at(data, 0) or []
    total = _at(data, 2) or 0
    jobs = []
    for row in rows:
        job_id = _at(row, 0)
        if not job_id:
            continue
        locations = [_at(loc, 0) for loc in (_at(row, 9) or []) if _at(loc, 0)]
        sections = [html_to_text(_at(row, i, 1)) for i in (10, 3, 4)]
        jobs.append(
            {
                "id": str(job_id),
                "title": _at(row, 1) or "",
                "company": _at(row, 7) or "Google",
                "locations": locations,
                "description": "\n\n".join(s for s in sections if s),
                "created_ts": _at(row, 12, 0),
            }
        )
    return jobs, int(total) if isinstance(total, int) else 0


class GoogleAdapter(BaseAdapter):
    source = "google"

    def __init__(self, config):
        super().__init__(config)
        self.location = config.get("location", "United States")

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        for query in self.queries:
            page = 1
            while (page - 1) * PAGE_SIZE < self.max_results:
                params = {"q": query, "location": self.location, "sort_by": "date", "page": page}
                try:
                    res = await request(self.client, "GET", SEARCH_URL, params=params)
                    rows, total = parse_google_html(res.text)
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    break
                for r in rows:
                    jobs.append(
                        self.make_job(
                            job_id=r["id"],
                            title=r["title"],
                            location="; ".join(r["locations"]),
                            url=f"{SEARCH_URL}{r['id']}",
                            description=r["description"],
                            posted_date=r["created_ts"],
                        )
                    )
                if len(rows) < PAGE_SIZE or page * PAGE_SIZE >= total:
                    break
                page += 1
        return jobs
