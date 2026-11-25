from datetime import UTC, datetime

from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_relevance import (
    SeniorityLevel,
    assess_job_relevance,
)


def make_job(
    title: str,
    experience_level: str,
    employment_type: str = "Full Time",
) -> JobPosting:
    return JobPosting(
        id="seniority-metadata-test",
        source="test",
        source_job_id="seniority-metadata-test",
        title=title,
        company="Example Company",
        experience_level=experience_level,
        employment_type=employment_type,
        discovered_at=datetime(2026, 11, 23, tzinfo=UTC),
    )


def test_entry_level_metadata_is_used_when_title_has_no_seniority() -> None:
    job = make_job(
        "QA Engineer",
        experience_level="Entry-level",
    )

    result = assess_job_relevance(job)

    assert result.seniority is SeniorityLevel.JUNIOR


def test_mid_level_metadata_is_used_when_title_has_no_seniority() -> None:
    job = make_job(
        "Web/App Test Engineer",
        experience_level="Mid-level",
    )

    result = assess_job_relevance(job)

    assert result.seniority is SeniorityLevel.MIDDLE


def test_employment_type_is_last_seniority_fallback() -> None:
    job = make_job(
        "QA Engineer",
        experience_level="",
        employment_type="Intern",
    )

    result = assess_job_relevance(job)

    assert result.seniority is SeniorityLevel.INTERNSHIP


def test_explicit_title_seniority_takes_precedence_over_metadata() -> None:
    job = make_job(
        "Junior QA Engineer",
        experience_level="Mid-level",
    )

    result = assess_job_relevance(job)

    assert result.seniority is SeniorityLevel.JUNIOR
