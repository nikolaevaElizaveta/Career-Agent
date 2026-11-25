"""Explicit user confirmation of candidate skill information."""

from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import VerificationStatus

SKILL_PROFICIENCY_LEVELS = frozenset({
    "beginner",
    "basic",
    "intermediate",
    "proficient",
})


class SkillReviewService:
    """Update skill information only from explicit user answers."""

    def confirm_proficiency(self, skill: SkillItem, level: str) -> None:
        if level not in SKILL_PROFICIENCY_LEVELS:
            raise ValueError(
                f"Unsupported proficiency level: {level}"
            )

        skill.proficiency.value = level
        skill.proficiency.status = VerificationStatus.CONFIRMED
        skill.proficiency.note = None

    def confirm_commercial_experience(
        self,
        skill: SkillItem,
        has_experience: bool,
    ) -> None:
        if not isinstance(has_experience, bool):
            raise TypeError("Commercial experience must be a boolean.")

        skill.commercial_experience.value = has_experience
        skill.commercial_experience.status = VerificationStatus.CONFIRMED
        skill.commercial_experience.note = None
