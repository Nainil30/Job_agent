"""Small pure helpers: HTML->text, date parsing, fingerprints, regex compilation."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime, timedelta

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", value)
    text = re.sub(r"(?i)<\s*li[^>]*>", "- ", text)
    text = html.unescape(_TAG.sub(" ", text))
    text = "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines())
    return _NL.sub("\n\n", text).strip()


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


_REL = re.compile(r"(\d+)\+?\s*(day|hour|week|month)s?\s*ago", re.I)
_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y")


def parse_posted(value: object) -> str | None:
    """Best-effort conversion of the many ATS date formats to an ISO date (YYYY-MM-DD)."""
    if value is None or value == "":
        return None
    now = now_utc()
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(ts, UTC).date().isoformat()
    s = str(value).strip()
    low = s.lower()
    if "today" in low or "just posted" in low:
        return now.date().isoformat()
    if "yesterday" in low:
        return (now - timedelta(days=1)).date().isoformat()
    m = _REL.search(s)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
        }[unit]
        return (now - delta).date().isoformat()
    iso = s.replace("Z", "+00:00")
    iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)  # +0000 -> +00:00
    try:
        return datetime.fromisoformat(iso).date().isoformat()
    except ValueError:
        pass
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def age_days(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return None
    return (now_utc().date() - d).days


def stable_hash(*parts: str) -> str:
    normalized = "_".join(p.strip().lower() for p in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|corp|corporation|ltd|co|technologies|services)\b\.?", re.I)


def normalize_company(name: str) -> str:
    return _NON_ALNUM.sub(" ", _COMPANY_SUFFIX.sub("", name.lower())).strip()


def fingerprint(company: str, title: str, location: str) -> str:
    """Cross-source identity: the same role seen on Workday and on LinkedIn collapses to one."""
    city = _NON_ALNUM.sub(" ", (location or "").lower()).split()
    city_token = next((t for t in city if t not in {"us", "usa", "united", "states"}), "")
    title_norm = _NON_ALNUM.sub(" ", re.sub(r"\(.*?\)", "", title.lower())).strip()
    return stable_hash(normalize_company(company), title_norm, city_token)[:16]


def compile_terms(terms: list[str] | dict[str, int] | None) -> list[tuple[re.Pattern[str], int]]:
    """Compile regex fragments with alphanumeric boundaries. List entries get weight 1."""
    if not terms:
        return []
    items = terms.items() if isinstance(terms, dict) else ((t, 1) for t in terms)
    return [(re.compile(rf"(?<![a-z0-9])(?:{t})(?![a-z0-9])", re.I), int(w)) for t, w in items]
