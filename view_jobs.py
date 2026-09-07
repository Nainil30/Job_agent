"""Utility script to convert NDJSON into a human-readable text file and terminal view."""

import json
from pathlib import Path

ledger_path = Path("data/jobs_ledger.ndjson")
output_path = Path("data/readable_jobs.txt")

if not ledger_path.exists():
    print("Error: data/jobs_ledger.ndjson not found.")
    exit()

output_lines = []
output_lines.append("=" * 80)
output_lines.append("                AUTONOMOUS JOB SCOUT - CURRENT JOB LEDGER")
output_lines.append("=" * 80 + "\n")

with open(ledger_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if not line.strip():
            continue
        record = json.loads(line)
        raw = record["raw"]
        evaluation = record.get("evaluation")

        block = []
        block.append(f"[{idx}] {raw['company'].upper()} - {raw['title']}")
        block.append(f"    Location   : {raw['location']}")
        block.append(f"    Posted     : {raw.get('posted_date', 'N/A')}")
        block.append(f"    Apply URL  : {raw['url']}")

        if evaluation:
            block.append(f"    Fit Score  : {evaluation['fit_score']}/100 ({evaluation['tier']})")
            block.append(f"    Action     : {evaluation['recommended_action']}")
            if evaluation.get("key_alignment_reasons"):
                block.append("    Strengths  :")
                for reason in evaluation["key_alignment_reasons"]:
                    block.append(f"      • {reason}")
            if evaluation.get("gap_analysis"):
                block.append("    Gaps / Focus Areas :")
                for gap in evaluation["gap_analysis"]:
                    block.append(f"      • {gap}")
        else:
            block.append("    Evaluation : Unscored (Awaiting LLM Evaluation)")

        block.append("-" * 80)
        output_lines.append("\n".join(block))

full_content = "\n".join(output_lines)

# 1. Print to Terminal
print(full_content)

# 2. Save to data/readable_jobs.txt
with open(output_path, "w", encoding="utf-8") as out:
    out.write(full_content)

print(f"\n[SUCCESS] Saved readable report to: {output_path.resolve()}")