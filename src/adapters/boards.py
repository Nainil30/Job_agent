"""Public job-board APIs used by most startups: Greenhouse, Lever, Ashby.

These return *every* open role for a company in one keyless call, so `queries`
are ignored — the deterministic title/location filter does the narrowing.
"""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import request
from src.utils import html_to_text


class _BoardAdapter(BaseAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.board = config.get("board") or config.get("slug") or ""
        if not self.board:
            raise ValueError(f"{self.company_name}: '{self.source}' source needs a `board` slug")


class GreenhouseAdapter(_BoardAdapter):
    """GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs (JD fetched per job in `enrich`)."""

    source = "greenhouse"
    api = "https://boards-api.greenhouse.io/v1/boards"

    async def fetch_jobs(self) -> list[RawJobPosting]:
        try:
            res = await request(self.client, "GET", f"{self.api}/{self.board}/jobs")
        except Exception as exc:
            self.record_error("board", exc)
            return []
        return [
            self.make_job(
                job_id=j.get("id"),
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                url=j.get("absolute_url", ""),
                posted_date=j.get("first_published") or j.get("updated_at"),
            )
            for j in res.json().get("jobs") or []
        ]

    async def enrich(self, job: RawJobPosting) -> RawJobPosting:
        res = await request(self.client, "GET", f"{self.api}/{self.board}/jobs/{job.job_id}")
        return job.model_copy(update={"description": html_to_text(html_to_text(res.json().get("content")))})


class LeverAdapter(_BoardAdapter):
    """GET https://api.lever.co/v0/postings/{board}?mode=json (descriptions included)."""

    source = "lever"

    async def fetch_jobs(self) -> list[RawJobPosting]:
        try:
            res = await request(
                self.client, "GET", f"https://api.lever.co/v0/postings/{self.board}", params={"mode": "json"}
            )
        except Exception as exc:
            self.record_error("board", exc)
            return []
        out = []
        for j in res.json() or []:
            cats = j.get("categories") or {}
            lists = "\n".join(
                f"{sec.get('text', '')}\n{html_to_text(sec.get('content'))}" for sec in j.get("lists") or []
            )
            out.append(
                self.make_job(
                    job_id=j.get("id"),
                    title=j.get("text", ""),
                    location=cats.get("location") or "; ".join(cats.get("allLocations") or []),
                    url=j.get("hostedUrl", ""),
                    description=f"{j.get('descriptionPlain', '')}\n{lists}".strip(),
                    posted_date=j.get("createdAt"),
                    department=cats.get("department") or cats.get("team"),
                )
            )
        return out


class AshbyAdapter(_BoardAdapter):
    """GET https://api.ashbyhq.com/posting-api/job-board/{board} (descriptions included)."""

    source = "ashby"

    async def fetch_jobs(self) -> list[RawJobPosting]:
        try:
            res = await request(self.client, "GET", f"https://api.ashbyhq.com/posting-api/job-board/{self.board}")
        except Exception as exc:
            self.record_error("board", exc)
            return []
        out = []
        for j in res.json().get("jobs") or []:
            if j.get("isListed") is False:
                continue
            locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            if j.get("isRemote"):
                locs.append("Remote")
            out.append(
                self.make_job(
                    job_id=j.get("id"),
                    title=j.get("title", ""),
                    location="; ".join(x for x in locs if x),
                    url=j.get("jobUrl", ""),
                    description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                    posted_date=j.get("publishedAt"),
                    department=j.get("department"),
                )
            )
        return out
