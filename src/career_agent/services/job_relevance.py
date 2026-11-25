"""Deterministic relevance classification for discovered vacancies."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.domain.job_posting import JobPosting


class RelevanceStatus(StrEnum):
    RELEVANT = "relevant"
    NEEDS_REVIEW = "needs_review"
    IRRELEVANT = "irrelevant"


class RoleType(StrEnum):
    MANUAL_QA = "manual_qa"
    API_QA = "api_qa"
    INTEGRATION_QA = "integration_qa"
    QA_AUTOMATION = "qa_automation"
    SOFTWARE_QA = "software_qa"
    AI_EVALUATION = "ai_evaluation"
    LOCALIZATION_QA = "localization_qa"
    BUSINESS_PROCESS_QA = "business_process_qa"
    SYSTEM_TESTING = "system_testing"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    INTERNSHIP = "internship"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    MANAGER_EXECUTIVE = "manager_executive"
    UNKNOWN = "unknown"


class JobRelevanceAssessment(BaseModel):
    status: RelevanceStatus
    role_type: RoleType = RoleType.UNKNOWN
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    matched_roles: list[str] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


ROLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "manual_qa": re.compile(
        r"\bmanual\s+(?:qa|test(?:er|ing)?)\b",
        re.I,
    ),
    "api_qa": re.compile(
        r"\bapi[-\s]+(?:qa|test(?:ing|er)?(?:\s+engineer)?)\b"
        r"|\bapi\s+test\s+engineer\b",
        re.I,
    ),
    "integration_testing": re.compile(
        r"\bintegration[-\s]+(?:testing|tester|test engineer|qa)\b",
        re.I,
    ),
    "qa_automation": re.compile(
        r"\b(?:qa\s+automation|test\s+automation|"
        r"automation\s+tester|automation\s+qa|sdet)\b",
        re.I,
    ),
    "quality_assurance": re.compile(
        r"\bqa\b|\bquality assurance\b",
        re.I,
    ),
    "software_testing": re.compile(
        r"\b(?:software\s+)?test(?:er|ing)?\s+"
        r"(?:engineer|analyst|specialist|lead|manager)\b"
        r"|\b(?:web/app|web|mobile)\s+test\s+engineer\b"
        r"|\btester\b|\bsdet\b",
        re.I,
    ),
}

AI_EVALUATION_PATTERN = re.compile(
    r"\b(?:ai|llm)\s+(?:qa|quality assurance|evaluation|"
    r"evaluator|testing)\b"
    r"|\bllm[- ]evaluation\b"
    r"|\bai[- ]safety[- ]testing\b",
    re.I,
)

LOCALIZATION_PATTERN = re.compile(
    r"\blqa\b"
    r"|\blocali[sz]ation.{0,30}(?:qa|test|tester)"
    r"|\b(?:game|linguistic).{0,20}\blqa\b",
    re.I,
)

BUSINESS_PROCESS_PATTERN = re.compile(
    r"\b(?:proofing|internal controls|reconciliation)\b",
    re.I,
)

SYSTEM_TESTING_PATTERN = re.compile(
    r"\b(?:kernel|firmware|embedded|device driver|hardware)\b",
    re.I,
)

QA_TITLE_PATTERN = re.compile(
    r"\bqa\b|\bquality assurance\b",
    re.I,
)

STRUCTURED_TEST_SIGNALS = re.compile(
    r"\b(?:testing|test automation|software testing|"
    r"selenium|playwright|postman|quality assurance|qa)\b",
    re.I,
)

GENERIC_SOFTWARE_ROLE = re.compile(
    r"\b(?:software|backend|back-end|frontend|front-end|"
    r"full-stack|full stack|web developer|software developer|"
    r"software engineer)\b",
    re.I,
)


def _source_job(job: JobPosting) -> dict:
    payload = job.raw_payload.get("job", {})
    return payload if isinstance(payload, dict) else {}


def _metadata_values(source_job: dict) -> list[str]:
    """Collect structured categories and tags from different providers."""
    values: list[str] = []

    for key in ("category", "categories", "tags"):
        raw = source_job.get(key)

        if isinstance(raw, str):
            values.append(raw)
        elif isinstance(raw, list):
            values.extend(str(item) for item in raw if item)

    return values


def _get_seniority(title: str) -> SeniorityLevel:
    """Infer seniority from the job title only."""
    patterns = [
        (
            SeniorityLevel.MANAGER_EXECUTIVE,
            r"\b(?:vp|vice president|chief|director|head|manager)\b",
        ),
        (
            SeniorityLevel.PRINCIPAL,
            r"\b(?:principal|staff)\b",
        ),
        (
            SeniorityLevel.LEAD,
            r"\b(?:lead|team lead|tech lead)\b",
        ),
        (
            SeniorityLevel.SENIOR,
            r"\b(?:senior|sr\.?)\b",
        ),
        (
            SeniorityLevel.MIDDLE,
            r"\b(?:mid[- ]level|middle|intermediate)\b",
        ),
        (
            SeniorityLevel.JUNIOR,
            r"\b(?:junior\+?|jr\.?|entry[- ]level|associate|graduate)\b",
        ),
        (
            SeniorityLevel.INTERNSHIP,
            r"\b(?:intern(?:ship)?|trainee)\b",
        ),
    ]

    for level, pattern in patterns:
        if re.search(pattern, title, re.I):
            return level

    return SeniorityLevel.UNKNOWN


def _assessment(
    status: RelevanceStatus,
    role_type: RoleType,
    seniority: SeniorityLevel,
    reason: str,
    signals: list[str] | None = None,
    matched_roles: list[str] | None = None,
) -> JobRelevanceAssessment:
    return JobRelevanceAssessment(
        status=status,
        role_type=role_type,
        seniority=seniority,
        matched_roles=matched_roles or [],
        matched_signals=signals or [],
        reasons=[reason],
    )


def assess_job_relevance(job: JobPosting) -> JobRelevanceAssessment:
    """Classify a vacancy by professional direction and seniority.

    Specialised QA-adjacent roles are kept separate from conventional
    software QA. The description is not used as a primary signal.
    """

    title = job.title.strip()
    source_job = _source_job(job)
    seniority = _get_seniority(title)

    if seniority is SeniorityLevel.UNKNOWN:
        seniority = _get_seniority(job.experience_level or "")

    if seniority is SeniorityLevel.UNKNOWN:
        seniority = _get_seniority(job.employment_type or "")

    metadata = _metadata_values(source_job)

    # 1. Specialised directions: these are not conventional software QA.
    if AI_EVALUATION_PATTERN.search(title):
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.AI_EVALUATION,
            seniority,
            "AI/LLM evaluation is adjacent to QA but differs from conventional software testing.",
            ["title:ai_evaluation"],
        )

    if LOCALIZATION_PATTERN.search(title):
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.LOCALIZATION_QA,
            seniority,
            "Localization testing is a specialised QA direction.",
            ["title:localization_qa"],
        )

    if (
        BUSINESS_PROCESS_PATTERN.search(title)
        and QA_TITLE_PATTERN.search(title)
    ):
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.BUSINESS_PROCESS_QA,
            seniority,
            "The title indicates business-process or operational quality control.",
            ["title:business_process_qa"],
        )

    if (
        SYSTEM_TESTING_PATTERN.search(title)
        and re.search(r"\b(?:test|testing|tester|qa)\b", title, re.I)
    ):
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.SYSTEM_TESTING,
            seniority,
            "Specialised hardware, kernel or embedded-system testing requires separate evaluation.",
            ["title:system_testing"],
        )

    # 2. Explicit software QA roles.
    matched_roles = [
        role
        for role, pattern in ROLE_PATTERNS.items()
        if pattern.search(title)
    ]

    if matched_roles:
        if "api_qa" in matched_roles:
            role_type = RoleType.API_QA
        elif "integration_testing" in matched_roles:
            role_type = RoleType.INTEGRATION_QA
        elif "manual_qa" in matched_roles:
            role_type = RoleType.MANUAL_QA
        elif "qa_automation" in matched_roles:
            role_type = RoleType.QA_AUTOMATION
        else:
            role_type = RoleType.SOFTWARE_QA

        return _assessment(
            RelevanceStatus.RELEVANT,
            role_type,
            seniority,
            "The job title explicitly identifies a software QA or testing role.",
            [f"title:{role}" for role in matched_roles],
            matched_roles,
        )

    # 3. Structured provider metadata can trigger manual review.
    metadata_text = " ".join(metadata).casefold()
    normalized_metadata = re.sub(r"[-_/]+", " ", metadata_text)

    has_qa_metadata = bool(
        re.search(r"\bqa\b|quality assurance", normalized_metadata)
    )
    has_testing_metadata = bool(
        STRUCTURED_TEST_SIGNALS.search(normalized_metadata)
    )

    if has_qa_metadata:
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.SOFTWARE_QA,
            seniority,
            "Provider categories or tags indicate QA, but the job title is ambiguous.",
            ["metadata:qa"],
        )

    if has_testing_metadata and GENERIC_SOFTWARE_ROLE.search(title):
        return _assessment(
            RelevanceStatus.NEEDS_REVIEW,
            RoleType.UNKNOWN,
            seniority,
            "Testing-related metadata was found, but the title describes a broader software role.",
            ["metadata:testing"],
        )

    return _assessment(
        RelevanceStatus.IRRELEVANT,
        RoleType.UNKNOWN,
        seniority,
        "No sufficiently strong QA or software-testing signal was found.",
    )
