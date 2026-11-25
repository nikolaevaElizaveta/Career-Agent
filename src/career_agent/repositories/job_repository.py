"""CRUD for job postings in SQLite."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from career_agent.domain.dedup import normalize_company, normalize_job_url, normalize_title
from career_agent.domain.job_posting import (
    JobPosting,
    LinkCheckStatus,
    RemoteScope,
    SalaryPeriod,
    SalaryType,
    WorkplaceType,
)
from career_agent.repositories.models import JobPostingRow


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, job: JobPosting) -> JobPosting:
        row = _to_row(job)
        self.session.merge(row)
        self.session.commit()
        return job

    def get(self, job_id: str) -> JobPosting | None:
        row = self.session.get(JobPostingRow, job_id)
        return _from_row(row) if row else None

    def get_by_source_id(self, source: str, source_job_id: str) -> JobPosting | None:
        stmt = select(JobPostingRow).where(
            JobPostingRow.source == source,
            JobPostingRow.source_job_id == source_job_id,
        )
        row = self.session.scalar(stmt)
        return _from_row(row) if row else None

    def list_jobs(self, limit: int = 20) -> list[JobPosting]:
        stmt = (
            select(JobPostingRow)
            .order_by(JobPostingRow.discovered_at.desc())
            .limit(limit)
        )
        return [_from_row(row) for row in self.session.scalars(stmt)]

    def all_jobs(self) -> list[JobPosting]:
        stmt = select(JobPostingRow)
        return [_from_row(row) for row in self.session.scalars(stmt)]

    def update(self, job: JobPosting) -> JobPosting:
        return self.save(job)

    def exists_source_id(self, source: str, source_job_id: str) -> bool:
        return self.get_by_source_id(source, source_job_id) is not None

    def find_by_id_or_prefix(self, token: str) -> list[JobPosting]:
        exact = self.get(token)
        if exact is not None:
            return [exact]
        stmt = select(JobPostingRow).where(JobPostingRow.id.startswith(token))
        return [_from_row(row) for row in self.session.scalars(stmt)]


def _to_row(job: JobPosting) -> JobPostingRow:
    return JobPostingRow(
        id=job.id,
        source=job.source,
        source_job_id=job.source_job_id,
        title=job.title,
        company=job.company,
        description=job.description,
        location=job.location,
        country_code=job.country_code,
        workplace_type=job.workplace_type.value,
        remote_scope=job.remote_scope.value,
        eligible_countries=job.eligible_countries,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period.value,
        salary_type=job.salary_type.value,
        published_at=job.published_at,
        expires_at=job.expires_at,
        discovered_at=job.discovered_at,
        last_seen_at=job.last_seen_at or job.discovered_at,
        link_checked_at=job.link_checked_at,
        link_check_status=job.link_check_status.value,
        link_check_http_status=job.link_check_http_status,
        job_url=job.job_url,
        application_url=job.application_url,
        source_url=job.source_url,
        duplicate_of_id=job.duplicate_of_id,
        related_urls=job.related_urls,
        raw_payload=job.raw_payload,
        company_norm=normalize_company(job.company),
        title_norm=normalize_title(job.title),
        url_norm=normalize_job_url(job.job_url or job.source_url),
    )


def _from_row(row: JobPostingRow) -> JobPosting:
    return JobPosting(
        id=row.id,
        source=row.source,
        source_job_id=row.source_job_id,
        title=row.title,
        company=row.company,
        description=row.description,
        location=row.location,
        country_code=row.country_code,
        workplace_type=WorkplaceType(row.workplace_type),
        remote_scope=RemoteScope(row.remote_scope),
        eligible_countries=row.eligible_countries,
        employment_type=row.employment_type,
        experience_level=row.experience_level,
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        salary_currency=row.salary_currency,
        salary_period=SalaryPeriod(row.salary_period),
        salary_type=SalaryType(row.salary_type),
        published_at=row.published_at,
        expires_at=row.expires_at,
        discovered_at=row.discovered_at,
        last_seen_at=row.last_seen_at or row.discovered_at,
        link_checked_at=row.link_checked_at,
        link_check_status=LinkCheckStatus(row.link_check_status or "unknown"),
        link_check_http_status=row.link_check_http_status,
        job_url=row.job_url,
        application_url=row.application_url,
        source_url=row.source_url,
        duplicate_of_id=row.duplicate_of_id,
        related_urls=row.related_urls or [],
        raw_payload=row.raw_payload or {},
    )
