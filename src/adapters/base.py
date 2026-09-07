"""Abstract base class for all career site ATS adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from src.engine.models import RawJobPosting


class BaseATSAdapter(ABC):
    """Common interface that every ATS scraper/API client must implement."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.company_name: str = config.get("name", "Unknown")
        self.base_url: str = config.get("base_url", "")
        self.search_queries: List[str] = config.get("search_queries", [])

    @abstractmethod
    async def fetch_jobs(self) -> List[RawJobPosting]:
        """Fetches and normalizes raw job postings from the ATS endpoint."""
        pass