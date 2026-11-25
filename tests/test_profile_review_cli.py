from pathlib import Path

from career_agent.domain.fields import VerificationStatus
from career_agent.main import build_parser, main
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def make_profile_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "candidate_profile.json"
    destination.write_bytes(EXAMPLE_PROFILE.read_bytes())
    return destination


def set_answers(monkeypatch, answers: list[str]) -> None:
    iterator = iter(answers)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: next(iterator),
    )


def test_review_saves_answers_and_quits_cleanly(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    path = make_profile_copy(tmp_path)
    original = ProfileService().load(path)
    first_skill_name = original.skills[0].name

    set_answers(monkeypatch, ["3", "2", "q"])

    result = main(["profile", "review", "--path", str(path)])

    output = capsys.readouterr().out
    saved = ProfileService().load(path)
    first_skill = next(
        skill for skill in saved.skills if skill.name == first_skill_name
    )

    assert result == 0
    assert first_skill.proficiency.value == "intermediate"
    assert first_skill.proficiency.status is VerificationStatus.CONFIRMED
    assert first_skill.commercial_experience.value is False
    assert (
        first_skill.commercial_experience.status
        is VerificationStatus.CONFIRMED
    )
    assert "Опрос остановлен" in output
    assert "сохран" in output.lower()


def test_skipped_field_remains_pending_and_can_be_reviewed_later(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = make_profile_copy(tmp_path)
    original = ProfileService().load(path)
    first_skill_name = original.skills[0].name

    set_answers(monkeypatch, ["s", "1", "q"])
    result = main(["profile", "review", "--path", str(path)])

    assert result == 0

    saved = ProfileService().load(path)
    first_skill = next(
        skill for skill in saved.skills if skill.name == first_skill_name
    )

    assert first_skill.proficiency.status is VerificationStatus.UNKNOWN
    assert first_skill.commercial_experience.value is True
    assert (
        first_skill.commercial_experience.status
        is VerificationStatus.CONFIRMED
    )

    set_answers(monkeypatch, ["4", "q"])
    result = main(["profile", "review", "--path", str(path)])

    assert result == 0

    saved_again = ProfileService().load(path)
    reviewed_skill = next(
        skill for skill in saved_again.skills if skill.name == first_skill_name
    )

    assert reviewed_skill.proficiency.value == "proficient"
    assert reviewed_skill.proficiency.status is VerificationStatus.CONFIRMED


def test_review_can_complete_all_skills(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = make_profile_copy(tmp_path)
    profile = ProfileService().load(path)

    answers: list[str] = []

    for skill in profile.skills:
        if skill.proficiency.status is not VerificationStatus.CONFIRMED:
            answers.append("3")

        if (
            skill.commercial_experience.status
            is not VerificationStatus.CONFIRMED
        ):
            answers.append("1")

    set_answers(monkeypatch, answers)

    result = main(["profile", "review", "--path", str(path)])

    assert result == 0

    saved = ProfileService().load(path)

    assert all(
        skill.proficiency.status is VerificationStatus.CONFIRMED
        and skill.commercial_experience.status
        is VerificationStatus.CONFIRMED
        for skill in saved.skills
    )


def test_review_command_is_registered() -> None:
    args = build_parser().parse_args(["profile", "review"])

    assert args.command == "profile"
    assert args.profile_command == "review"
    assert args.path is None
