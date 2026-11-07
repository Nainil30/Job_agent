"""Per-source health tracking — makes silent scraper breakage visible.

Status values:
    ok       returned listings
    empty    request succeeded but returned nothing (possible endpoint / query drift)
    partial  some queries failed
    error    every query failed
    skipped  dependency missing (e.g. Playwright not installed)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.utils import iso_now


@dataclass
class SourceHealth:
    name: str
    source: str
    tier: str
    status: str = "ok"
    fetched: int = 0
    kept: int = 0
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    checked_at: str = field(default_factory=iso_now)
    last_success: str | None = None
    consecutive_failures: int = 0


def merge_with_previous(current: list[SourceHealth], path: Path) -> list[SourceHealth]:
    """Carry forward last_success / failure streaks from the previous run."""
    previous: dict[str, dict] = {}
    if path.exists():
        try:
            previous = {h["name"]: h for h in json.loads(path.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, KeyError, TypeError):
            previous = {}
    for h in current:
        prev = previous.get(h.name, {})
        if h.status in ("ok", "partial"):
            h.last_success = h.checked_at
            h.consecutive_failures = 0
        else:
            h.last_success = prev.get("last_success")
            h.consecutive_failures = int(prev.get("consecutive_failures", 0)) + 1
    return current


def save_health(
    entries: list[SourceHealth], path: Path, merge: bool = True, configured: set[str] | None = None
) -> list[SourceHealth]:
    """Persist health. Sources skipped this run (e.g. `--tiers api`) keep their last entry,
    unless `configured` is given and they are no longer in the config."""
    if merge:
        entries = merge_with_previous(entries, path)
        if path.exists():
            try:
                names = {e.name for e in entries}
                for old in json.loads(path.read_text(encoding="utf-8")):
                    name = old.get("name")
                    if name not in names and (configured is None or name in configured):
                        entries.append(SourceHealth(**old))
            except (json.JSONDecodeError, TypeError):
                pass
    entries.sort(key=lambda e: (e.tier, e.name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(e) for e in entries], indent=2) + "\n", encoding="utf-8")
    return entries


def load_health(path: Path) -> list[SourceHealth]:
    if not path.exists():
        return []
    try:
        return [SourceHealth(**h) for h in json.loads(path.read_text(encoding="utf-8"))]
    except (json.JSONDecodeError, TypeError):
        return []
