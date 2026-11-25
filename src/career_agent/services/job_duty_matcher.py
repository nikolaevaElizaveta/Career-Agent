"""Compare job duties with candidate experience and confirmed skills."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.candidate import CandidateProfile
from career_agent.domain.fields import VerificationStatus


class DutyMatchStatus(StrEnum):
    CONFIRMED_EXPERIENCE = "confirmed_experience"
    CONFIRMED_SKILL_EVIDENCE = "confirmed_skill_evidence"
    NEEDS_CONFIRMATION = "needs_confirmation"
    PARTIAL = "partial"
    NO_EVIDENCE = "no_evidence"
    UNCLASSIFIED = "unclassified"


class DutyEvidenceSource(StrEnum):
    EXPERIENCE_RESPONSIBILITY = "experience_responsibility"
    CANDIDATE_SKILL = "candidate_skill"


class DutyEvidenceType(StrEnum):
    DIRECT = "direct"
    SUPPORTING = "supporting"


class DutyEvidence(BaseModel):
    source: DutyEvidenceSource
    evidence_type: DutyEvidenceType
    evidence_text: str
    verification_status: VerificationStatus
    role_title: str | None = None
    candidate_skill: str | None = None
    commercial_experience: bool | None = None
    commercial_experience_status: VerificationStatus | None = None
    matched_capabilities: list[str] = Field(default_factory=list)


class JobDutyMatch(BaseModel):
    requirement: str
    status: DutyMatchStatus
    required_capabilities: list[str] = Field(default_factory=list)
    supported_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    evidence_coverage_percent: float = 0.0
    confirmed_evidence_coverage_percent: float = 0.0
    verification_needed: bool = False
    evidence: list[DutyEvidence] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


_CAPABILITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "api_testing": re.compile(
        r"\bapi\s*(?:/\s*api)?\s+(?:(?:automated|manual)\s+)?tests?\b"
        r"|\bapi testing\b",
        re.I,
    ),
    "test_automation": re.compile(
        r"\bautomated tests?\b|\btest automation\b"
        r"|\bautomation testing\b|\bautomation scripts?\b"
        r"|\bautomated\b.{0,40}\b(?:tests?|testing)\b"
        r"|\b(?:tests?|testing)\b.{0,40}\bautomated\b"
        r"|\bautomation\b.{0,40}\b(?:testing|tests?|exploratory)\b",
        re.I,
    ),
    "mobile_app_testing": re.compile(
        r"\b(?:app|mobile)\s+testing\b|\btesting across "
        r"(?:android|ios)\b",
        re.I,
    ),
    "android_testing": re.compile(r"\bandroid\b", re.I),
    "ios_testing": re.compile(r"\bios\b", re.I),
    "manual_testing": re.compile(
        r"\bmanual(?:\s+exploratory)?\s+testing\b"
        r"|\bmanual tests?\b"
        r"|\btesting\b.{0,40}\bmanual\b",
        re.I,
    ),
    "functional_testing": re.compile(
        r"\bfunctional(?:\s+(?:and|,)\s+"
        r"(?:regression|acceptance|integration))*\s+testing\b",
        re.I,
    ),
    "integration_testing": re.compile(r"\bintegration testing\b", re.I),
    "acceptance_testing": re.compile(
        r"\bacceptance(?:\s+(?:and|,)\s+"
        r"(?:regression|functional|integration))*\s+testing\b",
        re.I,
    ),
    "regression_testing": re.compile(r"\bregression testing\b", re.I),
    "exploratory_testing": re.compile(r"\bexploratory testing\b", re.I),
    "performance_testing": re.compile(r"\bperformance testing\b", re.I),
    "cross_browser_testing": re.compile(
        r"\bcross[- ]browser\b|\bbrowser compatibility\b",
        re.I,
    ),
    "app_compatibility_testing": re.compile(
        r"\bapp compatibility testing\b|\bmobile app compatibility\b",
        re.I,
    ),
    "device_compatibility_testing": re.compile(
        r"\b(?:across\s+)?devices\b|\bdevice compatibility\b"
        r"|\bos versions?\b|\boperating system versions?\b",
        re.I,
    ),
    "cross_resolution_testing": re.compile(
        r"\bcross[- ]resolution\b|\bscreen sizes?\b"
        r"|\bscreen resolutions?\b",
        re.I,
    ),
    "test_case_design": re.compile(
        r"\btest case design\b|\bdesign.{0,60}\btest cases?\b"
        r"|\bcreate.{0,60}\btest scenarios?\b"
        r"|\btest scenarios?\b",
        re.I,
    ),
    "test_planning": re.compile(r"\btest plans?\b", re.I),
    "test_case_review": re.compile(r"\btest case reviews?\b", re.I),
    "test_data_preparation": re.compile(
        r"\bprepar\w*\s+test data\b|\btest data preparation\b",
        re.I,
    ),
    "test_documentation": re.compile(
        r"\btest documentation\b|\btest docs?\b",
        re.I,
    ),
    "requirements_analysis": re.compile(
        r"\banaly[sz](?:e|ing|ed|is)\s+requirements\b"
        r"|\brequirements analysis\b"
        r"|\banalysis of user requests\b",
        re.I,
    ),
    "defect_management": re.compile(
        r"\b(?:identify|identifying|locali[sz]e|locali[sz]ing|"
        r"report|reporting|track|tracking)\b.{0,60}\b(?:defects?|bugs?)\b"
        r"|\bbug tracking\b|\bdefect reporting\b",
        re.I,
    ),
    "defect_followup": re.compile(
        r"\b(?:ensure|drive|follow up on|push).{0,50}"
        r"\b(?:fixes|resolution|issues)\b"
        r"|\bissue resolution\b",
        re.I,
    ),
    "defect_retesting": re.compile(
        r"\bretest(?:ing)?\b.{0,40}\b(?:bugs?|defects?|fixes)\b"
        r"|\b(?:bugs?|defects?)\b.{0,40}\bretest(?:ing)?\b",
        re.I,
    ),
    "root_cause_analysis": re.compile(
        r"\broot[- ]cause analysis\b",
        re.I,
    ),
    "database_validation": re.compile(
        r"\bdatabase checks?\b|\bdata validation\b"
        r"|\bverify data consistency\b",
        re.I,
    ),
    "sql_usage": re.compile(r"\bsql\b", re.I),
    "kafka_integration": re.compile(r"\bkafka\b", re.I),
    "team_collaboration": re.compile(
        r"\b(?:collaborat\w*|communicat\w*)\b.{0,80}"
        r"\b(?:developers?|product managers?|product team|team)\b"
        r"|\bcross-functional collaboration\b",
        re.I,
    ),
    "release_participation": re.compile(
        r"\bparticipat\w*\b.{0,40}\breleases?\b"
        r"|\brelease testing\b",
        re.I,
    ),
    "feature_demonstration": re.compile(
        r"\b(?:demonstrat\w*|present\w*)\b.{0,50}"
        r"\b(?:functionality|features?|demos?)\b",
        re.I,
    ),
    "test_project_maintenance": re.compile(
        r"\bmaintain\w*\b.{0,40}\btest project\b",
        re.I,
    ),
    "ai_assisted_testing": re.compile(
        r"\bai tools?\b.{0,60}\btesting\b"
        r"|\bai-assisted testing\b",
        re.I,
    ),
    "test_coverage_optimization": re.compile(
        r"\b(?:test )?coverage\b.{0,60}\b(?:improv\w*|blind spots?)\b"
        r"|\bimprov\w*\b.{0,60}\bautomation effectiveness\b",
        re.I,
    ),
    "risk_analysis": re.compile(
        r"\b(?:risk points?|risk analysis|system impact)\b",
        re.I,
    ),
}


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def extract_duty_capabilities(text: str) -> set[str]:
    """Extract only explicitly recognised capability signals."""
    return {
        capability
        for capability, pattern in _CAPABILITY_PATTERNS.items()
        if pattern.search(text)
    }


# Exact confirmed profile competencies.
_DIRECT_SKILL_CAPABILITIES: dict[str, set[str]] = {
    "api testing": {"api_testing"},
    "manual testing": {"manual_testing"},
    "functional testing": {"functional_testing"},
    "integration testing": {"integration_testing"},
    "acceptance testing": {"acceptance_testing"},
    "regression testing": {"regression_testing"},
    "exploratory testing": {"exploratory_testing"},
    "performance testing": {"performance_testing"},
    "test case design and execution": {"test_case_design"},
    "test documentation": {"test_documentation"},
    "requirements analysis": {"requirements_analysis"},
    "defect reporting": {"defect_management"},
    "defect reporting and tracking": {"defect_management"},
    "retesting bug fixes": {"defect_retesting"},
    "root cause analysis": {"root_cause_analysis"},
    "ai assisted testing": {"ai_assisted_testing"},
    "cross functional collaboration": {"team_collaboration"},
    "feature demonstrations": {"feature_demonstration"},
}

# Tool familiarity supports a duty but does not prove the whole activity.
_SUPPORTING_SKILL_CAPABILITIES: dict[str, set[str]] = {
    "postman": {"api_testing"},
    "sql": {"sql_usage"},
    "dbeaver": {"database_validation"},
    "kafka": {"kafka_integration"},
}


def match_job_duty(
    requirement: str,
    profile: CandidateProfile,
) -> JobDutyMatch:
    """Compare one extracted job duty with profile responsibilities and skills."""
    required = extract_duty_capabilities(requirement)

    if not required:
        return JobDutyMatch(
            requirement=requirement,
            status=DutyMatchStatus.UNCLASSIFIED,
            reasons=[
                "No configured capability pattern recognises this duty yet."
            ],
        )

    evidence: list[DutyEvidence] = []
    confirmed_experience: set[str] = set()
    unconfirmed_experience: set[str] = set()
    confirmed_direct_skills: set[str] = set()
    unconfirmed_direct_skills: set[str] = set()
    confirmed_supporting_skills: set[str] = set()
    unconfirmed_supporting_skills: set[str] = set()

    for experience in profile.experience:
        role_title = experience.title.value

        for responsibility in experience.responsibilities:
            text = responsibility.value
            if not text:
                continue

            matched = extract_duty_capabilities(text).intersection(required)
            if not matched:
                continue

            evidence.append(
                DutyEvidence(
                    source=DutyEvidenceSource.EXPERIENCE_RESPONSIBILITY,
                    evidence_type=DutyEvidenceType.DIRECT,
                    evidence_text=text,
                    verification_status=responsibility.status,
                    role_title=role_title,
                    matched_capabilities=sorted(matched),
                )
            )

            if responsibility.status is VerificationStatus.CONFIRMED:
                confirmed_experience.update(matched)
            else:
                unconfirmed_experience.update(matched)

    for skill in profile.skills:
        key = _normalize(skill.name)
        direct = _DIRECT_SKILL_CAPABILITIES.get(key, set()).intersection(
            required
        )
        supporting = _SUPPORTING_SKILL_CAPABILITIES.get(key, set()).intersection(
            required
        )

        for matched, evidence_type in (
            (direct, DutyEvidenceType.DIRECT),
            (supporting, DutyEvidenceType.SUPPORTING),
        ):
            if not matched:
                continue

            evidence.append(
                DutyEvidence(
                    source=DutyEvidenceSource.CANDIDATE_SKILL,
                    evidence_type=evidence_type,
                    evidence_text=skill.name,
                    verification_status=skill.proficiency.status,
                    candidate_skill=skill.name,
                    commercial_experience=skill.commercial_experience.value,
                    commercial_experience_status=(
                        skill.commercial_experience.status
                    ),
                    matched_capabilities=sorted(matched),
                )
            )

            if evidence_type is DutyEvidenceType.DIRECT:
                if skill.proficiency.status is VerificationStatus.CONFIRMED:
                    confirmed_direct_skills.update(matched)
                else:
                    unconfirmed_direct_skills.update(matched)
            else:
                if skill.proficiency.status is VerificationStatus.CONFIRMED:
                    confirmed_supporting_skills.update(matched)
                else:
                    unconfirmed_supporting_skills.update(matched)

    supported = (
        confirmed_experience
        | unconfirmed_experience
        | confirmed_direct_skills
        | unconfirmed_direct_skills
        | confirmed_supporting_skills
        | unconfirmed_supporting_skills
    )
    confirmed = confirmed_experience | confirmed_direct_skills
    missing = required - supported

    has_unconfirmed_evidence = bool(
        unconfirmed_experience
        or unconfirmed_direct_skills
        or unconfirmed_supporting_skills
    )

    if required.issubset(confirmed_experience):
        status = DutyMatchStatus.CONFIRMED_EXPERIENCE
        reasons = [
            "Every recognised capability is supported by a confirmed work responsibility."
        ]
    elif required.issubset(confirmed_direct_skills):
        status = DutyMatchStatus.CONFIRMED_SKILL_EVIDENCE
        reasons = [
            "Every recognised capability is covered by confirmed profile skills; "
            "this does not independently confirm the same work responsibility."
        ]
    elif required.issubset(
        confirmed_experience
        | confirmed_direct_skills
        | unconfirmed_experience
        | unconfirmed_direct_skills
    ) and has_unconfirmed_evidence:
        status = DutyMatchStatus.NEEDS_CONFIRMATION
        reasons = [
            "The duty is covered by profile evidence, but at least one "
            "work-responsibility or skill record is not confirmed."
        ]
    elif supported:
        status = DutyMatchStatus.PARTIAL
        reasons = [
            "Some recognised capabilities have supporting evidence; "
            "the full duty is not confirmed."
        ]
        if has_unconfirmed_evidence:
            reasons.append(
                "Some supporting profile statements still need confirmation."
            )
    else:
        status = DutyMatchStatus.NO_EVIDENCE
        reasons = [
            "No matching confirmed skill or experience responsibility was found."
        ]

    return JobDutyMatch(
        requirement=requirement,
        status=status,
        required_capabilities=sorted(required),
        supported_capabilities=sorted(supported),
        missing_capabilities=sorted(missing),
        evidence_coverage_percent=round(
            len(supported) / len(required) * 100,
            1,
        ),
        confirmed_evidence_coverage_percent=round(
            len(confirmed) / len(required) * 100,
            1,
        ),
        verification_needed=has_unconfirmed_evidence,
        evidence=evidence,
        reasons=reasons,
    )


def match_job_duties(
    responsibilities: list[str],
    profile: CandidateProfile,
) -> list[JobDutyMatch]:
    """Compare all extracted job responsibilities with a candidate profile."""
    return [
        match_job_duty(requirement, profile)
        for requirement in responsibilities
    ]
