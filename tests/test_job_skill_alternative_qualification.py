from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_requirements import RequirementPriority
from career_agent.services.job_skill_matcher import (
    SkillAlternativeMatch,
    SkillMatchStatus,
    SkillRequirementMatch,
)
from career_agent.services.job_skill_qualification import (
    CommercialExperienceFitStatus,
    ProficiencyFitStatus,
    assess_skill_alternative_group,
)


def make_option(
    name: str,
    level: str,
    *,
    proficiency_status: VerificationStatus = VerificationStatus.CONFIRMED,
    commercial_experience: bool = False,
    commercial_status: VerificationStatus = VerificationStatus.CONFIRMED,
    evidence: list[str] | None = None,
) -> SkillRequirementMatch:
    match_status = {
        VerificationStatus.CONFIRMED: SkillMatchStatus.CONFIRMED,
        VerificationStatus.NEEDS_CONFIRMATION: SkillMatchStatus.NEEDS_CONFIRMATION,
        VerificationStatus.IMPORTED_FROM_CV: SkillMatchStatus.IMPORTED_FROM_CV,
        VerificationStatus.UNKNOWN: SkillMatchStatus.LISTED_UNVERIFIED,
    }[proficiency_status]

    return SkillRequirementMatch(
        requirement=name,
        priority=RequirementPriority.REQUIRED,
        status=match_status,
        candidate_skill=name,
        proficiency=level,
        proficiency_status=proficiency_status,
        commercial_experience=commercial_experience,
        commercial_experience_status=commercial_status,
        evidence=evidence or [],
    )


def make_group(
    skills: list[str],
    options: list[SkillRequirementMatch],
    evidence: list[str],
    *,
    match_rule: str = "any_of",
) -> SkillAlternativeMatch:
    status = (
        SkillMatchStatus.CONFIRMED
        if any(
            option.status is SkillMatchStatus.CONFIRMED
            for option in options
        )
        else SkillMatchStatus.LISTED_UNVERIFIED
        if options
        else SkillMatchStatus.MISSING
    )

    return SkillAlternativeMatch(
        skills=skills,
        match_rule=match_rule,
        priority=RequirementPriority.REQUIRED,
        status=status,
        matched_options=options,
        evidence=evidence,
    )


def test_any_of_group_meets_level_when_one_option_is_sufficient() -> None:
    evidence = [
        "Strong coding ability in at least one of Python, Java, or JavaScript"
    ]
    group = make_group(
        ["Python", "Java", "JavaScript"],
        [
            make_option("Python", "basic", evidence=evidence),
            make_option("Java", "intermediate", evidence=evidence),
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.MEETS_EXPECTATION
    assert result.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED
    assert result.missing_options == ["JavaScript"]


def test_any_of_group_is_below_expectation_when_all_options_are_too_basic() -> None:
    evidence = ["Strong coding ability in at least one of Python or Java"]
    group = make_group(
        ["Python", "Java"],
        [
            make_option("Python", "basic", evidence=evidence),
            make_option("Java", "basic", evidence=evidence),
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION


def test_any_of_group_needs_confirmation_when_an_option_could_qualify() -> None:
    evidence = ["Strong coding ability in at least one of Python or Java"]
    group = make_group(
        ["Python", "Java"],
        [
            make_option("Python", "basic", evidence=evidence),
            make_option(
                "Java",
                "intermediate",
                proficiency_status=VerificationStatus.NEEDS_CONFIRMATION,
                evidence=evidence,
            ),
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION


def test_any_of_group_reports_unspecified_level_without_inventing_threshold() -> None:
    evidence = ["Programming experience in Python or Java"]
    group = make_group(
        ["Python", "Java"],
        [make_option("Python", "basic", evidence=evidence)],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.NOT_SPECIFIED
    assert result.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED


def test_any_of_group_is_missing_when_no_option_is_in_profile() -> None:
    evidence = ["Strong coding ability in at least one of Python or Java"]
    group = make_group(
        ["Python", "Java"],
        [],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.SKILL_MISSING
    assert result.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED
    assert result.missing_options == ["Python", "Java"]


def test_any_of_group_fails_explicit_commercial_requirement() -> None:
    evidence = ["Professional experience with Postman or Selenium"]
    group = make_group(
        ["Postman", "Selenium"],
        [
            make_option(
                "Postman",
                "intermediate",
                commercial_experience=False,
                evidence=evidence,
            )
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert result.commercial_experience_required is True
    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT
    )


def test_any_of_group_meets_commercial_requirement_if_one_option_does() -> None:
    evidence = ["Professional experience with Postman or Selenium"]
    group = make_group(
        ["Postman", "Selenium"],
        [
            make_option(
                "Postman",
                "intermediate",
                commercial_experience=False,
                evidence=evidence,
            ),
            make_option(
                "Selenium",
                "basic",
                commercial_experience=True,
                evidence=evidence,
            ),
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT
    )


def test_any_of_group_needs_confirmation_for_unknown_commercial_experience() -> None:
    evidence = ["Professional experience with Postman or Selenium"]
    group = make_group(
        ["Postman", "Selenium"],
        [
            make_option(
                "Postman",
                "intermediate",
                commercial_experience=True,
                commercial_status=VerificationStatus.UNKNOWN,
                evidence=evidence,
            )
        ],
        evidence,
    )

    result = assess_skill_alternative_group(group)

    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.NEEDS_CONFIRMATION
    )


def test_unsupported_group_rule_needs_review() -> None:
    evidence = ["Strong coding ability in at least one of Python or Java"]
    group = make_group(
        ["Python", "Java"],
        [make_option("Python", "intermediate", evidence=evidence)],
        evidence,
        match_rule="all_of",
    )

    result = assess_skill_alternative_group(group)

    assert result.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION
