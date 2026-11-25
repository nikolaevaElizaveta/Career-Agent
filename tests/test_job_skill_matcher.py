from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.services.job_requirements import (
    JobRequirements,
    RequirementPriority,
    SkillAlternativeGroup,
    SkillRequirement,
)
from career_agent.services.job_skill_matcher import (
    SkillMatchStatus,
    match_job_skills,
)


def make_skill(
    name: str,
    *,
    proficiency: str | None = None,
    proficiency_status: VerificationStatus = VerificationStatus.UNKNOWN,
    commercial_experience: bool | None = None,
    commercial_status: VerificationStatus = VerificationStatus.UNKNOWN,
) -> SkillItem:
    return SkillItem(
        name=name,
        category="testing",
        proficiency=ProfileField[str](
            value=proficiency,
            status=proficiency_status,
        ),
        commercial_experience=ProfileField[bool](
            value=commercial_experience,
            status=commercial_status,
        ),
    )


def make_requirements(
    *,
    required: list[str] | None = None,
    preferred: list[str] | None = None,
    unspecified: list[str] | None = None,
    alternatives: list[list[str]] | None = None,
) -> JobRequirements:
    return JobRequirements(
        required_skills=[
            SkillRequirement(
                name=name,
                priority=RequirementPriority.REQUIRED,
                evidence=[f"Required: {name}"],
                sections=["required"],
            )
            for name in (required or [])
        ],
        preferred_skills=[
            SkillRequirement(
                name=name,
                priority=RequirementPriority.PREFERRED,
                evidence=[f"Preferred: {name}"],
                sections=["preferred"],
            )
            for name in (preferred or [])
        ],
        unspecified_skills=[
            SkillRequirement(
                name=name,
                priority=RequirementPriority.UNSPECIFIED,
                evidence=[f"Mentioned: {name}"],
                sections=["responsibilities"],
            )
            for name in (unspecified or [])
        ],
        alternative_skill_groups=[
            SkillAlternativeGroup(
                skills=group,
                match_rule="any_of",
                priority=RequirementPriority.REQUIRED,
                evidence=["Choose at least one option"],
                sections=["required"],
            )
            for group in (alternatives or [])
        ],
    )


def test_unknown_profile_skill_is_listed_but_unverified() -> None:
    requirements = make_requirements(required=["Postman"])
    skills = [make_skill("Postman")]

    result = match_job_skills(requirements, skills)

    match = result.required_skills[0]
    assert match.status == SkillMatchStatus.LISTED_UNVERIFIED
    assert match.candidate_skill == "Postman"
    assert match.proficiency_status == VerificationStatus.UNKNOWN


def test_confirmed_skill_is_matched_as_confirmed() -> None:
    requirements = make_requirements(required=["Python"])
    skills = [
        make_skill(
            "Python",
            proficiency="intermediate",
            proficiency_status=VerificationStatus.CONFIRMED,
        )
    ]

    result = match_job_skills(requirements, skills)

    assert result.required_skills[0].status == SkillMatchStatus.CONFIRMED
    assert result.required_skills[0].proficiency == "intermediate"


def test_commercial_experience_is_reported_separately() -> None:
    requirements = make_requirements(required=["SQL"])
    skills = [
        make_skill(
            "SQL",
            proficiency="basic",
            proficiency_status=VerificationStatus.CONFIRMED,
            commercial_experience=False,
            commercial_status=VerificationStatus.CONFIRMED,
        )
    ]

    result = match_job_skills(requirements, skills)
    match = result.required_skills[0]

    assert match.status == SkillMatchStatus.CONFIRMED
    assert match.commercial_experience is False
    assert (
        match.commercial_experience_status
        == VerificationStatus.CONFIRMED
    )


def test_needs_confirmation_status_is_preserved() -> None:
    requirements = make_requirements(required=["Kafka"])
    skills = [
        make_skill(
            "Kafka",
            proficiency="basic",
            proficiency_status=VerificationStatus.NEEDS_CONFIRMATION,
        )
    ]

    result = match_job_skills(requirements, skills)

    assert (
        result.required_skills[0].status
        == SkillMatchStatus.NEEDS_CONFIRMATION
    )


def test_imported_from_cv_is_not_treated_as_confirmed() -> None:
    requirements = make_requirements(required=["Java"])
    skills = [
        make_skill(
            "Java",
            proficiency="basic",
            proficiency_status=VerificationStatus.IMPORTED_FROM_CV,
        )
    ]

    result = match_job_skills(requirements, skills)

    assert (
        result.required_skills[0].status
        == SkillMatchStatus.IMPORTED_FROM_CV
    )


def test_missing_skill_is_reported() -> None:
    requirements = make_requirements(required=["Selenium"])

    result = match_job_skills(requirements, [])

    assert result.required_skills[0].status == SkillMatchStatus.MISSING
    assert result.required_skills[0].candidate_skill is None


def test_sql_does_not_automatically_match_mysql() -> None:
    requirements = make_requirements(required=["MySQL"])
    skills = [make_skill("SQL")]

    result = match_job_skills(requirements, skills)

    assert result.required_skills[0].status == SkillMatchStatus.MISSING


def test_normalization_ignores_case_and_extra_spaces() -> None:
    requirements = make_requirements(required=["JavaScript"])
    skills = [make_skill("  javascript  ")]

    result = match_job_skills(requirements, skills)

    assert (
        result.required_skills[0].status
        == SkillMatchStatus.LISTED_UNVERIFIED
    )


def test_any_of_group_matches_one_listed_option() -> None:
    requirements = make_requirements(
        alternatives=[["Java", "Python", "JavaScript"]]
    )
    skills = [make_skill("Java")]

    result = match_job_skills(requirements, skills)

    group = result.alternative_groups[0]
    assert group.status == SkillMatchStatus.LISTED_UNVERIFIED
    assert [item.candidate_skill for item in group.matched_options] == ["Java"]


def test_any_of_group_is_confirmed_if_one_option_is_confirmed() -> None:
    requirements = make_requirements(
        alternatives=[["Java", "Python", "JavaScript"]]
    )
    skills = [
        make_skill(
            "Python",
            proficiency="intermediate",
            proficiency_status=VerificationStatus.CONFIRMED,
        ),
        make_skill("Java"),
    ]

    result = match_job_skills(requirements, skills)

    assert (
        result.alternative_groups[0].status
        == SkillMatchStatus.CONFIRMED
    )


def test_any_of_group_is_missing_if_no_options_are_listed() -> None:
    requirements = make_requirements(
        alternatives=[["Selenium", "Appium", "Playwright"]]
    )

    result = match_job_skills(requirements, [])

    assert result.alternative_groups[0].status == SkillMatchStatus.MISSING
    assert result.alternative_groups[0].matched_options == []


def test_requirement_evidence_is_preserved() -> None:
    requirements = make_requirements(required=["Postman"])
    skills = [make_skill("Postman")]

    result = match_job_skills(requirements, skills)

    assert result.required_skills[0].evidence == ["Required: Postman"]


def test_duplicate_profile_entries_prefer_confirmed_record() -> None:
    requirements = make_requirements(required=["Python"])
    skills = [
        make_skill("Python"),
        make_skill(
            "Python",
            proficiency="intermediate",
            proficiency_status=VerificationStatus.CONFIRMED,
        ),
    ]

    result = match_job_skills(requirements, skills)

    assert result.required_skills[0].status == SkillMatchStatus.CONFIRMED


def test_report_counts_requirement_groups() -> None:
    requirements = make_requirements(
        required=["SQL", "Postman"],
        preferred=["Docker"],
        unspecified=["Kafka"],
        alternatives=[["Java", "Python"]],
    )

    result = match_job_skills(requirements, [])

    assert result.total_requirements == 5
