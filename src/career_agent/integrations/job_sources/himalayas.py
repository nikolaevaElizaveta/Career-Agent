"""Himalayas public jobs API adapter."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from career_agent.config_loader import HimalayasSettings
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
from career_agent.integrations.job_sources.location import COUNTRY_ALIASES

logger = logging.getLogger(__name__)

HIMALAYAS_SEARCH_URL = "https://himalayas.app/jobs/api/search"
PAGE_SIZE = 20


class HimalayasJobSource:
    name = "himalayas"

    def __init__(
        self,
        settings: HimalayasSettings,
        http: JobHttpClient,
        now: datetime | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self._now = now
        self._sleep = sleep_fn or time.sleep

    def fetch_jobs(self) -> FetchResult:
        if not self.settings.enabled:
            return FetchResult(
                source=self.name,
                skipped=True,
                skip_reason="Himalayas is disabled in config/job_search.yaml",
            )

        collected: dict[str, JobPosting] = {}
        errors: list[str] = []
        request_count = 0
        stop_search = False

        for country in self.settings.countries:
            for query in self.settings.queries:
                if stop_search:
                    break

                for page in range(1, self.settings.max_pages + 1):
                    if request_count:
                        delay = self.settings.request_delay_seconds
                        if delay > 0:
                            self._sleep(delay)

                    params = {
                        "q": query,
                        "country": country.upper(),
                        "sort": self.settings.sort,
                        "page": page,
                    }

                    try:
                        payload = self.http.get_json(
                            self.name,
                            HIMALAYAS_SEARCH_URL,
                            params=params,
                        )
                    except JobSourceError as exc:
                        errors.append(
                            f"{query} ({country}): {exc}"
                        )
                        logger.info(
                            "source_error source=himalayas status=%s",
                            exc.status_code,
                        )
                        if exc.status_code == 429:
                            stop_search = True
                            break
                        break

                    request_count += 1

                    items = (
                        payload.get("jobs")
                        if isinstance(payload, dict)
                        else None
                    )

                    if not isinstance(items, list):
                        errors.append(
                            f"{query} ({country}): unexpected JSON shape"
                        )
                        break

                    for item in items:
                        if not isinstance(item, dict):
                            continue

                        try:
                            job = self.normalize_job(
                                item,
                                search_query=query,
                                search_country=country,
                            )
                        except (KeyError, TypeError, ValueError):
                            logger.info(
                                "source_job_skipped source=himalayas reason=normalize"
                            )
                            continue

                        key = job.source_job_id

                        if key in collected:
                            _merge_search_metadata(
                                collected[key],
                                query,
                                country,
                            )
                        else:
                            collected[key] = job

                    if len(items) < PAGE_SIZE:
                        break

        jobs = list(collected.values())

        logger.info(
            "source_fetched source=himalayas requests=%s count=%s",
            request_count,
            len(jobs),
        )

        return FetchResult(
            source=self.name,
            jobs=jobs,
            error="; ".join(errors) if errors else None,
        )

    def normalize_job(
        self,
        payload: dict[str, Any],
        search_query: str | None = None,
        search_country: str | None = None,
    ) -> JobPosting:
        guid = str(payload.get("guid") or "").strip()
        if not guid:
            raise ValueError("Himalayas job has no guid")

        source_job_id = hashlib.sha256(
            guid.encode()
        ).hexdigest()

        application_link = payload.get("applicationLink")
        job_url = (
            guid
            if guid.startswith(("https://", "http://"))
            else None
        )

        restrictions = payload.get("locationRestrictions")
        eligible: list[str] | None = None
        country_code: str | None = None
        location: str | None = None
        scope = RemoteScope.UNKNOWN

        if isinstance(restrictions, list):
            if not restrictions:
                scope = RemoteScope.WORLDWIDE
                location = "Worldwide"
            else:
                eligible_values: list[str] = []
                names: list[str] = []

                for item in restrictions:
                    if isinstance(item, str):
                        name = item.strip()
                        code = COUNTRY_ALIASES.get(name.casefold())
                    elif isinstance(item, dict):
                        name = str(item.get("name") or "").strip()
                        raw_code = str(item.get("alpha2") or "").strip()
                        code = (
                            raw_code.upper()
                            or COUNTRY_ALIASES.get(name.casefold())
                        )
                    else:
                        continue

                    if not name and not code:
                        continue

                    canonical = code or name
                    if canonical and canonical not in eligible_values:
                        eligible_values.append(canonical)

                    if name and name not in names:
                        names.append(name)

                if eligible_values:
                    eligible = eligible_values
                    country_code = (
                        eligible_values[0]
                        if len(eligible_values) == 1
                        and len(eligible_values[0]) == 2
                        else None
                    )
                    scope = RemoteScope.COUNTRY_RESTRICTED
                    location = (
                        ", ".join(names)
                        if 0 < len(names) <= 3
                        else f"{len(eligible_values)} eligible countries"
                    )

        seniority = payload.get("seniority")
        if isinstance(seniority, list):
            experience_level = ", ".join(
                str(item) for item in seniority if item
            ) or None
        elif isinstance(seniority, str):
            experience_level = seniority
        else:
            experience_level = None

        salary_period_map = {
            "hourly": SalaryPeriod.HOUR,
            "weekly": SalaryPeriod.WEEK,
            "monthly": SalaryPeriod.MONTH,
            "annual": SalaryPeriod.YEAR,
        }
        salary_period_raw = str(payload.get("salaryPeriod") or "annual").lower()

        return JobPosting(
            id=hashlib.sha256(
                f"{self.name}:{source_job_id}".encode()
            ).hexdigest()[:36],
            source=self.name,
            source_job_id=source_job_id,
            title=str(payload.get("title") or "").strip() or "Untitled",
            company=str(payload.get("companyName") or "").strip()
            or "Unknown company",
            description=(
                payload.get("description")
                or payload.get("excerpt")
            ),
            location=location,
            country_code=country_code,
            workplace_type=WorkplaceType.REMOTE,
            remote_scope=scope,
            eligible_countries=eligible,
            employment_type=payload.get("employmentType"),
            experience_level=experience_level,
            salary_min=_as_float(payload.get("minSalary")),
            salary_max=_as_float(payload.get("maxSalary")),
            salary_currency=payload.get("currency"),
            salary_period=salary_period_map.get(
                salary_period_raw,
                SalaryPeriod.UNKNOWN,
            ),
            salary_type=SalaryType.UNKNOWN,
            published_at=_parse_timestamp(payload.get("pubDate")),
            expires_at=_parse_timestamp(payload.get("expiryDate")),
            discovered_at=self._now or datetime.now(UTC),
            job_url=job_url,
            application_url=application_link,
            source_url=job_url,
            raw_payload={
                "provider": "himalayas",
                "job": payload,
                "search_queries": [search_query] if search_query else [],
                "search_countries": (
                    [search_country.upper()] if search_country else []
                ),
            },
        )


def _merge_search_metadata(
    job: JobPosting,
    query: str,
    country: str,
) -> None:
    raw = job.raw_payload

    queries = raw.setdefault("search_queries", [])
    if query not in queries:
        queries.append(query)

    countries = raw.setdefault("search_countries", [])
    normalized_country = country.upper()
    if normalized_country not in countries:
        countries.append(normalized_country)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
