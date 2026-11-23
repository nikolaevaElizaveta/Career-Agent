"""Job posting model. Persistence and discovery come in later stages."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    LOCAL_EMPLOYMENT = "local_employment"
    EOR = "eor"
    B2B = "b2b"
    INDEPENDENT_CONTRACTOR = "independent_contractor"
    DIRECT_CONTRACTOR = "direct_contractor"
    UNKNOWN = "unknown"


class WorkAuthorizationVerdict(StrEnum):
    """Never upgrade Unknown to Eligible."""

    CAN_WORK_FROM_RUSSIA = "can_work_from_russia"
    RELOCATION_ONLY = "relocation_only"
    NEEDS_WORK_PERMIT = "needs_work_permit"
    UNKNOWN = "unknown"


class SalaryObservation(BaseModel):
    amount: float | None = None
    currency: str | None = None
    period: str | None = None
    is_net: bool | None = None
    raw_text: str | None = None


class Job(BaseModel):
    title: str
    company: str
    url: HttpUrl | None = None
    country: str | None = None
    city: str | None = None
    posted_on: date | None = None
    discovered_on: date | None = None
    salary: SalaryObservation | None = None
    level: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    technologies: list[str] = Field(default_factory=list)
    experience_requirements: str | None = None
    work_authorization: WorkAuthorizationVerdict = WorkAuthorizationVerdict.UNKNOWN
    relocation_offered: bool | None = None
    description: str | None = None
    source: str = "manual"
    canonical_key: str | None = None
