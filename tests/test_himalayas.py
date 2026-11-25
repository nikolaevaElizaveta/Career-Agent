from datetime import UTC, datetime

from career_agent.config_loader import HimalayasSettings
from career_agent.domain.job_posting import (
    RemoteScope,
    SalaryPeriod,
    SalaryType,
)
from career_agent.integrations.job_sources.himalayas import (
    HimalayasJobSource,
)

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


class FakeHttp:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def get_json(self, source, url, params=None, headers=None):
        self.calls.append(dict(params or {}))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def _payload(**overrides):
    result = {
        "guid": "https://himalayas.app/companies/example/jobs/qa-engineer",
        "title": "QA Engineer",
        "companyName": "Example Ltd",
        "employmentType": "Full Time",
        "locationRestrictions": [],
        "timezoneRestrictions": [],
        "categories": ["QA-Engineer", "Software-Testing"],
        "seniority": ["Entry-level"],
        "minSalary": 50000,
        "maxSalary": 70000,
        "salaryPeriod": "annual",
        "currency": "USD",
        "pubDate": 1795309630,
        "expiryDate": 1797577277,
        "applicationLink": (
            "https://himalayas.app/apply/example?utm_source=api"
        ),
        "description": "Manual and API testing.",
    }
    result.update(overrides)
    return result


def _source(http, **settings_overrides):
    settings_data = {
        "countries": ["RU"],
        "queries": ["QA Engineer"],
        "request_delay_seconds": 0,
    }
    settings_data.update(settings_overrides)
    settings = HimalayasSettings(**settings_data)
    return HimalayasJobSource(
        settings,
        http,
        now=NOW,
        sleep_fn=lambda _: None,
    )


def test_normalize_himalayas_job() -> None:
    source = _source(FakeHttp([{"jobs": []}]))
    job = source.normalize_job(
        _payload(),
        search_query="QA Engineer",
        search_country="RU",
    )

    assert job.source == "himalayas"
    assert job.source_job_id
    assert len(job.source_job_id) == 64
    assert job.title == "QA Engineer"
    assert job.company == "Example Ltd"
    assert job.remote_scope is RemoteScope.WORLDWIDE
    assert job.eligible_countries is None
    assert job.salary_min == 50000
    assert job.salary_max == 70000
    assert job.salary_currency == "USD"
    assert job.salary_period is SalaryPeriod.YEAR
    assert job.salary_type is SalaryType.UNKNOWN
    assert job.experience_level == "Entry-level"
    assert job.application_url == (
        "https://himalayas.app/apply/example?utm_source=api"
    )
    assert job.job_url == _payload()["guid"]
    assert job.published_at is not None
    assert job.expires_at == datetime.fromtimestamp(1797577277, tz=UTC)
    assert job.raw_payload["search_countries"] == ["RU"]


def test_country_restrictions_are_preserved() -> None:
    source = _source(FakeHttp([{"jobs": []}]))
    job = source.normalize_job(
        _payload(
            locationRestrictions=[
                {"alpha2": "GB", "name": "United Kingdom", "slug": "uk"},
                {"alpha2": "ES", "name": "Spain", "slug": "spain"},
            ]
        )
    )

    assert job.remote_scope is RemoteScope.COUNTRY_RESTRICTED
    assert job.eligible_countries == ["GB", "ES"]
    assert job.country_code is None
    assert job.location == "United Kingdom, Spain"


def test_himalayas_multiple_queries_are_deduplicated() -> None:
    same_job = _payload()
    http = FakeHttp([
        {"jobs": [same_job]},
        {"jobs": [same_job]},
    ])
    source = _source(
        http,
        queries=["QA Engineer", "Manual QA"],
    )

    result = source.fetch_jobs()

    assert result.error is None
    assert len(result.jobs) == 1
    assert len(http.calls) == 2
    assert result.jobs[0].raw_payload["search_queries"] == [
        "QA Engineer",
        "Manual QA",
    ]


def test_himalayas_uses_country_and_relevance_sort() -> None:
    http = FakeHttp([{"jobs": []}])
    source = _source(http)

    source.fetch_jobs()

    assert http.calls[0]["country"] == "RU"
    assert http.calls[0]["sort"] == "relevant"
    assert http.calls[0]["q"] == "QA Engineer"


def test_himalayas_missing_guid_is_rejected() -> None:
    source = _source(FakeHttp([{"jobs": []}]))

    try:
        source.normalize_job({"title": "QA Engineer"})
    except ValueError as exc:
        assert "guid" in str(exc)
    else:
        raise AssertionError("Missing guid should be rejected")

def test_cli_accepts_himalayas_source() -> None:
    from career_agent.main import build_parser

    args = build_parser().parse_args(
        ["jobs", "search", "--source", "himalayas"]
    )
    assert args.source == "himalayas"


def test_factory_registers_himalayas(tmp_path) -> None:
    from career_agent.config import Settings
    from career_agent.config_loader import load_job_search_config
    from career_agent.integrations.job_sources.factory import build_sources
    from career_agent.repositories.db import (
        make_engine,
        make_session_factory,
    )

    config_path = __import__("pathlib").Path(
        "config/job_search.yaml"
    ).resolve()

    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "factory.sqlite",
        job_search_config_path=config_path,
        profile_path=config_path.parent.parent / "data" / "candidate_profile.example.json",
    )
    search_config = load_job_search_config(config_path)

    engine = make_engine(settings.database_path)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        sources = build_sources(
            settings,
            search_config,
            session,
            http=FakeHttp([{"jobs": []}]),
        )

    assert [source.name for source in sources] == [
        "remotive",
        "himalayas",
        "adzuna",
    ]




def test_himalayas_string_country_restrictions() -> None:
    source = _source(FakeHttp([{"jobs": []}]))
    job = source.normalize_job(
        _payload(
            locationRestrictions=["Russian Federation", "Austria"]
        )
    )

    assert job.remote_scope is RemoteScope.COUNTRY_RESTRICTED
    assert job.eligible_countries == ["RU", "Austria"]
    assert job.country_code is None
    assert job.location == "Russian Federation, Austria"
