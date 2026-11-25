from datetime import UTC, datetime

import pytest

from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_relevance import (
    RelevanceStatus,
    RoleType,
    SeniorityLevel,
    assess_job_relevance,
)


def make_job(
    title: str,
    category: str | None = None,
    tags: list[str] | None = None,
    description: str | None = None,
    categories: list[str] | None = None,
) -> JobPosting:
    source_job = {
        "category": category,
        "categories": categories or [],
        "tags": tags or [],
    }

    return JobPosting(
        id=f"test-{title}",
        source="remotive",
        source_job_id=f"test-{title}",
        title=title,
        company="Example Company",
        discovered_at=datetime.now(UTC),
        description=description,
        raw_payload={"provider": "remotive", "job": source_job},
    )


@pytest.mark.parametrize(
    "title",
    [
        "QA Engineer",
        "Manual QA Tester",
        "API QA Engineer",
        "API Test Engineer",
        "Integration Test Engineer",
        "Junior QA Automation Engineer",
        "Software Test Analyst",
        "SDET",
    ],
)
def test_explicit_qa_titles_are_relevant(title: str) -> None:
    assessment = assess_job_relevance(make_job(title))
    assert assessment.status == RelevanceStatus.RELEVANT


def test_qa_category_without_clear_title_needs_review() -> None:
    job = make_job(
        "Technical Specialist",
        category="Quality Assurance",
    )
    assert assess_job_relevance(job).status == RelevanceStatus.NEEDS_REVIEW


def test_himalayas_qa_categories_without_clear_title_need_review() -> None:
    job = make_job(
        "Technical Specialist",
        categories=["QA-Engineer", "Software-Testing"],
    )

    assessment = assess_job_relevance(job)

    assert assessment.status == RelevanceStatus.NEEDS_REVIEW
    assert assessment.role_type == RoleType.SOFTWARE_QA


def test_generic_software_role_with_testing_tag_needs_review() -> None:
    job = make_job(
        "Software Engineer",
        tags=["Python", "Test Automation"],
    )
    assert assess_job_relevance(job).status == RelevanceStatus.NEEDS_REVIEW


def test_backend_developer_with_automation_tag_is_not_qa() -> None:
    job = make_job(
        "Senior Back-end Developer",
        category="Software Development",
        tags=["Python", "automation"],
    )
    assert assess_job_relevance(job).status == RelevanceStatus.IRRELEVANT


def test_unrelated_job_with_qa_only_in_description_is_irrelevant() -> None:
    job = make_job(
        "AI Trainer",
        category="Artificial Intelligence",
        description="Experience with QA teams is a plus.",
    )
    assert assess_job_relevance(job).status == RelevanceStatus.IRRELEVANT


def test_assessment_explains_matched_title() -> None:
    assessment = assess_job_relevance(make_job("API QA Engineer"))

    assert "api_qa" in assessment.matched_roles
    assert assessment.role_type == RoleType.API_QA
    assert assessment.reasons


def test_ai_qa_trainer_is_classified_separately() -> None:
    assessment = assess_job_relevance(
        make_job("AI QA Trainer – LLM Evaluation")
    )

    assert assessment.status == RelevanceStatus.NEEDS_REVIEW
    assert assessment.role_type == RoleType.AI_EVALUATION


def test_localization_qa_is_not_conventional_software_qa() -> None:
    assessment = assess_job_relevance(
        make_job("Freelance Game LQA Tester Chinese to English")
    )

    assert assessment.status == RelevanceStatus.NEEDS_REVIEW
    assert assessment.role_type == RoleType.LOCALIZATION_QA


def test_business_process_qa_is_separated() -> None:
    assessment = assess_job_relevance(
        make_job("Assistant Vice President – Lead QA & Proofing Unit")
    )

    assert assessment.status == RelevanceStatus.NEEDS_REVIEW
    assert assessment.role_type == RoleType.BUSINESS_PROCESS_QA
    assert assessment.seniority == SeniorityLevel.MANAGER_EXECUTIVE


def test_kernel_testing_is_specialised() -> None:
    assessment = assess_job_relevance(
        make_job("Ubuntu Linux Kernel Test Engineer")
    )

    assert assessment.status == RelevanceStatus.NEEDS_REVIEW
    assert assessment.role_type == RoleType.SYSTEM_TESTING


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("QA Intern", SeniorityLevel.INTERNSHIP),
        ("Junior QA Engineer", SeniorityLevel.JUNIOR),
        ("QA Engineer - Backend Junior+", SeniorityLevel.JUNIOR),
        ("QA Engineer", SeniorityLevel.UNKNOWN),
        ("Mid-level QA Engineer", SeniorityLevel.MIDDLE),
        ("Senior QA Engineer", SeniorityLevel.SENIOR),
        ("Lead QA Engineer", SeniorityLevel.LEAD),
        ("QA Principal", SeniorityLevel.PRINCIPAL),
        ("QA Manager", SeniorityLevel.MANAGER_EXECUTIVE),
    ],
)
def test_seniority_is_extracted_from_title(
    title: str,
    expected: SeniorityLevel,
) -> None:
    assessment = assess_job_relevance(make_job(title))
    assert assessment.seniority == expected


def test_web_app_test_engineer_is_software_qa() -> None:
    assessment = assess_job_relevance(
        make_job("Web/App Test Engineer")
    )

    assert assessment.status == RelevanceStatus.RELEVANT
    assert assessment.role_type == RoleType.SOFTWARE_QA


def test_format_relevant_jobs_includes_relevant_and_review_items() -> None:
    from career_agent.cli.jobs import format_relevant_jobs

    jobs = [
        make_job("QA Engineer"),
        make_job("AI QA Trainer"),
        make_job("Product Manager"),
    ]

    output = format_relevant_jobs(jobs)

    assert "QA Engineer" in output
    assert "AI QA Trainer" in output
    assert "Product Manager" not in output
    assert "RELEVANT" in output
    assert "NEEDS_REVIEW" in output


def test_jobs_relevant_cli_command_is_registered() -> None:
    from career_agent.main import build_parser

    args = build_parser().parse_args(["jobs", "relevant"])

    assert args.command == "jobs"
    assert args.jobs_command == "relevant"
