from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from career_agent.domain.job_posting import JobPosting
from career_agent.main import build_parser, main
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def make_job(job_id: str) -> JobPosting:
    return JobPosting(
        id=job_id,
        source="test",
        source_job_id=job_id,
        title="Junior QA Engineer",
        company=f"Example Company {job_id}",
        description=(
            "<h2>Requirements</h2>"
            "<ul><li>Experience with Postman.</li></ul>"
            "<h2>Responsibilities</h2>"
            "<ul><li>Perform functional testing.</li></ul>"
        ),
        location="Remote",
        discovered_at=datetime.now(UTC),
        job_url=f"https://example.com/{job_id}",
        application_url=f"https://example.com/{job_id}/apply",
        raw_payload={
            "job": {
                "locationRestrictions": [],
                "timezoneRestrictions": list(range(2, 13)),
            }
        },
    )


def prepare_cli(
    tmp_path: Path,
    monkeypatch,
    jobs: list[JobPosting],
    profile_path: Path = EXAMPLE_PROFILE,
) -> None:
    database_path = tmp_path / "test_jobs.sqlite"
    factory = make_session_factory(make_engine(database_path))

    with factory() as session:
        repository = JobRepository(session)
        for job in jobs:
            repository.save(job)

    settings = SimpleNamespace(
        log_level="WARNING",
        database_path=database_path,
        profile_path=profile_path,
    )

    monkeypatch.setattr(
        "career_agent.main.get_settings",
        lambda: settings,
    )


def test_jobs_assess_displays_candidate_report(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    job = make_job("assessment-job-001")
    prepare_cli(tmp_path, monkeypatch, [job])

    result = main(["jobs", "assess", job.id])

    captured = capsys.readouterr()

    assert result == 0
    assert "CANDIDATE JOB ASSESSMENT" in captured.out
    assert "Junior QA Engineer" in captured.out
    assert "REQUIRED SKILL COVERAGE" in captured.out
    assert "Postman" in captured.out
    assert "GEOGRAPHIC ELIGIBILITY" in captured.out
    assert "Legal work authorization: unknown" in captured.out


def test_jobs_assess_reports_unknown_job(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    prepare_cli(tmp_path, monkeypatch, [])

    result = main(["jobs", "assess", "missing-job"])

    captured = capsys.readouterr()

    assert result == 1
    assert "No job found" in captured.err


def test_jobs_assess_reports_ambiguous_prefix(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    jobs = [
        make_job("shared-job-001"),
        make_job("shared-job-002"),
    ]
    prepare_cli(tmp_path, monkeypatch, jobs)

    result = main(["jobs", "assess", "shared-job"])

    captured = capsys.readouterr()

    assert result == 1
    assert "matches 2 jobs" in captured.err


def test_jobs_assess_rejects_invalid_profile(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    invalid_profile = tmp_path / "invalid-profile.json"
    invalid_profile.write_text("{invalid json", encoding="utf-8")

    job = make_job("assessment-job-002")
    prepare_cli(
        tmp_path,
        monkeypatch,
        [job],
        profile_path=invalid_profile,
    )

    result = main(["jobs", "assess", job.id])

    captured = capsys.readouterr()

    assert result == 1
    assert "Candidate Profile is invalid" in captured.err


def test_jobs_assess_command_is_registered() -> None:
    args = build_parser().parse_args(["jobs", "assess", "some-job-id"])

    assert args.command == "jobs"
    assert args.jobs_command == "assess"
    assert args.job_id == "some-job-id"
