"""Persist request timestamps so Remotive stays within published limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from career_agent.repositories.db import Base

DEFAULT_SEARCH_COOLDOWN = timedelta(hours=6)


class SourceRequestLog(Base):
    __tablename__ = "source_request_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SqliteRateLimiter:
    """Allow at most `per_minute` calls / 60s and `per_day` calls / 24h."""

    def __init__(self, session: Session, *, per_minute: int, per_day: int) -> None:
        self.session = session
        self.per_minute = per_minute
        self.per_day = per_day

    def check(self, source: str, now: datetime | None = None) -> str | None:
        moment = now or datetime.now(UTC)
        self._prune(source, moment)
        minute_count = self._count_since(source, moment - timedelta(minutes=1))
        if minute_count >= self.per_minute:
            return (
                f"{source} rate limit: already {minute_count} request(s) in the last minute "
                f"(max {self.per_minute})."
            )
        day_count = self._count_since(source, moment - timedelta(hours=24))
        if day_count >= self.per_day:
            return (
                f"{source} rate limit: already {day_count} request(s) in the last 24 hours "
                f"(max {self.per_day})."
            )
        return None

    def record(self, source: str, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        self.session.add(SourceRequestLog(source=source, requested_at=moment))
        self.session.commit()

    def _count_since(self, source: str, since: datetime) -> int:
        stmt = select(SourceRequestLog).where(
            SourceRequestLog.source == source,
            SourceRequestLog.requested_at >= since,
        )
        return len(list(self.session.scalars(stmt)))

    def _prune(self, source: str, now: datetime) -> None:
        cutoff = now - timedelta(hours=48)
        self.session.execute(
            delete(SourceRequestLog).where(
                SourceRequestLog.source == source,
                SourceRequestLog.requested_at < cutoff,
            )
        )
        self.session.commit()


class SearchRunLog(Base):
    """Persist the last global job-search start time."""

    __tablename__ = "job_search_run_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        index=True,
    )


class SqliteSearchCooldown:
    """Persist a cooldown between complete job-search runs."""

    def __init__(self, session: Session, cooldown: timedelta) -> None:
        self.session = session
        self.cooldown = cooldown

    def reserve(self, now: datetime | None = None) -> timedelta | None:
        """Reserve a search slot or return the remaining cooldown."""
        moment = now or datetime.now(UTC)

        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        else:
            moment = moment.astimezone(UTC)

        last_started_at = self.session.scalar(
            select(SearchRunLog.started_at)
            .order_by(SearchRunLog.started_at.desc())
            .limit(1)
        )

        if last_started_at is not None:
            if last_started_at.tzinfo is None:
                last_started_at = last_started_at.replace(tzinfo=UTC)
            else:
                last_started_at = last_started_at.astimezone(UTC)

            remaining = self.cooldown - (moment - last_started_at)

            if remaining.total_seconds() > 0:
                return remaining

        # Keep only the latest run timestamp.
        self.session.execute(delete(SearchRunLog))
        self.session.add(
            SearchRunLog(
                started_at=moment.replace(tzinfo=None),
            )
        )
        self.session.commit()
        return None
