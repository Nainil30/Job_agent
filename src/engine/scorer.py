"""Free, deterministic 0-100 fit score. Always runs; the LLM only refines the top of the list.

Transparent by design: every point comes from a named keyword in persona.yaml, and
the matched keywords are stored as the explanation.
"""

from __future__ import annotations

from typing import Any

from src.engine.models import RawJobPosting
from src.utils import compile_terms

BASE = 10
TITLE_CAP = 50
DESC_CAP = 30


class HeuristicScorer:
    def __init__(self, scoring_cfg: dict[str, Any] | None = None):
        cfg = scoring_cfg or {}
        self.title_terms = compile_terms(
            cfg.get("title_keywords") or {"program manager": 10, "supply chain": 10, "npi": 15}
        )
        self.desc_terms = compile_terms(cfg.get("description_keywords") or {})
        self.location_bonus = {k.lower(): int(v) for k, v in (cfg.get("location_bonus") or {}).items()}
        self.tier_bonus = {k: int(v) for k, v in (cfg.get("tier_bonus") or {}).items()}
        self.penalties = compile_terms(cfg.get("penalties") or {})

    def score(self, job: RawJobPosting) -> tuple[int, list[str]]:
        reasons: list[str] = []

        title_pts = 0
        for pattern, weight in self.title_terms:
            m = pattern.search(job.title)
            if m:
                title_pts += weight
                reasons.append(f"title: {m.group(0).lower()}")
        title_pts = min(title_pts, TITLE_CAP)

        desc_pts = 0
        for pattern, weight in self.desc_terms:
            m = pattern.search(job.description)
            if m:
                desc_pts += weight
                reasons.append(f"jd: {m.group(0).lower()}")
        desc_pts = min(desc_pts, DESC_CAP)

        loc = job.location.lower()
        loc_pts = max((v for k, v in self.location_bonus.items() if k in loc), default=0)
        if loc_pts:
            reasons.append("preferred location")

        tier_pts = self.tier_bonus.get(job.company_tier, 0)

        penalty = 0
        text = f"{job.title}\n{job.description}"
        for pattern, weight in self.penalties:
            m = pattern.search(text)
            if m:
                penalty += weight  # weights are negative
                reasons.append(f"penalty: {m.group(0).lower()}")

        total = BASE + title_pts + desc_pts + loc_pts + tier_pts + penalty
        return max(0, min(100, total)), reasons
