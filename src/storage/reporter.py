"""Generates human-readable weekly Markdown digest summaries for weekend review."""

from datetime import datetime, timezone
import os
from typing import List
from loguru import logger
from src.engine.models import JobRecord


class DigestReporter:
    """Generates organized weekly Markdown digests in digests/YYYY-WW.md."""

    def __init__(self, digests_dir: str = "digests"):
        self.digests_dir = digests_dir
        os.makedirs(self.digests_dir, exist_ok=True)

    @staticmethod
    def get_current_week_file() -> str:
        now = datetime.now(timezone.utc)
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}.md"

    def generate_weekly_digest(self, all_records: List[JobRecord]) -> str:
        filename = self.get_current_week_file()
        filepath = os.path.join(self.digests_dir, filename)

        # Filter only evaluated jobs with valid scores
        evaluated = [r for r in all_records if r.evaluation and r.evaluation.fit_score >= 70]
        evaluated.sort(key=lambda x: x.evaluation.fit_score if x.evaluation else 0, reverse=True)

        tier_1 = [r for r in evaluated if r.evaluation and r.evaluation.fit_score >= 88]
        tier_2 = [r for r in evaluated if r.evaluation and 75 <= r.evaluation.fit_score < 88]

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# 🎯 Autonomous Job Hunt Digest — {filename.replace('.md', '')}",
            f"\n*Last updated: {now_str} | Total Scored Opportunities: {len(evaluated)}*\n",
            "## 🚀 Tier 1: Priority Matches (Score ≥ 88)\n",
        ]

        if tier_1:
            lines.append("| Company | Score | Title | Location | Gaps to Address | Action |")
            lines.append("| :--- | :---: | :--- | :--- | :--- | :---: |")
            for r in tier_1:
                ev = r.evaluation
                gaps = "<br>• ".join(ev.gap_analysis) if ev.gap_analysis else "None identified"
                lines.append(
                    f"| **{ev.company}** | **{ev.fit_score}** | {ev.title} | {ev.location} | • {gaps} | [Apply]({ev.apply_url}) |"
                )
        else:
            lines.append("*No Tier 1 roles matched this week yet.*\n")

        lines.append("\n## 📋 Tier 2: Strong Target Matches (75 ≤ Score < 88)\n")
        if tier_2:
            lines.append("| Company | Score | Title | Location | Gaps to Address | Action |")
            lines.append("| :--- | :---: | :--- | :--- | :--- | :---: |")
            for r in tier_2:
                ev = r.evaluation
                gaps = "<br>• ".join(ev.gap_analysis) if ev.gap_analysis else "None identified"
                lines.append(
                    f"| **{ev.company}** | {ev.fit_score} | {ev.title} | {ev.location} | • {gaps} | [Apply]({ev.apply_url}) |"
                )
        else:
            lines.append("*No Tier 2 roles matched this week yet.*\n")

        content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Generated weekly digest summary at {filepath}")
        return filepath