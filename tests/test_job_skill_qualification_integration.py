from datetime import UTC, datetime
from pathlib import Path

from career_agent.cli.job_assessment import format_candidate_assessment
from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_assessment import assess_candidate_job
from career_agent.services.job_skill_qualification import (
    CommercialExperienceFitStatus,
    ProficiencyFitStatus,
)
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
CONFIRMED = VerificationStatus.CONFIRMED


def make_skill(
    name: str,
    level: str,
    commercial_experience: bool,
) -> SkillItem:
    return SkillItem(
        name=name,
        category="testing",
        proficiency=ProfileField[str](
            value=level,
            status=CONFIRMED,
        ),
        commercial_experience=ProfileField[bool](
            value=commercial_experience,
            status=CONFIRMED,
        ),
    )


def test_assessment_integrates_proficiency_and_commercial_experience() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    profile.skills = [
        make_skill("SQL", "intermediate", True),
        make_skill("Postman", "intermediate", False),
        make_skill("Java", "basic", False),
    ]

    job = JobPosting(
        id="skill-qualification-integration",
        source="test",
        source_job_id="skill-qualification-integration",
        title="Junior QA Engineer",
        company="Example Company",
        description=(
            "<h2>Requirements</h2>"
            "<ul>"
            "<li>Proficiency in SQL.</li>"
            "<li>Professional experience with Postman.</li>"
            "<li>Strong coding ability in Java.</li>"
            "</ul>"
        ),
        discovered_at=datetime(2026, 11, 23, tzinfo=UTC),
    )

    assessment = assess_candidate_job(job, profile)
    qualifications = {
        item.requirement: item
        for item in assessment.skill_qualifications
    }

    sql = qualifications["SQL"]
    assert sql.expected_minimum_level == "intermediate"
    assert sql.proficiency_fit is ProficiencyFitStatus.MEETS_EXPECTATION
    assert sql.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED

    postman = qualifications["Postman"]
    assert postman.commercial_experience_required is True
    assert (
        postman.commercial_fit
        is CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT
    )

    java = qualifications["Java"]
    assert java.expected_minimum_level == "intermediate"
    assert java.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION

    report = format_candidate_assessment(assessment)

    assert "SKILL QUALIFICATION DETAILS" in report
    assert "meets_expectation" in report
    assert "below_expectation" in report
    assert "does_not_meet_explicit_requirement" in report
    assert "not explicitly stated by employer" in report
