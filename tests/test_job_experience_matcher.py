from datetime import date

from career_agent.domain.candidate import EducationItem, ExperienceItem
from career_agent.domain.dates import PartialDate
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.services.job_experience_matcher import (
    EducationMatchStatus,
    ExperienceMatchStatus,
    match_education_requirement,
    match_experience_requirement,
)
from career_agent.services.job_requirements import (
    EducationRequirement,
    ExperienceRequirement,
    RequirementPriority,
)

CONFIRMED = VerificationStatus.CONFIRMED
IMPORTED = VerificationStatus.IMPORTED_FROM_CV


def make_experience(
    title: str,
    start: str,
    end: str = "present",
    *,
    title_status: VerificationStatus = CONFIRMED,
    date_status: VerificationStatus = CONFIRMED,
    currently_employed: bool = True,
    responsibilities: list[tuple[str, VerificationStatus]] | None = None,
) -> ExperienceItem:
    return ExperienceItem(
        company=ProfileField[str](
            value="Example Company",
            status=CONFIRMED,
        ),
        title=ProfileField[str](
            value=title,
            status=title_status,
        ),
        start_date=ProfileField[PartialDate](
            value=PartialDate.parse(start),
            status=date_status,
        ),
        end_date=ProfileField[str](
            value=end,
            status=date_status,
        ),
        currently_employed=currently_employed,
        responsibilities=[
            ProfileField[str](value=value, status=status)
            for value, status in (responsibilities or [])
        ],
    )


def make_experience_requirement(
    area: str | None = "QA",
    min_years: float = 1,
) -> ExperienceRequirement:
    return ExperienceRequirement(
        min_years=min_years,
        max_years=None,
        area=area,
        priority=RequirementPriority.REQUIRED,
        evidence=f"{min_years} years of experience in {area or 'the field'}",
    )


def test_confirmed_qa_experience_is_below_one_year() -> None:
    experience = make_experience(
        "QA Engineer",
        "2026-03",
        responsibilities=[
            (
                "Manual, functional, and integration testing",
                IMPORTED,
            )
        ],
    )

    result = match_experience_requirement(
        make_experience_requirement(),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.BELOW_MINIMUM
    assert result.confirmed_min_months == 7
    assert result.possible_max_months == 8
    assert result.confirmed_roles == ["QA Engineer"]


def test_imported_analyst_experience_is_not_counted_as_qa() -> None:
    experiences = [
        make_experience("QA Engineer", "2026-03"),
        make_experience(
            "Analyst",
            "2025-02",
            title_status=IMPORTED,
            date_status=IMPORTED,
        ),
    ]

    result = match_experience_requirement(
        make_experience_requirement(),
        experiences,
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.BELOW_MINIMUM
    assert result.confirmed_min_months == 7
    assert result.confirmed_roles == ["QA Engineer"]
    assert "Analyst" not in result.confirmed_roles


def test_specialized_automation_experience_needs_confirmation() -> None:
    experience = make_experience(
        "QA Engineer",
        "2026-03",
        responsibilities=[
            (
                "Manual, functional, and integration testing",
                IMPORTED,
            )
        ],
    )

    result = match_experience_requirement(
        make_experience_requirement("Web or App automation testing"),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.AREA_NOT_EVIDENCED
    assert result.confirmed_min_months == 0
    assert result.unverified_roles == []


def test_overlapping_confirmed_roles_are_not_double_counted() -> None:
    experiences = [
        make_experience(
            "QA Engineer",
            "2025-01",
            "2025-12",
            currently_employed=False,
        ),
        make_experience(
            "Test Engineer",
            "2025-06",
            "2025-11",
            currently_employed=False,
        ),
    ]

    result = match_experience_requirement(
        make_experience_requirement(min_years=0.5),
        experiences,
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.MEETS_MINIMUM
    assert result.confirmed_min_months == 10
    assert result.possible_max_months == 11
    assert len(result.confirmed_roles) == 2


def test_unconfirmed_dates_do_not_count_as_confirmed_experience() -> None:
    experience = make_experience(
        "QA Engineer",
        "2025-01",
        title_status=CONFIRMED,
        date_status=IMPORTED,
    )

    result = match_experience_requirement(
        make_experience_requirement(),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.NEEDS_CONFIRMATION
    assert result.confirmed_min_months == 0


def make_education(
    *,
    degree_status: VerificationStatus = CONFIRMED,
    field_status: VerificationStatus = CONFIRMED,
) -> EducationItem:
    return EducationItem(
        institution=ProfileField[str](
            value="Example University",
            status=CONFIRMED,
        ),
        degree=ProfileField[str](
            value="Bachelor",
            status=degree_status,
        ),
        field=ProfileField[str](
            value="Computer Science",
            status=field_status,
        ),
        start_year=ProfileField[int](
            value=2022,
            status=CONFIRMED,
        ),
        end_year=ProfileField[int](
            value=2026,
            status=CONFIRMED,
        ),
    )


def make_education_requirement() -> EducationRequirement:
    return EducationRequirement(
        priority=RequirementPriority.REQUIRED,
        evidence=(
            "Undergraduate or postgraduate in Computer Science, "
            "Software Engineering, or a related field"
        ),
    )


def test_confirmed_bachelor_computer_science_matches() -> None:
    result = match_education_requirement(
        make_education_requirement(),
        [make_education()],
    )

    assert result.status is EducationMatchStatus.MATCHED
    assert result.matched_degree == "Bachelor"
    assert result.matched_field == "Computer Science"


def test_imported_education_is_not_treated_as_confirmed() -> None:
    result = match_education_requirement(
        make_education_requirement(),
        [make_education(degree_status=IMPORTED)],
    )

    assert result.status is EducationMatchStatus.NEEDS_CONFIRMATION


def test_unmatched_education_is_not_evidenced() -> None:
    education = make_education()
    education.field.value = "History"

    result = match_education_requirement(
        make_education_requirement(),
        [education],
    )

    assert result.status is EducationMatchStatus.NOT_EVIDENCED



def test_imported_specialized_duty_needs_confirmation() -> None:
    experience = make_experience(
        "QA Engineer",
        "2026-03",
        responsibilities=[
            ("Developing automated Web UI tests", IMPORTED)
        ],
    )

    result = match_experience_requirement(
        make_experience_requirement("Web or App automation testing"),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.NEEDS_CONFIRMATION
    assert result.confirmed_min_months == 0
    assert result.unverified_roles == ["QA Engineer"]

def test_confirmed_senior_title_counts_as_senior_experience() -> None:
    experience = make_experience(
        "Senior QA Engineer",
        "2024-01",
    )

    result = match_experience_requirement(
        make_experience_requirement("senior role", min_years=1),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.MEETS_MINIMUM
    assert result.confirmed_min_months >= 12
    assert result.confirmed_roles == ["Senior QA Engineer"]


def test_regular_qa_engineer_is_not_counted_as_senior_experience() -> None:
    experience = make_experience(
        "QA Engineer",
        "2024-01",
    )

    result = match_experience_requirement(
        make_experience_requirement("senior role", min_years=1),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.AREA_NOT_EVIDENCED
    assert result.confirmed_min_months == 0
    assert result.confirmed_roles == []
    assert result.unverified_roles == []


def test_imported_senior_title_requires_confirmation() -> None:
    experience = make_experience(
        "Senior QA Engineer",
        "2024-01",
        title_status=IMPORTED,
    )

    result = match_experience_requirement(
        make_experience_requirement("senior role", min_years=1),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.NEEDS_CONFIRMATION
    assert result.confirmed_min_months == 0
    assert result.unverified_roles == ["Senior QA Engineer"]

def test_product_manager_is_not_counted_as_senior_qa_experience() -> None:
    experience = make_experience(
        "Product Manager",
        "2024-01",
    )

    result = match_experience_requirement(
        make_experience_requirement("senior role", min_years=1),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.AREA_NOT_EVIDENCED
    assert result.confirmed_min_months == 0


def test_qa_manager_counts_as_senior_experience() -> None:
    experience = make_experience(
        "QA Manager",
        "2024-01",
    )

    result = match_experience_requirement(
        make_experience_requirement("senior role", min_years=1),
        [experience],
        as_of=date(2026, 11, 23),
    )

    assert result.status is ExperienceMatchStatus.MEETS_MINIMUM
    assert result.confirmed_min_months >= 12
