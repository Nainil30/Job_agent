"""Tier 2 — headless-browser adapter for career sites that only render with JavaScript.

Used only where no JSON endpoint exists (e.g. Meta). It is config-driven rather than
hand-coded per site: give it a search URL template and a CSS selector for job links,
and it reads the rendered anchors. Link selectors (`a[href*='/job_details/']`) are far
more stable than class-name selectors, which change on every frontend deploy.

This adapter does NOT try to defeat bot protection. Sites that block headless
browsers (Tesla's Akamai wall, for instance) are covered by the aggregator tier.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from loguru import logger

from src.adapters.base import BaseAdapter
from src.engine.models import RawJobPosting
from src.net import BROWSER_UA

_LOCATION_LINE = re.compile(r"(,\s*[A-Z]{2}\b|remote|united states|usa|\bUS\b)", re.I)
_CITY_COUNTRY = re.compile(r"^[A-Z][^,|]{1,40},\s*[A-Z][^,|]{1,40}(,\s*[A-Z][^,|]{1,40})?$")  # "Taipei, Taiwan"
_ID_TAIL = re.compile(r"/(\d{5,})/?(?:\?|$)")


def _is_location(line: str) -> bool:
    return bool(_LOCATION_LINE.search(line) or _CITY_COUNTRY.match(line))


def parse_anchor(href: str, text: str) -> tuple[str, str, str, str] | None:
    """Split a rendered job-card anchor into (job_id, title, location, extra_text)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and ln.strip() not in {"⋅", "·", "|"}]
    if not lines:
        return None
    title = lines[0]
    locations = [ln for ln in lines[1:] if _is_location(ln)]
    extras = [ln for ln in lines[1:] if ln not in locations]
    m = _ID_TAIL.search(href)
    job_id = m.group(1) if m else href.rstrip("/").rsplit("/", 1)[-1]
    return job_id, title, "; ".join(locations), " | ".join(extras)


def _playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on install
        raise RuntimeError(
            "playwright not installed: pip install playwright && python -m playwright install chromium"
        ) from exc
    return async_playwright


class BrowserAdapter(BaseAdapter):
    source = "browser"
    ingestion_tier = "browser"

    def __init__(self, config):
        super().__init__(config)
        self.url_template: str = config.get("url", "")
        self.link_selector: str = config.get("link_selector", "a[href*='job']")
        self.link_base: str = config.get("link_base", "")
        self.wait_ms: int = int(config.get("wait_ms", 4000))
        self.max_detail_pages: int = int(config.get("max_detail_pages", 15))

    async def run(self) -> list[RawJobPosting]:  # browser manages its own lifecycle, no httpx client
        self.errors = []
        jobs = await self.fetch_jobs()
        if not jobs and self.errors:
            raise RuntimeError("; ".join(self.errors[:3]))
        return list({j.job_id: j for j in jobs}.values())

    async def fetch_jobs(self) -> list[RawJobPosting]:
        jobs: list[RawJobPosting] = []
        async with _playwright()() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context(user_agent=BROWSER_UA, locale="en-US")).new_page()
            for query in self.queries:
                url = self.url_template.format(query=quote(query))
                try:
                    resp = await page.goto(url, wait_until="networkidle", timeout=45000)
                    if resp and resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status} (site may block automated browsers)")
                    # Results usually stream in after the first paint: wait until several job
                    # links exist (or give up after the timeout and take whatever rendered).
                    try:
                        await page.wait_for_function(
                            "sel => document.querySelectorAll(sel).length >= 3", arg=self.link_selector, timeout=15000
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    await page.wait_for_timeout(self.wait_ms)
                    anchors = await page.eval_on_selector_all(
                        self.link_selector, "els => els.map(e => [e.getAttribute('href'), e.innerText])"
                    )
                except Exception as exc:
                    self.record_error(f"query '{query}'", exc)
                    continue
                for href, text in anchors:
                    parsed = parse_anchor(href or "", text or "")
                    if not parsed:
                        continue
                    job_id, title, location, extra = parsed
                    jobs.append(
                        self.make_job(
                            job_id=job_id,
                            title=title,
                            location=location,
                            url=urljoin(self.link_base or url, href),
                            description=extra,
                        )
                    )
                logger.debug(f"[{self.label}] '{query}': {len(anchors)} links")
            await browser.close()
        return jobs

    async def enrich_many(self, jobs: list[RawJobPosting], concurrency: int = 1) -> list[RawJobPosting]:
        """Open each detail page in one shared browser session and keep its main text."""
        if not jobs:
            return jobs
        out: list[RawJobPosting] = []
        async with _playwright()() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context(user_agent=BROWSER_UA, locale="en-US")).new_page()
            for i, job in enumerate(jobs):
                if i >= self.max_detail_pages:
                    out.append(job)
                    continue
                try:
                    await page.goto(job.url, wait_until="networkidle", timeout=45000)
                    await page.wait_for_timeout(1500)
                    main = await page.query_selector("main") or await page.query_selector("body")
                    text = (await main.inner_text()) if main else ""
                    out.append(job.model_copy(update={"description": text[:8000] or job.description}))
                except Exception as exc:
                    logger.debug(f"[{self.label}] detail page failed for {job.job_id}: {exc}")
                    out.append(job)
            await browser.close()
        return out
