from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from career_agent.config import Settings
from career_agent.config_loader import AdzunaSettings, RemotiveSettings
from career_agent.domain.job_posting import JobPosting, RemoteScope, WorkplaceType
from career_agent.integrations.job_sources.adzuna import AdzunaJobSource
from career_agent.integrations.job_sources.base import FetchResult
from career_agent.integrations.job_sources.remotive import RemotiveJobSource
from career_agent.main import main
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository
from career_agent.services.job_discovery import JobDiscoveryService, find_probable_duplicate

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def _job(**overrides: object) -> JobPosting:
    payload: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "source": "remotive",
        "source_job_id": "100",
        "title": "QA Engineer",
        "company": "Acme Inc",
        "discovered_at": NOW,
        "job_url": "https://remotive.com/remote-jobs/qa/qa-engineer-100",
        "source_url": "https://remotive.com/remote-jobs/qa/qa-engineer-100",
    }
    payload.update(overrides)
    return JobPosting.model_validate(payload)


def _repo(tmp_path: Path) -> JobRepository:
    factory = make_session_factory(make_engine(tmp_path / "jobs.sqlite"))
    return JobRepository(factory())


class FakeHttp:
    def __init__(self, payload: object | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, str, object]] = []

    def get_json(self, source: str, url: str, params=None, headers=None):  # noqa: ANN001
        self.calls.append((source, url, params))
        if self.error:
            raise self.error
        return self.payload


class FakeSource:
    def __init__(self, name: str, result: FetchResult) -> None:
        self.name = name
        self._result = result

    def fetch_jobs(self) -> FetchResult:
        return self._result

    def normalize_job(self, payload: dict) -> JobPosting:  # noqa: ARG002
        raise NotImplementedError


def test_remotive_fetch_uses_qa_category() -> None:
    http = FakeHttp({"jobs": [{"id": 7, "title": "API QA", "company_name": "Nexus", "url": "https://remotive.com/j/7"}]})
    source = RemotiveJobSource(RemotiveSettings(), http, now=NOW)  # type: ignore[arg-type]
    result = source.fetch_jobs()
    assert result.error is None
    assert result.jobs[0].title == "API QA"
    assert http.calls[0][2] == {"category": "qa"}


def test_remotive_normalize_worldwide() -> None:
    source = RemotiveJobSource(RemotiveSettings(), FakeHttp(), now=NOW)  # type: ignore[arg-type]
    job = source.normalize_job(
        {
            "id": 42,
            "url": "https://remotive.com/remote-jobs/qa/qa-engineer-42",
            "title": "QA Engineer",
            "company_name": "Acme Inc",
            "candidate_required_location": "Worldwide",
            "job_type": "full_time",
            "publication_date": "2026-11-01T12:00:00",
            "description": "Manual and API testing",
            "salary": "",
        }
    )
    assert job.source == "remotive"
    assert job.display_source() == "Remotive"
    assert job.source_job_id == "42"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.remote_scope is RemoteScope.WORLDWIDE
    assert job.eligible_countries is None
    assert job.job_url.endswith("qa-engineer-42")
    assert job.published_at is not None
    assert job.expires_at is None
    assert job.salary_min is None
    assert job.raw_payload["provider"] == "remotive"


def test_adzuna_normalize_does_not_invent_net_salary() -> None:
    source = AdzunaJobSource(AdzunaSettings(), FakeHttp(), "id", "key", now=NOW)  # type: ignore[arg-type]
    job = source.normalize_job(
        {
            "id": "gb-9",
            "title": "Manual QA",
            "company": {"display_name": "Beta Ltd"},
            "location": {"display_name": "Madrid, Spain"},
            "created": "2026-11-01T00:00:00Z",
            "redirect_url": "https://www.adzuna.es/jobs/9",
            "salary_min": 30000,
            "salary_max": 40000,
            "contract_time": "full_time",
            "description": "Testing APIs",
        },
        country_hint="ES",
    )
    assert job.source == "adzuna"
    assert job.display_source() == "Adzuna"
    assert job.salary_min == 30000
    assert job.salary_type.value == "unknown"
    assert job.country_code in {"ES", None} or job.location == "Madrid, Spain"


def test_adzuna_skips_without_api_keys() -> None:
    source = AdzunaJobSource(
        AdzunaSettings(),
        FakeHttp(),  # type: ignore[arg-type]
        app_id=None,
        app_key=None,
    )
    result = source.fetch_jobs()
    assert result.skipped is True
    assert result.jobs == []
    assert result.skip_reason is not None
    assert "ADZUNA_APP_ID" in result.skip_reason


def test_save_and_list_jobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saved = repo.save(_job(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    listed = repo.list_jobs(limit=10)
    assert listed[0].id == saved.id
    assert repo.get(saved.id) is not None
    assert repo.exists_source_id("remotive", "100") is True


def test_exact_duplicate_is_not_saved_twice(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _job(source_job_id="dup-1")
    second = _job(id=str(uuid.uuid4()), source_job_id="dup-1")
    source = FakeSource("remotive", FetchResult(source="remotive", jobs=[first, second]))
    report = JobDiscoveryService(repo, [source]).search()
    summary = report.summaries[0]
    assert summary.saved == 1
    assert summary.duplicates == 1
    assert len(repo.all_jobs()) == 1


def test_cross_source_probable_duplicate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    remotive = _job(source="remotive", source_job_id="r1", company="Acme Inc", title="QA Engineer")
    adzuna = _job(
        id=str(uuid.uuid4()),
        source="adzuna",
        source_job_id="a1",
        company="Acme",
        title="QA Engineer",
        job_url="https://www.adzuna.co.uk/jobs/a1",
        source_url="https://www.adzuna.co.uk/jobs/a1",
    )
    remotive_source = FakeSource("remotive", FetchResult("remotive", [remotive]))
    JobDiscoveryService(repo, [remotive_source]).search()
    report = JobDiscoveryService(
        repo, [FakeSource("adzuna", FetchResult("adzuna", [adzuna]))]
    ).search()
    assert report.summaries[0].probable_duplicates == 1
    stored = repo.get_by_source_id("adzuna", "a1")
    assert stored is not None
    assert stored.duplicate_of_id == remotive.id
    assert remotive.job_url in stored.related_urls


def test_same_title_different_companies_are_not_duplicates() -> None:
    left = _job(company="Acme Inc", title="QA Engineer")
    right = _job(
        id=str(uuid.uuid4()),
        source="adzuna",
        source_job_id="other",
        company="Globex",
        title="QA Engineer",
        job_url="https://example.com/other",
        source_url="https://example.com/other",
    )
    assert find_probable_duplicate(right, [left]) is None


def test_one_source_error_does_not_stop_the_other(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ok_job = _job(source="adzuna", source_job_id="ok")
    remotive = FakeSource("remotive", FetchResult(source="remotive", error="HTTP 500"))
    adzuna = FakeSource("adzuna", FetchResult(source="adzuna", jobs=[ok_job]))
    report = JobDiscoveryService(repo, [remotive, adzuna]).search()
    assert report.summaries[0].error == "HTTP 500"
    assert report.summaries[1].saved == 1
    assert repo.get_by_source_id("adzuna", "ok") is not None


def test_cli_adzuna_search_explains_missing_keys(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "jobs.sqlite",
        job_search_config_path=ROOT / "config" / "job_search.yaml",
        adzuna_app_id=None,
        adzuna_app_key=None,
        profile_path=EXAMPLE_PROFILE,
    )
    monkeypatch.setattr("career_agent.main.get_settings", lambda: settings)
    assert main(["jobs", "search", "--source", "adzuna"]) == 0
    output = capsys.readouterr().out
    assert "ADZUNA_APP_ID" in output
    assert "skipped" in output


def test_cli_jobs_list_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "jobs.sqlite",
        job_search_config_path=ROOT / "config" / "job_search.yaml",
        profile_path=EXAMPLE_PROFILE,
    )
    monkeypatch.setattr("career_agent.main.get_settings", lambda: settings)
    assert main(["jobs", "list", "--limit", "10"]) == 0
    assert "No jobs stored yet" in capsys.readouterr().out


def test_profile_validate_still_works() -> None:
    assert main(["profile", "validate", "--path", str(EXAMPLE_PROFILE)]) == 0

def test_adzuna_market_country_is_not_work_eligibility() -> None:
    source = AdzunaJobSource(
        AdzunaSettings(), FakeHttp(), "id", "key", now=NOW
    )  # type: ignore[arg-type]

    job = source.normalize_job(
        {
            "id": "gb-10",
            "title": "QA Tester",
            "company": {"display_name": "Example Ltd"},
            "location": {"display_name": "London"},
            "redirect_url": "https://www.adzuna.co.uk/jobs/10",
            "description": "Manual QA testing",
        },
        country_hint="gb",
    )

    assert job.country_code == "GB"
    assert job.workplace_type is WorkplaceType.UNKNOWN
    assert job.remote_scope is RemoteScope.UNKNOWN
    assert job.eligible_countries is None



def test_existing_job_is_refreshed_without_resetting_first_discovery(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    original = _job(
        source_job_id="refresh-1",
        title="QA Engineer",
        description="Old description",
        salary_min=40000,
    )
    repo.save(original)

    refreshed_at = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    incoming = _job(
        id=original.id,
        source_job_id=original.source_job_id,
        title="QA Engineer II",
        description="Updated responsibilities and requirements",
        salary_min=60000,
        expires_at=datetime(2026, 12, 15, 12, 0, tzinfo=UTC),
        discovered_at=refreshed_at,
        job_url="https://example.com/updated-job",
        source_url="https://example.com/updated-job",
    )

    report = JobDiscoveryService(
        repo,
        [FakeSource("remotive", FetchResult("remotive", [incoming]))],
    ).search()

    summary = report.summaries[0]
    stored = repo.get_by_source_id("remotive", "refresh-1")

    assert stored is not None
    assert summary.saved == 0
    assert summary.updated == 1
    assert summary.duplicates == 0
    assert stored.id == original.id
    assert stored.title == "QA Engineer II"
    assert stored.description == "Updated responsibilities and requirements"
    assert stored.salary_min == 60000
    assert stored.expires_at is not None
    assert stored.expires_at.replace(tzinfo=UTC) == datetime(
        2026, 12, 15, 12, 0, tzinfo=UTC
    )
    assert stored.discovered_at.replace(tzinfo=UTC) == NOW
    assert stored.last_seen_at is not None
    assert stored.last_seen_at.replace(tzinfo=UTC) == refreshed_at
    assert original.job_url in stored.related_urls


def test_unchanged_existing_job_updates_last_seen_at(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    original = _job(source_job_id="unchanged-1")
    repo.save(original)

    seen_at = datetime(2026, 11, 23, 14, 0, tzinfo=UTC)
    incoming = original.model_copy(update={"discovered_at": seen_at})

    report = JobDiscoveryService(
        repo,
        [FakeSource("remotive", FetchResult("remotive", [incoming]))],
    ).search()

    summary = report.summaries[0]
    stored = repo.get_by_source_id("remotive", "unchanged-1")

    assert stored is not None
    assert summary.updated == 0
    assert summary.duplicates == 1
    assert stored.discovered_at.replace(tzinfo=UTC) == NOW
    assert stored.last_seen_at is not None
    assert stored.last_seen_at.replace(tzinfo=UTC) == seen_at
