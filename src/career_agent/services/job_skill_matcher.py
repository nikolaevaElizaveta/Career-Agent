"""Match extracted job requirements against verified candidate skills."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_requirements import (
    JobRequirements,
    RequirementPriority,
    SkillAlternativeGroup,
    SkillRequirement,
)


class SkillMatchStatus(StrEnum):
    CONFIRMED = "confirmed"
    LISTED_UNVERIFIED = "listed_unverified"
    NEEDS_CONFIRMATION = "needs_confirmation"
    IMPORTED_FROM_CV = "imported_from_cv"
    MISSING = "missing"


class SkillRequirementMatch(BaseModel):
    requirement: str
    priority: RequirementPriority
    status: SkillMatchStatus
    candidate_skill: str | None = None
    proficiency: str | None = None
    proficiency_status: VerificationStatus | None = None
    commercial_experience: bool | None = None
    commercial_experience_status: VerificationStatus | None = None
    evidence: list[str] = Field(default_factory=list)


class SkillAlternativeMatch(BaseModel):
    skills: list[str]
    match_rule: str
    priority: RequirementPriority
    status: SkillMatchStatus
    matched_options: list[SkillRequirementMatch] = Field(
        default_factory=list
    )
    evidence: list[str] = Field(default_factory=list)


class JobSkillMatchReport(BaseModel):
    required_skills: list[SkillRequirementMatch] = Field(
        default_factory=list
    )
    preferred_skills: list[SkillRequirementMatch] = Field(
        default_factory=list
    )
    unspecified_skills: list[SkillRequirementMatch] = Field(
        default_factory=list
    )
    alternative_groups: list[SkillAlternativeMatch] = Field(
        default_factory=list
    )

    @property
    def total_requirements(self) -> int:
        return (
            len(self.required_skills)
            + len(self.preferred_skills)
            + len(self.unspecified_skills)
            + len(self.alternative_groups)
        )


def _normalize_skill_name(value: str) -> str:
    """Normalize spacing and punctuation without merging distinct skills."""
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def _build_skill_index(
    candidate_skills: list[SkillItem],
) -> dict[str, list[SkillItem]]:
    index: dict[str, list[SkillItem]] = {}

    for skill in candidate_skills:
        key = _normalize_skill_name(skill.name)
        if key:
            index.setdefault(key, []).append(skill)

    return index


def _status_from_profile_field(
    status: VerificationStatus,
) -> SkillMatchStatus:
    mapping = {
        VerificationStatus.CONFIRMED: SkillMatchStatus.CONFIRMED,
        VerificationStatus.IMPORTED_FROM_CV: SkillMatchStatus.IMPORTED_FROM_CV,
        VerificationStatus.NEEDS_CONFIRMATION: SkillMatchStatus.NEEDS_CONFIRMATION,
        VerificationStatus.UNKNOWN: SkillMatchStatus.LISTED_UNVERIFIED,
    }
    return mapping[status]


def _match_skill(
    requirement: SkillRequirement,
    skill_index: dict[str, list[SkillItem]],
) -> SkillRequirementMatch:
    key = _normalize_skill_name(requirement.name)
    candidates = skill_index.get(key, [])

    if not candidates:
        return SkillRequirementMatch(
            requirement=requirement.name,
            priority=requirement.priority,
            status=SkillMatchStatus.MISSING,
            evidence=requirement.evidence,
        )

    # If duplicate entries exist, prefer the most trustworthy record.
    rank = {
        VerificationStatus.CONFIRMED: 4,
        VerificationStatus.NEEDS_CONFIRMATION: 3,
        VerificationStatus.IMPORTED_FROM_CV: 2,
        VerificationStatus.UNKNOWN: 1,
    }

    candidate = max(
        candidates,
        key=lambda item: rank[item.proficiency.status],
    )
    proficiency = candidate.proficiency
    commercial = candidate.commercial_experience

    return SkillRequirementMatch(
        requirement=requirement.name,
        priority=requirement.priority,
        status=_status_from_profile_field(proficiency.status),
        candidate_skill=candidate.name,
        proficiency=proficiency.value,
        proficiency_status=proficiency.status,
        commercial_experience=commercial.value,
        commercial_experience_status=commercial.status,
        evidence=requirement.evidence,
    )


def _combine_option_statuses(
    matches: list[SkillRequirementMatch],
) -> SkillMatchStatus:
    """An any-of group is confirmed when at least one option is confirmed."""
    statuses = {item.status for item in matches}

    if SkillMatchStatus.CONFIRMED in statuses:
        return SkillMatchStatus.CONFIRMED
    if SkillMatchStatus.NEEDS_CONFIRMATION in statuses:
        return SkillMatchStatus.NEEDS_CONFIRMATION
    if SkillMatchStatus.IMPORTED_FROM_CV in statuses:
        return SkillMatchStatus.IMPORTED_FROM_CV
    if SkillMatchStatus.LISTED_UNVERIFIED in statuses:
        return SkillMatchStatus.LISTED_UNVERIFIED
    return SkillMatchStatus.MISSING


def _match_alternative_group(
    group: SkillAlternativeGroup,
    skill_index: dict[str, list[SkillItem]],
) -> SkillAlternativeMatch:
    options = [
        _match_skill(
            SkillRequirement(
                name=name,
                priority=group.priority,
                evidence=group.evidence,
                sections=group.sections,
            ),
            skill_index,
        )
        for name in group.skills
    ]

    matched = [
        item for item in options
        if item.status is not SkillMatchStatus.MISSING
    ]

    if group.match_rule != "any_of":
        status = SkillMatchStatus.NEEDS_CONFIRMATION
    else:
        status = _combine_option_statuses(options)

    return SkillAlternativeMatch(
        skills=group.skills,
        match_rule=group.match_rule,
        priority=group.priority,
        status=status,
        matched_options=matched,
        evidence=group.evidence,
    )


def match_job_skills(
    requirements: JobRequirements,
    candidate_skills: list[SkillItem],
) -> JobSkillMatchReport:
    """Compare extracted skill requirements with Candidate Profile skills.

    Only exact normalized names are matched. Related technologies and
    transferable skills are deliberately not inferred.
    """
    skill_index = _build_skill_index(candidate_skills)

    return JobSkillMatchReport(
        required_skills=[
            _match_skill(item, skill_index)
            for item in requirements.required_skills
        ],
        preferred_skills=[
            _match_skill(item, skill_index)
            for item in requirements.preferred_skills
        ],
        unspecified_skills=[
            _match_skill(item, skill_index)
            for item in requirements.unspecified_skills
        ],
        alternative_groups=[
            _match_alternative_group(item, skill_index)
            for item in requirements.alternative_skill_groups
        ],
    )
