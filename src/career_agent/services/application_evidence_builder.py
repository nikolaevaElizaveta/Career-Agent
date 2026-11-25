"""Build a traceable evidence map for a job application."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.candidate import CandidateProfile
from career_agent.domain.fields import VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.job_candidate_assessment import (
    CandidateJobAssessment,
    assess_candidate_job,
)
from career_agent.services.job_duty_matcher import DutyMatchStatus
from career_agent.services.job_skill_matcher import (
    SkillAlternativeMatch,
    SkillMatchStatus,
    SkillRequirementMatch,
)


class ApplicationEvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NO_EVIDENCE = "no_evidence"


class ApplicationEvidenceCategory(StrEnum):
    REQUIRED_SKILL = "required_skill"
    PREFERRED_SKILL = "preferred_skill"
    UNSPECIFIED_SKILL = "unspecified_skill"
    ALTERNATIVE_SKILLS = "alternative_skills"
    RESPONSIBILITY = "responsibility"
    EXPERIENCE = "experience"
    EDUCATION = "education"


class ApplicationEvidenceSource(StrEnum):
    CANDIDATE_SKILL = "candidate_skill"
    EXPERIENCE_RESPONSIBILITY = "experience_responsibility"
    EDUCATION = "education"


class EvidenceFact(BaseModel):
    source: ApplicationEvidenceSource
    text: str
    verification_status: VerificationStatus
    usable_in_documents: bool = False
    claim_scope: str
    context: str | None = None
    matched_capabilities: list[str] = Field(default_factory=list)
    evidence_type: str | None = None
    limitation: str | None = None


class ApplicationEvidenceItem(BaseModel):
    category: ApplicationEvidenceCategory
    requirement: str
    priority: str = "unspecified"
    status: ApplicationEvidenceStatus
    evidence: list[EvidenceFact] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    note: str | None = None


class ApplicationEvidenceReport(BaseModel):
    job_id: str
    title: str
    company: str
    items: list[ApplicationEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def confirmed_count(self) -> int:
        return sum(
            item.status is ApplicationEvidenceStatus.CONFIRMED
            for item in self.items
        )

    @property
    def partial_count(self) -> int:
        return sum(
            item.status is ApplicationEvidenceStatus.PARTIAL
            for item in self.items
        )

    @property
    def needs_confirmation_count(self) -> int:
        return sum(
            item.status is ApplicationEvidenceStatus.NEEDS_CONFIRMATION
            for item in self.items
        )

    @property
    def no_evidence_count(self) -> int:
        return sum(
            item.status is ApplicationEvidenceStatus.NO_EVIDENCE
            for item in self.items
        )

    @property
    def document_ready_facts(self) -> list[EvidenceFact]:
        """Return unique facts explicitly allowed in generated documents."""
        result: list[EvidenceFact] = []
        seen: set[tuple[str, str, str]] = set()

        for item in self.items:
            for fact in item.evidence:
                if not fact.usable_in_documents:
                    continue

                key = (
                    fact.source.value,
                    fact.text,
                    fact.claim_scope,
                )
                if key in seen:
                    continue

                seen.add(key)
                result.append(fact)

        return result


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _skill_status(status: object) -> ApplicationEvidenceStatus:
    value = _value(status)

    if value == SkillMatchStatus.CONFIRMED.value:
        return ApplicationEvidenceStatus.CONFIRMED

    if value == SkillMatchStatus.MISSING.value:
        return ApplicationEvidenceStatus.NO_EVIDENCE

    return ApplicationEvidenceStatus.NEEDS_CONFIRMATION


def _skill_facts(match: SkillRequirementMatch) -> list[EvidenceFact]:
    if not match.candidate_skill:
        return []

    proficiency_status = match.proficiency_status or VerificationStatus.UNKNOWN
    confirmed = proficiency_status is VerificationStatus.CONFIRMED

    facts = [
        EvidenceFact(
            source=ApplicationEvidenceSource.CANDIDATE_SKILL,
            text=match.candidate_skill,
            verification_status=proficiency_status,
            usable_in_documents=confirmed,
            claim_scope="skill",
            limitation=(
                None
                if confirmed
                else "Уровень владения навыком ещё не подтверждён."
            ),
        )
    ]

    commercial_confirmed = (
        match.commercial_experience_status is VerificationStatus.CONFIRMED
    )

    if (
        confirmed
        and commercial_confirmed
        and match.commercial_experience is True
    ):
        facts.append(
            EvidenceFact(
                source=ApplicationEvidenceSource.CANDIDATE_SKILL,
                text=match.candidate_skill,
                verification_status=VerificationStatus.CONFIRMED,
                usable_in_documents=True,
                claim_scope="commercial_experience",
                limitation=None,
            )
        )

    return facts


def _alternative_facts(group: SkillAlternativeMatch) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []

    for option in group.matched_options:
        facts.extend(_skill_facts(option))

    return facts


def _find_experience_records(
    profile: CandidateProfile,
    evidence_text: str,
    role_title: str | None,
):
    for experience in profile.experience:
        if role_title and experience.title.value != role_title:
            continue

        for responsibility in experience.responsibilities:
            if responsibility.value == evidence_text:
                yield experience, responsibility


def _duty_facts(
    duty,
    profile: CandidateProfile,
) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []

    for evidence in duty.evidence:
        source = _value(evidence.source)

        if source == "experience_responsibility":
            for experience, responsibility in _find_experience_records(
                profile,
                evidence.evidence_text,
                evidence.role_title,
            ):
                context_confirmed = (
                    experience.company.usable_in_documents()
                    and experience.title.usable_in_documents()
                )
                responsibility_confirmed = (
                    responsibility.status is VerificationStatus.CONFIRMED
                    and bool(responsibility.value)
                )
                usable = context_confirmed and responsibility_confirmed

                if usable:
                    verification_status = VerificationStatus.CONFIRMED
                    context = (
                        f"{experience.title.value} — {experience.company.value}"
                    )
                    limitation = None
                else:
                    verification_status = VerificationStatus.NEEDS_CONFIRMATION
                    context = None

                    if not responsibility_confirmed:
                        limitation = "Рабочая обязанность не подтверждена."
                    else:
                        limitation = (
                            "Название должности и/или компании "
                            "не подтверждено."
                        )

                facts.append(
                    EvidenceFact(
                        source=ApplicationEvidenceSource.EXPERIENCE_RESPONSIBILITY,
                        text=responsibility.value or evidence.evidence_text,
                        verification_status=verification_status,
                        usable_in_documents=usable,
                        claim_scope="work_responsibility",
                        context=context,
                        matched_capabilities=evidence.matched_capabilities,
                        limitation=limitation,
                    )
                )

        elif source == "candidate_skill":
            skill_name = evidence.candidate_skill or evidence.evidence_text
            skill = next(
                (
                    item
                    for item in profile.skills
                    if item.name.casefold() == skill_name.casefold()
                ),
                None,
            )

            if skill is None:
                continue

            confirmed = (
                skill.proficiency.status is VerificationStatus.CONFIRMED
            )
            supporting = _value(evidence.evidence_type) == "supporting"

            if supporting:
                limitation = (
                    "Владение инструментом может поддерживать эту задачу, "
                    "но само по себе не доказывает выполнение всей обязанности."
                )
            else:
                limitation = (
                    "Подтверждает навык, но не доказывает коммерческий "
                    "опыт выполнения этой обязанности."
                )

            facts.append(
                EvidenceFact(
                    source=ApplicationEvidenceSource.CANDIDATE_SKILL,
                    text=skill.name,
                    verification_status=skill.proficiency.status,
                    usable_in_documents=confirmed,
                    claim_scope="skill",
                    matched_capabilities=evidence.matched_capabilities,
                    evidence_type=_value(evidence.evidence_type),
                    limitation=None if not confirmed else limitation,
                )
            )

    return facts


def _duty_status(duty, facts: list[EvidenceFact]) -> tuple[
    ApplicationEvidenceStatus, str | None
]:
    status = _value(duty.status)

    experience_capabilities = {
        capability
        for fact in facts
        if (
            fact.source
            is ApplicationEvidenceSource.EXPERIENCE_RESPONSIBILITY
            and fact.usable_in_documents
        )
        for capability in fact.matched_capabilities
    }

    direct_skill_capabilities = {
        capability
        for fact in facts
        if (
            fact.source is ApplicationEvidenceSource.CANDIDATE_SKILL
            and fact.evidence_type == "direct"
            and fact.usable_in_documents
        )
        for capability in fact.matched_capabilities
    }

    required = set(duty.required_capabilities)

    if status == DutyMatchStatus.CONFIRMED_EXPERIENCE.value:
        if required.issubset(experience_capabilities):
            return ApplicationEvidenceStatus.CONFIRMED, None

        return (
            ApplicationEvidenceStatus.NEEDS_CONFIRMATION,
            "Требуется подтвердить контекст рабочего опыта.",
        )

    if status == DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE.value:
        if required.issubset(direct_skill_capabilities):
            return (
                ApplicationEvidenceStatus.CONFIRMED,
                "Подтверждены навыки, но не обязательно коммерческий опыт "
                "выполнения этой обязанности.",
            )

        return (
            ApplicationEvidenceStatus.NEEDS_CONFIRMATION,
            "Не все навыки для этой обязанности подтверждены.",
        )

    if status == DutyMatchStatus.PARTIAL.value:
        if any(fact.usable_in_documents for fact in facts):
            return (
                ApplicationEvidenceStatus.PARTIAL,
                "Подтверждена только часть требуемых компетенций.",
            )

        if facts:
            return (
                ApplicationEvidenceStatus.NEEDS_CONFIRMATION,
                "Найденные сведения требуют подтверждения.",
            )

        return ApplicationEvidenceStatus.NO_EVIDENCE, None

    if status in {
        DutyMatchStatus.NEEDS_CONFIRMATION.value,
        DutyMatchStatus.UNCLASSIFIED.value,
    }:
        return (
            ApplicationEvidenceStatus.NEEDS_CONFIRMATION,
            "Требуется ручная проверка требования и доказательств.",
        )

    return ApplicationEvidenceStatus.NO_EVIDENCE, None


def _build_duty_item(duty, profile: CandidateProfile) -> ApplicationEvidenceItem:
    facts = _duty_facts(duty, profile)
    status, note = _duty_status(duty, facts)

    return ApplicationEvidenceItem(
        category=ApplicationEvidenceCategory.RESPONSIBILITY,
        requirement=duty.requirement,
        status=status,
        evidence=facts,
        missing_capabilities=duty.missing_capabilities,
        note=note,
    )


def _build_experience_items(
    assessment: CandidateJobAssessment,
) -> list[ApplicationEvidenceItem]:
    result = []

    for match in assessment.experience_matches:
        status_value = _value(match.status)
        facts = []

        if match.confirmed_min_months > 0:
            area = match.area or "релевантного"
            roles = ", ".join(match.confirmed_roles)

            facts.append(
                EvidenceFact(
                    source=ApplicationEvidenceSource.EXPERIENCE_RESPONSIBILITY,
                    text=(
                        f"{match.confirmed_min_months} подтверждённых полных "
                        f"месяцев опыта ({area})"
                    ),
                    verification_status=VerificationStatus.CONFIRMED,
                    usable_in_documents=True,
                    claim_scope="confirmed_experience_duration",
                    context=roles or None,
                )
            )

        if status_value == "meets_minimum":
            status = ApplicationEvidenceStatus.CONFIRMED
        elif status_value == "below_minimum":
            status = (
                ApplicationEvidenceStatus.PARTIAL
                if match.confirmed_min_months > 0
                else ApplicationEvidenceStatus.NO_EVIDENCE
            )
        elif status_value == "needs_confirmation":
            status = ApplicationEvidenceStatus.NEEDS_CONFIRMATION
        else:
            status = ApplicationEvidenceStatus.NO_EVIDENCE

        result.append(
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.EXPERIENCE,
                requirement=(
                    f"Стаж: минимум {match.min_years} года"
                    + (f" в направлении {match.area}" if match.area else "")
                ),
                priority=match.priority,
                status=status,
                evidence=facts,
                note=" ".join(match.reasons) or None,
            )
        )

    return result


def _build_education_items(
    assessment: CandidateJobAssessment,
) -> list[ApplicationEvidenceItem]:
    result = []

    for match in assessment.education_matches:
        status_value = _value(match.status)
        facts = []

        if status_value == "matched":
            parts = [
                value
                for value in (match.matched_degree, match.matched_field)
                if value
            ]

            if parts:
                facts.append(
                    EvidenceFact(
                        source=ApplicationEvidenceSource.EDUCATION,
                        text=", ".join(parts),
                        verification_status=VerificationStatus.CONFIRMED,
                        usable_in_documents=True,
                        claim_scope="education",
                    )
                )

            status = (
                ApplicationEvidenceStatus.CONFIRMED
                if facts
                else ApplicationEvidenceStatus.NEEDS_CONFIRMATION
            )
        elif status_value == "needs_confirmation":
            status = ApplicationEvidenceStatus.NEEDS_CONFIRMATION
        else:
            status = ApplicationEvidenceStatus.NO_EVIDENCE

        result.append(
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.EDUCATION,
                requirement=match.evidence,
                priority=match.priority,
                status=status,
                evidence=facts,
                note=" ".join(match.reasons) or None,
            )
        )

    return result


def build_application_evidence(
    job: JobPosting,
    profile: CandidateProfile,
    *,
    assessment: CandidateJobAssessment | None = None,
    as_of: date | None = None,
) -> ApplicationEvidenceReport:
    """Build a traceable map of employer requirements and candidate evidence."""
    resolved = assessment or assess_candidate_job(
        job,
        profile,
        as_of=as_of,
    )

    items: list[ApplicationEvidenceItem] = []

    skill_groups = (
        (
            ApplicationEvidenceCategory.REQUIRED_SKILL,
            resolved.skill_matches.required_skills,
        ),
        (
            ApplicationEvidenceCategory.PREFERRED_SKILL,
            resolved.skill_matches.preferred_skills,
        ),
        (
            ApplicationEvidenceCategory.UNSPECIFIED_SKILL,
            resolved.skill_matches.unspecified_skills,
        ),
    )

    for category, matches in skill_groups:
        for match in matches:
            items.append(
                ApplicationEvidenceItem(
                    category=category,
                    requirement=match.requirement,
                    priority=_value(match.priority),
                    status=_skill_status(match.status),
                    evidence=_skill_facts(match),
                    note=(
                        "Подтверждённый навык не означает автоматически "
                        "подтверждённый коммерческий опыт."
                        if (
                            match.proficiency_status
                            is VerificationStatus.CONFIRMED
                            and match.commercial_experience_status
                            is not VerificationStatus.CONFIRMED
                        )
                        else None
                    ),
                )
            )

    for group in resolved.skill_matches.alternative_groups:
        status = _skill_status(group.status)

        items.append(
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.ALTERNATIVE_SKILLS,
                requirement=" или ".join(group.skills),
                priority=_value(group.priority),
                status=status,
                evidence=_alternative_facts(group),
                note=(
                    "Альтернативное требование подтверждено, если "
                    "соответствует правило группы."
                    if group.match_rule == "any_of"
                    else "Правило альтернативного требования требует проверки."
                ),
            )
        )

    items.extend(
        _build_duty_item(duty, profile)
        for duty in resolved.duty_matches
    )
    items.extend(_build_experience_items(resolved))
    items.extend(_build_education_items(resolved))

    return ApplicationEvidenceReport(
        job_id=job.id,
        title=job.title,
        company=job.company,
        items=items,
        warnings=[
            "Технологии проектов и highlights образования пока не используются "
            "как доказательства: для отдельных элементов этих списков "
            "нет статуса подтверждения."
        ],
    )
