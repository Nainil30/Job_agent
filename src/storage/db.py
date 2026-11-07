"""Ephemeral in-memory SQLite view over the NDJSON ledger (used by the MCP server)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.storage.ledger import Ledger

COLUMNS = (
    "hash_id", "job_id", "company", "title", "location", "url", "source", "posted_at",
    "fit_score", "heuristic_score", "tier", "recommended_action", "evaluator", "summary",
    "strengths", "gaps", "bullets", "status", "created_at",
)  # fmt: skip


class MemoryDB:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            f"CREATE TABLE jobs ({', '.join(c + (' PRIMARY KEY' if c == 'hash_id' else '') for c in COLUMNS)})"
        )
        self.sync()

    def sync(self) -> None:
        self.ledger.load()
        self.conn.execute("DELETE FROM jobs")
        rows = []
        for r in self.ledger.all():
            ev = r.evaluation
            rows.append((
                r.hash_id, r.raw.job_id, r.raw.company, r.raw.title, r.raw.location, r.raw.url, r.raw.source_ats,
                r.raw.posted_at, r.score, ev.heuristic_score if ev else 0, ev.tier if ev else "Unscored",
                ev.recommended_action if ev else "SKIP", ev.evaluator if ev else "", ev.summary if ev else "",
                json.dumps(ev.key_alignment_reasons if ev else []), json.dumps(ev.gap_analysis if ev else []),
                json.dumps(ev.tailored_resume_bullets if ev else []), r.status, r.created_at,
            ))  # fmt: skip
        self.conn.executemany(f"INSERT OR REPLACE INTO jobs VALUES ({', '.join('?' * len(COLUMNS))})", rows)
        self.conn.commit()

    def search(
        self, min_score: int = 70, company: str | None = None, text: str | None = None, limit: int = 25
    ) -> list[dict[str, Any]]:
        self.sync()
        sql = "SELECT * FROM jobs WHERE fit_score >= ? AND status != 'ARCHIVED'"
        params: list[Any] = [min_score]
        if company:
            sql += " AND LOWER(company) LIKE ?"
            params.append(f"%{company.lower()}%")
        if text:
            sql += " AND (LOWER(title) LIKE ? OR LOWER(location) LIKE ?)"
            params += [f"%{text.lower()}%"] * 2
        sql += " ORDER BY fit_score DESC, created_at DESC LIMIT ?"
        params.append(limit)
        out = []
        for row in self.conn.execute(sql, params):
            d = dict(row)
            for k in ("strengths", "gaps", "bullets"):
                d[k] = json.loads(d[k])
            out.append(d)
        return out

    # v1 name
    def query_high_fit_jobs(self, min_score: int = 75, company: str | None = None) -> list[dict[str, Any]]:
        return self.search(min_score=min_score, company=company, limit=200)
