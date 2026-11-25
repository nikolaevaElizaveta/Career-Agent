from datetime import UTC, datetime

from career_agent.cli.jobs import format_eligible_jobs
from career_agent.domain.candidate import CareerPreferences
from career_agent.domain.job_posting import JobPosting
from career_agent.main import build_parser

ALL_RUSSIA_OFFSETS = list(range(2, 13))


def make_preferences() -> CareerPreferences:
    return CareerPreferences(
        target_roles=[
            "Manual QA / QA Engineer",
            "API QA / API Testing",
            "Integration Testing / Integration QA",
            "Junior QA Automation",
        ],
        experience_band="junior_0_2",
        also_consider_years="2_3_if_strong_fit",
    )


def make_job(
    *,
    title: str = "Junior QA Engineer",
    locations: list | None = None,
    timezones: list | None = None,
    include_geo_fields: bool = True,
) -> JobPosting:
    payload = {
        "provider": "himalayas",
        "job": {},
    }

    if include_geo_fields:
        payload["job"]["locationRestrictions"] = locations
        payload["job"]["timezoneRestrictions"] = timezones

    return JobPosting(
        id=f"test-{title.lower().replace(' ', '-')}",
        source="himalayas",
        source_job_id=f"test-{title}",
        title=title,
        company="Example Company",
        location="Remote",
        discovered_at=datetime.now(UTC),
        raw_payload=payload,
        job_url="https://example.com/job",
        application_url="https://example.com/apply",
    )


def test_eligible_formatter_shows_target_fit_job() -> None:
    job = make_job(
        locations=[],
        timezones=ALL_RUSSIA_OFFSETS,
    )

    result = format_eligible_jobs([job], make_preferences())

    assert "Target fit: 1" in result
    assert "[TARGET FIT]" in result
    assert "Junior QA Engineer @ Example Company" in result
    assert "Legal ability to hire a Russia-based candidate is unverified" in result


def test_eligible_formatter_sends_unknown_geo_data_to_review() -> None:
    job = make_job(include_geo_fields=False)

    result = format_eligible_jobs([job], make_preferences())

    assert "Needs manual review: 1" in result
    assert "[REVIEW]" in result
    assert "needs_verification" in result
    assert "[TARGET FIT]" not in result


def test_eligible_formatter_excludes_country_restricted_job() -> None:
    job = make_job(
        locations=["United Kingdom", "Spain"],
        timezones=ALL_RUSSIA_OFFSETS,
    )

    result = format_eligible_jobs([job], make_preferences())

    assert "Excluded by source geography: 1" in result
    assert "No QA vacancies found for the current search." in result


def test_eligible_formatter_keeps_ambiguous_qa_role_for_review() -> None:
    job = make_job(
        title="AI QA Trainer",
        locations=[],
        timezones=ALL_RUSSIA_OFFSETS,
    )

    result = format_eligible_jobs([job], make_preferences())

    assert "Needs manual review: 1" in result
    assert "AI QA Trainer @ Example Company" in result
    assert "[REVIEW]" in result


def test_eligible_formatter_excludes_lead_role_by_seniority() -> None:
    job = make_job(
        title="Lead QA Engineer",
        locations=[],
        timezones=ALL_RUSSIA_OFFSETS,
    )

    result = format_eligible_jobs([job], make_preferences())

    assert "Excluded by seniority: 1" in result
    assert "[EXCLUDED - SENIORITY]" in result
    assert "Lead QA Engineer @ Example Company" in result
    assert "level above the candidate" in result.lower()

def test_jobs_eligible_command_is_registered() -> None:
    args = build_parser().parse_args(["jobs", "eligible"])

    assert args.command == "jobs"
    assert args.jobs_command == "eligible"

def test_eligible_formatter_explains_target_role_exclusion() -> None:
    job = make_job(
        title="Junior QA Engineer",
        locations=[],
        timezones=ALL_RUSSIA_OFFSETS,
    )
    preferences = CareerPreferences(
        target_roles=["API QA / API Testing"],
        experience_band="junior_0_2",
        also_consider_years="2_3_if_strong_fit",
    )

    result = format_eligible_jobs([job], preferences)

    assert "Excluded by target role: 1" in result
    assert "[EXCLUDED - ROLE]" in result
    assert "Junior QA Engineer @ Example Company" in result
