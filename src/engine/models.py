"""Data contracts and validation schemas for jobs and evaluations."""

from datetime import datetime, timezone
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class RawJobPosting(BaseModel):
    """Normalized representation of a job posting fetched from any ATS adapter."""
    job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    posted_date: Optional[str] = None
    source_ats: str


class JobEvaluation(BaseModel):
    """Structured LLM evaluation output matching the candidate persona."""
    job_id: str
    company: str
    title: str
    location: str
    apply_url: str
    fit_score: int = Field(..., ge=0, le=100, description="Fit score from 0 to 100 based on NPI/SC/TPM domain fit")
    tier: Literal["Tier 1: Primary", "Tier 2: Target", "Skip"]
    key_alignment_reasons: List[str] = Field(..., max_length=3, description="2-3 bullet points detailing exact domain alignment")
    gap_analysis: List[str] = Field(..., max_length=2, description="Specific tooling or qualifications to emphasize/tailor")
    recommended_action: Literal["APPLY_IMMEDIATELY", "REVIEW_ON_WEEKEND", "SKIP"]
    tailored_resume_bullets: List[str] = Field(..., max_length=3, description="3 tailored impact bullets for candidate's resume")
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobRecord(BaseModel):
    """Complete record stored in the canonical NDJSON ledger."""
    hash_id: str
    raw: RawJobPosting
    evaluation: Optional[JobEvaluation] = None
    status: Literal["NEW", "EVALUATED", "APPLIED", "ARCHIVED"] = "NEW"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())