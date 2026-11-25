"""Load job-search settings from YAML so queries are not hardcoded."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RemotiveSettings(BaseModel):
    enabled: bool = True
    category: str = "qa"
    extra_search: str | None = None


class HimalayasSettings(BaseModel):
    enabled: bool = True
    countries: list[str] = Field(default_factory=lambda: ["RU"])
    queries: list[str] = Field(default_factory=lambda: [
        "QA Engineer",
        "Manual QA",
        "API Testing",
        "QA Automation",
        "Integration Testing",
        "API QA",
        "Integration QA",
    ])
    sort: str = "relevant"
    max_pages: int = Field(default=1, ge=1, le=3)
    request_delay_seconds: float = Field(default=1.5, ge=0, le=30)


class AdzunaSettings(BaseModel):
    enabled: bool = True
    countries: list[str] = Field(default_factory=lambda: ["gb", "es", "au"])
    queries: list[str] = Field(default_factory=lambda: ["QA Engineer"])
    results_per_page: int = 20


class GeographySettings(BaseModel):
    priority_countries: list[str] = Field(
        default_factory=lambda: ["Spain", "United Kingdom", "Australia"]
    )
    include_remote_worldwide: bool = True


class JobSearchFile(BaseModel):
    keywords: list[str]
    geography: GeographySettings = Field(default_factory=GeographySettings)
    remotive: RemotiveSettings = Field(default_factory=RemotiveSettings)
    himalayas: HimalayasSettings = Field(default_factory=HimalayasSettings)
    adzuna: AdzunaSettings = Field(default_factory=AdzunaSettings)
    sources_enabled: dict[str, bool] = Field(
        default_factory=lambda: {
            "remotive": True,
            "himalayas": True,
            "adzuna": True,
        }
    )


def load_job_search_config(path: Path) -> JobSearchFile:
    if not path.exists():
        raise FileNotFoundError(f"Job search config was not found: {path}")
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Job search config must be a YAML mapping")
    return JobSearchFile.model_validate(raw)
