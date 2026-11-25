import pytest

from career_agent.domain.candidate import CareerPreferences
from career_agent.services.job_candidate_fit import (
    CandidateFitStatus,
    RoleFit,
    SeniorityFit,
    assess_candidate_fit,
)
from career_agent.services.job_relevance import (
    JobRelevanceAssessment,
    RelevanceStatus,
    RoleType,
    SeniorityLevel,
)


def make_preferences(
    target_roles: list[str] | None = None,
    experience_band: str = "junior_0_2",
    also_consider_years: str = "2_3_if_strong_fit",
) -> CareerPreferences:
    return CareerPreferences(
        target_roles=target_roles or [
            "Manual QA / QA Engineer",
            "API QA / API Testing",
            "Integration Testing / Integration QA",
            "Junior QA Automation",
        ],
        experience_band=experience_band,
        also_consider_years=also_consider_years,
    )


def make_relevance(
    role_type: RoleType = RoleType.SOFTWARE_QA,
    seniority: SeniorityLevel = SeniorityLevel.JUNIOR,
    status: RelevanceStatus = RelevanceStatus.RELEVANT,
) -> JobRelevanceAssessment:
    return JobRelevanceAssessment(
        status=status,
        role_type=role_type,
        seniority=seniority,
    )


def test_junior_qa_engineer_is_target_fit() -> None:
    result = assess_candidate_fit(
        make_relevance(),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.TARGET_FIT
    assert result.role_fit == RoleFit.MATCH
    assert result.seniority_fit == SeniorityFit.TARGET


def test_manual_qa_matches_target_role() -> None:
    result = assess_candidate_fit(
        make_relevance(role_type=RoleType.MANUAL_QA),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.TARGET_FIT
    assert result.matched_target_roles == ["Manual QA / QA Engineer"]


@pytest.mark.parametrize(
    "role_type",
    [
        RoleType.API_QA,
        RoleType.INTEGRATION_QA,
        RoleType.QA_AUTOMATION,
    ],
)
def test_other_explicit_target_qa_roles_match(role_type: RoleType) -> None:
    result = assess_candidate_fit(
        make_relevance(role_type=role_type),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.TARGET_FIT


def test_middle_role_is_potential_stretch_not_confirmed_fit() -> None:
    result = assess_candidate_fit(
        make_relevance(seniority=SeniorityLevel.MIDDLE),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.POTENTIAL_STRETCH
    assert result.seniority_fit == SeniorityFit.POTENTIAL_STRETCH
    assert any("actual years" in reason for reason in result.reasons)


def test_unknown_seniority_requires_review() -> None:
    result = assess_candidate_fit(
        make_relevance(seniority=SeniorityLevel.UNKNOWN),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.NEEDS_REVIEW
    assert result.seniority_fit == SeniorityFit.NEEDS_REVIEW


@pytest.mark.parametrize(
    "seniority",
    [
        SeniorityLevel.SENIOR,
        SeniorityLevel.LEAD,
        SeniorityLevel.PRINCIPAL,
        SeniorityLevel.MANAGER_EXECUTIVE,
    ],
)
def test_senior_and_leadership_roles_are_out_of_scope(
    seniority: SeniorityLevel,
) -> None:
    result = assess_candidate_fit(
        make_relevance(seniority=seniority),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.OUT_OF_SCOPE
    assert result.seniority_fit == SeniorityFit.TOO_SENIOR


def test_adjacent_qa_specialization_requires_review() -> None:
    result = assess_candidate_fit(
        make_relevance(
            role_type=RoleType.AI_EVALUATION,
            status=RelevanceStatus.NEEDS_REVIEW,
        ),
        make_preferences(),
    )

    assert result.status == CandidateFitStatus.NEEDS_REVIEW
    assert result.role_fit == RoleFit.NEEDS_REVIEW


def test_non_target_qa_specialization_is_out_of_scope() -> None:
    result = assess_candidate_fit(
        make_relevance(role_type=RoleType.SOFTWARE_QA),
        make_preferences(target_roles=["API QA / API Testing"]),
    )

    assert result.status == CandidateFitStatus.OUT_OF_SCOPE


def test_middle_without_stretch_preference_requires_review() -> None:
    result = assess_candidate_fit(
        make_relevance(seniority=SeniorityLevel.MIDDLE),
        make_preferences(also_consider_years=""),
    )

    assert result.status == CandidateFitStatus.NEEDS_REVIEW
    assert result.seniority_fit == SeniorityFit.NEEDS_REVIEW
