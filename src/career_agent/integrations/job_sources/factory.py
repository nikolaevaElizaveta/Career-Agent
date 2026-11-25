"""Build enabled job sources from settings and YAML."""

from __future__ import annotations

from sqlalchemy.orm import Session

from career_agent.config import Settings
from career_agent.config_loader import JobSearchFile
from career_agent.integrations.job_sources.adzuna import AdzunaJobSource
from career_agent.integrations.job_sources.base import JobSource
from career_agent.integrations.job_sources.himalayas import HimalayasJobSource
from career_agent.integrations.job_sources.http import JobHttpClient
from career_agent.integrations.job_sources.rate_limit import SqliteRateLimiter
from career_agent.integrations.job_sources.remotive import (
    REMOTIVE_MAX_PER_DAY,
    REMOTIVE_MAX_PER_MINUTE,
    RemotiveJobSource,
)


def build_sources(
    settings: Settings,
    search: JobSearchFile,
    session: Session,
    http: JobHttpClient | None = None,
) -> list[JobSource]:
    client = http or JobHttpClient()
    limiter = SqliteRateLimiter(
        session,
        per_minute=REMOTIVE_MAX_PER_MINUTE,
        per_day=REMOTIVE_MAX_PER_DAY,
    )
    remotive_enabled = search.sources_enabled.get("remotive", True) and search.remotive.enabled
    himalayas_enabled = (
        search.sources_enabled.get("himalayas", True)
        and search.himalayas.enabled
    )
    adzuna_enabled = search.sources_enabled.get("adzuna", True) and search.adzuna.enabled

    remotive_settings = search.remotive.model_copy(update={"enabled": remotive_enabled})
    himalayas_settings = search.himalayas.model_copy(
        update={"enabled": himalayas_enabled}
    )
    adzuna_settings = search.adzuna.model_copy(update={"enabled": adzuna_enabled})

    return [
        RemotiveJobSource(remotive_settings, client, rate_limiter=limiter),
        HimalayasJobSource(himalayas_settings, client),
        AdzunaJobSource(
            adzuna_settings,
            client,
            app_id=settings.adzuna_app_id,
            app_key=settings.adzuna_app_key,
        ),
    ]
