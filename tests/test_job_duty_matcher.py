from pathlib import Path

from career_agent.domain.candidate import ExperienceItem, SkillItem
from career_agent.domain.dates import PartialDate
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.services.job_duty_matcher import (
    DutyEvidenceSource,
    DutyMatchStatus,
    extract_duty_capabilities,
    match_job_duties,
    match_job_duty,
)
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
CONFIRMED = VerificationStatus.CONFIRMED


def make_profile():
    profile = ProfileService().load(EXAMPLE_PROFILE)
    profile.skills = []
    profile.experience = []
    return profile


def make_skill(name: str, level: str = "intermediate") -> SkillItem:
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
    responsibilities: list[str],
    *,
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
                value=item,
                status=status,
            )
            for item in responsibilities
        ],
    )


def test_confirmed_experience_matches_job_duty() -> None:
    profile = make_profile()
    profile.experience = [
        make_experience(
            ["Functional and regression testing of applications"]
        )
    ]

    result = match_job_duty(
        "Perform functional and regression testing.",
        profile,
    )

    assert result.status is DutyMatchStatus.CONFIRMED_EXPERIENCE
    assert result.missing_capabilities == []
    assert result.confirmed_evidence_coverage_percent == 100


def test_imported_responsibility_requires_confirmation() -> None:
    profile = make_profile()
    profile.experience = [
        make_experience(
            ["API testing with Postman"],
            status=VerificationStatus.IMPORTED_FROM_CV,
        )
    ]

    result = match_job_duty(
        "Perform API testing.",
        profile,
    )

    assert result.status is DutyMatchStatus.NEEDS_CONFIRMATION
    assert result.verification_needed is True
    assert result.evidence[0].source is DutyEvidenceSource.EXPERIENCE_RESPONSIBILITY
    assert (
        result.evidence[0].verification_status
        is VerificationStatus.IMPORTED_FROM_CV
    )


def test_confirmed_skill_is_not_misrepresented_as_work_experience() -> None:
    profile = make_profile()
    profile.skills = [
        make_skill("Functional testing"),
        make_skill("Regression testing"),
    ]

    result = match_job_duty(
        "Perform functional and regression testing.",
        profile,
    )

    assert result.status is DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE
    assert result.confirmed_evidence_coverage_percent == 100
    assert all(
        item.source is DutyEvidenceSource.CANDIDATE_SKILL
        for item in result.evidence
    )


def test_partial_overlap_identifies_uncovered_parts_of_a_duty() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Test case design and execution")]

    result = match_job_duty(
        "Design test cases, maintain test plans, and organize test case reviews.",
        profile,
    )

    assert result.status is DutyMatchStatus.PARTIAL
    assert "test_case_design" in result.supported_capabilities
    assert "test_planning" in result.missing_capabilities
    assert "test_case_review" in result.missing_capabilities


def test_postman_is_supporting_evidence_not_full_api_testing_proof() -> None:
    profile = make_profile()
    profile.skills = [make_skill("Postman")]

    result = match_job_duty(
        "Perform API testing with Postman.",
        profile,
    )

    assert result.status is DutyMatchStatus.PARTIAL
    assert result.evidence[0].evidence_type.value == "supporting"
    assert result.confirmed_evidence_coverage_percent == 0


def test_missing_evidence_is_reported_without_guessing() -> None:
    profile = make_profile()

    result = match_job_duty(
        "Perform performance testing.",
        profile,
    )

    assert result.status is DutyMatchStatus.NO_EVIDENCE
    assert result.evidence == []
    assert result.missing_capabilities == ["performance_testing"]


def test_unrecognised_duty_is_not_automatically_a_gap() -> None:
    profile = make_profile()

    result = match_job_duty(
        "Help the business achieve ambitious strategic outcomes.",
        profile,
    )

    assert result.status is DutyMatchStatus.UNCLASSIFIED
    assert result.required_capabilities == []


def test_confirmed_skill_and_imported_experience_keep_separate_sources() -> None:
    profile = make_profile()
    profile.experience = [
        make_experience(
            ["API testing with Postman"],
            status=VerificationStatus.IMPORTED_FROM_CV,
        )
    ]
    profile.skills = [make_skill("API testing")]

    result = match_job_duty(
        "Perform API testing.",
        profile,
    )

    assert result.status is DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE
    assert any(
        item.source is DutyEvidenceSource.EXPERIENCE_RESPONSIBILITY
        and item.verification_status is VerificationStatus.IMPORTED_FROM_CV
        for item in result.evidence
    )
    assert any(
        item.source is DutyEvidenceSource.CANDIDATE_SKILL
        and item.verification_status is CONFIRMED
        for item in result.evidence
    )


def test_batch_matcher_returns_one_result_per_responsibility() -> None:
    profile = make_profile()
    profile.skills = [
        make_skill("API testing"),
        make_skill("Regression testing"),
    ]

    results = match_job_duties(
        [
            "Perform API testing.",
            "Perform regression testing.",
            "Perform performance testing.",
        ],
        profile,
    )

    assert len(results) == 3
    assert results[0].status is DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE
    assert results[1].status is DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE
    assert results[2].status is DutyMatchStatus.NO_EVIDENCE

def test_compound_testing_phrase_extracts_all_testing_types() -> None:
    capabilities = extract_duty_capabilities(
        "Acceptance and regression testing (automated and manual)"
    )

    assert {
        "acceptance_testing",
        "regression_testing",
        "test_automation",
        "manual_testing",
    }.issubset(capabilities)


def test_functional_and_regression_testing_are_both_recognised() -> None:
    capabilities = extract_duty_capabilities(
        "Execute functional and regression testing."
    )

    assert "functional_testing" in capabilities
    assert "regression_testing" in capabilities


def test_app_device_browser_and_resolution_compatibility_are_recognised() -> None:
    capabilities = extract_duty_capabilities(
        "Conduct App compatibility testing across devices, OS versions, "
        "and screen sizes, as well as Web cross-browser and "
        "cross-resolution testing."
    )

    assert {
        "app_compatibility_testing",
        "device_compatibility_testing",
        "cross_browser_testing",
        "cross_resolution_testing",
    }.issubset(capabilities)

def test_preparing_test_data_is_recognised() -> None:
    capabilities = extract_duty_capabilities(
        "Analyzing requirements, creating test scenarios, preparing test data"
    )

    assert "test_data_preparation" in capabilities

def test_automation_and_manual_exploratory_testing_are_recognised() -> None:
    capabilities = extract_duty_capabilities(
        "Combine automation and manual exploratory testing "
        "to validate user scenarios."
    )

    assert {
        "test_automation",
        "manual_testing",
        "exploratory_testing",
    }.issubset(capabilities)

def test_process_automation_is_not_misclassified_as_test_automation() -> None:
    capabilities = extract_duty_capabilities(
        "Improve process automation across internal workflows."
    )

    assert "test_automation" not in capabilities
