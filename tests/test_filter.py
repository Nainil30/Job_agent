"""Pass 1 deterministic filter: titles, geography, freshness."""

import pytest

from src.engine.filter import JobFilter, looks_us
from tests.conftest import make_job


@pytest.fixture
def filt(persona):
    return JobFilter(persona["search"])


@pytest.mark.parametrize(
    "title",
    [
        "Supply Chain Intern",
        "VP of Global Supply Chain",
        "Director, NPI Operations",
        "Hardware Sales Account Executive",
        "Talent Acquisition Recruiter - Hardware",
        "Legal Counsel, Operations",
        "2027 Undergrad Supply Chain Co-Op/Intern",
    ],
)
def test_blocked_titles(filt, title):
    ok, reason = filt.is_valid_title(title)
    assert not ok and reason == "title_blocklist"


@pytest.mark.parametrize(
    "title",
    [
        "NPI Operations Program Manager",
        "Materials Program Manager, Apple Silicon",
        "Hardware Technical Program Manager",
        "Supply Chain Analytics Program Manager",
        "Datacenter Infrastructure TPM",
        "New Product Introduction (NPI) Program Manager",
        "Program Manager II, Supply and Materials Planning, Cloud Supply Chain",
    ],
)
def test_target_titles(filt, title):
    assert filt.is_valid_title(title)[0]


def test_off_target_title(filt):
    assert filt.is_valid_title("Space Suit Sewer") == (False, "title_not_target")


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Austin, TX", True),
        ("US, CA, Santa Clara", True),
        ("Chicago, IL, US", True),
        ("Indianapolis, Indiana", True),
        ("Santa Fe, New Mexico", True),
        ("Remote", True),
        ("3 Locations", True),
        ("Taipei, Taiwan; Austin, TX, USA", True),
        ("Mexico, Remote", False),
        ("Bangalore, IN", False),
        ("Toronto, ON, Canada", False),
        ("Shanghai,CHN", False),
        ("Tel Aviv, Israel", False),
    ],
)
def test_locations(filt, location, expected):
    assert filt.is_valid_location("Nvidia", location)[0] is expected


def test_company_location_rule(filt):
    assert filt.is_valid_location("Amazon", "Austin, Texas, USA")[0]
    assert filt.is_valid_location("Amazon", "Seattle, WA, USA") == (False, "company_location_rule")
    assert filt.is_valid_location("Google", "Seattle, WA, USA")[0]


def test_freshness(filt):
    assert filt.check(make_job(posted_at="2000-01-01")) == (False, "too_old")
    assert filt.check(make_job(posted_at=None))[0]


def test_filter_jobs_counts_reasons(filt):
    jobs = [
        make_job(job_id="1"),
        make_job(job_id="2", title="Barista"),
        make_job(job_id="3", location="Munich, Germany"),
    ]
    kept, reasons = filt.filter_jobs(jobs)
    assert [j.job_id for j in kept] == ["1"]
    assert reasons == {"ok": 1, "title_not_target": 1, "location_blocklist": 1}


def test_looks_us_explicit_only():
    assert looks_us("Austin, TX")
    assert not looks_us("Austin, TX", explicit_only=True)
    assert looks_us("Austin, TX, USA", explicit_only=True)
