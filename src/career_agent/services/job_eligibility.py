"""Source-level geographic and timezone eligibility assessment."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.job_posting import JobPosting
from career_agent.integrations.job_sources.location import COUNTRY_ALIASES


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class EligibilityStatus(StrEnum):
    POTENTIALLY_ELIGIBLE = "potentially_eligible"
    COUNTRY_RESTRICTED = "country_restricted"
    TIMEZONE_MISMATCH = "timezone_mismatch"
    NEEDS_VERIFICATION = "needs_verification"


class JobEligibilityAssessment(BaseModel):
    status: EligibilityStatus
    country_compatibility: Compatibility
    timezone_compatibility: Compatibility
    legal_work_authorization: str = "unknown"
    reasons: list[str] = Field(default_factory=list)


RUSSIA_UTC_OFFSETS = frozenset(float(value) for value in range(2, 13))
MISSING = object()


def _job_payload(job: JobPosting) -> dict:
    payload = job.raw_payload.get("job", {})
    return payload if isinstance(payload, dict) else {}


def _normalize_country(value: object) -> str | None:
    if isinstance(value, dict):
        alpha2 = value.get("alpha2")
        if isinstance(alpha2, str) and alpha2.strip():
            return alpha2.strip().upper()
        value = value.get("name")

    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().casefold()
    return COUNTRY_ALIASES.get(normalized, normalized)


def _country_compatibility(
    payload: dict,
    candidate_country: str,
) -> Compatibility:
    restrictions = payload.get("locationRestrictions", MISSING)

    if not isinstance(restrictions, list):
        return Compatibility.UNKNOWN

    # The API defines an empty list as no country restrictions.
    if not restrictions:
        return Compatibility.COMPATIBLE

    target = _normalize_country(candidate_country)
    if target is None:
        return Compatibility.UNKNOWN

    normalized = {
        country
        for item in restrictions
        if (country := _normalize_country(item)) is not None
    }

    if not normalized:
        return Compatibility.UNKNOWN

    if target in normalized:
        return Compatibility.COMPATIBLE

    return Compatibility.INCOMPATIBLE


def _parse_utc_offset(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    text = value.strip().upper()
    text = re.sub(r"^(?:UTC|GMT)", "", text).strip()

    match = re.fullmatch(r"([+-]?\d{1,2})(?::(\d{2}))?", text)
    if not match:
        try:
            return float(text)
        except ValueError:
            return None

    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)

    if minutes >= 60:
        return None

    sign = -1 if hours < 0 or text.startswith("-") else 1
    return sign * (abs(hours) + minutes / 60)


def _timezone_compatibility(
    payload: dict,
    candidate_utc_offset: float | None,
) -> Compatibility:
    restrictions = payload.get("timezoneRestrictions", MISSING)

    if not isinstance(restrictions, list):
        return Compatibility.UNKNOWN

    # The API defines an empty list as no timezone requirements.
    if not restrictions:
        return Compatibility.COMPATIBLE

    parsed = [_parse_utc_offset(item) for item in restrictions]

    # Do not make a positive decision if part of the list is unparseable.
    if any(item is None for item in parsed):
        return Compatibility.UNKNOWN

    allowed = {item for item in parsed if item is not None}

    if candidate_utc_offset is not None:
        return (
            Compatibility.COMPATIBLE
            if float(candidate_utc_offset) in allowed
            else Compatibility.INCOMPATIBLE
        )

    overlap = allowed.intersection(RUSSIA_UTC_OFFSETS)

    if not overlap:
        return Compatibility.INCOMPATIBLE

    # Without a specified city, require compatibility with every
    # standard Russian offset before declaring nationwide compatibility.
    if RUSSIA_UTC_OFFSETS.issubset(allowed):
        return Compatibility.COMPATIBLE

    return Compatibility.UNKNOWN


def assess_job_eligibility(
    job: JobPosting,
    candidate_country: str = "RU",
    candidate_utc_offset: float | None = None,
) -> JobEligibilityAssessment:
    """Assess source restrictions, not legal permission to employ someone."""

    payload = _job_payload(job)

    country = _country_compatibility(payload, candidate_country)
    timezone = _timezone_compatibility(payload, candidate_utc_offset)

    if country is Compatibility.INCOMPATIBLE:
        status = EligibilityStatus.COUNTRY_RESTRICTED
        reasons = [
            f"The source does not list {candidate_country} as an eligible country."
        ]
    elif timezone is Compatibility.INCOMPATIBLE:
        status = EligibilityStatus.TIMEZONE_MISMATCH
        reasons = [
            "The permitted timezone offsets do not match the candidate's location."
        ]
    elif (
        country is Compatibility.COMPATIBLE
        and timezone is Compatibility.COMPATIBLE
    ):
        status = EligibilityStatus.POTENTIALLY_ELIGIBLE
        reasons = [
            "The source's country and timezone restrictions are compatible.",
            "The employer's legal ability to hire the candidate remains unverified.",
        ]
    else:
        status = EligibilityStatus.NEEDS_VERIFICATION
        reasons = [
            "One or more country/timezone restrictions are missing or ambiguous."
        ]

    return JobEligibilityAssessment(
        status=status,
        country_compatibility=country,
        timezone_compatibility=timezone,
        legal_work_authorization="unknown",
        reasons=reasons,
    )
