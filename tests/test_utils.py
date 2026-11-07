from datetime import timedelta

import pytest

from src.utils import fingerprint, html_to_text, now_utc, parse_posted

TODAY = now_utc().date()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Posted Today", TODAY.isoformat()),
        ("Posted Yesterday", (TODAY - timedelta(days=1)).isoformat()),
        ("Posted 3 Days Ago", (TODAY - timedelta(days=3)).isoformat()),
        ("Posted 30+ Days Ago", (TODAY - timedelta(days=30)).isoformat()),
        ("2026-09-11T20:50:00+0000", "2026-09-11"),
        ("2026-11-07T01:01:50.432Z", "2026-11-07"),
        ("June 12, 2026", "2026-06-12"),
        (1793577600, "2026-11-02"),
        (1793577600000, "2026-11-02"),
        ("whenever", None),
        (None, None),
    ],
)
def test_parse_posted(value, expected):
    assert parse_posted(value) == expected


def test_html_to_text():
    assert html_to_text("<ul><li>Own &amp; drive NPI</li><li>EVT</li></ul>") == "- Own & drive NPI\n- EVT"


def test_fingerprint_is_source_agnostic():
    a = fingerprint("Applied Materials, Inc.", "Supply Chain Project Manager (B3)", "Austin, TX, USA")
    b = fingerprint("Applied Materials", "Supply Chain Project Manager", "Austin,TX")
    assert a == b
    assert a != fingerprint("Applied Materials", "Supply Chain Project Manager", "Santa Clara, CA")
