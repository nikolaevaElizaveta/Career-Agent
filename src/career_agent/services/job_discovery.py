"""Fetch, deduplicate, and store job postings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter

from career_agent.domain.dedup import (
    normalize_company,
    normalize_title,
    urls_equivalent,
)
from career_agent.domain.job_posting import JobPosting
from career_agent.integrations.job_sources.base import JobSource
from career_agent.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


@dataclass
class SourceSummary:
    source: str
    fetched: int = 0
    saved: int = 0
    updated: int = 0
    duplicates: int = 0
    probable_duplicates: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class DiscoveryReport:
    summaries: list[SourceSummary] = field(default_factory=list)

    def format(self) -> str:
        lines = ["Job discovery"]
        for item in self.summaries:
            lines.append(f"[{item.source}] {item.duration_seconds:.2f}s")
            if item.skipped:
                lines.append(f"  skipped: {item.skip_reason}")
                continue
            if item.error:
                lines.append(f"  error: {item.error}")
            lines.append(
                f"  fetched={item.fetched} new={item.saved} "
                f"updated={item.updated} duplicates={item.duplicates} "
                f"probable={item.probable_duplicates}"
            )
        return "\n".join(lines)


class JobDiscoveryService:
    def __init__(self, repository: JobRepository, sources: list[JobSource]) -> None:
        self.repository = repository
        self.sources = sources

    def search(self, source_name: str | None = None) -> DiscoveryReport:
        selected = self.sources
        if source_name:
            selected = [item for item in self.sources if item.name == source_name]
            if not selected:
                report = DiscoveryReport(
                    summaries=[
                        SourceSummary(
                            source=source_name,
                            skipped=True,
                            skip_reason=(
                                f"Unknown source '{source_name}'. "
                                "Use remotive, himalayas or adzuna."
                            ),
                        )
                    ]
                )
                return report
        report = DiscoveryReport()
        for source in selected:
            report.summaries.append(self._run_source(source))
        return report

    def _run_source(self, source: JobSource) -> SourceSummary:
        started = perf_counter()
        logger.info("source_start source=%s", source.name)

        try:
            result = source.fetch_jobs()
        except Exception:
            duration = perf_counter() - started
            logger.exception("source_failed source=%s", source.name)
            return SourceSummary(
                source=source.name,
                error="Unexpected source error",
                duration_seconds=duration,
            )

        summary = SourceSummary(source=source.name)
        summary.skipped = result.skipped
        summary.skip_reason = result.skip_reason
        summary.error = result.error
        if result.skipped:
            summary.duration_seconds = perf_counter() - started
            logger.info("source_done source=%s skipped=1", source.name)
            return summary
        existing = self.repository.all_jobs()
        for job in result.jobs:
            summary.fetched += 1
            outcome = self._store(job, existing)
            if outcome == "new":
                summary.saved += 1
                existing.append(job)
            elif outcome == "updated":
                summary.updated += 1
            elif outcome == "probable":
                summary.probable_duplicates += 1
                existing.append(job)
            else:
                summary.duplicates += 1
        summary.duration_seconds = perf_counter() - started
        logger.info(
            "source_done source=%s fetched=%s new=%s duplicates=%s probable=%s duration=%.2f",
            source.name,
            summary.fetched,
            summary.saved,
            summary.duplicates,
            summary.probable_duplicates,
            summary.duration_seconds,
        )
        return summary

    def _store(self, job: JobPosting, existing: list[JobPosting]) -> str:
        existing_index = next(
            (
                index
                for index, stored in enumerate(existing)
                if stored.source == job.source
                and stored.source_job_id == job.source_job_id
            ),
            None,
        )

        if existing_index is not None:
            refreshed, changed = _refresh_existing_job(
                existing[existing_index],
                job,
            )
            self.repository.update(refreshed)
            existing[existing_index] = refreshed
            return "updated" if changed else "duplicate"

        match = find_probable_duplicate(job, existing)
        if match is not None:
            job.duplicate_of_id = match.id
            urls = [item for item in [job.job_url, job.source_url] if item]
            extras = [item for item in [match.job_url, *urls] if item]
            job.related_urls = list(dict.fromkeys([*match.related_urls, *extras]))
            match.related_urls = list(dict.fromkeys([*match.related_urls, *urls]))
            self.repository.update(match)
            self.repository.save(job)
            return "probable"
        self.repository.save(job)
        return "new"


_SOURCE_FIELDS = (
    "title",
    "company",
    "description",
    "location",
    "country_code",
    "workplace_type",
    "remote_scope",
    "eligible_countries",
    "employment_type",
    "experience_level",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_type",
    "published_at",
    "expires_at",
    "job_url",
    "application_url",
    "source_url",
)


def _refresh_existing_job(
    existing: JobPosting,
    incoming: JobPosting,
) -> tuple[JobPosting, bool]:
    """Refresh provider-owned fields while preserving local identity and history."""
    changed = any(
        getattr(existing, field) != getattr(incoming, field)
        for field in _SOURCE_FIELDS
    )

    related_urls = list(existing.related_urls)

    # Keep old URLs if the provider changes the canonical link.
    for old_url, new_url in (
        (existing.job_url, incoming.job_url),
        (existing.source_url, incoming.source_url),
        (existing.application_url, incoming.application_url),
    ):
        if old_url and old_url != new_url and old_url not in related_urls:
            related_urls.append(old_url)

    for url in incoming.related_urls:
        if url and url not in related_urls:
            related_urls.append(url)

    link_url_changed = any(
        getattr(existing, field) != getattr(incoming, field)
        for field in ("application_url", "job_url", "source_url")
    )

    updates = {
        field: getattr(incoming, field)
        for field in _SOURCE_FIELDS
    }
    updates.update(
        {
            # The first-discovered date and local identity never change.
            "discovered_at": existing.discovered_at,
            "last_seen_at": incoming.discovered_at,
            "link_checked_at": (
                None if link_url_changed else existing.link_checked_at
            ),
            "link_check_status": (
                existing.link_check_status.__class__.UNKNOWN
                if link_url_changed
                else existing.link_check_status
            ),
            "link_check_http_status": (
                None if link_url_changed else existing.link_check_http_status
            ),
            "id": existing.id,
            "duplicate_of_id": existing.duplicate_of_id,
            "related_urls": related_urls,
            "raw_payload": incoming.raw_payload,
        }
    )

    return existing.model_copy(update=updates), changed


def find_probable_duplicate(job: JobPosting, existing: list[JobPosting]) -> JobPosting | None:
    company = normalize_company(job.company)
    title = normalize_title(job.title)
    for other in existing:
        if other.source == job.source and other.source_job_id == job.source_job_id:
            continue
        same_company = normalize_company(other.company) == company
        same_title = normalize_title(other.title) == title
        same_url = urls_equivalent(job.job_url, other.job_url) or urls_equivalent(
            job.source_url, other.source_url
        )
        if same_url:
            return other
        if same_company and same_title:
            return other
    return None
