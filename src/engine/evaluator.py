"""Pass 2: LLM-as-a-Judge evaluation engine using Gemini 2.0 Flash."""

import os
from dotenv import load_dotenv

# Force load .env from project root
load_dotenv()

from typing import Optional
from google import genai
from google.genai import types
from loguru import logger
from src.engine.models import JobEvaluation, RawJobPosting


class LLMEvaluator:
    """Evaluates job fit against candidate persona using structured output schemas."""

    def __init__(self, persona_content: str, api_key: Optional[str] = None):
        self.persona = persona_content
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY environment variable is not set. Check your .env file.")
        self.client = genai.Client(api_key=key)

    def evaluate(self, job: RawJobPosting) -> Optional[JobEvaluation]:
        """Runs evaluation using Gemini 2.0 Flash with Pydantic JSON schema constraints."""
        prompt = f"""
You are an expert technical recruiter and supply chain executive.
Evaluate the following job posting against the target candidate persona.

--- CANDIDATE PERSONA ---
{self.persona}

--- JOB POSTING DETAILS ---
Company: {job.company}
Title: {job.title}
Location: {job.location}
URL: {job.url}
Description:
{job.description[:4000]}

--- EVALUATION INSTRUCTIONS ---
1. Score fit strictly from 0 to 100 based on alignment with NPI, Hardware MPM, TPM, or Supply Chain Analytics.
2. If fit_score >= 88: tier = 'Tier 1: Primary', recommended_action = 'APPLY_IMMEDIATELY'
3. If 75 <= fit_score < 88: tier = 'Tier 2: Target', recommended_action = 'REVIEW_ON_WEEKEND'
4. If fit_score < 75: tier = 'Skip', recommended_action = 'SKIP'
5. Provide 2-3 concise strengths, 1-2 specific technical gaps mentioned in the JD, and 3 tailored resume bullet points.
"""
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JobEvaluation,
                    temperature=0.1,
                ),
            )
            evaluation = JobEvaluation.model_validate_json(response.text)
            logger.info(f"Evaluated [{job.company}] {job.title} -> Score: {evaluation.fit_score} ({evaluation.tier})")
            return evaluation
        except Exception as exc:
            logger.error(f"Failed to evaluate job {job.job_id} at {job.company}: {exc}")
            return None