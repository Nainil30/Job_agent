import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings  # noqa: E402
from src.engine.models import RawJobPosting  # noqa: E402


@pytest.fixture
def persona():
    return Settings().persona()


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    for var in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "DISCORD_WEBHOOK_URL",
        "NTFY_TOPIC",
        "TELEGRAM_BOT_TOKEN",
        "SMTP_USER",
    ):
        monkeypatch.delenv(var, raising=False)
    return Settings(
        data_dir=tmp_path / "data", digests_dir=tmp_path / "digests", site_dir=tmp_path / "site", llm_provider="none"
    )


def make_job(**kw) -> RawJobPosting:
    base = dict(
        job_id="J1",
        company="Nvidia",
        title="NPI Program Manager",
        location="Austin, TX",
        url="https://example.com/j1",
        description="",
        source_ats="workday",
        company_tier="Primary",
    )
    base.update(kw)
    return RawJobPosting(**base)
