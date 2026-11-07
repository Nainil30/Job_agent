"""Markdown digest: digests/YYYY-Www.md (weekly archive) + digests/latest.md."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.engine.models import JobRecord
from src.storage.health import SourceHealth
from src.utils import now_utc

STATUS_ICON = {"ok": "🟢", "partial": "🟡", "empty": "🟠", "error": "🔴", "skipped": "⚪"}


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "/").replace("\n", " ").strip()


class DigestReporter:
    def __init__(self, digests_dir: str | Path = "digests", apply_now: int = 85, review: int = 70):
        self.dir = Path(digests_dir)
        self.apply_now = apply_now
        self.review = review

    @staticmethod
    def week_name() -> str:
        year, week, _ = now_utc().isocalendar()
        return f"{year}-W{week:02d}"

    def _table(self, records: list[JobRecord]) -> list[str]:
        lines = [
            "| Score | Company | Title | Location | Posted | Why | Link |",
            "| :---: | :--- | :--- | :--- | :--- | :--- | :---: |",
        ]
        for r in records:
            ev = r.evaluation
            why = (
                ev.summary
                if ev and ev.evaluator != "heuristic"
                else ", ".join((ev.key_alignment_reasons if ev else [])[:3])
            )
            scorer = "🤖" if r.llm_scored else "🔣"
            lines.append(
                f"| **{r.score}** {scorer} | {_cell(r.raw.company)} | {_cell(r.raw.title)} | {_cell(r.raw.location)[:60]} "
                f"| {r.raw.posted_at or '—'} | {_cell(why)[:140]} | [Open]({r.raw.url}) |"
            )
        return lines

    def build(self, records: list[JobRecord], health: list[SourceHealth], new_hashes: set[str] | None = None) -> str:
        new_hashes = new_hashes or set()
        scored = sorted(
            (r for r in records if r.evaluation and r.status != "ARCHIVED"), key=lambda r: r.score, reverse=True
        )
        tier1 = [r for r in scored if r.score >= self.apply_now]
        tier2 = [r for r in scored if self.review <= r.score < self.apply_now]
        new_good = [r for r in scored if r.hash_id in new_hashes and r.score >= self.review]

        lines = [
            f"# Job Scout Digest - {self.week_name()}",
            "",
            f"_Updated {now_utc():%Y-%m-%d %H:%M} UTC · {len(records)} open roles tracked · "
            f"{len(tier1)} apply-now · {len(tier2)} to review · 🤖 = LLM-scored, 🔣 = keyword-scored_",
            "",
        ]
        if new_good:
            lines += [f"## 🆕 New this run ({len(new_good)})", "", *self._table(new_good), ""]
        lines += [f"## 🚀 Tier 1 - Apply now (score ≥ {self.apply_now})", ""]
        lines += self._table(tier1) if tier1 else ["_Nothing at this level right now._"]
        lines += ["", f"## 📋 Tier 2 - Review (score {self.review}-{self.apply_now - 1})", ""]
        lines += self._table(tier2[:60]) if tier2 else ["_Nothing at this level right now._"]

        if health:
            lines += [
                "",
                "## 🩺 Source health",
                "",
                "| Source | Tier | Status | Listings | Kept | Note |",
                "| :--- | :--- | :---: | ---: | ---: | :--- |",
            ]
            for h in health:
                note = _cell(h.errors[0])[:90] if h.errors else ""
                if h.consecutive_failures >= 3:
                    note = f"failing {h.consecutive_failures} runs in a row - check config. {note}"
                lines.append(
                    f"| {h.name} | {h.tier} | {STATUS_ICON.get(h.status, '')} {h.status} | {h.fetched} | {h.kept} | {note} |"
                )
        return "\n".join(lines) + "\n"

    def write(self, records: list[JobRecord], health: list[SourceHealth], new_hashes: set[str] | None = None) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        content = self.build(records, health, new_hashes)
        weekly = self.dir / f"{self.week_name()}.md"
        weekly.write_text(content, encoding="utf-8")
        (self.dir / "latest.md").write_text(content, encoding="utf-8")
        logger.info(f"Digest written: {weekly}")
        return weekly
