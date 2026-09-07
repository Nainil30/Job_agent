"""Canonical NDJSON append-only ledger for storing job postings and evaluations."""

import hashlib
import json
import os
from typing import Dict, List, Optional
from loguru import logger
from src.engine.models import JobRecord, RawJobPosting, JobEvaluation


class LedgerManager:
    """Manages the Git-friendly, append-only NDJSON ledger with hash-based deduplication."""

    def __init__(self, ledger_path: str = "data/jobs_ledger.ndjson"):
        self.ledger_path = ledger_path
        self._ensure_file_exists()
        self.seen_hashes = self._load_seen_hashes()

    def _ensure_file_exists(self) -> None:
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        if not os.path.exists(self.ledger_path):
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                pass

    @staticmethod
    def compute_hash(company: str, job_id: str) -> str:
        """Generates a stable SHA-256 identifier for a job."""
        normalized = f"{company.strip().lower()}_{job_id.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load_seen_hashes(self) -> set:
        seen = set()
        if not os.path.exists(self.ledger_path):
            return seen

        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if "hash_id" in record:
                            seen.add(record["hash_id"])
                    except json.JSONDecodeError:
                        continue
        return seen

    def is_seen(self, company: str, job_id: str) -> bool:
        """Checks if a job has already been ingested and processed."""
        h = self.compute_hash(company, job_id)
        return h in self.seen_hashes

    def append(self, raw_job: RawJobPosting, evaluation: Optional[JobEvaluation] = None) -> JobRecord:
        """Appends a new job record to the NDJSON ledger."""
        hash_id = self.compute_hash(raw_job.company, raw_job.job_id)
        record = JobRecord(
            hash_id=hash_id,
            raw=raw_job,
            evaluation=evaluation,
            status="EVALUATED" if evaluation else "NEW",
        )
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

        self.seen_hashes.add(hash_id)
        logger.debug(f"Recorded job in ledger: [{raw_job.company}] {raw_job.title} ({hash_id[:8]})")
        return record

    def get_all_records(self) -> List[JobRecord]:
        """Loads all job records from the ledger."""
        records = []
        if not os.path.exists(self.ledger_path):
            return records

        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(JobRecord.model_validate_json(line))
                    except Exception as exc:
                        logger.warning(f"Skipping malformed ledger line: {exc}")
        return records