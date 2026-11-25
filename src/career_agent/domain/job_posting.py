"""Canonical job posting used by discovery, storage, and later matching."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkplaceType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class RemoteScope(StrEnum):
    WORLDWIDE = "worldwide"
    COUNTRY_RESTRICTED = "country_restricted"
    REGION_RESTRICTED = "region_restricted"
    UNKNOWN = "unknown"


class SalaryType(StrEnum):
    GROSS = "gross"
    NET = "net"
    UNKNOWN = "unknown"


class SalaryPeriod(StrEnum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class ListingStatus(StrEnum):
    UNKNOWN = "unknown"
    WITHIN_LISTED_PERIOD = "within_listed_period"
    EXPIRED = "expired"


class LinkCheckStatus(StrEnum):
    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    NOT_FOUND = "not_found"
    RESTRICTED = "restricted"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


class JobPosting(BaseModel):
    id: str
    source: str
    source_job_id: str
    title: str
    company: str
    description: str | None = None
    location: str | None = None
    country_code: str | None = None
    workplace_type: WorkplaceType = WorkplaceType.UNKNOWN
    remote_scope: RemoteScope = RemoteScope.UNKNOWN
    eligible_countries: list[str] | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod = SalaryPeriod.UNKNOWN
    salary_type: SalaryType = SalaryType.UNKNOWN
    published_at: datetime | None = None
    expires_at: datetime | None = None
    discovered_at: datetime
    last_seen_at: datetime | None = None
    link_checked_at: datetime | None = None
    link_check_status: LinkCheckStatus = LinkCheckStatus.UNKNOWN
    link_check_http_status: int | None = None
    job_url: str | None = None
    application_url: str | None = None
    source_url: str | None = None
    duplicate_of_id: str | None = None
    related_urls: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def listing_status(self, now: datetime | None = None) -> ListingStatus:
        """Evaluate the provider's listing expiry date, not application availability."""
        if self.expires_at is None:
            return ListingStatus.UNKNOWN

        moment = now or datetime.now(UTC)
        expiry = self.expires_at

        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        else:
            moment = moment.astimezone(UTC)

        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        else:
            expiry = expiry.astimezone(UTC)

        if expiry <= moment:
            return ListingStatus.EXPIRED

        return ListingStatus.WITHIN_LISTED_PERIOD

    def display_source(self) -> str:
        """Human-readable source label. Remotive must be named explicitly."""
        if self.source == "remotive":
            return "Remotive"
        if self.source == "adzuna":
            return "Adzuna"
        return self.source
