"""Ledger persistence, reporting, and an end-to-end pipeline run with fake sources."""

import json

from src import pipeline
from src.adapters.base import BaseAdapter
from src.storage.ledger import Ledger
from tests.conftest import make_job


def test_ledger_roundtrip_and_fingerprint_dedupe(tmp_path):
    ledger = Ledger(tmp_path / "l.ndjson")
    rec = ledger.add(make_job(company="Applied Materials", title="Supply Chain PM (B3)", job_id="WD1"))
    ledger.save()
    reloaded = Ledger(tmp_path / "l.ndjson")
    assert (
        reloaded.find(make_job(company="Applied Materials", title="Supply Chain PM (B3)", job_id="WD1")).hash_id
        == rec.hash_id
    )
    # Same role from LinkedIn (different id, company suffix) is recognised as a duplicate
    assert reloaded.find(
        make_job(
            company="Applied Materials, Inc.", title="Supply Chain PM", job_id="li-999", source_ats="jobspy:linkedin"
        )
    )
    assert json.loads((tmp_path / "seen_index.json").read_text())[rec.hash_id]


def test_ledger_loads_v1_records(tmp_path):
    v1 = {"hash_id": "abc", "raw": {"job_id": "JR1", "company": "Nvidia", "title": "TPM", "location": "3 Locations", "url": "u",
          "description": "d", "posted_date": "Posted 2 Days Ago", "source_ats": "workday"}, "evaluation": None, "status": "NEW",
          "created_at": "2026-09-07T16:01:31.981078+00:00"}  # fmt: skip
    path = tmp_path / "l.ndjson"
    path.write_text(json.dumps(v1) + "\n{not json\n", encoding="utf-8")
    ledger = Ledger(path)
    assert len(ledger.all()) == 1 and ledger.all()[0].fingerprint
    assert ledger.needs_scoring()


def test_set_status_by_prefix(tmp_path):
    ledger = Ledger(tmp_path / "l.ndjson")
    rec = ledger.add(make_job())
    assert ledger.set_status(rec.hash_id[:8], "APPLIED").status == "APPLIED"


class FakeAdapter(BaseAdapter):
    source = "fake"

    def __init__(self, name, jobs, tier="api", fail=False):
        super().__init__({"name": name})
        self.ingestion_tier = tier
        self._jobs, self._fail = jobs, fail

    async def fetch_jobs(self):
        if self._fail:
            self.record_error("query", "HTTP 404")
            return []
        return self._jobs

    async def enrich(self, job):
        return job.model_copy(
            update={"description": "Own EVT/DVT/PVT, clear-to-build, BOM risk with CM partners. Supplier ramp."}
        )


async def test_pipeline_end_to_end(tmp_settings, monkeypatch):
    direct = make_job(company="Nvidia", job_id="JR1", title="NPI Program Manager", location="Austin, TX")
    dup_from_linkedin = make_job(
        company="Nvidia",
        job_id="li-1",
        title="NPI Program Manager",
        location="Austin, TX, USA",
        source_ats="jobspy:linkedin",
    )
    noise = make_job(company="Nvidia", job_id="JR2", title="Barista")
    adapters = [
        FakeAdapter("Nvidia", [direct, noise]),
        FakeAdapter("JobSpy npi", [dup_from_linkedin], tier="aggregator"),
        FakeAdapter("Broken", [], fail=True),
    ]
    monkeypatch.setattr(pipeline, "build_adapters", lambda *a, **k: adapters)

    summary = await pipeline.run_pipeline(tmp_settings, send_notifications=False)

    assert summary.fetched == 3 and summary.unique == 2 and summary.kept == 1
    stored = Ledger(tmp_settings.ledger_path).all()
    assert len(stored) == 1 and stored[0].raw.source_ats == "workday"  # direct ATS beat the aggregator copy
    assert (
        stored[0].evaluation
        and stored[0].evaluation.heuristic_score > 50
        and "clear-to-build" in stored[0].raw.description
    )
    health = {h["name"]: h for h in json.loads(tmp_settings.health_path.read_text())}
    assert health["Broken (fake)"]["status"] == "error" and health["Nvidia (fake)"]["kept"] == 1
    assert (tmp_settings.digests_dir / "latest.md").exists()
    html = (tmp_settings.site_dir / "index.html").read_text(encoding="utf-8")
    assert "NPI Program Manager" in html and "/*__DATA__*/" not in html

    # Second run: nothing new, existing role just refreshed
    summary2 = await pipeline.run_pipeline(tmp_settings, send_notifications=False)
    assert summary2.kept == 0 and not summary2.new_records and len(Ledger(tmp_settings.ledger_path).all()) == 1
    assert json.loads(tmp_settings.health_path.read_text())[0]["consecutive_failures"] in (0, 2)


async def test_doctor_dry_run_writes_nothing(tmp_settings, monkeypatch):
    monkeypatch.setattr(pipeline, "build_adapters", lambda *a, **k: [FakeAdapter("Nvidia", [make_job()])])
    summary = await pipeline.run_pipeline(tmp_settings, dry_run=True)
    assert summary.kept == 1 and not tmp_settings.ledger_path.exists()
