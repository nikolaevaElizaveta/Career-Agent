from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_assessment import (
    RequiredSkillCoverage,
    assess_candidate_job,
)
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def make_profile() :
    return ProfileService().load(EXAMPLE_PROFILE)


def make_job(description: str | None) -> JobPosting:
    return JobPosting(
        id="assessment-test",
        source="test",
        source_job_id="assessment-test",
        title="Junior QA Engineer",
        company="Example Company",
        description=description,
        location="Remote",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_payload={
            "provider": "himalayas",
            "job": {
                "locationRestrictions": [],
                "timezoneRestrictions": list(range(2, 13)),
            },
        },
        job_url="https://example.com/job",
    )


def make_confirmed_skill(
    name: str,
    *,
    proficiency: str = "intermediate",
    commercial_experience: bool = True,
) -> SkillItem:
    return SkillItem(
        name=name,
        category="testing",
        proficiency=ProfileField[str](
            value=proficiency,
            status=VerificationStatus.CONFIRMED,
        ),
        commercial_experience=ProfileField[bool](
            value=commercial_experience,
            status=VerificationStatus.CONFIRMED,
        ),
    )


def test_confirmed_required_skill_is_covered() -> None:
    profile = make_profile()
    profile.skills = [make_confirmed_skill("Postman")]
    job = make_job(
        "<h2>Requirements</h2><ul><li>Experience with Postman.</li></ul>"
    )

    result = assess_candidate_job(job, profile)

    assert result.skill_coverage.status is RequiredSkillCoverage.ALL_SKILLS_PRESENT_IN_PROFILE
    assert result.skill_coverage.total_required == 1
    assert result.skill_coverage.confirmed == 1
    assert result.skill_coverage.missing == 0


def test_missing_required_skill_is_reported_as_gap() -> None:
    profile = make_profile()
    profile.skills = [make_confirmed_skill("Postman")]
    job = make_job(
        "<h2>Requirements</h2><ul><li>Experience with MySQL.</li></ul>"
    )

    result = assess_candidate_job(job, profile)

    assert result.skill_coverage.status is RequiredSkillCoverage.GAPS
    assert result.skill_coverage.missing == 1
    assert result.skill_matches.required_skills[0].status.value == "missing"


def test_skill_without_commercial_experience_is_not_missing() -> None:
    profile = make_profile()
    profile.skills = [
        make_confirmed_skill(
            "Python",
            proficiency="basic",
            commercial_experience=False,
        )
    ]
    job = make_job(
        "<h2>Requirements</h2><ul><li>Experience with Python.</li></ul>"
    )

    result = assess_candidate_job(job, profile)

    match = result.skill_matches.required_skills[0]

    assert result.skill_coverage.status is RequiredSkillCoverage.ALL_SKILLS_PRESENT_IN_PROFILE
    assert match.status.value == "confirmed"
    assert match.proficiency == "basic"
    assert match.commercial_experience is False


def test_no_description_is_not_assessed() -> None:
    profile = make_profile()
    job = make_job(None)

    result = assess_candidate_job(job, profile)

    assert (
        result.skill_coverage.status
        is RequiredSkillCoverage.NO_DESCRIPTION
    )
    assert result.skill_coverage.total_required == 0


def test_alternative_group_counts_as_one_requirement() -> None:
    profile = make_profile()
    profile.skills = [make_confirmed_skill("Python")]
    job = make_job(
        "<h2>Requirements</h2><ul><li>At least one of Python or Java.</li></ul>"
    )

    result = assess_candidate_job(job, profile)

    assert result.skill_coverage.total_required == 1
    assert result.skill_coverage.confirmed == 1
    assert result.skill_coverage.status is RequiredSkillCoverage.ALL_SKILLS_PRESENT_IN_PROFILE
    assert len(result.skill_matches.alternative_groups) == 1
