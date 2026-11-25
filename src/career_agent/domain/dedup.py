"""Company/title/URL normalization for duplicate detection."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|s\.?l\.?|s\.?a\.?|pty|plc|corp|co)\b\.?",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "source")


def normalize_company(name: str) -> str:
    text = name.casefold().strip()
    text = _COMPANY_SUFFIXES.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    text = title.casefold().strip()
    text = re.sub(r"[^\w\s+/]", " ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_job_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return url.strip().casefold()
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
        and key.casefold() not in {"ref", "source"}
    ]
    cleaned = urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/"),
            urlencode(query),
            "",
        )
    )
    return cleaned


def urls_equivalent(left: str | None, right: str | None) -> bool:
    a = normalize_job_url(left)
    b = normalize_job_url(right)
    return bool(a and b and a == b)
