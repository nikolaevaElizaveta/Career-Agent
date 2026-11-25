from pathlib import Path

from career_agent.cli.profile import format_profile_skills
from career_agent.main import main
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def test_formatter_displays_candidate_skills() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)

    result = format_profile_skills(profile)

    assert "Candidate skills:" in result
    assert "[TESTING]" in result
    assert "Manual testing" in result
    assert "Postman" in result
    assert "Python" in result


def test_formatter_displays_unknown_statuses() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)

    result = format_profile_skills(profile)

    assert "unknown:" in result
    assert "proficiency: not provided [unknown]" in result
    assert "commercial experience: not provided [unknown]" in result


def test_formatter_does_not_change_profile() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    before = profile.model_dump(mode="json")

    format_profile_skills(profile)

    assert profile.model_dump(mode="json") == before


def test_formatter_handles_empty_skill_list() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    profile.skills = []

    assert (
        format_profile_skills(profile)
        == "No skills found in Candidate Profile."
    )


def test_profile_skills_cli_exits_zero(capsys) -> None:
    result = main([
        "profile",
        "skills",
        "--path",
        str(EXAMPLE_PROFILE),
    ])

    captured = capsys.readouterr()

    assert result == 0
    assert "Candidate skills:" in captured.out
    assert "Postman" in captured.out


def test_profile_skills_cli_does_not_modify_profile_file(capsys) -> None:
    before = EXAMPLE_PROFILE.read_bytes()

    result = main([
        "profile",
        "skills",
        "--path",
        str(EXAMPLE_PROFILE),
    ])

    capsys.readouterr()

    assert result == 0
    assert EXAMPLE_PROFILE.read_bytes() == before


def test_profile_skills_cli_reports_missing_file(tmp_path: Path, capsys) -> None:
    missing_path = tmp_path / "missing-profile.json"

    result = main([
        "profile",
        "skills",
        "--path",
        str(missing_path),
    ])

    captured = capsys.readouterr()

    assert result == 1
    assert "Profile file was not found" in captured.err


def test_profile_skills_command_is_registered() -> None:
    from career_agent.main import build_parser

    args = build_parser().parse_args(["profile", "skills"])

    assert args.command == "profile"
    assert args.profile_command == "skills"
