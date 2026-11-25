"""Find explicitly configured relationships between job and profile skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_requirements import JobRequirements
from career_agent.services.job_skill_matcher import SkillMatchStatus


class SkillRelationshipType(StrEnum):
    PARTIAL_OVERLAP = "partial_overlap"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    RELATED = "related"


@dataclass(frozen=True)
class SkillRelationshipRule:
    requirement: str
    candidate_skill: str
    relationship_type: SkillRelationshipType
    rationale: str


class RelatedSkillEvidence(BaseModel):
    requirement: str
    priority: str
    candidate_skill: str
    relationship_type: SkillRelationshipType
    profile_status: SkillMatchStatus
    candidate_level: str | None = None
    proficiency_status: VerificationStatus
    commercial_experience: bool | None = None
    commercial_experience_status: VerificationStatus
    rationale: str
    counts_as_skill_match: bool = False


SKILL_RELATIONSHIP_RULES = (
    SkillRelationshipRule(
        requirement="API testing",
        candidate_skill="Postman",
        relationship_type=SkillRelationshipType.SUPPORTING_EVIDENCE,
        rationale=(
            "Postman experience supports API-testing evidence, but "
            "knowledge of the tool alone does not prove the full competency."
        ),
    ),
    SkillRelationshipRule(
        requirement="Test cases and test plans",
        candidate_skill="Test case design and execution",
        relationship_type=SkillRelationshipType.PARTIAL_OVERLAP,
        rationale=(
            "Test case design and execution overlap with part of this "
            "requirement, but do not by themselves confirm ownership of "
            "test plans or case reviews."
        ),
    ),
    SkillRelationshipRule(
        requirement="AI familiarity",
        candidate_skill="AI-assisted testing",
        relationship_type=SkillRelationshipType.SUPPORTING_EVIDENCE,
        rationale=(
            "Practical use of AI tools in testing supports familiarity "
            "with AI in that context, but does not establish broader AI "
            "familiarity."
        ),
    ),
)


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def _profile_status(status: VerificationStatus) -> SkillMatchStatus:
    mapping = {
        VerificationStatus.CONFIRMED: SkillMatchStatus.CONFIRMED,
        VerificationStatus.IMPORTED_FROM_CV: SkillMatchStatus.IMPORTED_FROM_CV,
        VerificationStatus.NEEDS_CONFIRMATION: SkillMatchStatus.NEEDS_CONFIRMATION,
        VerificationStatus.UNKNOWN: SkillMatchStatus.LISTED_UNVERIFIED,
    }
    return mapping[status]


def _requirement_priorities(
    requirements: JobRequirements,
) -> dict[str, str]:
    priorities: dict[str, str] = {}

    for collection in (
        requirements.required_skills,
        requirements.preferred_skills,
        requirements.unspecified_skills,
    ):
        for item in collection:
            priorities[_normalize(item.name)] = item.priority.value

    for group in requirements.alternative_skill_groups:
        for skill_name in group.skills:
            priorities[_normalize(skill_name)] = group.priority.value

    return priorities


def _candidate_skill_index(
    candidate_skills: list[SkillItem],
) -> dict[str, list[SkillItem]]:
    index: dict[str, list[SkillItem]] = {}

    for skill in candidate_skills:
        key = _normalize(skill.name)
        if key:
            index.setdefault(key, []).append(skill)

    return index


def find_related_skill_evidence(
    requirements: JobRequirements,
    candidate_skills: list[SkillItem],
) -> list[RelatedSkillEvidence]:
    """Return supporting or partially overlapping evidence, never exact matches."""
    priorities = _requirement_priorities(requirements)
    candidate_index = _candidate_skill_index(candidate_skills)

    verification_rank = {
        VerificationStatus.CONFIRMED: 4,
        VerificationStatus.NEEDS_CONFIRMATION: 3,
        VerificationStatus.IMPORTED_FROM_CV: 2,
        VerificationStatus.UNKNOWN: 1,
    }

    results: list[RelatedSkillEvidence] = []

    for rule in SKILL_RELATIONSHIP_RULES:
        requirement_key = _normalize(rule.requirement)
        priority = priorities.get(requirement_key)

        if priority is None:
            continue

        candidates = candidate_index.get(
            _normalize(rule.candidate_skill),
            [],
        )
        if not candidates:
            continue

        candidate = max(
            candidates,
            key=lambda item: verification_rank[item.proficiency.status],
        )

        results.append(
            RelatedSkillEvidence(
                requirement=rule.requirement,
                priority=priority,
                candidate_skill=candidate.name,
                relationship_type=rule.relationship_type,
                profile_status=_profile_status(candidate.proficiency.status),
                candidate_level=candidate.proficiency.value,
                proficiency_status=candidate.proficiency.status,
                commercial_experience=candidate.commercial_experience.value,
                commercial_experience_status=(
                    candidate.commercial_experience.status
                ),
                rationale=rule.rationale,
                counts_as_skill_match=False,
            )
        )

    return results
