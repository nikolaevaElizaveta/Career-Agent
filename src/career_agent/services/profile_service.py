"""Load, validate, and inspect the Candidate Profile without guessing facts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from career_agent.domain.candidate import (
    CandidateProfile,
    EducationItem,
    LanguageItem,
    ProjectItem,
    SkillItem,
)
from career_agent.domain.fields import (
    IssueSeverity,
    ProfileField,
    ProfileIssue,
    ValidationReport,
    VerificationStatus,
)

REQUIRED_VALUE_PATHS = (
    "personal.full_name",
    "contact.email",
    "personal.citizenship",
    "career_preferences.target_roles",
    "salary_expectations.amount",
)

FORBIDDEN_SENIORITY_LABELS = {"senior", "advanced", "expert", "staff", "principal"}


class ProfileService:
    """Use-cases around the JSON Candidate Profile."""

    def load(self, path: Path) -> CandidateProfile:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return CandidateProfile.model_validate(raw)

    def save(self, profile: CandidateProfile, path: Path) -> None:
        """Atomically save the complete Candidate Profile as UTF-8 JSON."""
        serialized = json.dumps(
            profile.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def validate_path(self, path: Path) -> tuple[ValidationReport, CandidateProfile | None]:
        if not path.exists():
            report = ValidationReport(
                valid=False,
                schema_ok=False,
                profile_path=str(path),
                missing_required=["profile file"],
                issues=[
                    ProfileIssue(
                        path=str(path),
                        message="Profile file was not found.",
                        severity=IssueSeverity.ERROR,
                    )
                ],
            )
            return report, None

        try:
            profile = self.load(path)
        except json.JSONDecodeError as exc:
            report = ValidationReport(
                valid=False,
                schema_ok=False,
                profile_path=str(path),
                issues=[
                    ProfileIssue(
                        path=str(path),
                        message=f"Invalid JSON: {exc.msg}",
                        severity=IssueSeverity.ERROR,
                    )
                ],
            )
            return report, None
        except ValidationError as exc:
            issues = [
                ProfileIssue(
                    path=".".join(str(item) for item in error["loc"]),
                    message=error["msg"],
                    severity=IssueSeverity.ERROR,
                )
                for error in exc.errors()
            ]
            report = ValidationReport(
                valid=False,
                schema_ok=False,
                profile_path=str(path),
                missing_required=[issue.path for issue in issues],
                issues=issues,
            )
            return report, None

        return self.analyze(profile, path), profile

    def analyze(self, profile: CandidateProfile, path: Path) -> ValidationReport:
        issues: list[ProfileIssue] = []
        missing: list[str] = []
        needs_confirmation: list[ProfileIssue] = []
        unknown_fields: list[ProfileIssue] = []

        for field_path in REQUIRED_VALUE_PATHS:
            if not self._path_has_value(profile, field_path):
                missing.append(field_path)
                issues.append(
                    ProfileIssue(
                        path=field_path,
                        message="Required value is missing.",
                        severity=IssueSeverity.ERROR,
                    )
                )

        if not profile.education:
            missing.append("education")
            issues.append(
                ProfileIssue(
                    path="education",
                    message="At least one education record is required.",
                    severity=IssueSeverity.ERROR,
                )
            )
        if not profile.skills:
            missing.append("skills")
            issues.append(
                ProfileIssue(
                    path="skills",
                    message="At least one skill is required.",
                    severity=IssueSeverity.ERROR,
                )
            )
        if not profile.experience:
            issues.append(
                ProfileIssue(
                    path="experience",
                    message="No work experience records. Applications will be thin.",
                    severity=IssueSeverity.WARNING,
                )
            )

        weights_total = profile.career_preferences.match_weights.total()
        if weights_total != 100:
            issues.append(
                ProfileIssue(
                    path="career_preferences.match_weights",
                    message=f"Match weights sum to {weights_total}, expected 100.",
                    severity=IssueSeverity.WARNING,
                )
            )

        email = profile.contact.email.value
        if email and not _looks_like_email(email):
            issues.append(
                ProfileIssue(
                    path="contact.email",
                    message="Email does not look valid.",
                    severity=IssueSeverity.ERROR,
                )
            )

        for field_path, field in walk_profile_fields(profile):
            if field.status is VerificationStatus.NEEDS_CONFIRMATION:
                item = ProfileIssue(
                    path=field_path,
                    message=field.note or "This value needs confirmation before use.",
                    severity=IssueSeverity.WARNING,
                    status=field.status,
                )
                needs_confirmation.append(item)
                issues.append(item)
            elif field.status is VerificationStatus.UNKNOWN:
                item = ProfileIssue(
                    path=field_path,
                    message=field.note or "Value is unknown; do not treat it as filled.",
                    severity=IssueSeverity.INFO,
                    status=field.status,
                )
                unknown_fields.append(item)
            elif field.status is VerificationStatus.IMPORTED_FROM_CV:
                issues.append(
                    ProfileIssue(
                        path=field_path,
                        message=(
                            "Imported from a CV. Confirm before putting it on a tailored resume."
                        ),
                        severity=IssueSeverity.INFO,
                        status=field.status,
                    )
                )

            value_text = "" if field.value is None else str(field.value).lower()
            if value_text in FORBIDDEN_SENIORITY_LABELS:
                issues.append(
                    ProfileIssue(
                        path=field_path,
                        message="Do not store seniority labels such as Senior/Advanced/Expert.",
                        severity=IssueSeverity.ERROR,
                    )
                )

        valid = not any(issue.severity is IssueSeverity.ERROR for issue in issues)
        return ValidationReport(
            valid=valid,
            schema_ok=True,
            profile_path=str(path),
            missing_required=missing,
            needs_confirmation=needs_confirmation,
            unknown_fields=unknown_fields,
            issues=issues,
        )

    def facts_for_documents(self, profile: CandidateProfile) -> dict[str, Any]:
        """Return only confirmed values. Used later by Application Assistant."""
        return confirmed_view(profile)

    def format_telegram_summary(self, profile: CandidateProfile) -> str:
        """Short profile view for an authorized Telegram user. No extra facts."""
        roles: list[str] = []
        for item in profile.experience:
            title = item.title.value or "Unknown role"
            company = item.company.value or "Unknown company"
            start = (
                item.start_date.value.as_text()
                if item.start_date.usable_in_documents() and item.start_date.value
                else "start date not confirmed"
            )
            end = item.end_date.value if item.end_date.value else "unknown"
            roles.append(f"- {title} at {company} ({start} — {end})")

        education_lines: list[str] = []
        for item in profile.education:
            institution = item.institution.value or "Unknown institution"
            field = item.field.value or "Unknown field"
            education_lines.append(f"- {institution}, {field}")

        email = profile.contact_email() or "not confirmed"
        salary = profile.salary_expectations
        targets = ", ".join(profile.career_preferences.target_roles) or "none"
        return "\n".join(
            [
                f"Name: {profile.display_name()}",
                f"Email: {email}",
                "Current / listed roles:",
                *(roles or ["- none"]),
                "Education:",
                *(education_lines or ["- none"]),
                f"Target roles: {targets}",
                (
                    f"Salary floor: {salary.amount} {salary.currency} "
                    f"{salary.kind} / {salary.period}"
                ),
            ]
        )

    def format_report(self, report: ValidationReport) -> str:
        lines = [
            f"Profile: {report.profile_path}",
            f"Schema: {'ok' if report.schema_ok else 'failed'}",
            f"Valid: {'yes' if report.valid else 'no'}",
        ]
        if report.missing_required:
            lines.append("Missing required data:")
            lines.extend(f"  - {item}" for item in report.missing_required)
        else:
            lines.append("Missing required data: none")

        if report.needs_confirmation:
            lines.append("Needs confirmation:")
            lines.extend(
                f"  - {item.path}: {item.message}" for item in report.needs_confirmation
            )
        else:
            lines.append("Needs confirmation: none")

        infos = [i for i in report.issues if i.severity is IssueSeverity.INFO]
        warnings = [i for i in report.issues if i.severity is IssueSeverity.WARNING]
        errors = [i for i in report.issues if i.severity is IssueSeverity.ERROR]
        if errors:
            lines.append("Errors:")
            lines.extend(f"  - {item.path}: {item.message}" for item in errors)
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {item.path}: {item.message}" for item in warnings)
        if infos:
            lines.append(
                f"Unknown or imported fields: {len(infos)} (not treated as confirmed)"
            )
        return "\n".join(lines)

    def _path_has_value(self, profile: CandidateProfile, dotted: str) -> bool:
        current: Any = profile
        for part in dotted.split("."):
            current = getattr(current, part)
        if isinstance(current, ProfileField):
            return current.value not in (None, "", [])
        if isinstance(current, list):
            return bool(current)
        return current is not None


def _looks_like_email(value: str) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def walk_profile_fields(
    obj: Any, prefix: str = ""
) -> list[tuple[str, ProfileField[Any]]]:
    found: list[tuple[str, ProfileField[Any]]] = []
    if isinstance(obj, ProfileField):
        found.append((prefix or "field", obj))
        return found
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            value = getattr(obj, name)
            path = f"{prefix}.{name}" if prefix else name
            found.extend(walk_profile_fields(value, path))
        return found
    if isinstance(obj, list):
        for index, item in enumerate(obj):
            path = f"{prefix}[{index}]"
            found.extend(walk_profile_fields(item, path))
    return found


def confirmed_view(obj: Any) -> Any:
    """Return confirmed document facts and exclude unverified free-text claims."""
    if isinstance(obj, ProfileField):
        if obj.usable_in_documents():
            return confirmed_view(obj.value)
        return None

    if isinstance(obj, SkillItem):
        proficiency_confirmed = obj.proficiency.usable_in_documents()
        return {
            "name": obj.name if proficiency_confirmed else None,
            "category": obj.category if proficiency_confirmed else None,
            "proficiency": confirmed_view(obj.proficiency),
            "commercial_experience": confirmed_view(
                obj.commercial_experience
            ),
        }

    if isinstance(obj, LanguageItem):
        level_confirmed = obj.level.usable_in_documents()
        return {
            "name": obj.name if level_confirmed else None,
            "level": confirmed_view(obj.level),
        }

    if isinstance(obj, ProjectItem):
        return {
            "name": confirmed_view(obj.name),
            "summary": confirmed_view(obj.summary),
            "technologies": [],
        }

    if isinstance(obj, EducationItem):
        return {
            "institution": confirmed_view(obj.institution),
            "degree": confirmed_view(obj.degree),
            "field": confirmed_view(obj.field),
            "start_year": confirmed_view(obj.start_year),
            "end_year": confirmed_view(obj.end_year),
            "highlights": [],
        }

    if isinstance(obj, BaseModel):
        return {
            name: confirmed_view(getattr(obj, name))
            for name in type(obj).model_fields
        }

    if isinstance(obj, list):
        return [confirmed_view(item) for item in obj]

    return obj
