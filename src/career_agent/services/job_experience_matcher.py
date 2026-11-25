"""Match job experience and education requirements against verified profile data."""

from __future__ import annotations

import calendar
import math
import re
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.candidate import (
    CandidateProfile,
    EducationItem,
    ExperienceItem,
)
from career_agent.domain.dates import DatePrecision, PartialDate
from career_agent.domain.fields import VerificationStatus
from career_agent.services.job_requirements import (
    EducationRequirement,
    ExperienceRequirement,
)


class ExperienceMatchStatus(StrEnum):
    MEETS_MINIMUM = "meets_minimum"
    BELOW_MINIMUM = "below_minimum"
    NEEDS_CONFIRMATION = "needs_confirmation"
    AREA_NOT_EVIDENCED = "area_not_evidenced"
    UNKNOWN = "unknown"


class EducationMatchStatus(StrEnum):
    MATCHED = "matched"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NOT_EVIDENCED = "not_evidenced"


class ExperienceRequirementMatch(BaseModel):
    area: str | None = None
    min_years: float
    max_years: float | None = None
    priority: str
    status: ExperienceMatchStatus
    confirmed_min_months: int = 0
    possible_max_months: int = 0
    confirmed_roles: list[str] = Field(default_factory=list)
    unverified_roles: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class EducationRequirementMatch(BaseModel):
    priority: str
    status: EducationMatchStatus
    matched_degree: str | None = None
    matched_field: str | None = None
    evidence: str
    reasons: list[str] = Field(default_factory=list)


DateInterval = tuple[date, date]


def _date_bounds(value: PartialDate) -> DateInterval:
    if value.precision is DatePrecision.DAY:
        exact = date(value.year, value.month, value.day)
        return exact, exact

    if value.precision is DatePrecision.MONTH:
        first = date(value.year, value.month, 1)
        last_day = calendar.monthrange(value.year, value.month)[1]
        last = date(value.year, value.month, last_day)
        return first, last

    first = date(value.year, 1, 1)
    last = date(value.year, 12, 31)
    return first, last


def _end_date_bounds(
    experience: ExperienceItem,
    as_of: date,
) -> DateInterval | None:
    if experience.end_date.status is not VerificationStatus.CONFIRMED:
        return None

    if experience.currently_employed:
        marker = (experience.end_date.value or "").strip().casefold()
        if marker in {"present", "current", "now"}:
            return as_of, as_of
        return None

    if not experience.end_date.value:
        return None

    try:
        parsed = PartialDate.parse(experience.end_date.value)
    except (TypeError, ValueError):
        return None

    return _date_bounds(parsed)


def _experience_intervals(
    experience: ExperienceItem,
    as_of: date,
) -> tuple[DateInterval | None, DateInterval | None]:
    """Return guaranteed and possible date intervals for a work record."""
    if experience.start_date.status is not VerificationStatus.CONFIRMED:
        return None, None

    if experience.start_date.value is None:
        return None, None

    end_bounds = _end_date_bounds(experience, as_of)
    if end_bounds is None:
        return None, None

    start_earliest, start_latest = _date_bounds(
        experience.start_date.value
    )
    end_earliest, end_latest = end_bounds

    if start_earliest > end_latest:
        return None, None

    possible = (start_earliest, end_latest)
    guaranteed = None

    if start_latest <= end_earliest:
        guaranteed = (start_latest, end_earliest)

    return guaranteed, possible


def _whole_months_between(start: date, end: date) -> int:
    if end < start:
        return 0

    months = (end.year - start.year) * 12 + end.month - start.month

    if end.day < start.day:
        months -= 1

    return max(0, months)


def _merge_intervals(intervals: list[DateInterval]) -> list[DateInterval]:
    if not intervals:
        return []

    ordered = sorted(intervals)
    merged: list[DateInterval] = [ordered[0]]

    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]

        if start <= previous_end + timedelta(days=1):
            merged[-1] = (
                previous_start,
                max(previous_end, end),
            )
        else:
            merged.append((start, end))

    return merged


def _total_completed_months(intervals: list[DateInterval]) -> int:
    return sum(
        _whole_months_between(start, end)
        for start, end in _merge_intervals(intervals)
    )


def _area_kind(area: str | None) -> str:
    if not area:
        return "general"

    normalized = area.casefold()

    if re.search(
        r"\b(senior|lead|principal|staff|head|manager|director|"
        r"vice president|vp|chief|supervisor)\b",
        normalized,
    ):
        return "senior"

    if re.search(
        r"\b(web|app|mobile|automation|automated|selenium|appium|playwright|sdet)\b",
        normalized,
    ):
        return "specialized"

    if re.search(r"\b(qa|test|testing|tester)\b", normalized):
        return "qa"

    return "general"


def _title_matches_area(title: str, kind: str) -> bool:
    normalized = title.casefold()

    if kind == "senior":
        has_senior_marker = bool(
            re.search(
                r"\b(senior|lead|principal|staff|head|director|"
                r"vice president|vp|chief|supervisor)\b",
                normalized,
            )
        )

        is_qa_manager = bool(
            re.search(r"\bmanager\b", normalized)
            and re.search(
                r"\b(qa|quality assurance|quality|test(?:er|ing)?|sdet)\b",
                normalized,
            )
        )

        return has_senior_marker or is_qa_manager

    if kind == "general":
        return bool(normalized.strip())

    if kind == "qa":
        return bool(
            re.search(
                r"\bqa\b|quality assurance|\btest(?:er|ing)?\b",
                normalized,
            )
        )

    return bool(
        re.search(
            r"\b(web|app|mobile|automation|sdet)\b",
            normalized,
        )
    )


def _responsibility_matches_area(text: str, kind: str) -> bool:
    normalized = text.casefold()

    # Ordinary QA responsibilities do not independently prove senior tenure.
    if kind == "senior":
        return False

    if kind == "general":
        return bool(normalized.strip())

    if kind == "qa":
        return bool(
            re.search(
                r"\b(qa|testing|test cases?|test plans?|tester|defects?|bugs?)\b",
                normalized,
            )
        )

    has_automation = bool(
        re.search(
            r"\b(automation|automated|selenium|playwright|appium|cypress)\b",
            normalized,
        )
    )
    has_surface = bool(
        re.search(r"\b(web|app|mobile|ui|api)\b", normalized)
    )
    return has_automation and has_surface


def _candidate_matches_area(
    experience: ExperienceItem,
    kind: str,
) -> tuple[bool, bool]:
    """Return (confirmed area match, possible but unverified area match)."""
    title = experience.title.value or ""
    title_matches = _title_matches_area(title, kind)

    confirmed_title = (
        title_matches
        and experience.title.status is VerificationStatus.CONFIRMED
    )

    confirmed_responsibility = any(
        item.value
        and item.status is VerificationStatus.CONFIRMED
        and _responsibility_matches_area(item.value, kind)
        for item in experience.responsibilities
    )

    confirmed_match = confirmed_title or confirmed_responsibility

    unverified_title = (
        title_matches
        and experience.title.status is not VerificationStatus.CONFIRMED
    )

    unverified_responsibility = any(
        item.value
        and item.status is not VerificationStatus.CONFIRMED
        and _responsibility_matches_area(item.value, kind)
        for item in experience.responsibilities
    )

    return (
        confirmed_match,
        unverified_title or unverified_responsibility,
    )

def match_experience_requirement(
    requirement: ExperienceRequirement,
    experiences: list[ExperienceItem],
    *,
    as_of: date | None = None,
) -> ExperienceRequirementMatch:
    """Assess one required period without counting imported facts or overlap."""
    reference_date = as_of or date.today()
    kind = _area_kind(requirement.area)

    confirmed_intervals: list[DateInterval] = []
    possible_intervals: list[DateInterval] = []
    confirmed_roles: list[str] = []
    unverified_roles: list[str] = []
    has_possible_area_match = False

    for item in experiences:
        confirmed_area, possible_area = _candidate_matches_area(item, kind)
        role = item.title.value or "Unknown role"

        if confirmed_area:
            guaranteed, possible = _experience_intervals(
                item,
                reference_date,
            )

            if possible is None:
                has_possible_area_match = True
                if role not in unverified_roles:
                    unverified_roles.append(role)
                continue

            possible_intervals.append(possible)

            if guaranteed is not None:
                confirmed_intervals.append(guaranteed)
                if role not in confirmed_roles:
                    confirmed_roles.append(role)

            continue

        if possible_area:
            has_possible_area_match = True
            if role not in unverified_roles:
                unverified_roles.append(role)

    confirmed_months = _total_completed_months(confirmed_intervals)
    possible_months = _total_completed_months(possible_intervals)
    required_months = math.ceil(requirement.min_years * 12)

    if confirmed_months >= required_months:
        status = ExperienceMatchStatus.MEETS_MINIMUM
        reasons = [
            f"Confirmed relevant experience is at least "
            f"{confirmed_months} full months; minimum required is "
            f"{required_months} months."
        ]
    elif has_possible_area_match:
        status = ExperienceMatchStatus.NEEDS_CONFIRMATION
        reasons = [
            "Potentially relevant experience exists, but its title, dates, "
            "or responsibilities are not fully confirmed."
        ]
    elif confirmed_roles:
        status = ExperienceMatchStatus.BELOW_MINIMUM
        reasons = [
            f"Confirmed relevant experience is {confirmed_months} full months; "
            f"minimum required is {required_months} months."
        ]
    elif experiences:
        status = ExperienceMatchStatus.AREA_NOT_EVIDENCED
        reasons = [
            "The Candidate Profile does not contain confirmed evidence "
            "for this specific experience area."
        ]
    else:
        status = ExperienceMatchStatus.UNKNOWN
        reasons = ["No work experience records are available in the profile."]

    return ExperienceRequirementMatch(
        area=requirement.area,
        min_years=requirement.min_years,
        max_years=requirement.max_years,
        priority=requirement.priority.value,
        status=status,
        confirmed_min_months=confirmed_months,
        possible_max_months=possible_months,
        confirmed_roles=confirmed_roles,
        unverified_roles=unverified_roles,
        evidence=[requirement.evidence],
        reasons=reasons,
    )


def match_experience_requirements(
    requirements: list[ExperienceRequirement],
    experiences: list[ExperienceItem],
    *,
    as_of: date | None = None,
) -> list[ExperienceRequirementMatch]:
    return [
        match_experience_requirement(item, experiences, as_of=as_of)
        for item in requirements
    ]


def _degree_matches(degree: str, evidence: str) -> bool:
    normalized_degree = degree.casefold()
    normalized_evidence = evidence.casefold()

    if any(word in normalized_evidence for word in ("undergraduate", "postgraduate")):
        return any(
            word in normalized_degree
            for word in ("bachelor", "bsc", "undergraduate", "master", "msc", "phd")
        )

    if "bachelor" in normalized_evidence or "bsc" in normalized_evidence:
        return any(
            word in normalized_degree
            for word in ("bachelor", "bsc", "undergraduate")
        )

    if "master" in normalized_evidence or "msc" in normalized_evidence:
        return any(word in normalized_degree for word in ("master", "msc"))

    if "ph.d" in normalized_evidence or "phd" in normalized_evidence:
        return "phd" in normalized_degree or "ph.d" in normalized_degree

    if "degree" in normalized_evidence:
        return bool(normalized_degree.strip())

    return False


def _field_matches(field: str, evidence: str) -> bool:
    normalized_field = re.sub(r"\s+", " ", field.casefold()).strip()
    normalized_evidence = re.sub(r"\s+", " ", evidence.casefold())

    if not normalized_field:
        return False

    return normalized_field in normalized_evidence


def match_education_requirement(
    requirement: EducationRequirement,
    education: list[EducationItem],
) -> EducationRequirementMatch:
    """Match degree and field only when profile values are explicitly confirmed."""
    pending_match = False

    for item in education:
        degree = item.degree.value or ""
        field = item.field.value or ""

        degree_matches = _degree_matches(degree, requirement.evidence)
        field_matches = _field_matches(field, requirement.evidence)

        if degree_matches and field_matches:
            if (
                item.degree.status is VerificationStatus.CONFIRMED
                and item.field.status is VerificationStatus.CONFIRMED
            ):
                return EducationRequirementMatch(
                    priority=requirement.priority.value,
                    status=EducationMatchStatus.MATCHED,
                    matched_degree=degree,
                    matched_field=field,
                    evidence=requirement.evidence,
                    reasons=["Degree and field match the requirement and are confirmed."],
                )

            pending_match = True

        elif (
            degree_matches or field_matches
        ) and (
            item.degree.status is not VerificationStatus.CONFIRMED
            or item.field.status is not VerificationStatus.CONFIRMED
        ):
            pending_match = True

    if pending_match:
        return EducationRequirementMatch(
            priority=requirement.priority.value,
            status=EducationMatchStatus.NEEDS_CONFIRMATION,
            evidence=requirement.evidence,
            reasons=["Potential education match contains unconfirmed fields."],
        )

    return EducationRequirementMatch(
        priority=requirement.priority.value,
        status=EducationMatchStatus.NOT_EVIDENCED,
        evidence=requirement.evidence,
        reasons=["No confirmed education record matches this requirement."],
    )


def match_education_requirements(
    requirements: list[EducationRequirement],
    education: list[EducationItem],
) -> list[EducationRequirementMatch]:
    return [
        match_education_requirement(item, education)
        for item in requirements
    ]


def assess_profile_qualifications(
    requirements: list[ExperienceRequirement],
    education_requirements: list[EducationRequirement],
    profile: CandidateProfile,
    *,
    as_of: date | None = None,
) -> tuple[list[ExperienceRequirementMatch], list[EducationRequirementMatch]]:
    return (
        match_experience_requirements(
            requirements,
            profile.experience,
            as_of=as_of,
        ),
        match_education_requirements(
            education_requirements,
            profile.education,
        ),
    )
