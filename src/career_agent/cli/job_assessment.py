"""Formatting for candidate-specific job assessment reports."""

from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_candidate_assessment import (
    CandidateJobAssessment,
    RequiredSkillCoverage,
)
from career_agent.services.job_duty_matcher import JobDutyMatch
from career_agent.services.job_requirements import RequirementPriority


def _commercial_label(value: bool | None, status: VerificationStatus | None) -> str:
    if status is not VerificationStatus.CONFIRMED:
        return "not confirmed"
    return "yes" if value is True else "no"


def _format_skill_match(match) -> list[str]:
    status_label = (
        "profile_confirmed"
        if match.status.value == "confirmed"
        else match.status.value
    )
    lines = [f"- [{status_label}] {match.requirement}"]

    if match.candidate_skill:
        lines.append(
            f"    Profile: {match.candidate_skill} | "
            f"level: {match.proficiency or 'not specified'} | "
            f"commercial experience: "
            f"{_commercial_label(match.commercial_experience, match.commercial_experience_status)}"
        )

    for evidence in match.evidence:
        lines.append(f"    Evidence: {evidence}")

    return lines


def _format_alternative_group(group) -> list[str]:
    options = " OR ".join(group.skills)
    status_label = (
        "at_least_one_profile_confirmed_option"
        if group.status.value == "confirmed"
        else group.status.value
    )
    lines = [f"- [{status_label}] {options}"]

    if group.matched_options:
        lines.append("    Matching profile options:")
        for option in group.matched_options:
            lines.extend(_format_skill_match(option))
    else:
        lines.append("    No options found in Candidate Profile.")

    for evidence in group.evidence:
        lines.append(f"    Evidence: {evidence}")

    return lines


def _format_duty_match(match: JobDutyMatch) -> list[str]:
    lines = [
        f"- [{match.status.value}] {match.requirement}",
        f"    Evidence coverage: {match.evidence_coverage_percent:.1f}%",
        (
            "    Confirmed evidence coverage: "
            f"{match.confirmed_evidence_coverage_percent:.1f}%"
        ),
    ]

    if match.required_capabilities:
        lines.append(
            "    Recognised capabilities: "
            + ", ".join(match.required_capabilities)
        )

    if match.missing_capabilities:
        lines.append(
            "    Capabilities without evidence: "
            + ", ".join(match.missing_capabilities)
        )

    if match.verification_needed:
        lines.append("    Verification: some evidence is not confirmed.")

    for evidence in match.evidence:
        lines.append(
            f"    Evidence [{evidence.source.value} / "
            f"{evidence.evidence_type.value} / "
            f"{evidence.verification_status.value}]: "
            f"{evidence.evidence_text}"
        )

        if evidence.role_title:
            lines.append(f"        Role: {evidence.role_title}")

        if evidence.candidate_skill:
            lines.append(f"        Candidate skill: {evidence.candidate_skill}")
            lines.append(
                "        Commercial experience: "
                + _commercial_label(
                    evidence.commercial_experience,
                    evidence.commercial_experience_status,
                )
            )

        if evidence.matched_capabilities:
            lines.append(
                "        Matched capabilities: "
                + ", ".join(evidence.matched_capabilities)
            )

    lines.extend(
        f"    Assessment: {reason}"
        for reason in match.reasons
    )

    return lines


def format_candidate_assessment(
    assessment: CandidateJobAssessment,
) -> str:
    """Render role, geography, and skills assessment with source evidence."""
    relevance = assessment.relevance
    fit = assessment.candidate_fit
    eligibility = assessment.eligibility
    coverage = assessment.skill_coverage
    matches = assessment.skill_matches

    lines = [
        "CANDIDATE JOB ASSESSMENT",
        f"{assessment.title} @ {assessment.company}",
        f"Job ID: {assessment.job_id}",
        "",
        "ROLE AND SENIORITY",
        f"Role classification: {relevance.role_type.value}",
        f"Role fit: {fit.role_fit.value}",
        f"Seniority: {relevance.seniority.value}",
        f"Seniority fit: {fit.seniority_fit.value}",
        f"Role/seniority fit (not overall): {fit.status.value}",
    ]

    lines.extend(f"- {reason}" for reason in fit.reasons)

    lines.extend([
        "",
        "GEOGRAPHIC ELIGIBILITY",
        f"Source eligibility: {eligibility.status.value}",
        f"Country compatibility: {eligibility.country_compatibility.value}",
        f"Timezone compatibility: {eligibility.timezone_compatibility.value}",
        f"Legal work authorization: {eligibility.legal_work_authorization}",
    ])
    lines.extend(f"- {reason}" for reason in eligibility.reasons)

    lines.extend([
        "",
        "REQUIRED SKILL COVERAGE",
        "Profile confirmation does not by itself prove the required proficiency "
        "or commercial experience.",
        f"Status: {coverage.status.value}",
        (
            "Required entries with profile-confirmed skills: "
            f"{coverage.confirmed}/{coverage.total_required}"
        ),
        f"Skills absent from profile: {coverage.missing}",
        f"Skill facts needing review: {coverage.needs_review}",
        f"Preferred skills absent from profile: {coverage.preferred_missing}",
    ])

    if assessment.skill_qualifications:
        lines.extend(["", "SKILL QUALIFICATION DETAILS"])

        for item in assessment.skill_qualifications:
            label = item.requirement

            if item.alternative_group:
                label = f"{item.alternative_group} -> {item.requirement}"

            lines.extend([
                "",
                f"- [{item.priority}] {label}",
                f"    Profile status: {item.profile_status.value}",
                (
                    f"    Candidate level: "
                    f"{item.candidate_level or 'not provided'}"
                ),
                (
                    f"    Expected minimum level: "
                    f"{item.expected_minimum_level or 'not specified'}"
                ),
                f"    Proficiency assessment: {item.proficiency_fit.value}",
                (
                    "    Commercial experience in profile: "
                    + _commercial_label(
                        item.commercial_experience,
                        item.commercial_experience_status,
                    )
                ),
            ])

            if item.commercial_experience_required:
                lines.append(
                    "    Commercial experience requirement: explicit | "
                    f"{item.commercial_fit.value}"
                )
            else:
                lines.append(
                    "    Commercial experience requirement: "
                    "not explicitly stated by employer"
                )

            lines.extend(
                f"    Assessment: {reason}"
                for reason in item.reasons
            )

    if assessment.alternative_skill_qualifications:
        lines.extend(["", "ALTERNATIVE GROUP QUALIFICATION DETAILS"])

        for group in assessment.alternative_skill_qualifications:
            lines.extend([
                "",
                f"- [{group.priority}] {group.requirement}",
                f"    Match rule: {group.match_rule}",
                f"    Proficiency assessment: {group.proficiency_fit.value}",
                (
                    "    Commercial experience requirement: "
                    + (
                        "explicit"
                        if group.commercial_experience_required
                        else "not explicitly stated by employer"
                    )
                ),
                (
                    "    Commercial experience assessment: "
                    f"{group.commercial_fit.value}"
                ),
            ])

            if group.option_qualifications:
                lines.append("    Options found in profile:")

                for option in group.option_qualifications:
                    name = option.candidate_skill or option.requirement
                    level = option.candidate_level or "not provided"
                    commercial = _commercial_label(
                        option.commercial_experience,
                        option.commercial_experience_status,
                    )
                    lines.append(
                        f"        - {name}: {level} | "
                        f"profile: {option.profile_status.value} | "
                        f"proficiency: {option.proficiency_fit.value} | "
                        f"commercial: {commercial}"
                    )
            else:
                lines.append("    No options found in Candidate Profile.")

            if group.missing_options:
                lines.append(
                    "    Options absent from profile: "
                    + ", ".join(group.missing_options)
                )

            lines.extend(
                f"    Assessment: {reason}"
                for reason in group.reasons
            )

    if assessment.related_skill_evidence:
        lines.extend(["", "RELATED SKILL EVIDENCE"])

        for item in assessment.related_skill_evidence:
            lines.extend([
                "",
                (
                    f"- [{item.priority}] "
                    f"{item.requirement} <- {item.candidate_skill}"
                ),
                f"    Relationship: {item.relationship_type.value}",
                f"    Profile status: {item.profile_status.value}",
                (
                    "    Candidate level: "
                    f"{item.candidate_level or 'not provided'}"
                ),
                (
                    "    Proficiency verification: "
                    f"{item.proficiency_status.value}"
                ),
                (
                    "    Commercial experience in profile: "
                    + _commercial_label(
                        item.commercial_experience,
                        item.commercial_experience_status,
                    )
                ),
                (
                    "    Counts as exact skill match: "
                    f"{'yes' if item.counts_as_skill_match else 'no'}"
                ),
                f"    Rationale: {item.rationale}",
            ])

    if assessment.duty_matches:
        lines.extend([
            "",
            "DUTY MATCH DETAILS",
            (
                "Confirmed coverage uses confirmed experience and direct "
                "skill evidence. Supporting evidence is shown separately."
            ),
        ])

        for item in assessment.duty_matches:
            lines.extend(_format_duty_match(item))

    score = assessment.match_score

    if score is not None:
        observed_label = (
            f"{score.observed_score:.1f}/100"
            if score.observed_score is not None
            else "not available"
        )

        lines.extend([
            "",
            "OVERALL MATCH SCORE",
            f"Status: {score.status.value}",
            f"Observed score: {observed_label}",
            (
                f"Possible score range: "
                f"{score.score_floor:.1f}–{score.score_ceiling:.1f}/100"
            ),
            f"Evidence coverage: {score.coverage_percent:.1f}%",
            (
                "Blocked from ranking: "
                f"{'yes' if score.blocked_from_ranking else 'no'}"
            ),
            "",
            "CATEGORY BREAKDOWN",
        ])

        for category in score.categories:
            category_score = (
                f"{category.score:.1f}/100"
                if category.score is not None
                else "not assessed"
            )

            lines.append(
                f"- {category.title}: {category_score} | "
                f"weight: {category.configured_weight:.1f}% | "
                f"coverage: {category.coverage_percent:.1f}% | "
                f"contribution: {category.weighted_contribution:.1f}"
            )

            for reason in category.reasons:
                lines.append(f"    Explanation: {reason}")

            for component in category.components:
                component_score = (
                    f"{component.score:.1f}"
                    if component.score is not None
                    else "unknown"
                )
                lines.append(
                    f"    - {component.name}: {component_score} | "
                    f"coverage: {component.coverage * 100:.1f}%"
                )

        if score.hard_exclusion_matches:
            lines.append(
                "Hard exclusion indicators: "
                + ", ".join(score.hard_exclusion_matches)
            )

        if score.lower_priority_matches:
            lines.append(
                "Lower-priority indicators: "
                + ", ".join(score.lower_priority_matches)
            )

        if score.warnings:
            lines.append("Scoring warnings:")
            lines.extend(f"    - {warning}" for warning in score.warnings)

    if coverage.status is RequiredSkillCoverage.NO_DESCRIPTION:
        lines.append("No job description is stored; skill matching is unavailable.")
    elif coverage.status is RequiredSkillCoverage.NO_REQUIRED_SKILLS:
        lines.append(
            "No required skills were extracted. This does not prove that "
            "the employer has no mandatory skill requirements."
        )

    def append_section(
        heading: str,
        items: list,
        groups: list,
    ) -> None:
        if not items and not groups:
            return

        lines.extend(["", heading])

        for item in items:
            lines.extend(_format_skill_match(item))

        for group in groups:
            lines.extend(_format_alternative_group(group))

    append_section(
        "REQUIRED SKILLS",
        matches.required_skills,
        [
            group
            for group in matches.alternative_groups
            if group.priority is RequirementPriority.REQUIRED
        ],
    )
    append_section(
        "PREFERRED SKILLS",
        matches.preferred_skills,
        [
            group
            for group in matches.alternative_groups
            if group.priority is RequirementPriority.PREFERRED
        ],
    )
    append_section(
        "OTHER MENTIONED SKILLS",
        matches.unspecified_skills,
        [
            group
            for group in matches.alternative_groups
            if group.priority is RequirementPriority.UNSPECIFIED
        ],
    )

    if assessment.experience_matches:
        lines.extend(["", "EXPERIENCE REQUIREMENTS"])

        for item in assessment.experience_matches:
            maximum = (
                str(item.max_years)
                if item.max_years is not None
                else "no stated maximum"
            )
            area = f" in {item.area}" if item.area else ""

            lines.append(
                f"- [{item.status.value}] {item.min_years}–{maximum} "
                f"years{area} [{item.priority}]"
            )
            lines.append(
                f"    Confirmed minimum: {item.confirmed_min_months} full months"
            )
            lines.append(
                f"    Possible maximum from date precision: "
                f"{item.possible_max_months} months"
            )

            if item.confirmed_roles:
                lines.append(
                    f"    Confirmed roles: {', '.join(item.confirmed_roles)}"
                )

            if item.unverified_roles:
                lines.append(
                    f"    Roles requiring confirmation: "
                    f"{', '.join(item.unverified_roles)}"
                )

            for reason in item.reasons:
                lines.append(f"    Assessment: {reason}")

            for evidence in item.evidence:
                lines.append(f"    Job evidence: {evidence}")

    if assessment.education_matches:
        lines.extend(["", "EDUCATION REQUIREMENTS"])

        for item in assessment.education_matches:
            lines.append(f"- [{item.status.value}] {item.evidence}")

            if item.matched_degree:
                lines.append(f"    Degree: {item.matched_degree}")

            if item.matched_field:
                lines.append(f"    Field: {item.matched_field}")

            for reason in item.reasons:
                lines.append(f"    Assessment: {reason}")

    if assessment.requirements.responsibilities:
        lines.extend(["", "EXTRACTED RESPONSIBILITIES"])
        lines.extend(
            f"- {item}" for item in assessment.requirements.responsibilities
        )

    return "\n".join(lines)
