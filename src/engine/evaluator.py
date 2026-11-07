"""Pass 2 — scoring. Heuristic for every job, LLM-as-a-judge for the most promising ones."""

from __future__ import annotations

from typing import Any

import yaml
from loguru import logger

from src.engine.llm import LLMClient
from src.engine.models import JobEvaluation, LLMVerdict, RawJobPosting
from src.engine.scorer import HeuristicScorer

SYSTEM_PROMPT = (
    "You are a senior technical recruiter for hardware, semiconductor and datacenter operations roles. "
    "You judge candidate-job fit honestly and conservatively, and you never invent facts about the candidate."
)

PROMPT_TEMPLATE = """Evaluate how well this job fits the candidate.

## Candidate
{candidate}

## Job
Company: {company}
Title: {title}
Location: {location}
Description:
{description}

## Scoring rubric (fit_score, integer 0-100)
- 90-100: role is squarely one of the candidate's target roles AND seniority/years fit
- 75-89: strong overlap in domain (NPI, materials, supply chain, hardware TPM); minor gaps
- 60-74: adjacent role or noticeable seniority / domain gap
- 0-59: different function, far more senior (e.g. Director, 10+ years), or wrong domain

## Return JSON with keys
fit_score (int), summary (one sentence), strengths (2-3 short strings),
gaps (1-2 specific requirements from the JD the candidate should address),
resume_bullets (3 bullets the candidate could adapt; ground them in the candidate's listed
competencies, use placeholders like [X%] instead of inventing numbers),
years_required (int minimum years of experience stated in the JD, or null).
"""


class Evaluator:
    def __init__(self, persona: dict[str, Any], llm: LLMClient | None = None, max_llm_calls: int = 40):
        self.persona = persona
        self.candidate_yaml = yaml.safe_dump(persona.get("candidate", {}), sort_keys=False, allow_unicode=True)
        self.experience_years = int((persona.get("candidate") or {}).get("experience_years") or 0)
        self.scorer = HeuristicScorer(persona.get("scoring"))
        tiers = persona.get("tiers") or {}
        self.apply_now = int(tiers.get("apply_now", 85))
        self.review = int(tiers.get("review", 70))
        self.min_heuristic = int((persona.get("llm") or {}).get("min_heuristic_score", 35))
        self.llm = llm
        self.max_llm_calls = max_llm_calls
        self.llm_calls = 0
        self.llm_failures = 0

    def tier_for(self, score: int) -> tuple[str, str]:
        if score >= self.apply_now:
            return "Tier 1: Apply Now", "APPLY_IMMEDIATELY"
        if score >= self.review:
            return "Tier 2: Review", "REVIEW_ON_WEEKEND"
        return "Skip", "SKIP"

    def heuristic(self, job: RawJobPosting) -> JobEvaluation:
        score, reasons = self.scorer.score(job)
        tier, action = self.tier_for(score)
        return JobEvaluation(
            fit_score=score,
            heuristic_score=score,
            tier=tier,
            recommended_action=action,
            summary="Keyword-based score (no LLM).",
            key_alignment_reasons=[r for r in reasons if not r.startswith("penalty")][:6],
            gap_analysis=[r for r in reasons if r.startswith("penalty")][:3],
        )

    def wants_llm(self, heuristic_score: int) -> bool:
        return bool(self.llm) and self.llm_calls < self.max_llm_calls and heuristic_score >= self.min_heuristic

    async def evaluate(self, job: RawJobPosting) -> JobEvaluation:
        base = self.heuristic(job)
        if not self.wants_llm(base.heuristic_score):
            return base
        self.llm_calls += 1
        prompt = PROMPT_TEMPLATE.format(
            candidate=self.candidate_yaml,
            company=job.company,
            title=job.title,
            location=job.location,
            description=(job.description or "(listing only - no description available)")[:6000],
        )
        try:
            verdict = LLMVerdict.model_validate(await self.llm.complete_json(SYSTEM_PROMPT, prompt))
        except Exception as exc:  # noqa: BLE001 - fall back to heuristic, never crash the run
            self.llm_failures += 1
            logger.warning(f"LLM evaluation failed for [{job.company}] {job.title}: {exc}")
            return base

        score = verdict.fit_score
        # Deterministic guard: a JD demanding far more experience can't be a top match.
        if verdict.years_required and self.experience_years and verdict.years_required >= self.experience_years + 4:
            score = min(score, self.review - 5)
        tier, action = self.tier_for(score)
        logger.info(f"LLM scored [{job.company}] {job.title}: {score} (heuristic {base.heuristic_score})")
        return JobEvaluation(
            fit_score=score,
            heuristic_score=base.heuristic_score,
            tier=tier,
            recommended_action=action,
            summary=verdict.summary,
            key_alignment_reasons=verdict.strengths[:3],
            gap_analysis=verdict.gaps[:2],
            tailored_resume_bullets=verdict.resume_bullets[:3],
            years_required=verdict.years_required,
            evaluator=self.llm.label,
        )
