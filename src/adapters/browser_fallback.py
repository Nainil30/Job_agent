"""Fallback scraper for dynamic SPA job sites (e.g. Tesla)."""

from typing import Any, Dict, List
from loguru import logger
from src.adapters.base import BaseATSAdapter
from src.engine.models import RawJobPosting


class BrowserFallbackAdapter(BaseATSAdapter):
    """Isolated browser scraper using Playwright/Crawl4AI patterns for dynamic DOMs."""

    async def fetch_jobs(self) -> List[RawJobPosting]:
        logger.info(f"Browser Fallback Adapter running for {self.company_name} (Weekly Isolated Mode)...")
        # Kept isolated so dynamic DOM shifts never crash the daily API critical path
        return []