from datetime import UTC, date, datetime
from pathlib import Path

from career_agent.cli.job_assessment import format_candidate_assessment
from career_agent.domain.candidate import EducationItem, ExperienceItem
from career_agent.domain.dates import PartialDate
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_assessment import assess_candidate_job
from career_agent.services.job_experience_matcher import (
    EducationMatchStatus,
    ExperienceMatchStatus,
)
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
CONFIRMED = VerificationStatus.CONFIRMED


def test_assessment_integrates_experience_and_education() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)

    profile.experience = [
        ExperienceItem(
            company=ProfileField[str](
                value="Example Company",
                status=CONFIRMED,
            ),
            title=ProfileField[str](
                value="QA Engineer",
                status=CONFIRMED,
            ),
            start_date=ProfileField[PartialDate](
                value=PartialDate.parse("2026-03"),
                status=CONFIRMED,
            ),
            end_date=ProfileField[str](
                value="present",
                status=CONFIRMED,
            ),
            currently_employed=True,
        )
    ]

    profile.education = [
        EducationItem(
            institution=ProfileField[str](
                value="Example University",
                status=CONFIRMED,
            ),
            degree=ProfileField[str](
                value="Bachelor",
                status=CONFIRMED,
            ),
            field=ProfileField[str](
                value="Computer Science",
                status=CONFIRMED,
            ),
            start_year=ProfileField[int](
                value=2022,
                status=CONFIRMED,
            ),
            end_year=ProfileField[int](
                value=2026,
                status=CONFIRMED,
            ),
        )
    ]

    job = JobPosting(
        id="qualification-integration-test",
        source="test",
        source_job_id="qualification-integration-test",
        title="Junior QA Engineer",
        company="Example Company",
        description=(
            "<h2>Requirements</h2>"
            "<ul>"
            "<li>1-2 years of experience in QA.</li>"
            "<li>Undergraduate or postgraduate in Computer Science, "
            "Software Engineering, or a related field.</li>"
            "</ul>"
        ),
        discovered_at=datetime(2026, 11, 23, tzinfo=UTC),
        raw_payload={},
    )

    assessment = assess_candidate_job(
        job,
        profile,
        as_of=date(2026, 11, 23),
    )

    assert len(assessment.experience_matches) == 1
    experience = assessment.experience_matches[0]

    assert experience.status is ExperienceMatchStatus.BELOW_MINIMUM
    assert experience.confirmed_min_months == 7
    assert experience.possible_max_months == 8

    assert len(assessment.education_matches) == 1
    education = assessment.education_matches[0]

    assert education.status is EducationMatchStatus.MATCHED
    assert education.matched_degree == "Bachelor"
    assert education.matched_field == "Computer Science"

    report = format_candidate_assessment(assessment)

    assert "EXPERIENCE REQUIREMENTS" in report
    assert "below_minimum" in report
    assert "Confirmed minimum: 7 full months" in report
    assert "EDUCATION REQUIREMENTS" in report
    assert "[matched]" in report
