"""FastMCP server exposing job scout intelligence to Cursor and Claude Desktop."""

import json
import os
import yaml
from fastmcp import FastMCP
from src.engine.evaluator import LLMEvaluator
from src.engine.models import RawJobPosting
from src.storage.db import MemoryDB
from src.storage.ledger import LedgerManager

mcp = FastMCP("JobScoutIntelligence")

ledger = LedgerManager()
db = MemoryDB(ledger)


def get_persona() -> str:
    persona_path = "config/persona.yaml"
    if os.path.exists(persona_path):
        with open(persona_path, "r", encoding="utf-8") as f:
            return yaml.dump(yaml.safe_load(f))
    return "Candidate with Senior NPI, Materials Program Management, and Hardware TPM experience."


@mcp.tool()
def get_weekend_review(min_score: int = 75, company: str = "") -> str:
    """Retrieves high-fit job opportunities evaluated by the automated agent."""
    jobs = db.query_high_fit_jobs(min_score=min_score, company=company if company else None)
    if not jobs:
        return f"No jobs found with score >= {min_score}."
    return json.dumps(jobs, indent=2)


@mcp.tool()
def evaluate_custom_jd(company: str, title: str, location: str, description: str) -> str:
    """Evaluates any custom job description directly against the candidate profile."""
    evaluator = LLMEvaluator(persona_content=get_persona())
    raw = RawJobPosting(
        job_id="custom_adhoc",
        company=company,
        title=title,
        location=location,
        url="https://adhoc-evaluation.internal",
        description=description,
        source_ats="custom_mcp",
    )
    result = evaluator.evaluate(raw)
    return result.model_dump_json(indent=2) if result else "Evaluation failed."


@mcp.tool()
def generate_tailored_bullets(company: str, title: str, job_id: str) -> str:
    """Generates tailored resume bullet points for a specific job in the database."""
    records = ledger.get_all_records()
    target = next((r for r in records if r.raw.company.lower() == company.lower() and r.raw.job_id == job_id), None)
    if not target or not target.evaluation:
        return f"Job ID {job_id} at {company} not found in evaluated database."

    bullets = "\n".join([f"- {b}" for b in target.evaluation.tailored_resume_bullets])
    return f"### Tailored Resume Bullets for {company} — {title}\n\n{bullets}"


if __name__ == "__main__":
    mcp.run()