"""Data contracts shared across adapters, engine, and storage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.utils import fingerprint, iso_now

Tier = Literal["Tier 1: Apply Now", "Tier 2: Review", "Skip"]
Action = Literal["APPLY_IMMEDIATELY", "REVIEW_ON_WEEKEND", "SKIP"]


class RawJobPosting(BaseModel):
    """Normalized job posting produced by any adapter."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    company: str
    title: str
    location: str = ""
    url: str
    description: str = ""
    posted_date: str | None = None  # raw value from the source
    posted_at: str | None = None  # ISO date when parseable
    source_ats: str
    company_tier: str = "Secondary"
    department: str | None = None

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.company, self.title, self.location)


class LLMVerdict(BaseModel):
    """What the LLM is asked for. Tier and action are derived in code, not by the model."""

    model_config = ConfigDict(extra="ignore")

    fit_score: int = Field(..., ge=0, le=100)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    resume_bullets: list[str] = Field(default_factory=list)
    years_required: int | None = None


class JobEvaluation(BaseModel):
    """Final evaluation stored with each job."""

    model_config = ConfigDict(extra="ignore")

    fit_score: int = Field(..., ge=0, le=100)
    heuristic_score: int = Field(0, ge=0, le=100)
    tier: Tier
    recommended_action: Action
    summary: str = ""
    key_alignment_reasons: list[str] = Field(default_factory=list)
    gap_analysis: list[str] = Field(default_factory=list)
    tailored_resume_bullets: list[str] = Field(default_factory=list)
    years_required: int | None = None
    evaluator: str = "heuristic"
    evaluated_at: str = Field(default_factory=iso_now)


class JobRecord(BaseModel):
    """One line of the canonical NDJSON ledger."""

    model_config = ConfigDict(extra="ignore")

    hash_id: str
    fingerprint: str = ""
    raw: RawJobPosting
    evaluation: JobEvaluation | None = None
    status: Literal["NEW", "EVALUATED", "APPLIED", "ARCHIVED"] = "NEW"
    created_at: str = Field(default_factory=iso_now)

    @property
    def score(self) -> int:
        return self.evaluation.fit_score if self.evaluation else 0

    @property
    def llm_scored(self) -> bool:
        return bool(self.evaluation and self.evaluation.evaluator != "heuristic")
