"""Application tracker records. Status `applied` is set only after a confirmed send."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class ApplicationStatus(StrEnum):
    DISCOVERED = "discovered"
    SHORTLISTED = "shortlisted"
    REJECTED_BY_MATCHER = "rejected_by_matcher"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    RESPONSE_RECEIVED = "response_received"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED_BY_COMPANY = "rejected_by_company"
    WITHDRAWN = "withdrawn"


class ApplicationRecord(BaseModel):
    vacancy_id: str
    company: str
    position: str
    link: HttpUrl | None = None
    match_score: int | None = Field(default=None, ge=0, le=100)
    date_discovered: date | None = None
    date_applied: date | None = None
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    resume_version: str | None = None
    cover_letter_version: str | None = None
    recruiter_contact: str | None = None
    last_communication_date: date | None = None
    next_follow_up_date: date | None = None
    interview_dates: list[date] = Field(default_factory=list)
    notes: str | None = None
    rejection_reason: str | None = None
