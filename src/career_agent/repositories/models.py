"""SQLAlchemy tables for discovered jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from career_agent.repositories.db import Base


class JobPostingRow(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_source_id"),
        Index("ix_job_discovered_at", "discovered_at"),
        Index("ix_job_company", "company"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    workplace_type: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    eligible_countries: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    salary_period: Mapped[str] = mapped_column(String(16), nullable=False)
    salary_type: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    link_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    link_check_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    link_check_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    related_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    company_norm: Mapped[str] = mapped_column(String(512), nullable=False)
    title_norm: Mapped[str] = mapped_column(String(512), nullable=False)
    url_norm: Mapped[str | None] = mapped_column(Text, nullable=True)
