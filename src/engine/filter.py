"""Pass 1 — deterministic title / location / freshness gate (zero cost, no network)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from loguru import logger

from src.engine.models import RawJobPosting
from src.utils import age_days, compile_terms

_AMBIGUOUS = re.compile(r"^\s*(\d+\s+locations?|multiple( locations)?|various|tbd|)\s*$", re.I)
_WEAK_US_MARKERS = {"remote"}
# Two-letter codes that are also common country codes (IN=India, DE=Germany) are left out;
# those states are still matched by full name.
_US_STATES = (
    "AL AK AZ AR CA CO CT FL GA HI ID IL IA KS KY LA MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
    "PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
_US_STATE_NAMES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|"
    "indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|"
    "montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|"
    "oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|"
    "west virginia|wisconsin|wyoming"
)
# Explicit country markers: "United States", "USA", "US, CA, Santa Clara", "US-TX-Austin"
_US_EXPLICIT = re.compile(r"united states|\bUSA?\b|\bU\.S\.", re.I)
# State markers: "Austin, TX" (case-sensitive code) or "Texas" (name)
_US_STATE_CODE = re.compile(rf"(?<![A-Za-z])(?:{'|'.join(_US_STATES)})(?![A-Za-z])")
_US_STATE_NAME = re.compile(rf"\b(?:{_US_STATE_NAMES})\b", re.I)


def looks_us(location: str, explicit_only: bool = False) -> bool:
    if _US_EXPLICIT.search(location):
        return True
    if explicit_only:
        return False
    return bool(_US_STATE_CODE.search(location) or _US_STATE_NAME.search(location))


DEFAULT_SEARCH: dict[str, Any] = {
    "title_allow": ["npi", "supply chain", "program manager", "materials"],
    "title_block": ["intern(ship)?", "director", "vp", "vice president", "sales", "recruiter"],
    "locations": {"allow": ["United States", "USA", "Remote", "TX", "CA"], "block": [], "allow_ambiguous": True},
    "company_location_rules": {},
    "max_age_days": 60,
}


class JobFilter:
    """Pre-filters listings so only plausible roles reach enrichment and scoring."""

    def __init__(self, search_cfg: dict[str, Any] | None = None):
        cfg = {**DEFAULT_SEARCH, **(search_cfg or {})}
        self.allow = compile_terms(cfg["title_allow"])
        self.block = compile_terms(cfg["title_block"])
        locs = {**DEFAULT_SEARCH["locations"], **(cfg.get("locations") or {})}
        self.loc_allow = [s.lower() for s in locs.get("allow") or []]
        block = [re.escape(s) for s in locs.get("block") or []]
        # word-boundary match so "India" doesn't hit "Indiana"
        self.loc_block = re.compile(rf"(?<!new )\b(?:{'|'.join(block)})\b", re.I) if block else None
        self.allow_ambiguous = bool(locs.get("allow_ambiguous", True))
        self.us_anywhere = bool(locs.get("us_anywhere", True))
        self.company_rules = {
            k.lower(): [s.lower() for s in v] for k, v in (cfg.get("company_location_rules") or {}).items()
        }
        self.max_age_days = cfg.get("max_age_days")

    def is_valid_title(self, title: str) -> tuple[bool, str]:
        for pattern, _ in self.block:
            if pattern.search(title):
                return False, "title_blocklist"
        if not any(p.search(title) for p, _ in self.allow):
            return False, "title_not_target"
        return True, "ok"

    def is_valid_location(self, company: str, location: str) -> tuple[bool, str]:
        loc = (location or "").lower()
        rule = self.company_rules.get(company.lower())
        if rule is not None:
            return (True, "ok") if any(r in loc for r in rule) else (False, "company_location_rule")
        if _AMBIGUOUS.match(loc):
            return (True, "ok") if self.allow_ambiguous else (False, "location_ambiguous")
        blocked = bool(self.loc_block and self.loc_block.search(loc))
        if blocked:
            # A blocked country only passes alongside an explicit US marker ("Taipei; Austin, TX, USA")
            return (True, "ok") if looks_us(location, explicit_only=True) else (False, "location_blocklist")
        if self.us_anywhere and looks_us(location):
            return True, "ok"
        if any(a in loc for a in self.loc_allow):
            return True, "ok"
        return False, "location_not_target"

    def is_fresh(self, job: RawJobPosting) -> tuple[bool, str]:
        age = age_days(job.posted_at)
        if self.max_age_days and age is not None and age > int(self.max_age_days):
            return False, "too_old"
        return True, "ok"

    def check(self, job: RawJobPosting) -> tuple[bool, str]:
        for test in (
            lambda: self.is_valid_title(job.title),
            lambda: self.is_valid_location(job.company, job.location),
            lambda: self.is_fresh(job),
        ):
            ok, reason = test()
            if not ok:
                return False, reason
        return True, "ok"

    def filter_jobs(self, jobs: list[RawJobPosting]) -> tuple[list[RawJobPosting], Counter]:
        passed: list[RawJobPosting] = []
        reasons: Counter = Counter()
        for job in jobs:
            ok, reason = self.check(job)
            reasons[reason] += 1
            if ok:
                passed.append(job)
        logger.info(f"Pass 1 filter: kept {len(passed)}/{len(jobs)} ({dict(reasons)})")
        return passed, reasons


# Backwards-compatible name used by v1
DeterministicFilter = JobFilter
