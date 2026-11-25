from datetime import UTC, date, datetime
from pathlib import Path

from career_agent.cli.job_assessment import format_candidate_assessment
from career_agent.domain.job_posting import JobPosting, WorkplaceType
from career_agent.services.job_candidate_assessment import assess_candidate_job
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def make_job() -> JobPosting:
    return JobPosting(
        id="matcher-integration",
        source="test",
        source_job_id="matcher-integration",
        title="Junior QA Engineer",
        company="Example Company",
        description=(
            "<h2>Responsibilities</h2>"
            "<ul>"
            "<li>Perform functional testing.</li>"
            "<li>Prepare test data.</li>"
            "</ul>"
            "<h2>Requirements</h2>"
            "<ul>"
            "<li>Manual testing</li>"
            "<li>API testing</li>"
            "<li>SQL</li>"
            "</ul>"
        ),
        workplace_type=WorkplaceType.REMOTE,
        raw_payload={
            "job": {
                "locationRestrictions": [],
                "timezoneRestrictions": [],
            }
        },
        discovered_at=datetime(2026, 11, 23, tzinfo=UTC),
    )


def test_candidate_assessment_includes_all_score_categories() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    job = make_job()

    assessment = assess_candidate_job(
        job,
        profile,
        as_of=date(2026, 11, 23),
    )

    score = assessment.match_score

    assert score is not None
    assert score.observed_score is not None
    assert 0 <= score.coverage_percent <= 100
    assert score.score_floor <= score.score_ceiling

    assert {item.key for item in score.categories} == {
        "role_and_duties",
        "technical_skills",
        "geography",
        "salary",
        "ethics",
    }

    assert sum(
        item.configured_weight for item in score.categories
    ) == 100


def test_candidate_assessment_includes_duty_matches() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    assessment = assess_candidate_job(
        make_job(),
        profile,
        as_of=date(2026, 11, 23),
    )

    duties = [item.requirement.casefold() for item in assessment.duty_matches]

    assert len(duties) == 2
    assert any("functional testing" in item for item in duties)
    assert any("test data" in item for item in duties)


def test_cli_report_contains_explainable_score() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    assessment = assess_candidate_job(
        make_job(),
        profile,
        as_of=date(2026, 11, 23),
    )

    report = format_candidate_assessment(assessment)

    assert "DUTY MATCH DETAILS" in report
    assert "Perform functional testing." in report
    assert "Evidence coverage:" in report
    assert "OVERALL MATCH SCORE" in report
    assert "CATEGORY BREAKDOWN" in report
    assert "Evidence coverage:" in report
    assert "Possible score range:" in report
    assert "Technical skills:" in report
    assert "Salary:" in report
