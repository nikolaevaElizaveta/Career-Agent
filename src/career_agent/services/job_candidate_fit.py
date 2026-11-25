"""Candidate-specific role and seniority fit assessment."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.candidate import CareerPreferences
from career_agent.services.job_relevance import (
    JobRelevanceAssessment,
    RelevanceStatus,
    RoleType,
    SeniorityLevel,
)


class CandidateFitStatus(StrEnum):
    TARGET_FIT = "target_fit"
    POTENTIAL_STRETCH = "potential_stretch"
    NEEDS_REVIEW = "needs_review"
    OUT_OF_SCOPE = "out_of_scope"


class RoleFit(StrEnum):
    MATCH = "match"
    NEEDS_REVIEW = "needs_review"
    OUT_OF_SCOPE = "out_of_scope"


class SeniorityFit(StrEnum):
    TARGET = "target"
    POTENTIAL_STRETCH = "potential_stretch"
    NEEDS_REVIEW = "needs_review"
    TOO_SENIOR = "too_senior"


class CandidateFitAssessment(BaseModel):
    status: CandidateFitStatus
    role_fit: RoleFit
    seniority_fit: SeniorityFit
    matched_target_roles: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _supported_target_roles(
    preferences: CareerPreferences,
) -> dict[RoleType, list[str]]:
    """Translate human-readable profile preferences into known role types."""
    result: dict[RoleType, list[str]] = {}

    for target in preferences.target_roles:
        normalized = re.sub(r"[-_/]+", " ", target.casefold())
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if re.search(r"\bmanual\s+qa\b", normalized):
            result.setdefault(RoleType.MANUAL_QA, []).append(target)

        if re.search(r"\bqa\s+engineer\b|\bsoftware\s+qa\b", normalized):
            result.setdefault(RoleType.SOFTWARE_QA, []).append(target)

        if re.search(r"\bapi\s+(?:qa|testing)\b", normalized):
            result.setdefault(RoleType.API_QA, []).append(target)

        if re.search(r"\bintegration\s+(?:testing|qa)\b", normalized):
            result.setdefault(RoleType.INTEGRATION_QA, []).append(target)

        if re.search(
            r"\b(?:qa\s+automation|test\s+automation|automation\s+qa|sdet)\b",
            normalized,
        ):
            result.setdefault(RoleType.QA_AUTOMATION, []).append(target)

    return result


def _assess_seniority(
    seniority: SeniorityLevel,
    preferences: CareerPreferences,
) -> tuple[SeniorityFit, str]:
    if preferences.experience_band != "junior_0_2":
        return (
            SeniorityFit.NEEDS_REVIEW,
            "The configured experience band is not supported by this assessment yet.",
        )

    if seniority in {SeniorityLevel.INTERNSHIP, SeniorityLevel.JUNIOR}:
        return (
            SeniorityFit.TARGET,
            "The title or provider's experience-level metadata indicates "
            "an internship or junior-level position.",
        )

    if seniority is SeniorityLevel.MIDDLE:
        if preferences.also_consider_years == "2_3_if_strong_fit":
            return (
                SeniorityFit.POTENTIAL_STRETCH,
                "Middle-level roles are considered as potential stretch; actual years "
                "of required experience and responsibilities must be checked.",
            )
        return (
            SeniorityFit.NEEDS_REVIEW,
            "Middle-level roles are outside the configured primary experience band.",
        )

    if seniority in {
        SeniorityLevel.SENIOR,
        SeniorityLevel.LEAD,
        SeniorityLevel.PRINCIPAL,
        SeniorityLevel.MANAGER_EXECUTIVE,
    }:
        return (
            SeniorityFit.TOO_SENIOR,
            "The title indicates a level above the candidate's target experience band.",
        )

    return (
        SeniorityFit.NEEDS_REVIEW,
        "The job title does not provide enough information to determine seniority.",
    )


def assess_candidate_fit(
    relevance: JobRelevanceAssessment,
    preferences: CareerPreferences,
) -> CandidateFitAssessment:
    """Compare a vacancy's role and title seniority with Candidate Profile preferences."""
    targets = _supported_target_roles(preferences)
    matched_targets = targets.get(relevance.role_type, [])

    if relevance.status is RelevanceStatus.IRRELEVANT:
        role_fit = RoleFit.OUT_OF_SCOPE
        role_reason = "The vacancy was classified as unrelated to the target QA roles."
    elif relevance.status is RelevanceStatus.NEEDS_REVIEW:
        role_fit = RoleFit.NEEDS_REVIEW
        role_reason = "The vacancy's professional direction requires manual review."
    elif matched_targets:
        role_fit = RoleFit.MATCH
        role_reason = "The vacancy matches one of the target roles in Candidate Profile."
    elif not targets:
        role_fit = RoleFit.NEEDS_REVIEW
        role_reason = "No supported target roles could be mapped from Candidate Profile."
    else:
        role_fit = RoleFit.OUT_OF_SCOPE
        role_reason = "The vacancy's QA specialization is not in the target roles."

    seniority_fit, seniority_reason = _assess_seniority(
        relevance.seniority,
        preferences,
    )

    if seniority_fit is SeniorityFit.TOO_SENIOR:
        status = CandidateFitStatus.OUT_OF_SCOPE
    elif role_fit is RoleFit.OUT_OF_SCOPE:
        status = CandidateFitStatus.OUT_OF_SCOPE
    elif (
        role_fit is RoleFit.NEEDS_REVIEW
        or seniority_fit is SeniorityFit.NEEDS_REVIEW
    ):
        status = CandidateFitStatus.NEEDS_REVIEW
    elif seniority_fit is SeniorityFit.POTENTIAL_STRETCH:
        status = CandidateFitStatus.POTENTIAL_STRETCH
    else:
        status = CandidateFitStatus.TARGET_FIT

    return CandidateFitAssessment(
        status=status,
        role_fit=role_fit,
        seniority_fit=seniority_fit,
        matched_target_roles=matched_targets,
        reasons=[role_reason, seniority_reason],
    )
