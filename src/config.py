"""Configuration loading: YAML files + environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Legacy key names from v1 configs -> current names
_LEGACY_KEYS = {"ats_type": "source", "base_url": "url", "site_domain": "site_url", "search_queries": "queries"}


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize_company(cfg: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(defaults or {})
    for k, v in cfg.items():
        out[_LEGACY_KEYS.get(k, k)] = v
    out.setdefault("queries", [])
    out.setdefault("tier", "Secondary")
    out.setdefault("enabled", True)
    return out


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass
class Settings:
    companies_path: Path = ROOT / "config" / "companies.yaml"
    persona_path: Path = ROOT / "config" / "persona.yaml"
    data_dir: Path = ROOT / "data"
    digests_dir: Path = ROOT / "digests"
    site_dir: Path = ROOT / "site"

    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "auto").lower())
    llm_max_calls: int = field(default_factory=lambda: _env_int("LLM_MAX_CALLS_PER_RUN", 40))
    llm_rpm: int = field(default_factory=lambda: _env_int("LLM_REQUESTS_PER_MINUTE", 8))
    notify_min_score: int = field(default_factory=lambda: _env_int("NOTIFY_MIN_SCORE", 80))

    @property
    def ledger_path(self) -> Path:
        return self.data_dir / "jobs_ledger.ndjson"

    @property
    def seen_index_path(self) -> Path:
        return self.data_dir / "seen_index.json"

    @property
    def health_path(self) -> Path:
        return self.data_dir / "source_health.json"

    def companies(self) -> list[dict[str, Any]]:
        raw = load_yaml(self.companies_path)
        defaults = raw.get("defaults", {}) or {}
        return [normalize_company(c, defaults) for c in raw.get("companies", []) or [] if c]

    def aggregators(self) -> dict[str, Any]:
        return load_yaml(self.companies_path).get("aggregators", {}) or {}

    def persona(self) -> dict[str, Any]:
        return load_yaml(self.persona_path)
