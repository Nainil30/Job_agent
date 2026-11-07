"""MCP server: query the job database conversationally from Claude Desktop / Cursor.

pip install -r requirements-mcp.txt
python -m src.mcp.server
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastmcp import FastMCP  # noqa: E402

from src.config import Settings  # noqa: E402
from src.engine.evaluator import Evaluator  # noqa: E402
from src.engine.llm import get_llm  # noqa: E402
from src.engine.models import RawJobPosting  # noqa: E402
from src.storage.db import MemoryDB  # noqa: E402
from src.storage.health import load_health  # noqa: E402
from src.storage.ledger import Ledger  # noqa: E402

settings = Settings()
ledger = Ledger(settings.ledger_path, settings.seen_index_path)
db = MemoryDB(ledger)
mcp = FastMCP("JobScout")


@mcp.tool()
def search_jobs(min_score: int = 70, company: str = "", text: str = "", limit: int = 20) -> str:
    """Ranked roles from the job database. Filter by minimum score, company, or title/location text."""
    rows = db.search(min_score=min_score, company=company or None, text=text or None, limit=limit)
    if not rows:
        return f"No roles with score >= {min_score} match."
    keep = (
        "hash_id",
        "company",
        "title",
        "location",
        "fit_score",
        "tier",
        "evaluator",
        "summary",
        "posted_at",
        "status",
        "url",
    )
    return json.dumps([{k: r[k] for k in keep} | {"hash_id": r["hash_id"][:10]} for r in rows], indent=2)


@mcp.tool()
def job_details(job_id_prefix: str) -> str:
    """Full record for one role (strengths, gaps, tailored resume bullets, description)."""
    matches = [r for r in ledger.all() if r.hash_id.startswith(job_id_prefix) or r.raw.job_id == job_id_prefix]
    if not matches:
        return "Not found."
    return matches[0].model_dump_json(indent=2)


@mcp.tool()
async def evaluate_job_description(company: str, title: str, location: str, description: str) -> str:
    """Score any pasted job description against the candidate profile."""
    evaluator = Evaluator(settings.persona(), llm=get_llm(settings.llm_provider, settings.llm_rpm), max_llm_calls=1)
    job = RawJobPosting(
        job_id="adhoc",
        company=company,
        title=title,
        location=location,
        url="",
        description=description,
        source_ats="mcp",
    )
    return (await evaluator.evaluate(job)).model_dump_json(indent=2)


@mcp.tool()
def source_health() -> str:
    """Which job sources worked on the last run, and which are failing."""
    return json.dumps([h.__dict__ for h in load_health(settings.health_path)], indent=2)


@mcp.tool()
def mark_status(job_id_prefix: str, status: str) -> str:
    """Track a role as APPLIED or ARCHIVED (the agent never applies on your behalf)."""
    rec = ledger.set_status(job_id_prefix, status.upper())
    ledger.save()
    return f"{rec.raw.company} - {rec.raw.title} -> {rec.status}"


if __name__ == "__main__":
    mcp.run()
