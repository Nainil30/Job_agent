"""End-to-end run: ingest -> de-duplicate -> filter -> enrich -> score -> store -> report -> notify."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import Counter
from dataclasses import dataclass, field

from loguru import logger

from src import notify
from src.adapters.base import BaseAdapter
from src.adapters.registry import ALL_TIERS, build_adapters
from src.config import Settings
from src.engine.evaluator import Evaluator
from src.engine.filter import JobFilter
from src.engine.llm import get_llm
from src.engine.models import JobRecord, RawJobPosting
from src.storage.dashboard import write_dashboard
from src.storage.health import SourceHealth, load_health, save_health
from src.storage.ledger import Ledger
from src.storage.reporter import DigestReporter

# When the same role is found by several sources, keep the most direct one.
TIER_PRIORITY = {"api": 0, "browser": 1, "aggregator": 2}
MAX_CONCURRENT_SOURCES = 6


@dataclass
class RunSummary:
    fetched: int = 0
    unique: int = 0
    new: int = 0
    kept: int = 0
    llm_calls: int = 0
    llm_failures: int = 0
    filter_reasons: Counter = field(default_factory=Counter)
    health: list[SourceHealth] = field(default_factory=list)
    new_records: list[JobRecord] = field(default_factory=list)
    notified: list[str] = field(default_factory=list)


async def run_source(
    adapter: BaseAdapter, sem: asyncio.Semaphore
) -> tuple[BaseAdapter, list[RawJobPosting], SourceHealth]:
    health = SourceHealth(name=adapter.label, source=adapter.source, tier=adapter.ingestion_tier)
    start = time.perf_counter()
    jobs: list[RawJobPosting] = []
    # Aggregator searches serialise themselves (rate limits), so they don't take a slot here.
    gate = sem if adapter.ingestion_tier != "aggregator" else contextlib.nullcontext()
    async with gate:
        try:
            jobs = await adapter.run()
            if adapter.errors:
                health.status = "partial"
            elif not jobs:
                health.status = "empty"
        except RuntimeError as exc:
            msg = str(exc)
            health.status = "skipped" if "not installed" in msg else "error"
            adapter.errors.append(msg)
        except Exception as exc:  # noqa: BLE001 - one broken source must never stop the run
            health.status = "error"
            adapter.errors.append(f"{type(exc).__name__}: {exc}")
    health.fetched = len(jobs)
    health.errors = [e[:300] for e in adapter.errors[:5]]
    health.duration_s = round(time.perf_counter() - start, 2)
    level = "INFO" if health.status in ("ok", "empty") else "WARNING"
    logger.log(level, f"{adapter.label:<45} {health.status:<8} {len(jobs):>4} listings  {health.duration_s:>6.1f}s")
    return adapter, jobs, health


async def ingest(adapters: list[BaseAdapter]) -> list[tuple[BaseAdapter, list[RawJobPosting], SourceHealth]]:
    sem = asyncio.Semaphore(MAX_CONCURRENT_SOURCES)
    return list(await asyncio.gather(*(run_source(a, sem) for a in adapters)))


def dedupe(results) -> list[tuple[BaseAdapter, RawJobPosting]]:
    """Collapse the same role across sources (fingerprint), preferring direct ATS listings."""
    best: dict[str, tuple[int, BaseAdapter, RawJobPosting]] = {}
    for adapter, jobs, _ in results:
        prio = TIER_PRIORITY.get(adapter.ingestion_tier, 9)
        for job in jobs:
            fp = job.fingerprint
            if fp not in best or prio < best[fp][0]:
                best[fp] = (prio, adapter, job)
    return [(a, j) for _, a, j in best.values()]


async def run_pipeline(
    settings: Settings | None = None,
    tiers: tuple[str, ...] | list[str] = ALL_TIERS,
    only: list[str] | None = None,
    use_llm: bool = True,
    send_notifications: bool = True,
    dry_run: bool = False,
) -> RunSummary:
    settings = settings or Settings()
    persona = settings.persona()
    summary = RunSummary()
    job_filter = JobFilter(persona.get("search"))
    ledger = Ledger(settings.ledger_path, settings.seen_index_path)

    adapters = build_adapters(settings.companies(), settings.aggregators(), tiers=tiers, only=only)
    logger.info(f"Running {len(adapters)} sources (tiers: {', '.join(tiers)})")
    results = await ingest(adapters)
    summary.health = [h for _, _, h in results]
    summary.fetched = sum(len(j) for _, j, _ in results)

    candidates = dedupe(results)
    summary.unique = len(candidates)

    # Split into already-known (just refresh last-seen) and new
    fresh: list[tuple[BaseAdapter, RawJobPosting]] = []
    for adapter, job in candidates:
        existing = ledger.find(job)
        if existing:
            ledger.touch(existing.hash_id)
        else:
            fresh.append((adapter, job))
    summary.new = len(fresh)

    # Pass 1: free deterministic filter
    kept: list[tuple[BaseAdapter, RawJobPosting]] = []
    kept_per_source: Counter = Counter()
    for adapter, job in fresh:
        ok, reason = job_filter.check(job)
        summary.filter_reasons[reason] += 1
        if ok:
            kept.append((adapter, job))
            kept_per_source[adapter.label] += 1
    summary.kept = len(kept)
    for h in summary.health:
        h.kept = kept_per_source.get(h.name, 0)
    logger.info(
        f"Fetched {summary.fetched} -> {summary.unique} unique -> {summary.new} new -> {summary.kept} pass filter"
    )

    if dry_run:
        return summary

    # Enrich survivors with full descriptions (grouped per source)
    by_adapter: dict[int, tuple[BaseAdapter, list[RawJobPosting]]] = {}
    for adapter, job in kept:
        by_adapter.setdefault(id(adapter), (adapter, []))[1].append(job)
    enriched: list[RawJobPosting] = []
    for adapter, jobs in by_adapter.values():
        enriched.extend(await adapter.enrich_many(jobs))

    # Pass 2: score. Heuristic for all; LLM budget goes to the most promising first.
    llm = get_llm(settings.llm_provider, settings.llm_rpm) if use_llm else None
    evaluator = Evaluator(persona, llm=llm, max_llm_calls=settings.llm_max_calls)
    enriched.sort(key=lambda j: evaluator.heuristic(j).heuristic_score, reverse=True)
    for job in enriched:
        evaluation = await evaluator.evaluate(job)
        summary.new_records.append(ledger.add(job, evaluation))

    # Backfill: score legacy / unscored records, then spend leftover LLM budget on open ones
    for rec in ledger.needs_scoring():
        ledger.set_evaluation(rec.hash_id, evaluator.heuristic(rec.raw))
    if llm:
        for rec in ledger.llm_candidates(evaluator.min_heuristic):
            if not evaluator.wants_llm(rec.evaluation.heuristic_score):
                break
            evaluation = await evaluator.evaluate(rec.raw)
            if evaluation.evaluator != "heuristic":
                ledger.set_evaluation(rec.hash_id, evaluation)
    summary.llm_calls, summary.llm_failures = evaluator.llm_calls, evaluator.llm_failures

    ledger.save()
    configured = {a.label for a in build_adapters(settings.companies(), settings.aggregators())}
    summary.health = save_health(summary.health, settings.health_path, configured=configured)
    publish(settings, ledger, summary.health, {r.hash_id for r in summary.new_records}, evaluator)

    if send_notifications:
        hot = sorted(
            (r for r in summary.new_records if r.score >= settings.notify_min_score),
            key=lambda r: r.score,
            reverse=True,
        )
        summary.notified = notify.send(hot)

    logger.success(
        f"Done: {len(summary.new_records)} new roles stored, {summary.llm_calls} LLM calls "
        f"({summary.llm_failures} failed), {sum(h.status == 'error' for h in summary.health)} sources erroring"
    )
    return summary


def publish(
    settings: Settings, ledger: Ledger, health, new_hashes: set[str], evaluator: Evaluator | None = None
) -> None:
    persona = settings.persona()
    tiers = persona.get("tiers") or {}
    reporter = DigestReporter(settings.digests_dir, int(tiers.get("apply_now", 85)), int(tiers.get("review", 70)))
    open_records = ledger.open_records()
    reporter.write(open_records, health, new_hashes)
    write_dashboard(settings.site_dir, open_records, health, ledger.last_seen)


def report_only(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    ledger = Ledger(settings.ledger_path, settings.seen_index_path)
    evaluator = Evaluator(settings.persona())
    changed = False
    for rec in ledger.needs_scoring():
        ledger.set_evaluation(rec.hash_id, evaluator.heuristic(rec.raw))
        changed = True
    if changed:
        ledger.save()
    publish(settings, ledger, load_health(settings.health_path), set())
