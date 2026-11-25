"""Check provider job pages at most once every seven days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from career_agent.domain.job_posting import (
    JobPosting,
    LinkCheckStatus,
)
from career_agent.integrations.job_sources.http import JobHttpClient
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository

LINK_CHECK_INTERVAL = timedelta(days=7)

# Only check canonical pages on the job platforms already used by the agent.
ALLOWED_SOURCE_HOSTS = {
    "himalayas": ("himalayas.app",),
    "remotive": ("remotive.com",),
    "adzuna": ("adzuna.co.uk", "adzuna.es", "adzuna.com.au", "adzuna.com"),
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _provider_page_url(job: JobPosting) -> str | None:
    allowed_hosts = ALLOWED_SOURCE_HOSTS.get(job.source, ())
    candidates = (
        job.application_url,
        job.job_url,
        job.source_url,
    )

    for candidate in candidates:
        if not candidate:
            continue

        try:
            parsed = urlsplit(candidate)
            host = (parsed.hostname or "").casefold()
        except ValueError:
            continue

        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            continue

        if any(
            host == allowed or host.endswith("." + allowed)
            for allowed in allowed_hosts
        ):
            return candidate

    return None


def _classify_result(status_code: int | None) -> LinkCheckStatus:
    if status_code is None:
        return LinkCheckStatus.ERROR

    if 200 <= status_code < 400:
        return LinkCheckStatus.REACHABLE

    if status_code in {404, 410}:
        return LinkCheckStatus.NOT_FOUND

    if 400 <= status_code < 500:
        return LinkCheckStatus.RESTRICTED

    return LinkCheckStatus.ERROR


def check_job_link(
    database_path,
    job_id: str,
    now: datetime | None = None,
) -> JobPosting | None:
    """Check one provider page if its seven-day cooldown has elapsed."""
    moment = _utc(now or datetime.now(UTC))
    engine = make_engine(database_path)

    try:
        session_factory = make_session_factory(engine)

        with session_factory() as session:
            repository = JobRepository(session)
            job = repository.get(job_id)

            if job is None:
                return None

            if job.link_checked_at is not None:
                checked_at = _utc(job.link_checked_at)
                if moment - checked_at < LINK_CHECK_INTERVAL:
                    return job

            url = _provider_page_url(job)

            if url is None:
                # No supported canonical provider URL: do not make a request.
                updated = job.model_copy(
                    update={
                        "link_checked_at": moment,
                        "link_check_status": LinkCheckStatus.UNSUPPORTED,
                        "link_check_http_status": None,
                    }
                )
            else:
                client = JobHttpClient()
                try:
                    result = client.check_url(url)
                finally:
                    client.close()

                updated = job.model_copy(
                    update={
                        "link_checked_at": moment,
                        "link_check_status": _classify_result(result.status_code),
                        "link_check_http_status": result.status_code,
                    }
                )

            repository.update(updated)
            return updated
    finally:
        engine.dispose()
