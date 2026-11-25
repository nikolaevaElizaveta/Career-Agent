"""Shared contract for job sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from career_agent.domain.job_posting import JobPosting


@dataclass
class FetchResult:
    source: str
    jobs: list[JobPosting] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None


class JobSource(Protocol):
    name: str

    def fetch_jobs(self) -> FetchResult:
        """Return normalized jobs or a skipped/error result. Must not raise to the CLI."""
        ...

    def normalize_job(self, payload: dict[str, Any]) -> JobPosting:
        ...


class SourceRegistry:
    def __init__(self, sources: Sequence[JobSource]) -> None:
        self._sources = list(sources)

    def all(self) -> list[JobSource]:
        return list(self._sources)

    def get(self, name: str) -> JobSource | None:
        needle = name.casefold()
        for source in self._sources:
            if source.name.casefold() == needle:
                return source
        return None
