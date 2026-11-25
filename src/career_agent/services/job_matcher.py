"""Explainable weighted scoring for one candidate and one job."""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from career_agent.domain.candidate import CandidateProfile
from career_agent.domain.fields import VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_description import clean_job_description
from career_agent.services.job_duty_matcher import (
    DutyEvidence,
    DutyEvidenceSource,
    DutyEvidenceType,
    JobDutyMatch,
)
from career_agent.services.job_eligibility import Compatibility, EligibilityStatus
from career_agent.services.job_skill_qualification import (
    CommercialExperienceFitStatus,
    ProficiencyFitStatus,
)

if TYPE_CHECKING:
    from career_agent.services.job_candidate_assessment import (
        CandidateJobAssessment,
    )


class JobMatchStatus(StrEnum):
    STRONG_MATCH = "strong_match"
    POTENTIAL_MATCH = "potential_match"
    NEEDS_REVIEW = "needs_review"
    WEAK_MATCH = "weak_match"
    OUT_OF_SCOPE = "out_of_scope"
    INELIGIBLE = "ineligible"
    BLOCKED_BY_HARD_EXCLUSION = "blocked_by_hard_exclusion"


class MatchScoreComponent(BaseModel):
    name: str
    score: float | None = None
    weight: float = 1.0
    coverage: float = 0.0
    status: str
    reason: str


class MatchCategoryAssessment(BaseModel):
    key: str
    title: str
    configured_weight: float
    score: float | None = None
    coverage_percent: float = 0.0
    weighted_contribution: float = 0.0
    status: str
    components: list[MatchScoreComponent] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class JobMatchScoreAssessment(BaseModel):
    observed_score: float | None = None
    score_floor: float = 0.0
    score_ceiling: float = 100.0
    coverage_percent: float = 0.0
    status: JobMatchStatus = JobMatchStatus.NEEDS_REVIEW
    blocked_from_ranking: bool = False
    hard_exclusion_matches: list[str] = Field(default_factory=list)
    lower_priority_matches: list[str] = Field(default_factory=list)
    categories: list[MatchCategoryAssessment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_PROFICIENCY_ORDER = {
    "beginner": 0,
    "basic": 1,
    "intermediate": 2,
    "proficient": 3,
}

_TECHNICAL_PRIORITY_WEIGHTS = {
    "required": 3.0,
    "preferred": 1.0,
    "unspecified": 0.25,
}

_EXPERIENCE_PRIORITY_WEIGHTS = {
    "required": 6.0,
    "preferred": 2.0,
    "unspecified": 0.5,
}

_EDUCATION_PRIORITY_WEIGHTS = {
    "required": 2.0,
    "preferred": 1.0,
    "unspecified": 0.25,
}

_DUTY_ALIGNMENT_WEIGHT = 3.0


def _round(value: float) -> float:
    return round(value, 1)


def _component(
    name: str,
    score: float | None,
    *,
    weight: float = 1.0,
    coverage: float = 1.0,
    reason: str,
) -> MatchScoreComponent:
    status = (
        "unknown"
        if score is None or coverage <= 0
        else "assessed"
        if coverage >= 1
        else "partially_assessed"
    )
    return MatchScoreComponent(
        name=name,
        score=_round(score) if score is not None else None,
        weight=weight,
        coverage=coverage,
        status=status,
        reason=reason,
    )


def _category(
    key: str,
    title: str,
    configured_weight: float,
    components: list[MatchScoreComponent],
    reasons: list[str] | None = None,
) -> MatchCategoryAssessment:
    applicable_weight = sum(item.weight for item in components)

    if applicable_weight <= 0:
        return MatchCategoryAssessment(
            key=key,
            title=title,
            configured_weight=configured_weight,
            status="not_assessed",
            reasons=reasons or ["No applicable criteria were extracted."],
        )

    assessed_weight = sum(
        item.weight * item.coverage
        for item in components
    )
    weighted_score = sum(
        item.weight * item.coverage * (item.score or 0.0)
        for item in components
    )

    coverage = assessed_weight / applicable_weight

    if assessed_weight > 0:
        score = weighted_score / assessed_weight
        contribution = configured_weight * coverage * score / 100
        status = (
            "assessed"
            if coverage >= 1
            else "partially_assessed"
        )
    else:
        score = None
        contribution = 0.0
        status = "unknown"

    category_reasons = list(reasons or [])
    category_reasons.extend(
        item.reason
        for item in components
        if item.reason not in category_reasons
    )

    return MatchCategoryAssessment(
        key=key,
        title=title,
        configured_weight=configured_weight,
        score=_round(score) if score is not None else None,
        coverage_percent=_round(coverage * 100),
        weighted_contribution=_round(contribution),
        status=status,
        components=components,
        reasons=category_reasons,
    )


def _duty_evidence_quality(
    evidence: DutyEvidence,
) -> tuple[float, float]:
    """Return the evidence score and its confidence coverage."""
    confirmed = evidence.verification_status is VerificationStatus.CONFIRMED

    if evidence.source is DutyEvidenceSource.EXPERIENCE_RESPONSIBILITY:
        return (100.0, 1.0) if confirmed else (60.0, 0.5)

    if confirmed:
        if evidence.evidence_type is DutyEvidenceType.DIRECT:
            return 80.0, 1.0
        return 40.0, 1.0

    if evidence.evidence_type is DutyEvidenceType.DIRECT:
        return 60.0, 0.5

    return 30.0, 0.5


def _duty_match_metrics(
    duty: JobDutyMatch,
) -> tuple[float | None, float]:
    """Score one duty without double-counting evidence sources."""
    if not duty.required_capabilities:
        return None, 0.0

    capability_metrics: list[tuple[float, float]] = []

    for capability in duty.required_capabilities:
        matching_evidence = [
            _duty_evidence_quality(evidence)
            for evidence in duty.evidence
            if capability in evidence.matched_capabilities
        ]

        if matching_evidence:
            best_evidence = max(
                matching_evidence,
                key=lambda item: (
                    item[0] * item[1],
                    item[0],
                    item[1],
                ),
            )
            capability_metrics.append(best_evidence)
        else:
            # The requirement is understood, but no candidate evidence exists.
            capability_metrics.append((0.0, 1.0))

    total_confidence = sum(
        confidence for _, confidence in capability_metrics
    )

    if total_confidence <= 0:
        return None, 0.0

    weighted_score = sum(
        score * confidence
        for score, confidence in capability_metrics
    )

    return (
        weighted_score / total_confidence,
        total_confidence / len(capability_metrics),
    )


def _duty_alignment_component(
    duties: list[JobDutyMatch],
) -> MatchScoreComponent:
    """Aggregate duties equally while preserving evidence uncertainty."""
    results = [_duty_match_metrics(duty) for duty in duties]

    total_confidence = sum(coverage for _, coverage in results)
    recognised_count = sum(
        score is not None for score, _ in results
    )

    score = (
        sum(
            score * coverage
            for score, coverage in results
            if score is not None
        ) / total_confidence
        if total_confidence > 0
        else None
    )
    coverage = total_confidence / len(duties)

    return _component(
        "duty_alignment",
        score,
        weight=_DUTY_ALIGNMENT_WEIGHT,
        coverage=coverage,
        reason=(
            f"Responsibilities: {recognised_count} of {len(duties)} duties "
            "had recognised capability requirements. Scores distinguish "
            "confirmed experience, direct skills, supporting evidence, "
            "and unverified records."
        ),
    )


def _role_category(assessment, weight: float) -> MatchCategoryAssessment:
    fit = assessment.candidate_fit

    role_scores = {
        "match": (100.0, 1.0, "The role matches a configured target role."),
        "needs_review": (
            None,
            0.0,
            "The role classification needs manual review.",
        ),
        "out_of_scope": (
            0.0,
            1.0,
            "The role is outside the configured target roles.",
        ),
    }
    role_score, role_coverage, role_reason = role_scores[fit.role_fit.value]

    seniority_scores = {
        "target": (100.0, 1.0, "The seniority is within the target range."),
        "potential_stretch": (
            70.0,
            1.0,
            "The role is a potential stretch beyond the primary target range.",
        ),
        "needs_review": (
            None,
            0.0,
            "The job seniority cannot be determined confidently.",
        ),
        "too_senior": (
            0.0,
            1.0,
            "The job seniority is above the configured target range.",
        ),
    }
    seniority_score, seniority_coverage, seniority_reason = (
        seniority_scores[fit.seniority_fit.value]
    )

    components = [
        _component(
            "target_role",
            role_score,
            weight=2.0,
            coverage=role_coverage,
            reason=role_reason,
        ),
        _component(
            "seniority",
            seniority_score,
            weight=1.0,
            coverage=seniority_coverage,
            reason=seniority_reason,
        ),
    ]

    for index, item in enumerate(assessment.experience_matches, start=1):
        required_months = math.ceil(item.min_years * 12)

        if required_months <= 0:
            score = 100.0
            coverage = 1.0
        elif item.status.value == "meets_minimum":
            score = 100.0
            coverage = 1.0
        elif item.status.value == "below_minimum":
            score = min(
                100.0,
                item.confirmed_min_months / required_months * 100,
            )
            coverage = 1.0
        elif item.status.value == "needs_confirmation":
            score = min(
                100.0,
                item.confirmed_min_months / required_months * 100,
            )
            coverage = 0.5
        elif item.status.value == "area_not_evidenced":
            score = 0.0
            coverage = 0.5
        else:
            score = None
            coverage = 0.0

        components.append(
            _component(
                f"experience_requirement_{index}",
                score,
                weight=_EXPERIENCE_PRIORITY_WEIGHTS.get(
                    item.priority,
                    0.5,
                ),
                coverage=coverage,
                reason=(
                    f"{item.status.value}: {item.confirmed_min_months} "
                    f"confirmed months; {required_months} required."
                ),
            )
        )

    for index, item in enumerate(assessment.education_matches, start=1):
        if item.status.value == "matched":
            score, coverage = 100.0, 1.0
        elif item.status.value == "needs_confirmation":
            score, coverage = 50.0, 0.5
        else:
            score, coverage = 0.0, 0.5

        components.append(
            _component(
                f"education_requirement_{index}",
                score,
                weight=_EDUCATION_PRIORITY_WEIGHTS.get(
                    item.priority,
                    0.25,
                ),
                coverage=coverage,
                reason=f"Education requirement status: {item.status.value}.",
            )
        )

    if assessment.duty_matches:
        components.append(
            _duty_alignment_component(assessment.duty_matches)
        )

    return _category(
        "role_and_duties",
        "Role, seniority, experience and education",
        weight,
        components,
        reasons=[
            (
                "Extracted responsibilities contribute through duty alignment. "
                "Evidence quality and verification status affect score and coverage."
                if assessment.duty_matches
                else "No explicit job responsibilities were extracted."
            )
        ],
    )


def _proficiency_ratio(
    candidate_level: str | None,
    expected_level: str | None,
) -> float | None:
    if not candidate_level or not expected_level:
        return None

    actual = _PROFICIENCY_ORDER.get(candidate_level.casefold())
    expected = _PROFICIENCY_ORDER.get(expected_level.casefold())

    if actual is None or expected is None or expected <= 0:
        return None

    return min(100.0, actual / expected * 100)


def _proficiency_measure(
    status: ProficiencyFitStatus,
    candidate_level: str | None,
    expected_level: str | None,
) -> tuple[float | None, float, str]:
    if status is ProficiencyFitStatus.MEETS_EXPECTATION:
        return 100.0, 1.0, "The confirmed level meets the stated expectation."

    if status is ProficiencyFitStatus.NOT_SPECIFIED:
        return (
            100.0,
            1.0,
            "The skill is confirmed; the employer did not specify a minimum level.",
        )

    if status is ProficiencyFitStatus.BELOW_EXPECTATION:
        ratio = _proficiency_ratio(candidate_level, expected_level)
        return (
            ratio if ratio is not None else 50.0,
            1.0,
            "The profile level is below the employer's stated expectation.",
        )

    if status is ProficiencyFitStatus.NEEDS_CONFIRMATION:
        ratio = _proficiency_ratio(candidate_level, expected_level)
        return (
            ratio if ratio is not None else 50.0,
            0.5,
            "The skill or proficiency level requires confirmation.",
        )

    return 0.0, 1.0, "The required skill is absent from the profile."


def _commercial_measure(
    status: CommercialExperienceFitStatus,
) -> tuple[float | None, float, str]:
    if status is CommercialExperienceFitStatus.NOT_REQUIRED:
        return None, 0.0, "The employer did not explicitly require commercial experience."

    if status is CommercialExperienceFitStatus.MEETS_EXPLICIT_REQUIREMENT:
        return 100.0, 1.0, "Explicit commercial experience is confirmed."

    if status is CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT:
        return 0.0, 1.0, "Explicit commercial experience is not present."

    if status is CommercialExperienceFitStatus.NEEDS_CONFIRMATION:
        return 50.0, 0.5, "Commercial experience needs confirmation."

    return 0.0, 1.0, "The skill required for commercial experience is missing."


def _qualification_measure(
    proficiency_status: ProficiencyFitStatus,
    candidate_level: str | None,
    expected_level: str | None,
    commercial_required: bool,
    commercial_status: CommercialExperienceFitStatus,
) -> tuple[float | None, float, str]:
    proficiency_score, proficiency_coverage, proficiency_reason = (
        _proficiency_measure(
            proficiency_status,
            candidate_level,
            expected_level,
        )
    )

    dimensions = [
        (proficiency_score, proficiency_coverage, 0.7),
    ]

    commercial_score, commercial_coverage, commercial_reason = (
        _commercial_measure(commercial_status)
    )

    if commercial_required:
        dimensions.append(
            (commercial_score, commercial_coverage, 0.3)
        )

    dimension_weight = sum(item[2] for item in dimensions)
    assessed_weight = sum(
        weight * coverage
        for _, coverage, weight in dimensions
    )

    if assessed_weight <= 0:
        score = None
        coverage = 0.0
    else:
        score = sum(
            (value or 0.0) * coverage * weight
            for value, coverage, weight in dimensions
        ) / assessed_weight
        coverage = assessed_weight / dimension_weight

    reasons = [proficiency_reason]
    if commercial_required:
        reasons.append(commercial_reason)

    return (
        score,
        coverage,
        " ".join(reasons),
    )


def _technical_category(
    assessment,
    weight: float,
) -> MatchCategoryAssessment:
    components: list[MatchScoreComponent] = []

    ordinary = [
        item
        for item in assessment.skill_qualifications
        if item.alternative_group is None
    ]

    for item in ordinary:
        score, coverage, reason = _qualification_measure(
            item.proficiency_fit,
            item.candidate_level,
            item.expected_minimum_level,
            item.commercial_experience_required,
            item.commercial_fit,
        )
        components.append(
            _component(
                f"{item.priority}:{item.requirement}",
                score,
                weight=_TECHNICAL_PRIORITY_WEIGHTS.get(
                    item.priority,
                    0.25,
                ),
                coverage=coverage,
                reason=reason,
            )
        )

    for group in assessment.alternative_skill_qualifications:
        option_scores = [
            _proficiency_ratio(
                option.candidate_level,
                option.expected_minimum_level,
            )
            for option in group.option_qualifications
        ]
        known_option_scores = [
            value for value in option_scores
            if value is not None
        ]

        if group.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION:
            proficiency_score = max(known_option_scores, default=50.0)
            proficiency_coverage = 1.0
        elif group.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION:
            proficiency_score = max(known_option_scores, default=50.0)
            proficiency_coverage = 0.5
        elif group.proficiency_fit is ProficiencyFitStatus.SKILL_MISSING:
            proficiency_score = 0.0
            proficiency_coverage = 1.0
        else:
            proficiency_score = 100.0
            proficiency_coverage = 1.0

        group_score, group_coverage, reason = _qualification_measure(
            group.proficiency_fit,
            None,
            None,
            group.commercial_experience_required,
            group.commercial_fit,
        )

        if group.proficiency_fit is ProficiencyFitStatus.BELOW_EXPECTATION:
            group_score = proficiency_score
        elif group.proficiency_fit is ProficiencyFitStatus.NEEDS_CONFIRMATION:
            group_score = proficiency_score
            group_coverage = min(group_coverage, proficiency_coverage)

        components.append(
            _component(
                f"{group.priority}:{group.requirement}",
                group_score,
                weight=_TECHNICAL_PRIORITY_WEIGHTS.get(
                    group.priority,
                    0.25,
                ),
                coverage=group_coverage,
                reason=reason,
            )
        )

    if not components:
        components.append(
            _component(
                "extracted_skills",
                None,
                coverage=0.0,
                reason="No skill requirements were extracted from the description.",
            )
        )

    reasons = []
    if assessment.related_skill_evidence:
        reasons.append(
            "Related skills are shown as supplementary evidence but are not "
            "given numeric bonus points until relationship weights are calibrated."
        )

    return _category(
        "technical_skills",
        "Technical skills",
        weight,
        components,
        reasons=reasons,
    )


def _compatibility_measure(value: Compatibility) -> tuple[float | None, float, str]:
    if value is Compatibility.COMPATIBLE:
        return 100.0, 1.0, "The source restriction is compatible."
    if value is Compatibility.INCOMPATIBLE:
        return 0.0, 1.0, "The source restriction is incompatible."
    return None, 0.0, "The source restriction is unknown."


def _geography_category(
    job: JobPosting,
    profile: CandidateProfile,
    assessment,
    weight: float,
) -> MatchCategoryAssessment:
    eligibility = assessment.eligibility

    country_score = _compatibility_measure(
        eligibility.country_compatibility
    )
    timezone_score = _compatibility_measure(
        eligibility.timezone_compatibility
    )

    components = [
        _component(
            "source_country_compatibility",
            country_score[0],
            weight=40,
            coverage=country_score[1],
            reason=country_score[2],
        ),
        _component(
            "timezone_compatibility",
            timezone_score[0],
            weight=25,
            coverage=timezone_score[1],
            reason=timezone_score[2],
        ),
    ]

    preferred_mode = profile.employment_preferences.preferred_work_mode.casefold()
    workplace = job.workplace_type.value

    if workplace == "unknown":
        mode_score, mode_coverage = None, 0.0
        mode_reason = "The job's workplace type is unknown."
    elif workplace == preferred_mode:
        mode_score, mode_coverage = 100.0, 1.0
        mode_reason = "The workplace type matches the preferred work mode."
    elif (
        workplace in {"hybrid", "onsite"}
        and profile.geographic_preferences.relocation_desired
        and profile.employment_preferences.hybrid_or_office_if_relocation
    ):
        mode_score, mode_coverage = 70.0, 1.0
        mode_reason = (
            "Hybrid or office work may be considered with relocation."
        )
    else:
        mode_score, mode_coverage = 0.0, 1.0
        mode_reason = "The workplace type does not match configured preferences."

    components.append(
        _component(
            "workplace_type",
            mode_score,
            weight=20,
            coverage=mode_coverage,
            reason=mode_reason,
        )
    )

    authorization = eligibility.legal_work_authorization.casefold()
    if authorization in {"yes", "true", "authorized", "compatible"}:
        legal_score, legal_coverage = 100.0, 1.0
        legal_reason = "Legal work authorization is confirmed."
    elif authorization in {"no", "false", "not_authorized", "incompatible"}:
        legal_score, legal_coverage = 0.0, 1.0
        legal_reason = "Legal work authorization is not available."
    else:
        legal_score, legal_coverage = None, 0.0
        legal_reason = "The employer's legal ability to hire remains unverified."

    components.append(
        _component(
            "legal_work_authorization",
            legal_score,
            weight=15,
            coverage=legal_coverage,
            reason=legal_reason,
        )
    )

    reasons = [
        "Priority-country preference is not scored without reliable eligible-country data."
    ]

    return _category(
        "geography",
        "Geography and work mode",
        weight,
        components,
        reasons=reasons,
    )


def _salary_category(
    job: JobPosting,
    profile: CandidateProfile,
    weight: float,
) -> MatchCategoryAssessment:
    expected = profile.salary_expectations
    reason: str
    score: float | None
    coverage: float

    if expected.amount <= 0:
        score, coverage = None, 0.0
        reason = "No positive salary expectation is configured."
    elif not job.salary_currency:
        score, coverage = None, 0.0
        reason = "The job does not disclose a salary currency."
    elif job.salary_currency.casefold() != expected.currency.casefold():
        score, coverage = None, 0.0
        reason = (
            "Salary currencies differ; no exchange rate is assumed."
        )
    elif job.salary_type.value != expected.kind:
        score, coverage = None, 0.0
        reason = (
            "Salary types differ or are unknown; gross and net amounts "
            "are not compared."
        )
    else:
        candidate_period = expected.period.casefold()
        job_period = job.salary_period.value

        if candidate_period not in {"month", "year"} or job_period not in {
            "month",
            "year",
        }:
            score, coverage = None, 0.0
            reason = "Salary periods cannot be compared without assumptions."
        else:
            annual_expected = (
                expected.amount * 12
                if candidate_period == "month"
                else expected.amount
            )
            job_expected = (
                annual_expected / 12
                if job_period == "month"
                else annual_expected
            )

            minimum = job.salary_min
            maximum = job.salary_max

            if minimum is None and maximum is None:
                score, coverage = None, 0.0
                reason = "The employer did not disclose a salary range."
            elif (
                minimum is not None
                and maximum is not None
                and minimum > maximum
            ):
                score, coverage = None, 0.0
                reason = "The disclosed salary range is invalid."
            elif maximum is not None and maximum < job_expected:
                score = max(0.0, maximum / job_expected * 100)
                coverage = 1.0
                reason = "The published salary ceiling is below the expectation."
            elif minimum is not None and minimum >= job_expected:
                score, coverage = 100.0, 1.0
                reason = "The published salary floor meets the expectation."
            else:
                score, coverage = 50.0, 0.5
                reason = (
                    "The disclosed range is incomplete or crosses the "
                    "expected amount; full compatibility is not established."
                )

    component = _component(
        "salary_compatibility",
        score,
        coverage=coverage,
        reason=reason,
    )

    return _category(
        "salary",
        "Salary",
        weight,
        [component],
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def _contains_literal_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {_normalize_text(text)} "
    normalized_phrase = _normalize_text(phrase)

    if not normalized_phrase:
        return False

    return f" {normalized_phrase} " in normalized_text


def _ethics_category(
    job: JobPosting,
    profile: CandidateProfile,
    weight: float,
) -> tuple[MatchCategoryAssessment, list[str], list[str]]:
    description = clean_job_description(job.description or "")
    searchable_text = " ".join(
        part for part in (
            job.title,
            job.company,
            job.location or "",
            job.employment_type or "",
            description,
        )
        if part
    )

    if not searchable_text.strip():
        component = _component(
            "literal_exclusion_screen",
            None,
            coverage=0.0,
            reason="There is not enough job text to screen configured exclusions.",
        )
        return (
            _category(
                "ethics",
                "Ethical restrictions",
                weight,
                [component],
            ),
            [],
            [],
        )

    hard_matches = [
        term
        for term in profile.ethical_restrictions.hard_exclusions
        if _contains_literal_phrase(searchable_text, term)
    ]
    lower_matches = [
        term
        for term in profile.ethical_restrictions.lower_priority
        if _contains_literal_phrase(searchable_text, term)
    ]

    if not profile.ethical_restrictions.unpaid_work_allowed and re.search(
        r"\b(?:unpaid|volunteer)\b",
        searchable_text,
        re.IGNORECASE,
    ):
        hard_matches.append("unpaid or volunteer work")

    if hard_matches:
        score = 0.0
        coverage = 1.0
        reason = (
            "A literal hard-exclusion or unpaid-work indicator was found. "
            "The vacancy is blocked pending manual review."
        )
    else:
        score = None
        coverage = 0.0
        reason = (
            "No literal hard-exclusion indicators were detected, but broader "
            "ethical suitability, company culture and values have not been assessed."
        )

    component = _component(
        "literal_exclusion_screen",
        score,
        coverage=coverage,
        reason=reason,
    )

    return (
        _category(
            "ethics",
            "Ethical restrictions",
            weight,
            [component],
        ),
        hard_matches,
        lower_matches,
    )


def _required_skill_signals(
    assessment: CandidateJobAssessment,
) -> tuple[int, int]:
    """Count explicit required-skill gaps and facts needing confirmation."""
    gaps = 0
    reviews = 0

    def inspect(
        proficiency: ProficiencyFitStatus,
        commercial: CommercialExperienceFitStatus,
    ) -> None:
        nonlocal gaps, reviews

        if proficiency in {
            ProficiencyFitStatus.SKILL_MISSING,
            ProficiencyFitStatus.BELOW_EXPECTATION,
        } or commercial in {
            CommercialExperienceFitStatus.SKILL_MISSING,
            CommercialExperienceFitStatus.DOES_NOT_MEET_EXPLICIT_REQUIREMENT,
        }:
            gaps += 1
        elif (
            proficiency is ProficiencyFitStatus.NEEDS_CONFIRMATION
            or commercial is CommercialExperienceFitStatus.NEEDS_CONFIRMATION
        ):
            reviews += 1

    for item in assessment.skill_qualifications:
        if item.priority != "required" or item.alternative_group is not None:
            continue
        inspect(item.proficiency_fit, item.commercial_fit)

    for group in assessment.alternative_skill_qualifications:
        if group.priority == "required":
            inspect(group.proficiency_fit, group.commercial_fit)

    return gaps, reviews


def score_candidate_job(
    job: JobPosting,
    profile: CandidateProfile,
    assessment: CandidateJobAssessment,
) -> JobMatchScoreAssessment:
    """Calculate weighted score, evidence coverage, and an uncertainty range."""
    weights = profile.career_preferences.match_weights

    categories = [
        _role_category(assessment, weights.role_and_duties),
        _technical_category(assessment, weights.technical_skills),
        _geography_category(job, profile, assessment, weights.geography),
        _salary_category(job, profile, weights.salary),
    ]

    ethics_category, hard_matches, lower_matches = _ethics_category(
        job,
        profile,
        weights.ethics,
    )
    categories.append(ethics_category)

    total_weight = sum(item.configured_weight for item in categories)
    if total_weight <= 0:
        total_weight = 100.0

    assessed_weight = sum(
        item.configured_weight * item.coverage_percent / 100
        for item in categories
    )
    contribution = sum(
        item.weighted_contribution
        for item in categories
    )

    observed = (
        contribution / assessed_weight * 100
        if assessed_weight > 0
        else None
    )
    floor = contribution / total_weight * 100
    ceiling = (
        contribution + total_weight - assessed_weight
    ) / total_weight * 100
    coverage = assessed_weight / total_weight * 100

    required_skill_gaps, required_skill_reviews = (
        _required_skill_signals(assessment)
    )
    required_experience_gaps = [
        item
        for item in assessment.experience_matches
        if item.priority == "required"
        and item.status.value in {"below_minimum", "area_not_evidenced"}
    ]
    required_experience_reviews = [
        item
        for item in assessment.experience_matches
        if item.priority == "required"
        and item.status.value in {"needs_confirmation", "unknown"}
    ]

    eligibility_status = assessment.eligibility.status
    if hard_matches:
        status = JobMatchStatus.BLOCKED_BY_HARD_EXCLUSION
    elif eligibility_status in {
        EligibilityStatus.COUNTRY_RESTRICTED,
        EligibilityStatus.TIMEZONE_MISMATCH,
    }:
        status = JobMatchStatus.INELIGIBLE
    elif assessment.candidate_fit.status.value == "out_of_scope":
        status = JobMatchStatus.OUT_OF_SCOPE
    elif required_experience_gaps:
        status = JobMatchStatus.NEEDS_REVIEW
    elif observed is None or coverage < 55:
        status = JobMatchStatus.NEEDS_REVIEW
    elif required_skill_gaps >= 3:
        status = JobMatchStatus.WEAK_MATCH
    elif (
        assessment.candidate_fit.status.value == "needs_review"
        or required_skill_reviews
        or required_experience_reviews
    ):
        status = JobMatchStatus.NEEDS_REVIEW
    elif observed >= 60 and coverage >= 60:
        # Strong-match remains disabled while duty-scoring thresholds are calibrated.
        status = JobMatchStatus.POTENTIAL_MATCH
    else:
        status = JobMatchStatus.WEAK_MATCH

    warnings: list[str] = []

    if required_skill_gaps:
        warnings.append(
            f"{required_skill_gaps} explicit required skill requirement(s) "
            "are missing or below the stated expectation."
        )

    if required_experience_gaps:
        warnings.append(
            f"{len(required_experience_gaps)} required experience "
            "requirement(s) are below the stated minimum or lack confirmed "
            "area-specific evidence."
        )

    warnings.append(
        "Strong-match classification remains withheld while duty-scoring "
        "weights and thresholds are being calibrated against real vacancy data."
    )

    if any(
        item.key == "salary" and item.score is None
        for item in categories
    ):
        warnings.append(
            "Salary could not be compared; the score range includes this uncertainty."
        )

    if assessment.eligibility.legal_work_authorization == "unknown":
        warnings.append(
            "Employer legal work authorization remains unverified."
        )

    if lower_matches:
        warnings.append(
            "The vacancy contains lower-priority terms from Candidate Profile; "
            "they are flagged separately and do not yet change the numeric score."
        )

    if not hard_matches:
        warnings.append(
            "No literal hard-exclusion indicators were detected, but broader "
            "ethical suitability and company culture remain unassessed."
        )

    if assessment.related_skill_evidence:
        warnings.append(
            "Related skill evidence is displayed separately and is not assigned "
            "an arbitrary numeric bonus."
        )

    if job.employment_type:
        warnings.append(
            f"Provider employment type '{job.employment_type}' is not directly "
            "equivalent to the configured contract-type preferences."
        )

    if not math.isclose(total_weight, 100.0):
        warnings.append(
            f"Configured category weights sum to {total_weight}, not 100."
        )

    return JobMatchScoreAssessment(
        observed_score=_round(observed) if observed is not None else None,
        score_floor=_round(floor),
        score_ceiling=_round(ceiling),
        coverage_percent=_round(coverage),
        status=status,
        blocked_from_ranking=bool(hard_matches)
        or status in {
            JobMatchStatus.INELIGIBLE,
            JobMatchStatus.OUT_OF_SCOPE,
        },
        hard_exclusion_matches=hard_matches,
        lower_priority_matches=lower_matches,
        categories=categories,
        warnings=warnings,
    )
