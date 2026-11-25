"""Adzuna search API. Disabled when APP_ID / APP_KEY are missing."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from career_agent.config_loader import AdzunaSettings
from career_agent.domain.job_posting import (
    JobPosting,
    RemoteScope,
    SalaryPeriod,
    SalaryType,
    WorkplaceType,
)
from career_agent.integrations.job_sources.base import FetchResult
from career_agent.integrations.job_sources.errors import JobSourceError
from career_agent.integrations.job_sources.http import JobHttpClient

logger = logging.getLogger(__name__)

ADZUNA_SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


class AdzunaJobSource:
    name = "adzuna"

    def __init__(
        self,
        settings: AdzunaSettings,
        http: JobHttpClient,
        app_id: str | None,
        app_key: str | None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.app_id = app_id.strip() if app_id else None
        self.app_key = app_key.strip() if app_key else None
        self._now = now

    def fetch_jobs(self) -> FetchResult:
        if not self.settings.enabled:
            return FetchResult(
                source=self.name,
                skipped=True,
                skip_reason="Adzuna is disabled in config/job_search.yaml",
            )
        if not self.app_id or not self.app_key:
            reason = (
                "Adzuna is skipped: ADZUNA_APP_ID and ADZUNA_APP_KEY are not set. "
                "Create a free app at https://developer.adzuna.com/ and add the keys "
                "to local .env. Do not paste keys into chat."
            )
            logger.info("source_skipped source=adzuna reason=missing_credentials")
            return FetchResult(source=self.name, skipped=True, skip_reason=reason)

        jobs: list[JobPosting] = []
        errors: list[str] = []
        for country in self.settings.countries:
            for query in self.settings.queries:
                try:
                    payload = self._search(country, query)
                except JobSourceError as exc:
                    if exc.status_code == 404:
                        errors.append(f"Adzuna market '{country}' is not available (HTTP 404).")
                        logger.info("source_market_unavailable source=adzuna country=%s", country)
                        break
                    logger.info("source_error source=adzuna country=%s error=%s", country, exc)
                    errors.append(str(exc))
                    continue
                results = payload.get("results") if isinstance(payload, dict) else None
                if not isinstance(results, list):
                    errors.append(f"Adzuna {country}: unexpected JSON shape.")
                    continue
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    try:
                        jobs.append(self.normalize_job(item, country_hint=country.upper()))
                    except (KeyError, TypeError, ValueError):
                        logger.info("source_job_skipped source=adzuna reason=normalize")
        logger.info("source_fetched source=adzuna count=%s", len(jobs))
        if jobs:
            return FetchResult(
                source=self.name,
                jobs=jobs,
                error="; ".join(errors) if errors else None,
            )
        if errors:
            return FetchResult(source=self.name, error="; ".join(errors))
        return FetchResult(source=self.name, jobs=[])

    def _search(self, country: str, query: str) -> Any:
        url = ADZUNA_SEARCH_URL.format(country=country, page=1)
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query,
            "results_per_page": self.settings.results_per_page,
            "content-type": "application/json",
        }
        return self.http.get_json(self.name, url, params=params)

    def normalize_job(self, payload: dict[str, Any], country_hint: str | None = None) -> JobPosting:
        company_obj = payload.get("company") or {}
        location_obj = payload.get("location") or {}
        company = ""
        if isinstance(company_obj, dict):
            company = str(company_obj.get("display_name") or "")
        location = None
        if isinstance(location_obj, dict):
            location = location_obj.get("display_name")
        # country_hint identifies the Adzuna search market,
        # not the countries from which an employer accepts candidates.
        country_code = country_hint.upper() if country_hint else None
        scope = RemoteScope.UNKNOWN
        eligible = None
        created = payload.get("created")
        salary_min = _as_float(payload.get("salary_min"))
        salary_max = _as_float(payload.get("salary_max"))
        redirect = payload.get("redirect_url")
        source_id = str(payload.get("id") or "")
        return JobPosting(
            id=str(uuid.uuid4()),
            source=self.name,
            source_job_id=source_id,
            title=str(payload.get("title") or "").strip() or "Untitled",
            company=company.strip() or "Unknown company",
            description=payload.get("description"),
            location=location if isinstance(location, str) else None,
            country_code=country_code,
            workplace_type=WorkplaceType.UNKNOWN,
            remote_scope=scope,
            eligible_countries=eligible,
            employment_type=payload.get("contract_type") or payload.get("contract_time"),
            experience_level=None,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=None,
            salary_period=SalaryPeriod.YEAR if salary_min or salary_max else SalaryPeriod.UNKNOWN,
            salary_type=SalaryType.UNKNOWN,
            published_at=_parse_datetime(created),
            discovered_at=self._now or datetime.now(UTC),
            job_url=redirect,
            application_url=redirect,
            source_url=redirect,
            raw_payload={"provider": "adzuna", "job": payload},
        )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
