"""Unified entry point for running the autonomous job hunter pipeline."""
import sys
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Rest of your imports follow below:
import argparse
import asyncio
import os
import yaml
from loguru import logger

from src.adapters.amazon import AmazonAdapter
from src.adapters.apple import AppleJobsAdapter
from src.adapters.browser_fallback import BrowserFallbackAdapter
from src.adapters.google import GoogleCareersAdapter
from src.adapters.workday import WorkdayAdapter
from src.engine.evaluator import LLMEvaluator
from src.engine.filter import DeterministicFilter
from src.engine.models import RawJobPosting
from src.storage.ledger import LedgerManager
from src.storage.reporter import DigestReporter


def load_yaml(filepath: str) -> dict:
    if not os.path.exists(filepath):
        logger.error(f"Config file not found: {filepath}")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_pipeline(mode: str = "api") -> None:
    logger.info(f"Starting Job Scout Pipeline in mode: [{mode.upper()}]")

    companies_cfg = load_yaml("config/companies.yaml")
    persona_cfg = load_yaml("config/persona.yaml")
    persona_str = yaml.dump(persona_cfg)

    ledger = LedgerManager()
    pre_filter = DeterministicFilter()
    reporter = DigestReporter()

    # 1. Initialize Adapters
    adapters = []
    for comp in companies_cfg.get("companies", []):
        ats_type = comp.get("ats_type")
        if ats_type == "workday":
            adapters.append(WorkdayAdapter(comp))
        elif ats_type == "amazon":
            adapters.append(AmazonAdapter(comp))
        elif ats_type == "google":
            adapters.append(GoogleCareersAdapter(comp))
        elif ats_type == "apple":
            adapters.append(AppleJobsAdapter(comp))
        elif ats_type == "browser" and mode == "all":
            adapters.append(BrowserFallbackAdapter(comp))

    # 2. Ingest Jobs Across All Adapters
    all_raw_jobs: list[RawJobPosting] = []
    for adapter in adapters:
        jobs = await adapter.fetch_jobs()
        all_raw_jobs.extend(jobs)

    logger.info(f"Ingestion Complete: Fetched {len(all_raw_jobs)} total job postings.")

    # 3. Deduplication (Skip jobs already in ledger)
    unseen_jobs = [j for j in all_raw_jobs if not ledger.is_seen(j.company, j.job_id)]
    logger.info(f"Deduplication Complete: {len(unseen_jobs)} new postings to evaluate.")

    if not unseen_jobs:
        logger.info("No new job postings found. Updating digest with existing records.")
        reporter.generate_weekly_digest(ledger.get_all_records())
        return

    # 4. Pass 1 Deterministic Pre-Filtering
    qualified_jobs = pre_filter.filter_jobs(unseen_jobs)
    logger.info(f"Pass 1 Filter: {len(qualified_jobs)} passed to LLM-as-a-Judge.")

    # 5. Pass 2 LLM Evaluation (Gemini 2.0 Flash)
    evaluator = None
    if qualified_jobs:
        try:
            evaluator = LLMEvaluator(persona_content=persona_str)
        except Exception as exc:
            logger.error(f"Cannot initialize Gemini Evaluator: {exc}. Storing as raw records.")

    for job in qualified_jobs:
        evaluation = evaluator.evaluate(job) if evaluator else None
        ledger.append(raw_job=job, evaluation=evaluation)

    # 6. Generate Weekly Markdown Summary
    reporter.generate_weekly_digest(ledger.get_all_records())
    logger.info("Pipeline execution successfully completed.")


def main():
    parser = argparse.ArgumentParser(description="Autonomous NPI & Hardware TPM Job Hunter")
    parser.add_argument("--mode", choices=["api", "all", "report"], default="api", help="Execution mode")
    args = parser.parse_args()

    asyncio.run(run_pipeline(mode=args.mode))


if __name__ == "__main__":
    main()