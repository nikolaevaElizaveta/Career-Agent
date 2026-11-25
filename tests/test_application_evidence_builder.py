from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from career_agent.domain.candidate import ExperienceItem, SkillItem
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.domain.job_posting import JobPosting
from career_agent.services.application_evidence_builder import (
    ApplicationEvidenceCategory,
    ApplicationEvidenceSource,
    ApplicationEvidenceStatus,
    EvidenceFact,
    _duty_status,
    build_application_evidence,
)
from career_agent.services.job_duty_matcher import DutyMatchStatus
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def _job(description: str) -> JobPosting:
    return JobPosting(
        id="evidence-job",
        source="himalayas",
        source_job_id="evidence-job",
        title="Junior QA Engineer",
        company="Example Ltd",
        description=description,
        discovered_at=datetime(2026, 11, 23, tzinfo=UTC),
    )


def _profile():
    return ProfileService().load(EXAMPLE_PROFILE)


def test_confirmed_skill_is_usable_without_claiming_commercial_experience() -> None:
    profile = _profile()
    profile.skills.append(
        SkillItem(
            name="Playwright",
            category="test_automation",
            proficiency=ProfileField(
                value="basic",
                status=VerificationStatus.CONFIRMED,
            ),
            commercial_experience=ProfileField(
                value=None,
                status=VerificationStatus.UNKNOWN,
            ),
        )
    )

    job = _job(
        "<h2>Requirements</h2><ul><li>Playwright</li></ul>"
    )

    report = build_application_evidence(job, profile)

    item = next(
        item
        for item in report.items
        if (
            item.category is ApplicationEvidenceCategory.REQUIRED_SKILL
            and item.requirement == "Playwright"
        )
    )

    assert item.status is ApplicationEvidenceStatus.CONFIRMED
    assert len(item.evidence) == 1
    assert item.evidence[0].usable_in_documents is True
    assert item.evidence[0].claim_scope == "skill"
    assert "коммерческий опыт" in item.note.casefold()
    assert not any(
        fact.claim_scope == "commercial_experience"
        for fact in report.document_ready_facts
    )


def test_imported_responsibility_is_not_document_ready() -> None:
    profile = _profile()
    profile.experience.append(
        ExperienceItem(
            company=ProfileField(
                value="Example Consulting",
                status=VerificationStatus.CONFIRMED,
            ),
            title=ProfileField(
                value="QA Engineer",
                status=VerificationStatus.CONFIRMED,
            ),
            start_date=ProfileField(status=VerificationStatus.UNKNOWN),
            end_date=ProfileField(status=VerificationStatus.UNKNOWN),
            responsibilities=[
                ProfileField(
                    value="Root cause analysis",
                    status=VerificationStatus.IMPORTED_FROM_CV,
                )
            ],
        )
    )

    job = _job(
        "<h2>Responsibilities</h2><ul><li>Root cause analysis</li></ul>"
    )

    report = build_application_evidence(job, profile)

    item = next(
        item
        for item in report.items
        if (
            item.category is ApplicationEvidenceCategory.RESPONSIBILITY
            and item.requirement == "Root cause analysis"
        )
    )

    experience_facts = [
        fact
        for fact in item.evidence
        if fact.claim_scope == "work_responsibility"
    ]

    assert experience_facts
    assert all(not fact.usable_in_documents for fact in experience_facts)
    assert all(
        fact.verification_status is VerificationStatus.NEEDS_CONFIRMATION
        for fact in experience_facts
    )


def test_unconfirmed_company_context_blocks_work_experience_claim() -> None:
    profile = _profile()
    profile.experience.append(
        ExperienceItem(
            company=ProfileField(
                value="Example Consulting",
                status=VerificationStatus.UNKNOWN,
            ),
            title=ProfileField(
                value="QA Engineer",
                status=VerificationStatus.CONFIRMED,
            ),
            start_date=ProfileField(status=VerificationStatus.UNKNOWN),
            end_date=ProfileField(status=VerificationStatus.UNKNOWN),
            responsibilities=[
                ProfileField(
                    value="Root cause analysis",
                    status=VerificationStatus.CONFIRMED,
                )
            ],
        )
    )

    job = _job(
        "<h2>Responsibilities</h2><ul><li>Root cause analysis</li></ul>"
    )

    report = build_application_evidence(job, profile)

    item = next(
        item
        for item in report.items
        if (
            item.category is ApplicationEvidenceCategory.RESPONSIBILITY
            and item.requirement == "Root cause analysis"
        )
    )

    fact = next(
        fact
        for fact in item.evidence
        if fact.claim_scope == "work_responsibility"
        and fact.text == "Root cause analysis"
    )

    assert fact.usable_in_documents is False
    assert fact.context is None
    assert fact.limitation is not None
    assert "компании" in fact.limitation


def test_missing_skill_is_reported_without_invented_evidence() -> None:
    profile = _profile()
    job = _job(
        "<h2>Requirements</h2><ul><li>Playwright</li></ul>"
    )

    report = build_application_evidence(job, profile)

    item = next(
        item
        for item in report.items
        if (
            item.category is ApplicationEvidenceCategory.REQUIRED_SKILL
            and item.requirement == "Playwright"
        )
    )

    assert item.status is ApplicationEvidenceStatus.NO_EVIDENCE
    assert item.evidence == []


def test_document_ready_facts_are_unique() -> None:
    profile = _profile()
    profile.skills.append(
        SkillItem(
            name="Playwright",
            category="test_automation",
            proficiency=ProfileField(
                value="basic",
                status=VerificationStatus.CONFIRMED,
            ),
            commercial_experience=ProfileField(
                value=None,
                status=VerificationStatus.UNKNOWN,
            ),
        )
    )

    job = _job(
        "<h2>Requirements</h2><ul><li>Playwright</li></ul>"
    )
    report = build_application_evidence(job, profile)

    facts = report.document_ready_facts
    keys = [
        (fact.source, fact.text, fact.claim_scope)
        for fact in facts
    ]

    assert len(keys) == len(set(keys))

def test_duty_status_does_not_depend_on_evidence_list_alignment() -> None:
    # Первое доказательство отсутствует в профиле и было пропущено
    # при построении facts. Второе доказательство — прямой навык.
    duty = SimpleNamespace(
        status=DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE,
        required_capabilities=["api_testing"],
        evidence=[
            SimpleNamespace(
                source="candidate_skill",
                evidence_type="supporting",
            ),
            SimpleNamespace(
                source="candidate_skill",
                evidence_type="direct",
            ),
        ],
    )

    facts = [
        EvidenceFact(
            source=ApplicationEvidenceSource.CANDIDATE_SKILL,
            text="Postman",
            verification_status=VerificationStatus.CONFIRMED,
            usable_in_documents=True,
            claim_scope="skill",
            matched_capabilities=["api_testing"],
            evidence_type="direct",
        )
    ]

    status, note = _duty_status(duty, facts)

    assert status is ApplicationEvidenceStatus.CONFIRMED
    assert note is not None
    assert "коммерческий опыт" in note.casefold()
