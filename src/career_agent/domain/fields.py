"""Field wrapper that records how trustworthy a value is."""

from enum import StrEnum

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    """How we treat a stored value.

    - confirmed: user explicitly stands behind it; safe for CVs and letters.
    - imported_from_cv: copied from a resume; confirm before using on a new CV.
    - needs_confirmation: conflicting or incomplete; never invent a value.
    - unknown: we do not have the information.
    """

    CONFIRMED = "confirmed"
    IMPORTED_FROM_CV = "imported_from_cv"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNKNOWN = "unknown"


class ProfileField[T](BaseModel):
    """A profile value plus its verification status."""

    value: T | None = None
    status: VerificationStatus = VerificationStatus.UNKNOWN
    note: str | None = None

    def usable_in_documents(self) -> bool:
        """Only confirmed, non-empty values may appear on generated documents."""
        return self.status is VerificationStatus.CONFIRMED and self.value not in (None, "")


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ProfileIssue(BaseModel):
    """One problem found while validating a profile."""

    path: str
    message: str
    severity: IssueSeverity
    status: VerificationStatus | None = None


class ValidationReport(BaseModel):
    """Result of loading and checking a Candidate Profile."""

    valid: bool
    schema_ok: bool
    profile_path: str
    missing_required: list[str] = Field(default_factory=list)
    needs_confirmation: list[ProfileIssue] = Field(default_factory=list)
    unknown_fields: list[ProfileIssue] = Field(default_factory=list)
    issues: list[ProfileIssue] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is IssueSeverity.ERROR)
