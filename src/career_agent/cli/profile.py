"""CLI formatting helpers for Candidate Profile."""

from __future__ import annotations

from collections import Counter

from career_agent.domain.candidate import CandidateProfile
from career_agent.domain.fields import VerificationStatus


def _display_value(value: object) -> str:
    if value is None:
        return "not provided"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def format_profile_skills(profile: CandidateProfile) -> str:
    """Display profile skills and their verification statuses without mutation."""
    skills = sorted(
        profile.skills,
        key=lambda item: (item.category.casefold(), item.name.casefold()),
    )

    if not skills:
        return "No skills found in Candidate Profile."

    proficiency_counts = Counter(
        item.proficiency.status for item in skills
    )
    commercial_counts = Counter(
        item.commercial_experience.status for item in skills
    )

    lines = [
        f"Candidate skills: {len(skills)}",
        "",
        "PROFICIENCY STATUS:",
    ]

    for status in VerificationStatus:
        lines.append(
            f"- {status.value}: {proficiency_counts[status]}"
        )

    lines.extend(["", "COMMERCIAL EXPERIENCE STATUS:"])

    for status in VerificationStatus:
        lines.append(
            f"- {status.value}: {commercial_counts[status]}"
        )

    lines.append("")

    current_category = None

    for skill in skills:
        if skill.category != current_category:
            current_category = skill.category
            lines.extend([
                "",
                f"[{current_category.upper()}]",
            ])

        proficiency = skill.proficiency
        commercial = skill.commercial_experience

        lines.append(
            f"- {skill.name} | "
            f"proficiency: {_display_value(proficiency.value)} "
            f"[{proficiency.status.value}] | "
            f"commercial experience: "
            f"{_display_value(commercial.value)} "
            f"[{commercial.status.value}]"
        )

    return "\n".join(lines)
