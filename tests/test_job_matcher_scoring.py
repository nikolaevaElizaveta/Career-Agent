from datetime import UTC, date, datetime
from pathlib import Path

from career_agent.domain.candidate import ExperienceItem, SkillItem
from career_agent.domain.dates import PartialDate
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.domain.job_posting import (
    JobPosting,
    SalaryPeriod,
    SalaryType,
    WorkplaceType,
)
from career_agent.services.job_candidate_assessment import assess_candidate_job
from career_agent.services.job_matcher import (
    JobMatchStatus,
    score_candidate_job,
)
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
CONFIRMED = VerificationStatus.CONFIRMED


def make_profile() :
    profile = ProfileService().load(EXAMPLE_PROFILE)
    profile.career_preferences.target_roles = ["Manual QA / QA Engineer"]
    profile.salary_expectations.amount = 10_000
    profile.salary_expectations.currency = "RUB"
    profile.salary_expectations.period = "month"
    profile.salary_expectations.kind = "net"
    profile.employment_preferences.preferred_work_mode = "remote"
    profile.ethical_restrictions.hard_exclusions = ["gambling"]
    profile.ethical_restrictions.lower_priority = ["crypto"]
    return profile


def make_skill(
    name: str,
    level: str = "intermediate",
) -> SkillItem:
    return SkillItem(
        name=name,
        category="testing",
        proficiency=ProfileField[str](
            value=level,
            status=CONFIRMED,
        ),
        commercial_experience=ProfileField[bool](
            value=True,
            status=CONFIRMED,
        ),
    )


def make_experience(
    responsibility: str,
    status: VerificationStatus = CONFIRMED,
) -> ExperienceItem:
    return ExperienceItem(
        company=ProfileField[str](
            value="Example Company",
            status=CONFIRMED,
        ),
        title=ProfileField[str](
            value="QA Engineer",
            status=CONFIRMED,
        ),
        start_date=ProfileField[PartialDate](
            value=PartialDate.parse("2025-01"),
            status=CONFIRMED,
        ),
        end_date=ProfileField[str](
            value="present",
            status=CONFIRMED,
        ),
        currently_employed=True,
        responsibilities=[
            ProfileField[str](
                value=responsibility,
                status=status,
            )
        ],
    )


def make_responsibility_job(*duties: str) -> JobPosting:
    items = "".join(f"<li>{item}</li>" for item in duties)
    return make_job(
        description=(
            "<h2>Responsibilities</h2>"
            f"<ul>{items}</ul>"
        )
    )


def get_duty_component(score):
    category = get_category(score, "role_and_duties")
    components = [
        item
        for item in category.components
        if item.name == "duty_alignment"
    ]
    assert len(components) == 1
    return components[0]


def make_job(
    description: str = (
        "<h2>Requirements</h2>"
        "<ul><li>Manual QA testing</li></ul>"
    ),
    **overrides,
) -> JobPosting:
    values = {
        "id": "scoring-test",
        "source": "test",
        "source_job_id": "scoring-test",
        "title": "Junior QA Engineer",
        "company": "Example Company",
        "description": description,
        "workplace_type": WorkplaceType.REMOTE,
        "raw_payload": {
            "job": {
                "locationRestrictions": [],
                "timezoneRestrictions": [],
            }
        },
        "discovered_at": datetime(2026, 11, 23, tzinfo=UTC),
    }
    values.update(overrides)
    return JobPosting(**values)


def assess_and_score(job: JobPosting, profile=None):
    candidate = profile or make_profile()
    assessment = assess_candidate_job(
        job,
        candidate,
        as_of=date(2026, 11, 23),
    )
    return score_candidate_job(job, candidate, assessment)


def get_category(score, key: str):
    return next(item for item in score.categories if item.key == key)


def test_missing_salary_is_unknown_not_zero() -> None:
    score = assess_and_score(make_job())

    salary = get_category(score, "salary")

    assert salary.score is None
    assert salary.coverage_percent == 0
    assert score.observed_score is not None
    assert score.score_ceiling > score.score_floor
    assert score.coverage_percent < 100


def test_comparable_salary_meeting_expectation_scores_fully() -> None:
    job = make_job(
        salary_min=12_000,
        salary_max=15_000,
        salary_currency="RUB",
        salary_period=SalaryPeriod.MONTH,
        salary_type=SalaryType.NET,
    )

    score = assess_and_score(job)
    salary = get_category(score, "salary")

    assert salary.score == 100
    assert salary.coverage_percent == 100


def test_gross_and_net_salary_are_not_compared() -> None:
    job = make_job(
        salary_min=12_000,
        salary_max=15_000,
        salary_currency="RUB",
        salary_period=SalaryPeriod.MONTH,
        salary_type=SalaryType.GROSS,
    )

    score = assess_and_score(job)

    assert get_category(score, "salary").score is None


def test_currency_mismatch_is_not_converted_implicitly() -> None:
    job = make_job(
        salary_min=1_000,
        salary_max=2_000,
        salary_currency="EUR",
        salary_period=SalaryPeriod.MONTH,
        salary_type=SalaryType.NET,
    )

    score = assess_and_score(job)

    assert get_category(score, "salary").score is None


def test_hard_exclusion_blocks_automatic_ranking() -> None:
    job = make_job(
        description=(
            "<h2>About</h2>"
            "<p>We build an online gambling platform.</p>"
        )
    )

    score = assess_and_score(job)

    assert score.status is JobMatchStatus.BLOCKED_BY_HARD_EXCLUSION
    assert score.blocked_from_ranking is True
    assert score.hard_exclusion_matches == ["gambling"]


def test_country_restriction_blocks_automatic_ranking() -> None:
    job = make_job(
        raw_payload={
            "job": {
                "locationRestrictions": ["US"],
                "timezoneRestrictions": [],
            }
        }
    )

    score = assess_and_score(job)

    assert score.status is JobMatchStatus.INELIGIBLE
    assert score.blocked_from_ranking is True


def test_lower_priority_term_is_flagged_without_arbitrary_penalty() -> None:
    job = make_job(
        description="<p>Experience in crypto products is preferred.</p>"
    )

    score = assess_and_score(job)

    assert score.lower_priority_matches == ["crypto"]
    assert any("lower-priority" in warning for warning in score.warnings)
    ethics = get_category(score, "ethics")
    assert ethics.score is None
    assert ethics.coverage_percent == 0
    assert ethics.weighted_contribution == 0


def test_alternative_group_is_counted_once() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Python", "basic")]

    job = make_job(
        description=(
            "<h2>Requirements</h2>"
            "<ul>"
            "<li>Strong coding ability in at least one of Python or Java</li>"
            "</ul>"
        )
    )

    assessment = assess_candidate_job(
        job,
        profile,
        as_of=date(2026, 11, 23),
    )
    score = score_candidate_job(job, profile, assessment)

    technical = get_category(score, "technical_skills")
    alternative_components = [
        item for item in technical.components
        if "Python OR Java" in item.name
    ]

    assert len(alternative_components) == 1
    assert alternative_components[0].score == 50


def test_related_evidence_does_not_change_exact_skill_score() -> None:
    job = make_job(
        description="<h2>Requirements</h2><ul><li>API testing</li></ul>"
    )

    exact_profile = make_profile()
    exact_profile.skills = [make_skill("API testing")]

    related_profile = make_profile()
    related_profile.skills = [
        make_skill("API testing"),
        make_skill("Postman"),
    ]

    exact_score = assess_and_score(job, exact_profile)
    related_score = assess_and_score(job, related_profile)

    assert (
        get_category(exact_score, "technical_skills").score
        == get_category(related_score, "technical_skills").score
    )

    related_assessment = assess_candidate_job(
        job,
        related_profile,
        as_of=date(2026, 11, 23),
    )
    assert any(
        item.candidate_skill == "Postman"
        for item in related_assessment.related_skill_evidence
    )


def test_three_required_skill_gaps_force_weak_match() -> None:
    profile = make_profile()
    profile.skills = []

    job = make_job(
        description=(
            "<h2>Requirements</h2>"
            "<ul>"
            "<li>SQL</li>"
            "<li>MySQL</li>"
            "<li>Postman</li>"
            "<li>Docker</li>"
            "</ul>"
        )
    )

    score = assess_and_score(job, profile)

    assert score.status is JobMatchStatus.WEAK_MATCH
    assert any("explicit required skill" in item for item in score.warnings)


def test_strong_match_is_withheld_while_duty_scoring_is_uncalibrated() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Manual testing")]

    job = make_job(
        description=(
            "<h2>Requirements</h2>"
            "<ul><li>Manual testing</li></ul>"
        )
    )

    score = assess_and_score(job, profile)

    assert score.observed_score is not None
    assert score.observed_score >= 80
    assert score.status is JobMatchStatus.POTENTIAL_MATCH
    assert any(
        "duty-scoring weights and thresholds" in item
        for item in score.warnings
    )

def test_no_detected_hard_exclusion_does_not_award_ethics_points() -> None:
    score = assess_and_score(make_job())
    ethics = get_category(score, "ethics")

    assert ethics.score is None
    assert ethics.coverage_percent == 0
    assert ethics.weighted_contribution == 0
    assert any(
        "ethical suitability" in warning
        for warning in score.warnings
    )

def test_confirmed_work_experience_receives_full_duty_score() -> None:
    profile = make_profile()
    profile.skills = []
    profile.experience = [
        make_experience("Perform manual testing.")
    ]

    score = assess_and_score(
        make_responsibility_job("Perform manual testing."),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 100
    assert component.coverage == 1
    assert component.weight == 3.0


def test_confirmed_direct_skill_receives_partial_duty_score() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Manual testing")]
    profile.experience = []

    score = assess_and_score(
        make_responsibility_job("Perform manual testing."),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 80
    assert component.coverage == 1


def test_imported_work_experience_has_reduced_confidence() -> None:
    profile = make_profile()
    profile.skills = []
    profile.experience = [
        make_experience(
            "Perform manual testing.",
            VerificationStatus.IMPORTED_FROM_CV,
        )
    ]

    score = assess_and_score(
        make_responsibility_job("Perform manual testing."),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 60
    assert component.coverage == 0.5


def test_supporting_tool_is_not_equal_to_direct_skill_evidence() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Postman")]
    profile.experience = []

    score = assess_and_score(
        make_responsibility_job("Perform API testing with Postman."),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 40
    assert component.coverage == 1


def test_unclassified_duty_reduces_coverage_without_zero_score_penalty() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Manual testing")]
    profile.experience = []

    score = assess_and_score(
        make_responsibility_job(
            "Perform manual testing.",
            "Help the business achieve ambitious strategic outcomes.",
        ),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 80
    assert component.coverage == 0.5


def test_missing_duty_evidence_receives_zero_score() -> None:
    profile = make_profile()
    profile.skills = []
    profile.experience = []

    score = assess_and_score(
        make_responsibility_job("Perform performance testing."),
        profile,
    )

    component = get_duty_component(score)

    assert component.score == 0
    assert component.coverage == 1


def test_no_extracted_responsibilities_adds_no_duty_component() -> None:
    score = assess_and_score(make_job())
    category = get_category(score, "role_and_duties")

    assert not any(
        item.name == "duty_alignment"
        for item in category.components
    )

def test_required_experience_gap_forces_manual_review() -> None:
    job = make_job(
        description=(
            "<h2>Requirements</h2>"
            "<p>1–2 years of experience in QA</p>"
            "<p>Manual QA testing</p>"
        )
    )

    score = assess_and_score(job)

    assert score.status is JobMatchStatus.NEEDS_REVIEW
    assert score.blocked_from_ranking is False
    assert any(
        "required experience requirement(s)" in warning
        for warning in score.warnings
    )
