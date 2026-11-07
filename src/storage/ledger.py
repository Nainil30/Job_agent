"""Canonical job store: Git-friendly NDJSON ledger + a small last-seen index.

* `data/jobs_ledger.ndjson` — one JSON record per line, sorted, rewritten atomically.
  A record changes only when its evaluation or status changes, so daily diffs stay small.
* `data/seen_index.json` — {hash_id: last_seen_date}. Lets the digest show only roles
  that are still live without churning every ledger line each run.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from loguru import logger

from src.engine.models import JobEvaluation, JobRecord, RawJobPosting
from src.utils import now_utc, stable_hash


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


class Ledger:
    def __init__(self, path: str | Path = "data/jobs_ledger.ndjson", seen_index_path: str | Path | None = None):
        self.path = Path(path)
        self.seen_path = Path(seen_index_path) if seen_index_path else self.path.with_name("seen_index.json")
        self.records: dict[str, JobRecord] = {}
        self.by_fingerprint: dict[str, str] = {}
        self.last_seen: dict[str, str] = {}
        self.load()

    # -- identity -------------------------------------------------------------------
    @staticmethod
    def compute_hash(company: str, job_id: str) -> str:
        return stable_hash(company, job_id)

    def find(self, job: RawJobPosting) -> JobRecord | None:
        h = self.compute_hash(job.company, job.job_id)
        if h in self.records:
            return self.records[h]
        fp_hash = self.by_fingerprint.get(job.fingerprint)
        return self.records.get(fp_hash) if fp_hash else None

    def is_seen(self, company: str, job_id: str) -> bool:
        return self.compute_hash(company, job_id) in self.records

    # -- io -------------------------------------------------------------------------
    def load(self) -> None:
        self.records.clear()
        self.by_fingerprint.clear()
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = JobRecord.model_validate_json(line)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"Skipping malformed ledger line {n}: {exc}")
                        continue
                    if not rec.fingerprint:
                        rec.fingerprint = rec.raw.fingerprint
                    self._index(rec)
        if self.seen_path.exists():
            try:
                self.last_seen = json.loads(self.seen_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.last_seen = {}

    def _index(self, rec: JobRecord) -> None:
        self.records[rec.hash_id] = rec
        self.by_fingerprint.setdefault(rec.fingerprint, rec.hash_id)

    def save(self) -> None:
        ordered = sorted(self.records.values(), key=lambda r: (r.created_at, r.hash_id))
        _atomic_write(self.path, "".join(r.model_dump_json(exclude_none=False) + "\n" for r in ordered))
        live = {h: d for h, d in sorted(self.last_seen.items()) if h in self.records}
        _atomic_write(self.seen_path, json.dumps(live, indent=0, sort_keys=True) + "\n")

    # -- mutation -------------------------------------------------------------------
    def add(self, job: RawJobPosting, evaluation: JobEvaluation | None = None) -> JobRecord:
        rec = JobRecord(
            hash_id=self.compute_hash(job.company, job.job_id),
            fingerprint=job.fingerprint,
            raw=job,
            evaluation=evaluation,
            status="EVALUATED" if evaluation else "NEW",
        )
        self._index(rec)
        self.touch(rec.hash_id)
        return rec

    # v1 name
    def append(self, raw_job: RawJobPosting, evaluation: JobEvaluation | None = None) -> JobRecord:
        rec = self.add(raw_job, evaluation)
        self.save()
        return rec

    def set_evaluation(self, hash_id: str, evaluation: JobEvaluation, raw: RawJobPosting | None = None) -> None:
        rec = self.records[hash_id]
        rec.evaluation = evaluation
        if raw is not None:
            rec.raw = raw
        if rec.status == "NEW":
            rec.status = "EVALUATED"

    def set_status(self, hash_prefix: str, status: str) -> JobRecord:
        matches = [r for h, r in self.records.items() if h.startswith(hash_prefix)]
        if len(matches) != 1:
            raise KeyError(f"{len(matches)} records match '{hash_prefix}' - use a longer prefix")
        matches[0].status = status  # type: ignore[assignment]
        return matches[0]

    def touch(self, hash_id: str) -> None:
        self.last_seen[hash_id] = now_utc().date().isoformat()

    # -- queries --------------------------------------------------------------------
    def all(self) -> list[JobRecord]:
        return list(self.records.values())

    def get_all_records(self) -> list[JobRecord]:  # v1 name
        return self.all()

    def open_records(self, within_days: int = 14) -> list[JobRecord]:
        """Records seen by a source within the window (i.e. probably still accepting applicants)."""
        cutoff = (now_utc() - timedelta(days=within_days)).date().isoformat()
        out = []
        for h, rec in self.records.items():
            seen = self.last_seen.get(h) or rec.created_at[:10]
            if seen >= cutoff and rec.status != "ARCHIVED":
                out.append(rec)
        return out

    def needs_scoring(self) -> list[JobRecord]:
        return [r for r in self.records.values() if r.evaluation is None]

    def llm_candidates(self, min_heuristic: int) -> list[JobRecord]:
        """Open, heuristic-only records worth an LLM pass, best first."""
        live = {r.hash_id for r in self.open_records()}
        cands = [
            r
            for r in self.records.values()
            if r.hash_id in live and r.evaluation and not r.llm_scored and r.evaluation.heuristic_score >= min_heuristic
        ]
        return sorted(cands, key=lambda r: r.evaluation.heuristic_score, reverse=True)


# v1 name
LedgerManager = Ledger
