"""Candidate Profile — the only source of facts for later modules."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from career_agent.domain.dates import PartialDate
from career_agent.domain.fields import ProfileField, VerificationStatus


class PersonalInfo(BaseModel):
    full_name: ProfileField[str]
    citizenship: ProfileField[str]
    native_language: ProfileField[str]
    english_level: ProfileField[str]


class ContactInfo(BaseModel):
    email: ProfileField[str]
    telegram: ProfileField[str]
    linkedin: ProfileField[str]


class EducationItem(BaseModel):
    institution: ProfileField[str]
    degree: ProfileField[str]
    field: ProfileField[str]
    start_year: ProfileField[int]
    end_year: ProfileField[int]
    highlights: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    company: ProfileField[str]
    title: ProfileField[str]
    location: ProfileField[str] = Field(
        default_factory=lambda: ProfileField[str](status=VerificationStatus.UNKNOWN)
    )
    start_date: ProfileField[PartialDate]
    end_date: ProfileField[str]
    currently_employed: bool = False
    responsibilities: list[ProfileField[str]] = Field(default_factory=list)

    @field_validator("start_date", mode="before")
    @classmethod
    def coerce_start_date(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = value.get("value")
        if raw is None or isinstance(raw, PartialDate):
            return value
        return {**value, "value": PartialDate.parse(raw)}


class ProjectItem(BaseModel):
    name: ProfileField[str]
    summary: ProfileField[str]
    technologies: list[str] = Field(default_factory=list)


class SkillItem(BaseModel):
    name: str
    category: str
    proficiency: ProfileField[str] = Field(
        default_factory=lambda: ProfileField[str](status=VerificationStatus.UNKNOWN)
    )
    commercial_experience: ProfileField[bool] = Field(
        default_factory=lambda: ProfileField[bool](
            value=None, status=VerificationStatus.UNKNOWN
        )
    )


class LanguageItem(BaseModel):
    name: str
    level: ProfileField[str]


class MatchWeights(BaseModel):
    role_and_duties: int = 25
    technical_skills: int = 25
    geography: int = 25
    salary: int = 15
    ethics: int = 10

    @field_validator("role_and_duties", "technical_skills", "geography", "salary", "ethics")
    @classmethod
    def non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("match weights must be >= 0")
        return value

    def total(self) -> int:
        return (
            self.role_and_duties
            + self.technical_skills
            + self.geography
            + self.salary
            + self.ethics
        )


class CareerPreferences(BaseModel):
    target_roles: list[str]
    experience_band: str = "junior_0_2"
    also_consider_years: str = "2_3_if_strong_fit"
    match_weights: MatchWeights = Field(default_factory=MatchWeights)


class GeographicPreferences(BaseModel):
    priority_countries: list[str]
    other_countries_allowed: bool = True
    work_from_russia_first: bool = True
    relocation_desired: bool = True
    relocation_required: bool = False
    has_foreign_work_permit: ProfileField[bool]
    has_foreign_residence_permit: ProfileField[bool]


class SalaryExpectations(BaseModel):
    amount: int
    currency: str = "RUB"
    period: str = "month"
    kind: str = "net"
    preferred_currencies: list[str] = Field(
        default_factory=lambda: ["EUR", "USD", "GBP", "AUD", "RUB"]
    )

    @field_validator("kind")
    @classmethod
    def kind_must_be_net_or_gross(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"net", "gross"}:
            raise ValueError("salary kind must be 'net' or 'gross'")
        return normalized


class EmploymentPreferences(BaseModel):
    accepted_types: list[str]
    preferred_work_mode: str = "remote"
    hybrid_or_office_if_relocation: bool = True


class EthicalRestrictions(BaseModel):
    hard_exclusions: list[str]
    lower_priority: list[str] = Field(default_factory=list)
    unpaid_work_allowed: bool = False


class CandidateProfile(BaseModel):
    """Structured profile shared by discovery, matching, and applications."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    personal: PersonalInfo
    contact: ContactInfo
    education: list[EducationItem]
    experience: list[ExperienceItem]
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    career_preferences: CareerPreferences
    geographic_preferences: GeographicPreferences
    salary_expectations: SalaryExpectations
    employment_preferences: EmploymentPreferences
    ethical_restrictions: EthicalRestrictions

    def display_name(self) -> str:
        return self.personal.full_name.value or "Unknown candidate"

    def contact_email(self) -> str | None:
        if self.contact.email.usable_in_documents():
            return str(self.contact.email.value)
        return None
