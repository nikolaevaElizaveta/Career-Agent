"""Map provider location strings without inventing eligibility."""

from __future__ import annotations

from career_agent.domain.job_posting import RemoteScope

COUNTRY_ALIASES: dict[str, str] = {
    "usa": "US",
    "us": "US",
    "united states": "US",
    "united states of america": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "spain": "ES",
    "es": "ES",
    "australia": "AU",
    "au": "AU",
    "canada": "CA",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "ireland": "IE",
    "portugal": "PT",
    "italy": "IT",
    "poland": "PL",
    "russia": "RU",
    "russian federation": "RU",
    "ru": "RU",
}

REGION_TOKENS = {
    "europe",
    "eu",
    "emea",
    "latam",
    "apac",
    "asia",
    "africa",
    "americas",
    "usa timezones",
}

WORLDWIDE_TOKENS = {"worldwide", "anywhere", "remote worldwide", "global", "world wide"}


def parse_required_location(raw: str | None) -> tuple[RemoteScope, list[str] | None, str | None]:
    """Return remote_scope, eligible_countries (None = unknown), country_code."""
    if raw is None or not raw.strip():
        return RemoteScope.UNKNOWN, None, None

    text = raw.strip()
    lowered = text.casefold()
    if lowered in WORLDWIDE_TOKENS:
        return RemoteScope.WORLDWIDE, None, None

    parts = [part.strip() for part in text.replace("/", ",").split(",") if part.strip()]
    if not parts:
        return RemoteScope.UNKNOWN, None, None

    codes: list[str] = []
    region_seen = False
    unknown_token = False
    for part in parts:
        key = part.casefold()
        if key in WORLDWIDE_TOKENS:
            continue
        if key in REGION_TOKENS or any(token in key for token in REGION_TOKENS):
            region_seen = True
            codes.append(part)
            continue
        mapped = COUNTRY_ALIASES.get(key)
        if mapped:
            if mapped not in codes:
                codes.append(mapped)
        else:
            unknown_token = True
            codes.append(part)

    if region_seen:
        return RemoteScope.REGION_RESTRICTED, codes or None, None
    if unknown_token and not any(item in COUNTRY_ALIASES.values() for item in codes):
        return RemoteScope.UNKNOWN, codes, None
    if codes and all(len(item) == 2 and item.isalpha() for item in codes):
        country = codes[0] if len(codes) == 1 else None
        return RemoteScope.COUNTRY_RESTRICTED, codes, country
    if codes:
        return RemoteScope.COUNTRY_RESTRICTED, codes, None
    return RemoteScope.UNKNOWN, None, None
