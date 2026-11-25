from career_agent.integrations.job_sources.base import FetchResult
from career_agent.services.job_discovery import JobDiscoveryService


class EmptyRepository:
    def all_jobs(self):
        return []


class BrokenSource:
    name = "broken"

    def fetch_jobs(self):
        raise RuntimeError("simulated provider failure")


class HealthySource:
    name = "healthy"

    def fetch_jobs(self):
        return FetchResult(source=self.name, jobs=[])


def test_one_provider_failure_does_not_stop_other_sources() -> None:
    service = JobDiscoveryService(
        EmptyRepository(),
        [BrokenSource(), HealthySource()],
    )

    report = service.search()

    assert len(report.summaries) == 2
    assert report.summaries[0].source == "broken"
    assert report.summaries[0].error == "Unexpected source error"
    assert report.summaries[1].source == "healthy"
    assert report.summaries[1].error is None
    assert report.summaries[1].skipped is False
