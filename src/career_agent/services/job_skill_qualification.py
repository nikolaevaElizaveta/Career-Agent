"""Assess whether verified candidate skills satisfy explicit job expectations."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_skill_matcher import (
    SkillAlternativeMatch,
    SkillMatchStatus,
    SkillRequirementMatch,
)


class ProficiencyFitStatus(StrEnum):
    MEETS_EXPECTATION = "meets_expectation"
    BELOW_EXPECTATION = "below_expectation"
    NOT_SPECIFIED = "not_specified"
    NEEDS_CONFIRMATION = "needs_confirmation"
    SKILL_MISSING = "skill_missing"


class CommercialExperienceFitStatus(StrEnum):
    MEETS_EXPLICIT_REQUIREMENT = "meets_explicit_requirement"
    DOES_NOT_MEET_EXPLICIT_REQUIREMENT = "does_not_meet_explicit_requirement"
    NOT_REQUIRED = "not_required"
    NEEDS_CONFIRMATION = "needs_confirmation"
    SKILL_MISSING = "skill_missing"


class SkillQualificationAssessment(BaseModel):
    requirement: str
    priority: str
    alternative_group: str | None = None
    candidate_skill: str | None = None
    profile_status: SkillMatchStatus
    candidate_level: str | None = None
    expected_minimum_level: str | None = None
    proficiency_fit: ProficiencyFitStatus
    commercial_experience_required: bool = False
    commercial_experience: bool | None = None
    commercial_experience_status: VerificationStatus | None = None
    commercial_fit: CommercialExperienceFitStatus
    evidence: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


_PROFICIENCY_ORDER = {
    "beginner": 0,
    "basic": 1,
    "intermediate": 2,
    "proficient": 3,
}


def _expected_minimum_level(evidence: list[str]) -> str | None:
    """Infer a minimum only from explicit level-related language.

    Conservative mappings:
    - familiar/basic knowledge -> basic
    - working knowledge/proficiency/strong ability -> intermediate
    - advanced/expert -> proficient

    Generic phrases such as 'experience with' do not imply a level.
    """
    text = " ".join(evidence).casefold()

    if re.search(r"\b(advanced|expert|expertise)\b", text):
        return "proficient"

    if re.search(
        r"\b(intermediate|working knowledge|proficien(?:t|cy)|"
        r"strong coding ability|strong proficiency)\b",
        text,
    ):
        return "intermediate"

    if re.search(
        r"\b(beginner|basic knowledge|basic understanding|"
        r"familiar with|familiarity with)\b",
        text,
    ):
        return "basic"

    return None


def _requires_commercial_experience(evidence: list[str]) -> bool:
    """Require commercial experience only when the employer states it."""
    text = " ".join(evidence).casefold()

    return bool(
        re.search(
            r"\b(commercial|professional|industry)\s+(?:work\s+)?experience\b"
            r"|\bexperience\s+in\s+(?:a\s+)?production\s+environment\b"
            r"|\bpaid\s+professional\s+experience\b",
            text,
        )
    )


def _assess_proficiency(
    match: SkillRequirementMatch,
    expected_level: str | None,
) -> tuple[ProficiencyFitStatus, list[str]]:
    if match.status is SkillMatchStatus.MISSING:
        return (
            ProficiencyFitStatus.SKILL_MISSING,
            ["The required skill is absent from Candidate Profile."],
        )

    if match.status is not SkillMatchStatus.CONFIRMED:
        return (
            ProficiencyFitStatus.NEEDS_CONFIRMATION,
            ["The candidate's skill information is not fully confirmed."],
        )

    if expected_level is None:
        return (
            ProficiencyFitStatus.NOT_SPECIFIED,
            ["The job description does not specify a minimum proficiency level."],
        )

    if match.proficiency not in _PROFICIENCY_ORDER:
        return (
            ProficiencyFitStatus.NEEDS_CONFIRMATION,
            ["The candidate's proficiency level is not available."],
        )

    actual = _PROFICIENCY_ORDER[match.proficiency]
    expected = _PROFICIENCY_ORDER[expected_level]

    if actual >= expected:
        return (
            ProficiencyFitStatus.MEETS_EXPECTATION,
            [
                f"Candidate level '{match.proficiency}' meets the explicitly "
                f"stated minimum '{expected_level}'."
            ],
        )

    return (
        ProficiencyFitStatus.BELOW_EXPECTATION,
        [
            f"Candidate level '{match.proficiency}' is below the explicitly "
            f"stated minimum '{expected_level}'."
        ],
    )


def _assess_commercial_experience(
    match: SkillRequirementMatch,
    required: bool,
) -> tuple[CommercialExperienceFitStatus, list[str]]:
    if not required:
        return (
            CommercialExperienceFitStatus.NOT_REQUIRED,
            ["The job description does not explicitly require commercial experience."],
        )

    if match.status is SkillMatchStatus.MISSING:
        return (
            CommercialExperienceFitStatus.SKILL_MISSING,
            ["The skill itself is absent from Candidate Profile."],
        )

    if (
        match.commercial_experience_status
        is not VerificationStatus.CONFIRMED
    ):
        return (
            CommercialExperienceFitStatus.NEEDS_CONFIRMATION,
            ["Commercial experience for this skill is not confirmed."],
        )

    if match.commercial_experience is True:
        return (
            CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT,
            ["Commercial experience is confirmed."],
        )

    return (
        CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT,
        ["The candidate confirmed no commercial experience with this skill."],
    )


def assess_skill_requirement(
    match: SkillRequirementMatch,
    *,
    alternative_group: str | None = None,
) -> SkillQualificationAssessment:
    """Assess profile evidence against explicit proficiency and experience cues."""
    expected_level = _expected_minimum_level(match.evidence)
    commercial_required = _requires_commercial_experience(match.evidence)

    proficiency_fit, proficiency_reasons = _assess_proficiency(
        match,
        expected_level,
    )
    commercial_fit, commercial_reasons = _assess_commercial_experience(
        match,
        commercial_required,
    )

    return SkillQualificationAssessment(
        requirement=match.requirement,
        priority=match.priority.value,
        alternative_group=alternative_group,
        candidate_skill=match.candidate_skill,
        profile_status=match.status,
        candidate_level=match.proficiency,
        expected_minimum_level=expected_level,
        proficiency_fit=proficiency_fit,
        commercial_experience_required=commercial_required,
        commercial_experience=match.commercial_experience,
        commercial_experience_status=match.commercial_experience_status,
        commercial_fit=commercial_fit,
        evidence=match.evidence,
        reasons=proficiency_reasons + commercial_reasons,
    )

class SkillAlternativeQualificationAssessment(BaseModel):
    """Aggregate qualification results for an any-of skill requirement."""

    requirement: str
    priority: str
    match_rule: str
    proficiency_fit: ProficiencyFitStatus
    commercial_experience_required: bool
    commercial_fit: CommercialExperienceFitStatus
    option_qualifications: list[SkillQualificationAssessment] = Field(
        default_factory=list
    )
    missing_options: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def assess_skill_alternative_group(
    group: SkillAlternativeMatch,
) -> SkillAlternativeQualificationAssessment:
    """Assess an alternative group without treating every option as mandatory."""
    requirement = " OR ".join(group.skills)
    options = [
        assess_skill_requirement(
            option,
            alternative_group=requirement,
        )
        for option in group.matched_options
    ]
    commercial_required = _requires_commercial_experience(group.evidence)

    if group.match_rule != "any_of":
        proficiency_fit = ProficiencyFitStatus.NEEDS_CONFIRMATION
        proficiency_reason = (
            f"Matching rule '{group.match_rule}' is not supported for "
            "automatic group qualification."
        )
    elif not options:
        proficiency_fit = ProficiencyFitStatus.SKILL_MISSING
        proficiency_reason = (
            "None of the alternative skills is present in Candidate Profile."
        )
    elif any(
        item.proficiency_fit is ProficiencyFitStatus.MEETS_EXPECTATION
        for item in options
    ):
        proficiency_fit = ProficiencyFitStatus.MEETS_EXPECTATION
        proficiency_reason = (
            "At least one confirmed option meets the explicitly stated "
            "minimum proficiency level."
        )
    elif any(
        item.profile_status is SkillMatchStatus.CONFIRMED
        and item.proficiency_fit is ProficiencyFitStatus.NOT_SPECIFIED
        for item in options
    ):
        proficiency_fit = ProficiencyFitStatus.NOT_SPECIFIED
        proficiency_reason = (
            "At least one option is confirmed in Candidate Profile, "
            "but the employer did not specify a minimum proficiency level."
        )
    elif any(
        item.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION
        for item in options
    ):
        proficiency_fit = ProficiencyFitStatus.NEEDS_CONFIRMATION
        proficiency_reason = (
            "At least one available option needs confirmation before "
            "the group can be assessed reliably."
        )
    elif all(
        item.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION
        for item in options
    ):
        proficiency_fit = ProficiencyFitStatus.BELOW_EXPECTATION
        proficiency_reason = (
            "None of the profile-listed options meets the explicitly "
            "stated minimum proficiency level."
        )
    else:
        proficiency_fit = ProficiencyFitStatus.NEEDS_CONFIRMATION
        proficiency_reason = (
            "The available option data is insufficient to assess this group."
        )

    if not commercial_required:
        commercial_fit = CommercialExperienceFitStatus.NOT_REQUIRED
        commercial_reason = (
            "The employer does not explicitly require commercial experience."
        )
    elif group.match_rule != "any_of":
        commercial_fit = CommercialExperienceFitStatus.NEEDS_CONFIRMATION
        commercial_reason = (
            "Commercial experience cannot be aggregated safely because "
            f"the matching rule '{group.match_rule}' is unsupported."
        )
    elif not options:
        commercial_fit = CommercialExperienceFitStatus.SKILL_MISSING
        commercial_reason = (
            "No alternative skill is present in Candidate Profile."
        )
    elif any(
        item.commercial_fit
        is CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT
        for item in options
    ):
        commercial_fit = (
            CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT
        )
        commercial_reason = (
            "At least one available option has confirmed commercial experience."
        )
    elif any(
        item.commercial_fit
        is CommercialExperienceFitStatus.NEEDS_CONFIRMATION
        for item in options
    ):
        commercial_fit = CommercialExperienceFitStatus.NEEDS_CONFIRMATION
        commercial_reason = (
            "Commercial experience for at least one available option "
            "needs confirmation."
        )
    elif all(
        item.commercial_fit
        is CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT
        for item in options
    ):
        commercial_fit = (
            CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT
        )
        commercial_reason = (
            "None of the profile-listed options has the explicitly "
            "required commercial experience."
        )
    else:
        commercial_fit = CommercialExperienceFitStatus.NEEDS_CONFIRMATION
        commercial_reason = (
            "The available commercial-experience data is insufficient."
        )

    matched_names = {
        option.requirement
        for option in group.matched_options
    }
    missing_options = [
        name for name in group.skills
        if name not in matched_names
    ]

    return SkillAlternativeQualificationAssessment(
        requirement=requirement,
        priority=group.priority.value,
        match_rule=group.match_rule,
        proficiency_fit=proficiency_fit,
        commercial_experience_required=commercial_required,
        commercial_fit=commercial_fit,
        option_qualifications=options,
        missing_options=missing_options,
        reasons=[proficiency_reason, commercial_reason],
    )
