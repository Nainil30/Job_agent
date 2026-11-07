"""Command-line interface.

python -m src.main run                      # full pipeline, all tiers
python -m src.main run --tiers api          # fast daily run (no browser / aggregator)
python -m src.main run --only nvidia,tesla  # just some sources
python -m src.main doctor                   # test every source, store nothing
python -m src.main report                   # rebuild digest + dashboard from the ledger
python -m src.main list --min-score 75      # print ranked roles in the terminal
python -m src.main mark 6ecc731a applied    # track roles you applied to manually
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src.adapters.registry import ALL_TIERS  # noqa: E402
from src.config import Settings  # noqa: E402
from src.pipeline import report_only, run_pipeline  # noqa: E402
from src.storage.ledger import Ledger  # noqa: E402

STATUS_ICON = {"ok": "OK", "partial": "PARTIAL", "empty": "EMPTY", "error": "ERROR", "skipped": "SKIPPED"}


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def cmd_run(args) -> int:
    tiers = _csv(args.tiers) or list(ALL_TIERS)
    summary = asyncio.run(
        run_pipeline(
            Settings(),
            tiers=tiers,
            only=_csv(args.only),
            use_llm=not args.no_llm,
            send_notifications=not args.no_notify,
        )
    )
    return 1 if summary.health and all(h.status == "error" for h in summary.health) else 0


def cmd_doctor(args) -> int:
    tiers = _csv(args.tiers) or list(ALL_TIERS)
    summary = asyncio.run(run_pipeline(Settings(), tiers=tiers, only=_csv(args.only), dry_run=True))
    print(f"\n{'SOURCE':<48}{'TIER':<12}{'STATUS':<9}{'LISTINGS':>9}{'KEPT':>6}  NOTE")
    for h in sorted(summary.health, key=lambda h: (h.tier, h.name)):
        note = h.errors[0][:70] if h.errors else ""
        print(f"{h.name:<48}{h.tier:<12}{STATUS_ICON[h.status]:<9}{h.fetched:>9}{h.kept:>6}  {note}")
    bad = [h for h in summary.health if h.status in ("error", "empty")]
    print(
        f"\n{len(summary.health) - len(bad)}/{len(summary.health)} sources healthy · {summary.unique} unique listings · {summary.kept} would pass the filter"
    )
    print("Filter breakdown:", dict(summary.filter_reasons))
    return 0


def cmd_report(_args) -> int:
    report_only(Settings())
    return 0


def cmd_list(args) -> int:
    s = Settings()
    ledger = Ledger(s.ledger_path, s.seen_index_path)
    recs = [r for r in ledger.open_records(args.days) if r.score >= args.min_score]
    if args.company:
        recs = [r for r in recs if args.company.lower() in r.raw.company.lower()]
    recs.sort(key=lambda r: r.score, reverse=True)
    lines = []
    for r in recs[: args.limit]:
        ev = r.evaluation
        lines.append(f"[{r.score:>3}] {r.raw.company} - {r.raw.title}")
        lines.append(
            f"      {r.raw.location} | posted {r.raw.posted_at or '?'} | {ev.evaluator if ev else 'unscored'} | id {r.hash_id[:8]} | {r.status}"
        )
        if ev and ev.summary and ev.evaluator != "heuristic":
            lines.append(f"      {ev.summary}")
        lines.append(f"      {r.raw.url}")
    text = "\n".join(lines) or "No roles match."
    print(text)
    if args.export:
        Path(args.export).write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved to {args.export}")
    return 0


def cmd_mark(args) -> int:
    s = Settings()
    ledger = Ledger(s.ledger_path, s.seen_index_path)
    rec = ledger.set_status(args.id, args.status.upper())
    ledger.save()
    print(f"{rec.raw.company} - {rec.raw.title} -> {rec.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="job-scout", description="Find and rank relevant jobs. Never applies on your behalf."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("run", help="run the full pipeline")
    p.add_argument("--tiers", help="comma list of api,browser,aggregator (default: all)")
    p.add_argument("--only", help="comma list of company / search names to run")
    p.add_argument("--no-llm", action="store_true", help="heuristic scoring only")
    p.add_argument("--no-notify", action="store_true", help="skip notifications")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("doctor", help="check every source without storing anything")
    p.add_argument("--tiers")
    p.add_argument("--only")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("report", help="regenerate digest + dashboard from the ledger")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("list", help="print ranked open roles")
    p.add_argument("--min-score", type=int, default=70)
    p.add_argument("--company")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--days", type=int, default=14, help="only roles seen in the last N days")
    p.add_argument("--export", help="also write the list to this file")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("mark", help="set a role's status (you apply yourself; this just tracks it)")
    p.add_argument("id", help="hash id prefix shown by `list`")
    p.add_argument("status", choices=["applied", "archived", "evaluated"], type=str.lower)
    p.set_defaults(func=cmd_mark)

    # v1 compatibility: `python src/main.py --mode api`
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--mode"] and len(argv) > 1:
        argv = (
            ["report"]
            if argv[1] == "report"
            else ["run", "--tiers", "api" if argv[1] == "api" else ",".join(ALL_TIERS)]
        )

    args = parser.parse_args(argv)
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if args.verbose else "INFO",
        format="<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> {message}",
    )
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
