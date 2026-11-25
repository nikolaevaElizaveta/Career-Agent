from datetime import UTC, datetime, timedelta

from career_agent.domain.job_posting import JobPosting, LinkCheckStatus
from career_agent.integrations.job_sources.http import URLCheckResult
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository
from career_agent.services.job_link_checker import (
    _classify_result,
    check_job_link,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _save_job(database_path, url="https://himalayas.app/jobs/qa"):
    engine = make_engine(database_path)
    try:
        factory = make_session_factory(engine)
        with factory() as session:
            job = JobPosting(
                id="test-job",
                source="himalayas",
                source_job_id="test-job",
                title="QA Engineer",
                company="Example Ltd",
                discovered_at=NOW,
                job_url=url,
                application_url=url,
                source_url=url,
            )
            JobRepository(session).save(job)
    finally:
        engine.dispose()


def test_link_status_classification() -> None:
    assert _classify_result(200) is LinkCheckStatus.REACHABLE
    assert _classify_result(301) is LinkCheckStatus.REACHABLE
    assert _classify_result(404) is LinkCheckStatus.NOT_FOUND
    assert _classify_result(410) is LinkCheckStatus.NOT_FOUND
    assert _classify_result(403) is LinkCheckStatus.RESTRICTED
    assert _classify_result(429) is LinkCheckStatus.RESTRICTED
    assert _classify_result(503) is LinkCheckStatus.ERROR
    assert _classify_result(None) is LinkCheckStatus.ERROR


def test_link_check_is_persisted_and_respects_seven_day_interval(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "jobs.sqlite"
    _save_job(database_path)

    class FakeHttpClient:
        calls = 0

        def check_url(self, url):
            assert url == "https://himalayas.app/jobs/qa"
            self.calls += 1
            if self.calls == 1:
                return URLCheckResult(200)
            return URLCheckResult(404)

        def close(self):
            pass

    fake_client = FakeHttpClient()
    monkeypatch.setattr(
        "career_agent.services.job_link_checker.JobHttpClient",
        lambda: fake_client,
    )

    first = check_job_link(database_path, "test-job", NOW)
    assert first is not None
    assert first.link_check_status is LinkCheckStatus.REACHABLE
    assert first.link_check_http_status == 200
    assert fake_client.calls == 1

    # Six days later, the stored result is reused without another request.
    second = check_job_link(
        database_path,
        "test-job",
        NOW + timedelta(days=6),
    )
    assert second is not None
    assert second.link_check_status is LinkCheckStatus.REACHABLE
    assert fake_client.calls == 1

    # At seven days the page is checked again.
    third = check_job_link(
        database_path,
        "test-job",
        NOW + timedelta(days=7),
    )
    assert third is not None
    assert third.link_check_status is LinkCheckStatus.NOT_FOUND
    assert third.link_check_http_status == 404
    assert fake_client.calls == 2


def test_unsupported_host_is_not_requested(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "jobs.sqlite"
    _save_job(database_path, "https://untrusted.example/jobs/qa")

    def unexpected_client():
        raise AssertionError("Unsupported host must not be requested")

    monkeypatch.setattr(
        "career_agent.services.job_link_checker.JobHttpClient",
        unexpected_client,
    )

    result = check_job_link(database_path, "test-job", NOW)

    assert result is not None
    assert result.link_check_status is LinkCheckStatus.UNSUPPORTED
    assert result.link_checked_at is not None


def test_missing_job_returns_none(tmp_path) -> None:
    result = check_job_link(tmp_path / "jobs.sqlite", "missing", NOW)
    assert result is None
