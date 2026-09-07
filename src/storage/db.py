"""Ephemeral in-memory SQLite indexing layer built on top of the NDJSON ledger."""

import json
import sqlite3
from typing import Any, Dict, List, Optional
from src.storage.ledger import LedgerManager


class MemoryDB:
    """In-memory SQLite query layer for FastMCP and instant local SQL analytics."""

    def __init__(self, ledger_manager: LedgerManager):
        self.ledger = ledger_manager
        self.conn = sqlite3.connect(":memory:")
        self._init_schema()
        self.sync_from_ledger()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                hash_id TEXT PRIMARY KEY,
                job_id TEXT,
                company TEXT,
                title TEXT,
                location TEXT,
                url TEXT,
                fit_score INTEGER,
                tier TEXT,
                recommended_action TEXT,
                key_alignment TEXT,
                gap_analysis TEXT,
                tailored_bullets TEXT,
                evaluated_at TEXT,
                status TEXT
            )
        """)
        self.conn.commit()

    def sync_from_ledger(self) -> None:
        """Loads all records from the NDJSON ledger into the in-memory SQLite table."""
        records = self.ledger.get_all_records()
        cur = self.conn.cursor()
        cur.execute("DELETE FROM jobs")

        for r in records:
            eval_data = r.evaluation
            cur.execute("""
                INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.hash_id,
                r.raw.job_id,
                r.raw.company,
                r.raw.title,
                r.raw.location,
                r.raw.url,
                eval_data.fit_score if eval_data else 0,
                eval_data.tier if eval_data else "Unscored",
                eval_data.recommended_action if eval_data else "SKIP",
                json.dumps(eval_data.key_alignment_reasons) if eval_data else "[]",
                json.dumps(eval_data.gap_analysis) if eval_data else "[]",
                json.dumps(eval_data.tailored_resume_bullets) if eval_data else "[]",
                eval_data.evaluated_at if eval_data else "",
                r.status,
            ))
        self.conn.commit()

    def query_high_fit_jobs(self, min_score: int = 75, company: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries evaluated jobs matching score and company criteria."""
        self.sync_from_ledger()
        cur = self.conn.cursor()
        query = "SELECT company, title, location, fit_score, tier, recommended_action, gap_analysis, url FROM jobs WHERE fit_score >= ?"
        params: List[Any] = [min_score]

        if company:
            query += " AND LOWER(company) = LOWER(?)"
            params.append(company)

        query += " ORDER BY fit_score DESC"
        cur.execute(query, params)
        rows = cur.fetchall()

        return [
            {
                "company": r[0],
                "title": r[1],
                "location": r[2],
                "fit_score": r[3],
                "tier": r[4],
                "recommended_action": r[5],
                "gap_analysis": json.loads(r[6]),
                "url": r[7],
            }
            for r in rows
        ]