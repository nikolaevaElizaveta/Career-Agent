"""Interactive review of candidate skills."""

from collections.abc import Callable
from pathlib import Path

from career_agent.domain.candidate import CandidateProfile, SkillItem
from career_agent.domain.fields import VerificationStatus
from career_agent.services.profile_service import ProfileService
from career_agent.services.skill_review_service import SkillReviewService

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]

PROFICIENCY_LABELS = {
    "1": ("beginner", "Начальный"),
    "2": ("basic", "Базовый"),
    "3": ("intermediate", "Средний"),
    "4": ("proficient", "Уверенный"),
}


def _is_pending(skill: SkillItem) -> bool:
    return (
        skill.proficiency.status is not VerificationStatus.CONFIRMED
        or skill.commercial_experience.status is not VerificationStatus.CONFIRMED
    )


def _pending_field_count(skills: list[SkillItem]) -> int:
    count = 0

    for skill in skills:
        if skill.proficiency.status is not VerificationStatus.CONFIRMED:
            count += 1
        if (
            skill.commercial_experience.status
            is not VerificationStatus.CONFIRMED
        ):
            count += 1

    return count


def _ask_choice(
    question: str,
    options: dict[str, str],
    input_fn: InputFunction,
    output_fn: OutputFunction,
) -> str:
    output_fn(question)

    for key, label in options.items():
        output_fn(f"  {key}. {label}")

    output_fn("  s. Пропустить этот вопрос")
    output_fn("  q. Сохранить ответы и выйти")

    while True:
        try:
            answer = input_fn("Ваш выбор: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            output_fn("")
            return "q"

        if answer in options:
            return answer

        if answer in {"s", "q"}:
            return answer

        output_fn("Неизвестный вариант. Выбери один из предложенных.")


def _save_answer(
    service: ProfileService,
    path: Path,
    profile: CandidateProfile,
    output_fn: OutputFunction,
) -> bool:
    try:
        service.save(profile, path)
    except (OSError, TypeError, ValueError) as exc:
        output_fn(f"Ошибка сохранения профиля: {exc}")
        return False

    output_fn("Ответ сохранён.")
    return True


def run_profile_review(
    path: Path,
    input_fn: InputFunction | None = None,
    output_fn: OutputFunction | None = None,
) -> int:
    """Review pending skill fields and persist every confirmed answer."""
    reader = input if input_fn is None else input_fn
    writer = print if output_fn is None else output_fn

    profile_service = ProfileService()
    review_service = SkillReviewService()

    report, profile = profile_service.validate_path(path)

    if profile is None:
        writer(profile_service.format_report(report))
        return 1

    if not report.valid:
        writer(
            "Warning: Candidate Profile has validation issues. "
            "The skill review can continue, but review the profile afterwards."
        )

    pending_skills = [skill for skill in profile.skills if _is_pending(skill)]
    initial_pending = _pending_field_count(profile.skills)

    if initial_pending == 0:
        writer("Все поля навыков уже подтверждены.")
        return 0

    writer(f"Навыков, требующих проверки: {len(pending_skills)}")
    writer(f"Полей, требующих подтверждения: {initial_pending}")
    confirmed_this_run = 0
    should_quit = False

    for index, skill in enumerate(pending_skills, start=1):
        writer("")
        writer(f"[{index}/{len(pending_skills)}] {skill.name} ({skill.category})")

        if skill.proficiency.status is not VerificationStatus.CONFIRMED:
            answer = _ask_choice(
                "Как оцениваешь свой уровень владения?",
                {
                    key: label
                    for key, (_value, label) in PROFICIENCY_LABELS.items()
                },
                reader,
                writer,
            )

            if answer == "q":
                should_quit = True
                break

            if answer in PROFICIENCY_LABELS:
                value, _label = PROFICIENCY_LABELS[answer]
                review_service.confirm_proficiency(skill, value)

                if not _save_answer(profile_service, path, profile, writer):
                    return 1

                confirmed_this_run += 1

        if (
            skill.commercial_experience.status
            is not VerificationStatus.CONFIRMED
        ):
            answer = _ask_choice(
                "Использовала ли ты этот навык в коммерческой работе?",
                {
                    "1": "Да",
                    "2": "Нет",
                },
                reader,
                writer,
            )

            if answer == "q":
                should_quit = True
                break

            if answer in {"1", "2"}:
                review_service.confirm_commercial_experience(
                    skill,
                    answer == "1",
                )

                if not _save_answer(profile_service, path, profile, writer):
                    return 1

                confirmed_this_run += 1

    remaining = _pending_field_count(profile.skills)

    writer("")
    writer(f"Подтверждено полей за этот запуск: {confirmed_this_run}")
    writer(f"Осталось полей для проверки: {remaining}")

    if should_quit:
        writer("Опрос остановлен. Все введённые ответы сохранены.")
    elif remaining == 0:
        writer("Проверка навыков завершена.")
    else:
        writer("Неподтверждённые поля можно проверить при следующем запуске.")

    return 0
