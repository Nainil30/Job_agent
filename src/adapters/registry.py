"""Maps `source:` values in companies.yaml to adapter classes."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.adapters.aggregator import JobSpyAdapter
from src.adapters.amazon import AmazonAdapter
from src.adapters.apple import AppleAdapter
from src.adapters.base import BaseAdapter
from src.adapters.boards import AshbyAdapter, GreenhouseAdapter, LeverAdapter
from src.adapters.browser import BrowserAdapter
from src.adapters.eightfold import EightfoldAdapter
from src.adapters.google import GoogleAdapter
from src.adapters.jibe import JibeAdapter
from src.adapters.workday import WorkdayAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "workday": WorkdayAdapter,
    "eightfold": EightfoldAdapter,
    "jibe": JibeAdapter,
    "amazon": AmazonAdapter,
    "apple": AppleAdapter,
    "google": GoogleAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "browser": BrowserAdapter,
}

ALL_TIERS = ("api", "browser", "aggregator")


def build_adapters(
    companies: list[dict[str, Any]],
    aggregators: dict[str, Any] | None = None,
    tiers: tuple[str, ...] | list[str] = ALL_TIERS,
    only: list[str] | None = None,
) -> list[BaseAdapter]:
    """Instantiate enabled adapters for the requested ingestion tiers.

    `only` filters by company name (case-insensitive substring), e.g. ["nvidia", "tesla"].
    """
    wanted = [o.lower() for o in only or []]

    def selected(name: str) -> bool:
        return not wanted or any(w in name.lower() for w in wanted)

    adapters: list[BaseAdapter] = []
    for cfg in companies:
        if not cfg.get("enabled", True) or not selected(cfg.get("name", "")):
            continue
        cls = ADAPTERS.get(str(cfg.get("source", "")).lower())
        if cls is None:
            logger.warning(f"Unknown source '{cfg.get('source')}' for {cfg.get('name')} - skipped")
            continue
        if cls.ingestion_tier not in tiers:
            continue
        try:
            adapters.append(cls(cfg))
        except ValueError as exc:
            logger.warning(str(exc))

    spy = (aggregators or {}).get("jobspy") or {}
    if "aggregator" in tiers and spy.get("enabled", False):
        known = {c["name"]: c.get("tier", "Secondary") for c in companies}
        for search in spy.get("searches") or []:
            label = " ".join([search.get("term", "")] + list(search.get("companies") or []))
            if selected(label):
                adapters.append(JobSpyAdapter(search, spy, known))
    return adapters
