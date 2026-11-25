"""Remotive public API. Jobs are delayed ~24 hours by the provider."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from career_agent.config_loader import RemotiveSettings
from career_agent.domain.job_posting import (
    JobPosting,
    SalaryPeriod,
    SalaryType,
    WorkplaceType,
)
from career_agent.integrations.job_sources.base import FetchResult
from career_agent.integrations.job_sources.errors import JobSourceError
from career_agent.integrations.job_sources.http import JobHttpClient
from career_agent.integrations.job_sources.location import parse_required_location
from career_agent.integrations.job_sources.rate_limit import SqliteRateLimiter

logger = logging.getLogger(__name__)

REMOTIVE_JOBS_URL = "https://remotive.com/api/remote-jobs"
REMOTIVE_MAX_PER_MINUTE = 2
REMOTIVE_MAX_PER_DAY = 4


class RemotiveJobSource:
    name = "remotive"

    def __init__(
        self,
        settings: RemotiveSettings,
        http: JobHttpClient,
        rate_limiter: SqliteRateLimiter | None = None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.rate_limiter = rate_limiter
        self._now = now

    def fetch_jobs(self) -> FetchResult:
        if not self.settings.enabled:
            return FetchResult(
                source=self.name,
                skipped=True,
                skip_reason="Remotive is disabled in config/job_search.yaml",
            )
        if self.rate_limiter is not None:
            blocked = self.rate_limiter.check(self.name, self._now)
            if blocked:
                logger.info("source_skipped source=remotive reason=rate_limit")
                return FetchResult(source=self.name, skipped=True, skip_reason=blocked)
        try:
            params: dict[str, str] = {"category": self.settings.category}
            payload = self.http.get_json(self.name, REMOTIVE_JOBS_URL, params=params)
            if self.rate_limiter is not None:
                self.rate_limiter.record(self.name, self._now)
        except JobSourceError as exc:
            logger.info("source_error source=remotive error=%s", exc)
            return FetchResult(source=self.name, error=str(exc))

        jobs_raw = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs_raw, list):
            return FetchResult(
                source=self.name,
                error="remotive: unexpected JSON shape (missing jobs list)",
            )

        jobs: list[JobPosting] = []
        for item in jobs_raw:
            if not isinstance(item, dict):
                continue
            try:
                jobs.append(self.normalize_job(item))
            except (KeyError, TypeError, ValueError) as exc:
                logger.info("source_job_skipped source=remotive reason=%s", exc.__class__.__name__)
        logger.info("source_fetched source=remotive count=%s", len(jobs))
        return FetchResult(source=self.name, jobs=jobs)

    def normalize_job(self, payload: dict[str, Any]) -> JobPosting:
        source_job_id = str(payload["id"])
        url = payload.get("url")
        location_raw = payload.get("candidate_required_location")
        scope, eligible, country_code = parse_required_location(
            location_raw if isinstance(location_raw, str) else None
        )
        published = _parse_datetime(payload.get("publication_date"))
        discovered = self._now or datetime.now(UTC)
        return JobPosting(
            id=str(uuid.uuid4()),
            source=self.name,
            source_job_id=source_job_id,
            title=str(payload.get("title") or "").strip() or "Untitled",
            company=str(payload.get("company_name") or "").strip() or "Unknown company",
            description=payload.get("description"),
            location=location_raw if isinstance(location_raw, str) else None,
            country_code=country_code,
            workplace_type=WorkplaceType.REMOTE,
            remote_scope=scope,
            eligible_countries=eligible,
            employment_type=payload.get("job_type"),
            experience_level=None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            salary_period=SalaryPeriod.UNKNOWN,
            salary_type=SalaryType.UNKNOWN,
            published_at=published,
            discovered_at=discovered,
            job_url=url,
            application_url=url,
            source_url=url,
            raw_payload={
                "provider": "remotive",
                "legal_notice": (
                    "Do not republish Remotive jobs on third-party aggregators. "
                    "Always show Remotive as the source and keep the original URL."
                ),
                "job": _public_raw(payload),
            },
        )


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _public_raw(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep original fields except huge HTML if needed later; store as given."""
    return payload
