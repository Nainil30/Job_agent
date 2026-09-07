"""Unit tests verifying deterministic title and location filtering rules."""

from src.engine.filter import DeterministicFilter


def test_blocklist_titles():
    filt = DeterministicFilter()
    invalid_titles = [
        "Supply Chain Intern",
        "VP of Global Supply Chain",
        "Hardware Sales Account Executive",
        "Talent Acquisition Recruiter - Hardware",
        "Legal Counsel, Operations",
    ]
    for title in invalid_titles:
        ok, reason = filt.is_valid_title(title)
        assert not ok, f"Expected '{title}' to be blocked, but passed: {reason}"


def test_allowlist_titles():
    filt = DeterministicFilter()
    valid_titles = [
        "NPI Operations Program Manager",
        "Materials Program Manager, Apple Silicon",
        "Hardware Technical Program Manager",
        "Supply Chain Analytics Program Manager",
        "Datacenter Infrastructure TPM",
    ]
    for title in valid_titles:
        ok, reason = filt.is_valid_title(title)
        assert ok, f"Expected '{title}' to pass, but was rejected: {reason}"


def test_amazon_austin_strict_gating():
    filt = DeterministicFilter()
    ok_austin, _ = filt.is_valid_location("Amazon", "Austin, TX, USA")
    assert ok_austin

    ok_seattle, _ = filt.is_valid_location("Amazon", "Seattle, WA, USA")
    assert not ok_seattle

    ok_other, _ = filt.is_valid_location("Google", "Sunnyvale, CA, USA")
    assert ok_other