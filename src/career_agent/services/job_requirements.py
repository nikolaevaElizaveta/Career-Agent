"""Deterministic extraction of skills and qualifications from job descriptions."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from career_agent.services.job_description import clean_job_description


class RequirementPriority(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNSPECIFIED = "unspecified"


class DescriptionSection(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    RESPONSIBILITIES = "responsibilities"
    OTHER = "other"


class SkillRequirement(BaseModel):
    name: str
    priority: RequirementPriority
    evidence: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)


class SkillAlternativeGroup(BaseModel):
    skills: list[str]
    match_rule: str = "any_of"
    priority: RequirementPriority
    evidence: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)


class ExperienceRequirement(BaseModel):
    min_years: float
    max_years: float | None = None
    area: str | None = None
    priority: RequirementPriority
    evidence: str


class EducationRequirement(BaseModel):
    priority: RequirementPriority
    evidence: str


class JobRequirements(BaseModel):
    required_skills: list[SkillRequirement] = Field(default_factory=list)
    preferred_skills: list[SkillRequirement] = Field(default_factory=list)
    unspecified_skills: list[SkillRequirement] = Field(default_factory=list)
    alternative_skill_groups: list[SkillAlternativeGroup] = Field(
        default_factory=list
    )
    experience_requirements: list[ExperienceRequirement] = Field(
        default_factory=list
    )
    education_requirements: list[EducationRequirement] = Field(
        default_factory=list
    )
    responsibilities: list[str] = Field(default_factory=list)


_SKILL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Postman", re.compile(r"\bPostman\b", re.I)),
    ("Selenium", re.compile(r"\bSelenium\b", re.I)),
    ("Playwright", re.compile(r"\bPlaywright\b", re.I)),
    ("Appium", re.compile(r"\bAppium\b", re.I)),
    ("MySQL", re.compile(r"\bMySQL\b", re.I)),
    ("PostgreSQL", re.compile(r"\bPostgreSQL\b", re.I)),
    ("Kafka", re.compile(r"\bKafka\b", re.I)),
    ("Git", re.compile(r"\bGit\b", re.I)),
    ("Docker", re.compile(r"\bDocker\b", re.I)),
    ("Linux", re.compile(r"\bLinux\b", re.I)),
    ("Grafana", re.compile(r"\bGrafana\b", re.I)),
    ("Python", re.compile(r"\bPython\b", re.I)),
    ("JavaScript", re.compile(r"\bJavaScript\b|\bJS\b", re.I)),
    ("Java", re.compile(r"\bJava\b", re.I)),
    (
        "Go",
        re.compile(
            r"\bGolang\b|\bGo(?=\s*(?:[/,;.)]|$|\band\b|\bor\b))",
            re.I,
        ),
    ),
    ("SQL", re.compile(r"(?<![A-Za-z])SQL(?![A-Za-z])", re.I)),
    ("HTML", re.compile(r"\bHTML\b", re.I)),
    ("CSS", re.compile(r"\bCSS\b", re.I)),
    ("Android", re.compile(r"\bAndroid\b", re.I)),
    ("iOS", re.compile(r"\biOS\b", re.I)),
    (
        "API testing",
        re.compile(
            r"\bAPI(?:\s*/\s*API)?\s+"
            r"(?:(?:automated|manual)\s+)?tests?\b"
            r"|\bAPI testing\b",
            re.I,
        ),
    ),
    (
        "Test automation",
        re.compile(
            r"\b(?:test|testing)\s+automation\b"
            r"|\bautomation\s+testing\b"
            r"|\bautomated\s+tests?\b"
            r"|\bautomated\s+testing\b",
            re.I,
        ),
    ),
    ("Manual testing", re.compile(r"\bmanual\s+(?:testing|tests?|QA)\b", re.I)),
    ("Functional testing", re.compile(r"\bfunctional\s+testing\b", re.I)),
    ("Regression testing", re.compile(r"\bregression\s+testing\b", re.I)),
    ("Acceptance testing", re.compile(r"\bacceptance\s+testing\b", re.I)),
    ("Exploratory testing", re.compile(r"\bexploratory\s+testing\b", re.I)),
    ("Performance testing", re.compile(r"\bperformance\s+testing\b", re.I)),
    (
        "Cross-browser testing",
        re.compile(r"\bcross[- ]browser\s+testing\b", re.I),
    ),
    (
        "Test cases and test plans",
        re.compile(r"\btest\s+(?:cases?|plans?)\b", re.I),
    ),
    ("Test documentation", re.compile(r"\btest\s+documentation\b", re.I)),
    (
        "Requirements analysis",
        re.compile(
            r"\b(?:analy[sz]ing\s+requirements|requirements?\s+analysis)\b",
            re.I,
        ),
    ),
    (
        "Defect reporting and tracking",
        re.compile(r"\b(?:reporting\s+defects?|bug\s+tracking)\b", re.I),
    ),
    ("Root cause analysis", re.compile(r"\broot\s+cause\s+analysis\b", re.I)),
    (
        "AI-assisted testing",
        re.compile(
            r"\bAI[- ]assisted testing\b"
            r"|\bAI tools? (?:in|for) testing\b"
            r"|\bAI tools? to (?:enhance|improve|support) testing\b",
            re.I,
        ),
    ),
    (
        "AI familiarity",
        re.compile(r"\b(?:familiarity with|familiar with)\s+AI\b", re.I),
    ),
]


_REQUIRED_HEADINGS = {
    "requirements",
    "what makes you a great fit",
    "who may apply",
    "who we are looking for",
    "what we are looking for",
    "what we're looking for",
    "minimum qualifications",
    "basic qualifications",
    "qualifications",
    "ideal candidate profile",
    "candidate profile",
    "skills & competencies",
    "background",
    "core competencies",
    "what you bring",
}

_PREFERRED_HEADINGS = {
    "bonus skills",
    "your bonus skills",
    "nice to have",
    "nice-to-have",
    "preferred qualifications",
    "preferred skills",
    "preferred experience / skills",
    "good to have",
    "desirable skills",
}

_RESPONSIBILITY_HEADINGS = {
    "responsibilities",
    "key responsibilities",
    "your responsibilities",
    "what you will do",
    "what you'll do",
    "challenges that await you",
    "duties",
    "day to day",
}

_OTHER_HEADINGS = {
    "about",
    "about us",
    "why us",
    "why join us",
    "why binance",
    "benefits",
    "our benefits",
    "our ways of working",
    "what we offer",
    "equal opportunity",
    "terms",
    "how to apply",
    "application process",
    "application instructions",
}

_PREFERRED_CUES = re.compile(
    r"\b(?:preferred|preferably|bonus|desirable|"
    r"nice to have|good to have|is a plus|would be a plus)\b",
    re.I,
)

_ALTERNATIVE_CLAUSES = [
    re.compile(r"\bat least one of\s+(?P<items>[^.;]+)", re.I),
    re.compile(r"\bprogramming experience in\s+(?P<items>[^.;]+)", re.I),
    re.compile(r"\busing\s+(?P<items>[^.;]+)", re.I),
    re.compile(r"\btools?\s+such\s+as\s+(?P<items>[^.;]+)", re.I),
]

_RANGE_EXPERIENCE = re.compile(
    r"\b(?P<minimum>\d+(?:\.\d+)?)\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)\s+years?\b"
    r"(?P<tail>[^.!?]*)",
    re.I,
)

_MINIMUM_EXPERIENCE = re.compile(
    r"\b(?:minimum|min\.?)\s+"
    r"(?P<years>\d+(?:\.\d+)?)\s*\+\s*years?\b"
    r"(?P<tail>[^.!?]*)",
    re.I,
)

_AT_LEAST_EXPERIENCE = re.compile(
    r"\bat least\s+(?P<years>\d+(?:\.\d+)?)\s+years?\b"
    r"(?P<tail>[^.!?]*)",
    re.I,
)

_SINGLE_EXPERIENCE = re.compile(
    r"(?<![\d–—-])\b(?P<years>\d+(?:\.\d+)?)\s+years?\b"
    r"(?P<tail>[^.!?]*)",
    re.I,
)

# Only explicit academic qualifications count as education requirements.
_EDUCATION_PATTERN = re.compile(
    r"\b(?:undergraduate|postgraduate|bachelor'?s?|master'?s?|"
    r"ph\.?d\.?|bsc|msc|degree|university student|college student)\b",
    re.I,
)


def _normalize_heading(line: str) -> str:
    value = line.strip().lstrip("•").strip().casefold()
    return value.rstrip(" :")


def _detect_section(line: str) -> DescriptionSection | None:
    if len(line) > 80:
        return None

    heading = _normalize_heading(line)

    if heading in _RESPONSIBILITY_HEADINGS:
        return DescriptionSection.RESPONSIBILITIES

    if heading in _PREFERRED_HEADINGS:
        return DescriptionSection.PREFERRED

    if heading in _REQUIRED_HEADINGS:
        return DescriptionSection.REQUIRED

    if heading in _OTHER_HEADINGS:
        return DescriptionSection.OTHER

    return None


def _priority_for_line(
    section: DescriptionSection,
    line: str,
) -> RequirementPriority:
    if _PREFERRED_CUES.search(line):
        return RequirementPriority.PREFERRED

    if section is DescriptionSection.REQUIRED:
        return RequirementPriority.REQUIRED

    if section is DescriptionSection.PREFERRED:
        return RequirementPriority.PREFERRED

    return RequirementPriority.UNSPECIFIED


def _matched_skill_names(text: str) -> list[str]:
    return [
        name
        for name, pattern in _SKILL_PATTERNS
        if pattern.search(text)
    ]


def _find_alternative_groups(
    line: str,
    priority: RequirementPriority,
    section: DescriptionSection,
) -> list[SkillAlternativeGroup]:
    groups: list[SkillAlternativeGroup] = []

    for pattern in _ALTERNATIVE_CLAUSES:
        for match in pattern.finditer(line):
            skills = _matched_skill_names(match.group("items"))

            if len(skills) < 2:
                continue

            group = SkillAlternativeGroup(
                skills=skills,
                match_rule="any_of",
                priority=priority,
                evidence=[line],
                sections=[section.value],
            )

            if not any(
                item.skills == group.skills
                and item.evidence == group.evidence
                for item in groups
            ):
                groups.append(group)

    return groups


def _find_skills(
    lines: list[tuple[str, DescriptionSection]],
) -> tuple[list[SkillRequirement], list[SkillAlternativeGroup]]:
    grouped: dict[str, dict] = {}
    alternative_groups: list[SkillAlternativeGroup] = []
    priority_rank = {
        RequirementPriority.UNSPECIFIED: 0,
        RequirementPriority.PREFERRED: 1,
        RequirementPriority.REQUIRED: 2,
    }

    for line, section in lines:
        if section is DescriptionSection.OTHER:
            continue

        priority = _priority_for_line(section, line)
        groups = _find_alternative_groups(line, priority, section)
        alternative_groups.extend(groups)

        alternative_names = {
            name
            for group in groups
            for name in group.skills
        }

        for name in _matched_skill_names(line):
            # Alternative skills are represented by their group, not as
            # individually mandatory requirements.
            if name in alternative_names:
                continue

            entry = grouped.setdefault(
                name,
                {
                    "priority": priority,
                    "evidence": [],
                    "sections": [],
                },
            )

            if (
                priority_rank[priority]
                > priority_rank[entry["priority"]]
            ):
                entry["priority"] = priority

            if line not in entry["evidence"]:
                entry["evidence"].append(line)

            if section.value not in entry["sections"]:
                entry["sections"].append(section.value)

    results = [
        SkillRequirement(
            name=name,
            priority=data["priority"],
            evidence=data["evidence"],
            sections=data["sections"],
        )
        for name, data in grouped.items()
    ]
    results.sort(key=lambda item: item.name.casefold())

    # Merge repeated groups and retain all supporting evidence.
    unique_groups: dict[tuple[str, ...], SkillAlternativeGroup] = {}

    for group in alternative_groups:
        key = tuple(sorted(group.skills))
        existing = unique_groups.get(key)

        if existing is None:
            unique_groups[key] = group
            continue

        priority_rank = {
            RequirementPriority.UNSPECIFIED: 0,
            RequirementPriority.PREFERRED: 1,
            RequirementPriority.REQUIRED: 2,
        }

        if priority_rank[group.priority] > priority_rank[existing.priority]:
            existing.priority = group.priority

        for evidence in group.evidence:
            if evidence not in existing.evidence:
                existing.evidence.append(evidence)

        for section in group.sections:
            if section not in existing.sections:
                existing.sections.append(section)

    return results, list(unique_groups.values())


def _clean_experience_area(tail: str) -> str | None:
    area = tail.strip(" ,;:-")
    area = re.sub(r"^of\s+", "", area, flags=re.I)
    area = re.sub(r"^experience\s+(?:in|with)\s+", "", area, flags=re.I)
    area = re.sub(r"^experience\s+", "", area, flags=re.I)
    area = re.sub(r"^in\s+", "", area, flags=re.I)
    area = re.sub(r"^(?:a|an|the)\s+", "", area, flags=re.I)
    area = re.split(r",|\bincluding\b", area, maxsplit=1, flags=re.I)[0]
    area = re.sub(r"\s+experience$", "", area, flags=re.I)
    area = area.strip(" ,;:-")
    return area or None


def _find_experience(
    lines: list[tuple[str, DescriptionSection]],
) -> list[ExperienceRequirement]:
    results: list[ExperienceRequirement] = []

    for line, section in lines:
        if section is DescriptionSection.OTHER:
            continue

        priority = _priority_for_line(section, line)
        occupied: list[tuple[int, int]] = []

        for match in _RANGE_EXPERIENCE.finditer(line):
            occupied.append(match.span())
            results.append(
                ExperienceRequirement(
                    min_years=float(match.group("minimum")),
                    max_years=float(match.group("maximum")),
                    area=_clean_experience_area(match.group("tail")),
                    priority=priority,
                    evidence=line,
                )
            )

        for match in _MINIMUM_EXPERIENCE.finditer(line):
            occupied.append(match.span())
            results.append(
                ExperienceRequirement(
                    min_years=float(match.group("years")),
                    max_years=None,
                    area=_clean_experience_area(match.group("tail")),
                    priority=priority,
                    evidence=line,
                )
            )

        for match in _AT_LEAST_EXPERIENCE.finditer(line):
            occupied.append(match.span())
            results.append(
                ExperienceRequirement(
                    min_years=float(match.group("years")),
                    max_years=None,
                    area=_clean_experience_area(match.group("tail")),
                    priority=priority,
                    evidence=line,
                )
            )

        for match in _SINGLE_EXPERIENCE.finditer(line):
            if any(start <= match.start() < end for start, end in occupied):
                continue

            results.append(
                ExperienceRequirement(
                    min_years=float(match.group("years")),
                    max_years=float(match.group("years")),
                    area=_clean_experience_area(match.group("tail")),
                    priority=priority,
                    evidence=line,
                )
            )

    unique: dict[tuple, ExperienceRequirement] = {}
    for item in results:
        key = (item.min_years, item.max_years, item.area, item.evidence)
        unique[key] = item

    return list(unique.values())


def extract_job_requirements(description: str | None) -> JobRequirements:
    """Extract skills, responsibilities and qualifications with source evidence."""
    text = clean_job_description(description)

    if not text:
        return JobRequirements()

    current_section = DescriptionSection.OTHER
    classified_lines: list[tuple[str, DescriptionSection]] = []
    responsibilities: list[str] = []
    education_requirements: list[EducationRequirement] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        detected = _detect_section(line)
        if detected is not None:
            current_section = detected
            continue

        line = re.sub(r"^•\s*", "", line).strip()
        if not line:
            continue

        classified_lines.append((line, current_section))

        if current_section is DescriptionSection.RESPONSIBILITIES:
            if line not in responsibilities:
                responsibilities.append(line)

        if (
            current_section
            in {DescriptionSection.REQUIRED, DescriptionSection.PREFERRED}
            and _EDUCATION_PATTERN.search(line)
        ):
            education_requirements.append(
                EducationRequirement(
                    priority=_priority_for_line(current_section, line),
                    evidence=line,
                )
            )

    skills, alternative_groups = _find_skills(classified_lines)
    experience = _find_experience(classified_lines)

    return JobRequirements(
        required_skills=[
            item for item in skills
            if item.priority is RequirementPriority.REQUIRED
        ],
        preferred_skills=[
            item for item in skills
            if item.priority is RequirementPriority.PREFERRED
        ],
        unspecified_skills=[
            item for item in skills
            if item.priority is RequirementPriority.UNSPECIFIED
        ],
        alternative_skill_groups=alternative_groups,
        experience_requirements=experience,
        education_requirements=education_requirements,
        responsibilities=responsibilities,
    )
