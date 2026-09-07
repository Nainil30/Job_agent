"""Pass 1: Deterministic regex and geographic pre-filtering engine."""

import re
from typing import List, Tuple
from loguru import logger
from src.engine.models import RawJobPosting

# Drop obvious mismatches at 0 LLM token cost
BLOCKLIST_REGEX = re.compile(
    r"\b(intern|internship|co-op|coop|director|vp|vice president|sales|account executive|"
    r"recruiter|talent|hr|human resources|legal|counsel|tax|facilities|technician|custodian|"
    r"administrative|receptionist|nurse|culinary|barista|cashier)\b",
    re.IGNORECASE,
)

# Target role patterns
ALLOWLIST_REGEX = re.compile(
    r"\b(npi|new product introduction|materials|materials program|mpm|supply chain|"
    r"hardware tpm|technical program manager|datacenter|data center|infrastructure tpm|"
    r"launch readiness|operations program|operations manager|supply planning|"
    r"demand planning|commodity manager|global supply manager|gsm|analytics engineer)\b",
    re.IGNORECASE,
)


class DeterministicFilter:
    """Pre-filters raw job postings to eliminate irrelevant roles prior to LLM evaluation."""

    @staticmethod
    def is_valid_title(title: str) -> Tuple[bool, str]:
        """Validates job title against blocklist and allowlist."""
        if BLOCKLIST_REGEX.search(title):
            return False, "Matched title blocklist"
        if not ALLOWLIST_REGEX.search(title):
            return False, "Did not match target role allowlist"
        return True, "Valid title"

    @staticmethod
    def is_valid_location(company: str, location: str) -> Tuple[bool, str]:
        """Applies company-specific geographic constraints (e.g. strict Austin for Amazon)."""
        if company.lower() == "amazon":
            if not re.search(r"\b(austin|tx|texas)\b", location, re.IGNORECASE):
                return False, "Amazon role not located in Austin, TX"
        return True, "Valid location"

    def filter_jobs(self, jobs: List[RawJobPosting]) -> List[RawJobPosting]:
        """Filters a list of raw job postings, returning only qualified candidates."""
        passed_jobs: List[RawJobPosting] = []
        for job in jobs:
            title_ok, title_reason = self.is_valid_title(job.title)
            if not title_ok:
                logger.debug(f"Skipping '{job.title}' ({job.company}): {title_reason}")
                continue

            loc_ok, loc_reason = self.is_valid_location(job.company, job.location)
            if not loc_ok:
                logger.debug(f"Skipping '{job.title}' ({job.company}): {loc_reason}")
                continue

            passed_jobs.append(job)

        logger.info(f"Pass 1 Deterministic Filter: {len(passed_jobs)}/{len(jobs)} postings retained.")
        return passed_jobs