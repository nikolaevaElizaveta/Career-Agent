"""CLI helpers for job discovery."""

from __future__ import annotations

from career_agent.domain.candidate import CareerPreferences
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_fit import (
    CandidateFitStatus,
    SeniorityFit,
    assess_candidate_fit,
)
from career_agent.services.job_discovery import DiscoveryReport
from career_agent.services.job_eligibility import (
    Compatibility,
    EligibilityStatus,
    assess_job_eligibility,
)
from career_agent.services.job_relevance import (
    RelevanceStatus,
    assess_job_relevance,
)


def format_job_list(jobs: list[JobPosting]) -> str:
    if not jobs:
        return "No jobs stored yet. Run: python -m career_agent jobs search"
    lines: list[str] = []
    for job in jobs:
        location = job.location or "location unknown"
        salary = "salary unknown"
        if job.salary_min is not None or job.salary_max is not None:
            low = job.salary_min if job.salary_min is not None else "?"
            high = job.salary_max if job.salary_max is not None else "?"
            currency = job.salary_currency or ""
            salary = f"{low}–{high} {currency} ({job.salary_type.value})"
        lines.append(
            f"{job.id[:8]}…  [{job.display_source()}] {job.title} @ {job.company}\n"
            f"         {location} | {job.workplace_type.value} | "
            f"{job.remote_scope.value} | {salary}\n"
            f"         {job.job_url or 'no url'}"
        )
    return "\n".join(lines)


def format_job_detail(job: JobPosting) -> str:
    eligible = (
        ", ".join(job.eligible_countries)
        if job.eligible_countries is not None
        else "unknown"
    )
    published = job.published_at.isoformat() if job.published_at else "unknown"
    lines = [
        f"ID: {job.id}",
        f"Source: {job.display_source()}",
        f"Source job ID: {job.source_job_id}",
        f"Title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location or 'unknown'}",
        f"Country code: {job.country_code or 'unknown'}",
        f"Workplace: {job.workplace_type.value}",
        f"Remote scope: {job.remote_scope.value}",
        f"Eligible countries: {eligible}",
        f"Employment type: {job.employment_type or 'unknown'}",
        f"Experience level: {job.experience_level or 'unknown'}",
        (
            "Salary: "
            f"{job.salary_min}–{job.salary_max} {job.salary_currency or ''} "
            f"{job.salary_period.value} ({job.salary_type.value})"
        ),
        f"Published at: {published}",
        f"Discovered at: {job.discovered_at.isoformat()}",
        f"Job URL: {job.job_url or 'unknown'}",
        f"Application URL: {job.application_url or 'unknown'}",
        f"Source URL: {job.source_url or 'unknown'}",
        f"Probable duplicate of: {job.duplicate_of_id or 'no'}",
        f"Related URLs: {', '.join(job.related_urls) or 'none'}",
        "",
        job.description or "(no description)",
    ]
    return "\n".join(lines)


def format_report(report: DiscoveryReport) -> str:
    return report.format()

def format_relevant_jobs(jobs: list[JobPosting]) -> str:
    """Display relevant and review-needed jobs from stored vacancies."""
    classified = []

    for job in jobs:
        assessment = assess_job_relevance(job)
        if assessment.status != RelevanceStatus.IRRELEVANT:
            classified.append((job, assessment))

    if not classified:
        return "No relevant or review-needed vacancies found."

    priority = {
        RelevanceStatus.RELEVANT: 0,
        RelevanceStatus.NEEDS_REVIEW: 1,
    }
    classified.sort(
        key=lambda item: (
            priority[item[1].status],
            item[0].title.casefold(),
        )
    )

    lines = [f"QA-related vacancies: {len(classified)}"]

    for job, assessment in classified:
        lines.extend([
            "",
            (
                f"[{assessment.status.value.upper()}] "
                f"{assessment.role_type.value} | "
                f"level: {assessment.seniority.value}"
            ),
            f"{job.title} @ {job.company}",
            (
                f"Source: {job.display_source()} | "
                f"Location: {job.location or 'unknown'} | "
                f"Remote scope: {job.remote_scope.value}"
            ),
            f"URL: {job.application_url or job.job_url or 'unknown'}",
        ])

        queries = job.raw_payload.get("search_queries", [])
        if queries:
            lines.append(f"Search queries: {', '.join(queries)}")

        lines.append(f"Reason: {' '.join(assessment.reasons)}")

    return "\n".join(lines)

def format_eligible_jobs(
    jobs: list[JobPosting],
    preferences: CareerPreferences,
) -> str:
    """Display QA vacancies with transparent candidate-fit decisions."""
    target_fit = []
    potential_stretch = []
    needs_review = []
    excluded_seniority = []
    excluded_role = []
    geography_excluded = 0

    for job in jobs:
        relevance = assess_job_relevance(job)
        if relevance.status == RelevanceStatus.IRRELEVANT:
            continue

        eligibility = assess_job_eligibility(job)

        if (
            eligibility.country_compatibility == Compatibility.INCOMPATIBLE
            or eligibility.timezone_compatibility == Compatibility.INCOMPATIBLE
        ):
            geography_excluded += 1
            continue

        fit = assess_candidate_fit(relevance, preferences)
        item = (job, relevance, eligibility, fit)

        if fit.status == CandidateFitStatus.OUT_OF_SCOPE:
            if fit.seniority_fit == SeniorityFit.TOO_SENIOR:
                excluded_seniority.append(item)
            else:
                excluded_role.append(item)
            continue

        if eligibility.status != EligibilityStatus.POTENTIALLY_ELIGIBLE:
            needs_review.append(item)
        elif fit.status == CandidateFitStatus.TARGET_FIT:
            target_fit.append(item)
        elif fit.status == CandidateFitStatus.POTENTIAL_STRETCH:
            potential_stretch.append(item)
        else:
            needs_review.append(item)

    for group in (
        target_fit,
        potential_stretch,
        needs_review,
        excluded_seniority,
        excluded_role,
    ):
        group.sort(key=lambda item: item[0].title.casefold())

    lines = [
        "Candidate Fit based on the local Candidate Profile",
        f"Target fit: {len(target_fit)}",
        f"Potential stretch: {len(potential_stretch)}",
        f"Needs manual review: {len(needs_review)}",
        f"Excluded by seniority: {len(excluded_seniority)}",
        f"Excluded by target role: {len(excluded_role)}",
        f"Excluded by source geography: {geography_excluded}",
        (
            "Legal ability to hire a Russia-based candidate is unverified. "
            "A stretch result is not a confirmed skills or experience match."
        ),
    ]

    def append_section(
        heading: str,
        items: list,
        marker: str,
    ) -> None:
        if not items:
            return

        lines.extend(["", f"{heading}:"])

        for job, relevance, eligibility, fit in items:
            reasons = list(dict.fromkeys(
                relevance.reasons + fit.reasons + eligibility.reasons
            ))
            lines.extend([
                "",
                f"[{marker}] {job.title} @ {job.company}",
                (
                    f"Role: {relevance.role_type.value} | "
                    f"Seniority: {relevance.seniority.value}"
                ),
                (
                    f"Source: {job.display_source()} | "
                    f"Location: {job.location or 'unknown'}"
                ),
                (
                    f"Candidate fit: {fit.status.value} | "
                    f"Geography: {eligibility.status.value}"
                ),
                f"Reason: {' '.join(reasons)}",
                f"URL: {job.application_url or job.job_url or 'unknown'}",
            ])

    append_section("Target-fit vacancies", target_fit, "TARGET FIT")
    append_section("Potential stretch vacancies", potential_stretch, "STRETCH")
    append_section("Vacancies requiring manual review", needs_review, "REVIEW")
    append_section(
        "Excluded because of seniority",
        excluded_seniority,
        "EXCLUDED - SENIORITY",
    )
    append_section(
        "Excluded because of target role",
        excluded_role,
        "EXCLUDED - ROLE",
    )

    if not any((
        target_fit,
        potential_stretch,
        needs_review,
        excluded_seniority,
        excluded_role,
    )):
        lines.extend([
            "",
            "No QA vacancies found for the current search.",
        ])

    return "\n".join(lines)
