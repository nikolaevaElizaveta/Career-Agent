from pathlib import Path

import pytest

from career_agent.domain.fields import VerificationStatus
from career_agent.services.profile_service import ProfileService
from career_agent.services.skill_review_service import (
    SKILL_PROFICIENCY_LEVELS,
    SkillReviewService,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def get_postman_skill():
    profile = ProfileService().load(EXAMPLE_PROFILE)
    return next(skill for skill in profile.skills if skill.name == "Postman")


@pytest.mark.parametrize("level", sorted(SKILL_PROFICIENCY_LEVELS))
def test_confirm_proficiency(level: str) -> None:
    skill = get_postman_skill()
    service = SkillReviewService()

    service.confirm_proficiency(skill, level)

    assert skill.proficiency.value == level
    assert skill.proficiency.status is VerificationStatus.CONFIRMED
    assert skill.proficiency.note is None


def test_confirm_proficiency_rejects_unsupported_level() -> None:
    skill = get_postman_skill()
    service = SkillReviewService()

    with pytest.raises(ValueError, match="Unsupported proficiency level"):
        service.confirm_proficiency(skill, "expert")

    assert skill.proficiency.value is None
    assert skill.proficiency.status is VerificationStatus.UNKNOWN


@pytest.mark.parametrize("has_experience", [True, False])
def test_confirm_commercial_experience(has_experience: bool) -> None:
    skill = get_postman_skill()
    service = SkillReviewService()

    service.confirm_commercial_experience(skill, has_experience)

    assert skill.commercial_experience.value is has_experience
    assert (
        skill.commercial_experience.status
        is VerificationStatus.CONFIRMED
    )
    assert skill.commercial_experience.note is None


def test_confirm_commercial_experience_rejects_non_boolean() -> None:
    skill = get_postman_skill()
    service = SkillReviewService()

    with pytest.raises(TypeError, match="must be a boolean"):
        service.confirm_commercial_experience(skill, "yes")

    assert skill.commercial_experience.value is None
    assert skill.commercial_experience.status is VerificationStatus.UNKNOWN
