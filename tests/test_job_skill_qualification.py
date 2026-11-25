from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_skill_matcher import (
    SkillMatchStatus,
    SkillRequirementMatch,
)
from career_agent.services.job_skill_qualification import (
    CommercialExperienceFitStatus,
    ProficiencyFitStatus,
    assess_skill_requirement,
)


def make_match(
    requirement: str,
    *,
    candidate_skill: str | None = "Java",
    status: SkillMatchStatus = SkillMatchStatus.CONFIRMED,
    proficiency: str | None = "basic",
    commercial_experience: bool | None = False,
    commercial_status: VerificationStatus = VerificationStatus.CONFIRMED,
) -> SkillRequirementMatch:
    return SkillRequirementMatch(
        requirement=requirement,
        priority="required",
        status=status,
        candidate_skill=candidate_skill,
        proficiency=proficiency,
        proficiency_status=VerificationStatus.CONFIRMED,
        commercial_experience=commercial_experience,
        commercial_experience_status=commercial_status,
        evidence=[requirement],
    )


def test_basic_level_meets_familiarity_requirement() -> None:
    match = make_match("Familiar with Java")

    result = assess_skill_requirement(match)

    assert result.expected_minimum_level == "basic"
    assert result.proficiency_fit is ProficiencyFitStatus.MEETS_EXPECTATION


def test_basic_level_does_not_meet_strong_coding_requirement() -> None:
    match = make_match("Strong coding ability in Java")

    result = assess_skill_requirement(match)

    assert result.expected_minimum_level == "intermediate"
    assert result.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION


def test_generic_experience_does_not_invent_proficiency_threshold() -> None:
    match = make_match("Experience with Git")

    result = assess_skill_requirement(match)

    assert result.expected_minimum_level is None
    assert result.proficiency_fit is ProficiencyFitStatus.NOT_SPECIFIED
    assert result.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED


def test_intermediate_level_meets_proficiency_requirement() -> None:
    match = make_match(
        "Proficiency in SQL",
        candidate_skill="SQL",
        proficiency="intermediate",
        commercial_experience=True,
    )

    result = assess_skill_requirement(match)

    assert result.expected_minimum_level == "intermediate"
    assert result.proficiency_fit is ProficiencyFitStatus.MEETS_EXPECTATION


def test_no_commercial_experience_fails_explicit_professional_requirement() -> None:
    match = make_match(
        "Professional experience with Postman",
        candidate_skill="Postman",
        proficiency="intermediate",
        commercial_experience=False,
    )

    result = assess_skill_requirement(match)

    assert result.commercial_experience_required is True
    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT
    )


def test_confirmed_commercial_experience_meets_explicit_requirement() -> None:
    match = make_match(
        "Commercial experience with Postman",
        candidate_skill="Postman",
        proficiency="intermediate",
        commercial_experience=True,
    )

    result = assess_skill_requirement(match)

    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT
    )


def test_unconfirmed_commercial_experience_needs_review() -> None:
    match = make_match(
        "Professional experience with Postman",
        commercial_experience=None,
        commercial_status=VerificationStatus.UNKNOWN,
    )

    result = assess_skill_requirement(match)

    assert (
        result.commercial_fit
        is CommercialExperienceFitStatus.NEEDS_CONFIRMATION
    )


def test_missing_skill_is_not_treated_as_a_proficiency_match() -> None:
    match = make_match(
        "Familiar with Java",
        candidate_skill=None,
        status=SkillMatchStatus.MISSING,
        proficiency=None,
        commercial_experience=None,
        commercial_status=VerificationStatus.UNKNOWN,
    )

    result = assess_skill_requirement(match)

    assert result.proficiency_fit is ProficiencyFitStatus.SKILL_MISSING
    assert result.commercial_fit is CommercialExperienceFitStatus.NOT_REQUIRED


def test_unverified_skill_does_not_pass_proficiency_requirement() -> None:
    match = make_match(
        "Familiar with Java",
        status=SkillMatchStatus.LISTED_UNVERIFIED,
        proficiency=None,
        commercial_status=VerificationStatus.UNKNOWN,
    )

    result = assess_skill_requirement(match)

    assert result.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION
