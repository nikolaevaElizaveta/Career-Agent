"""Combine role, geography, and skill assessments for one candidate and job."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from career_agent.domain.candidate import CandidateProfile
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_fit import (
    CandidateFitAssessment,
    assess_candidate_fit,
)
from career_agent.services.job_duty_matcher import (
    JobDutyMatch,
    match_job_duties,
)
from career_agent.services.job_eligibility import (
    JobEligibilityAssessment,
    assess_job_eligibility,
)
from career_agent.services.job_experience_matcher import (
    EducationRequirementMatch,
    ExperienceRequirementMatch,
    assess_profile_qualifications,
)
from career_agent.services.job_matcher import (
    JobMatchScoreAssessment,
    score_candidate_job,
)
from career_agent.services.job_relevance import (
    JobRelevanceAssessment,
    assess_job_relevance,
)
from career_agent.services.job_requirements import (
    JobRequirements,
    RequirementPriority,
    extract_job_requirements,
)
from career_agent.services.job_skill_matcher import (
    JobSkillMatchReport,
    SkillMatchStatus,
    match_job_skills,
)
from career_agent.services.job_skill_qualification import (
    SkillAlternativeQualificationAssessment,
    SkillQualificationAssessment,
    assess_skill_alternative_group,
    assess_skill_requirement,
)
from career_agent.services.skill_relationships import (
    RelatedSkillEvidence,
    find_related_skill_evidence,
)


class RequiredSkillCoverage(StrEnum):
    ALL_SKILLS_PRESENT_IN_PROFILE = "all_skills_present_in_profile"
    GAPS = "gaps"
    NEEDS_REVIEW = "needs_review"
    NO_REQUIRED_SKILLS = "no_required_skills"
    NO_DESCRIPTION = "no_description"


class SkillCoverageSummary(BaseModel):
    status: RequiredSkillCoverage
    total_required: int = 0
    confirmed: int = 0
    missing: int = 0
    needs_review: int = 0
    preferred_missing: int = 0


class CandidateJobAssessment(BaseModel):
    job_id: str
    title: str
    company: str
    relevance: JobRelevanceAssessment
    candidate_fit: CandidateFitAssessment
    eligibility: JobEligibilityAssessment
    requirements: JobRequirements
    skill_matches: JobSkillMatchReport
    skill_coverage: SkillCoverageSummary
    skill_qualifications: list[SkillQualificationAssessment]
    alternative_skill_qualifications: list[
        SkillAlternativeQualificationAssessment
    ]
    related_skill_evidence: list[RelatedSkillEvidence]
    duty_matches: list[JobDutyMatch]
    experience_matches: list[ExperienceRequirementMatch]
    education_matches: list[EducationRequirementMatch]
    match_score: JobMatchScoreAssessment | None = None


def _build_skill_coverage(
    requirements: JobRequirements,
    matches: JobSkillMatchReport,
    description: str | None,
) -> SkillCoverageSummary:
    required_statuses = [
        item.status for item in matches.required_skills
    ]
    required_statuses.extend(
        group.status
        for group in matches.alternative_groups
        if group.priority is RequirementPriority.REQUIRED
    )

    preferred_statuses = [
        item.status for item in matches.preferred_skills
    ]
    preferred_statuses.extend(
        group.status
        for group in matches.alternative_groups
        if group.priority is RequirementPriority.PREFERRED
    )

    missing = sum(
        status is SkillMatchStatus.MISSING
        for status in required_statuses
    )
    confirmed = sum(
        status is SkillMatchStatus.CONFIRMED
        for status in required_statuses
    )
    needs_review = sum(
        status not in {
            SkillMatchStatus.CONFIRMED,
            SkillMatchStatus.MISSING,
        }
        for status in required_statuses
    )
    preferred_missing = sum(
        status is SkillMatchStatus.MISSING
        for status in preferred_statuses
    )

    if not description or not description.strip():
        status = RequiredSkillCoverage.NO_DESCRIPTION
    elif not required_statuses:
        status = RequiredSkillCoverage.NO_REQUIRED_SKILLS
    elif missing:
        status = RequiredSkillCoverage.GAPS
    elif needs_review:
        status = RequiredSkillCoverage.NEEDS_REVIEW
    else:
        status = RequiredSkillCoverage.ALL_SKILLS_PRESENT_IN_PROFILE

    return SkillCoverageSummary(
        status=status,
        total_required=len(required_statuses),
        confirmed=confirmed,
        missing=missing,
        needs_review=needs_review,
        preferred_missing=preferred_missing,
    )


def _build_skill_qualifications(
    matches: JobSkillMatchReport,
) -> list[SkillQualificationAssessment]:
    """Assess proficiency and commercial expectations for matched requirements."""
    results = []

    ordinary_matches = (
        matches.required_skills
        + matches.preferred_skills
        + matches.unspecified_skills
    )

    for match in ordinary_matches:
        results.append(assess_skill_requirement(match))

    for group in matches.alternative_groups:
        group_label = " OR ".join(group.skills)

        for option in group.matched_options:
            results.append(
                assess_skill_requirement(
                    option,
                    alternative_group=group_label,
                )
            )

    return results


def _build_alternative_skill_qualifications(
    matches: JobSkillMatchReport,
) -> list[SkillAlternativeQualificationAssessment]:
    """Assess each any-of group as one requirement."""
    return [
        assess_skill_alternative_group(group)
        for group in matches.alternative_groups
    ]


def assess_candidate_job(
    job: JobPosting,
    profile: CandidateProfile,
    *,
    as_of: date | None = None,
) -> CandidateJobAssessment:
    """Assess role, geography, and extracted job requirements for a candidate."""
    relevance = assess_job_relevance(job)
    candidate_fit = assess_candidate_fit(
        relevance,
        profile.career_preferences,
    )
    eligibility = assess_job_eligibility(job)
    requirements = extract_job_requirements(job.description)
    skill_matches = match_job_skills(requirements, profile.skills)
    skill_coverage = _build_skill_coverage(
        requirements,
        skill_matches,
        job.description,
    )
    skill_qualifications = _build_skill_qualifications(skill_matches)
    alternative_skill_qualifications = (
        _build_alternative_skill_qualifications(skill_matches)
    )
    related_skill_evidence = find_related_skill_evidence(
        requirements,
        profile.skills,
    )
    duty_matches = match_job_duties(
        requirements.responsibilities,
        profile,
    )
    experience_matches, education_matches = assess_profile_qualifications(
        requirements.experience_requirements,
        requirements.education_requirements,
        profile,
        as_of=as_of,
    )

    candidate_assessment = CandidateJobAssessment(
        job_id=job.id,
        title=job.title,
        company=job.company,
        relevance=relevance,
        candidate_fit=candidate_fit,
        eligibility=eligibility,
        requirements=requirements,
        skill_matches=skill_matches,
        skill_coverage=skill_coverage,
        skill_qualifications=skill_qualifications,
        alternative_skill_qualifications=alternative_skill_qualifications,
        related_skill_evidence=related_skill_evidence,
        duty_matches=duty_matches,
        experience_matches=experience_matches,
        education_matches=education_matches,
    )

    match_score = score_candidate_job(
        job,
        profile,
        candidate_assessment,
    )

    return candidate_assessment.model_copy(
        update={"match_score": match_score}
    )
