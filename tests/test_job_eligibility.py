from datetime import UTC, datetime

import pytest

from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_eligibility import (
    Compatibility,
    EligibilityStatus,
    assess_job_eligibility,
)


def make_job(
    locations: list | None,
    timezones: list | None,
) -> JobPosting:
    return JobPosting(
        id="eligibility-test",
        source="himalayas",
        source_job_id="eligibility-test",
        title="QA Engineer",
        company="Example Company",
        discovered_at=datetime.now(UTC),
        raw_payload={
            "provider": "himalayas",
            "job": {
                "locationRestrictions": locations,
                "timezoneRestrictions": timezones,
            },
        },
    )


ALL_RUSSIA_OFFSETS = list(range(2, 13))


def test_worldwide_job_is_potentially_eligible() -> None:
    job = make_job([], ALL_RUSSIA_OFFSETS)

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.POTENTIALLY_ELIGIBLE
    assert result.country_compatibility == Compatibility.COMPATIBLE
    assert result.timezone_compatibility == Compatibility.COMPATIBLE
    assert result.legal_work_authorization == "unknown"


def test_russia_in_string_country_list_is_eligible() -> None:
    job = make_job(
        ["Austria", "Russian Federation", "Spain"],
        ALL_RUSSIA_OFFSETS,
    )

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.POTENTIALLY_ELIGIBLE
    assert result.country_compatibility == Compatibility.COMPATIBLE


def test_dict_country_format_is_supported() -> None:
    job = make_job(
        [
            {"alpha2": "RU", "name": "Russian Federation"},
            {"alpha2": "ES", "name": "Spain"},
        ],
        ["UTC+2", "UTC+3", "UTC+4", "UTC+5", "UTC+6",
         "UTC+7", "UTC+8", "UTC+9", "UTC+10", "UTC+11", "UTC+12"],
    )

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.POTENTIALLY_ELIGIBLE


def test_country_restriction_excluding_russia() -> None:
    job = make_job(
        ["United Kingdom", "Spain"],
        ALL_RUSSIA_OFFSETS,
    )

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.COUNTRY_RESTRICTED
    assert result.country_compatibility == Compatibility.INCOMPATIBLE


def test_timezone_with_no_russian_overlap_is_rejected() -> None:
    job = make_job([], [-5, -4, -3, 0, 1])

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.TIMEZONE_MISMATCH
    assert result.timezone_compatibility == Compatibility.INCOMPATIBLE


def test_partial_russian_timezone_overlap_needs_verification() -> None:
    job = make_job(["Russian Federation"], [3, 4])

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.NEEDS_VERIFICATION
    assert result.timezone_compatibility == Compatibility.UNKNOWN


def test_specific_candidate_timezone_can_be_checked() -> None:
    job = make_job(["RU"], [3, 4])

    result = assess_job_eligibility(
        job,
        candidate_country="RU",
        candidate_utc_offset=3,
    )

    assert result.status == EligibilityStatus.POTENTIALLY_ELIGIBLE


def test_specific_candidate_timezone_can_be_rejected() -> None:
    job = make_job(["RU"], [4, 5])

    result = assess_job_eligibility(
        job,
        candidate_country="RU",
        candidate_utc_offset=3,
    )

    assert result.status == EligibilityStatus.TIMEZONE_MISMATCH


def test_empty_timezone_restrictions_mean_no_timezone_limit() -> None:
    job = make_job(["RU"], [])

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.POTENTIALLY_ELIGIBLE


@pytest.mark.parametrize(
    "restrictions",
    [
        None,
        ["UTC+3", "not-a-timezone"],
    ],
)
def test_unknown_timezone_data_needs_verification(restrictions) -> None:
    job = make_job(["RU"], restrictions)

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.NEEDS_VERIFICATION


def test_missing_location_restrictions_need_verification() -> None:
    job = make_job(None, ALL_RUSSIA_OFFSETS)

    result = assess_job_eligibility(job)

    assert result.status == EligibilityStatus.NEEDS_VERIFICATION
    assert result.country_compatibility == Compatibility.UNKNOWN
