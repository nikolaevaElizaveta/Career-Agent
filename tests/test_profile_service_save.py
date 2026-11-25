import json
from pathlib import Path

import pytest

from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"


def test_save_creates_valid_profile_json(tmp_path: Path) -> None:
    service = ProfileService()
    profile = service.load(EXAMPLE_PROFILE)
    destination = tmp_path / "candidate_profile.json"

    service.save(profile, destination)

    saved_profile = service.load(destination)

    assert saved_profile.model_dump(mode="json") == profile.model_dump(
        mode="json"
    )
    assert json.loads(destination.read_text(encoding="utf-8")) == (
        profile.model_dump(mode="json")
    )


def test_save_replaces_existing_file(tmp_path: Path) -> None:
    service = ProfileService()
    profile = service.load(EXAMPLE_PROFILE)
    destination = tmp_path / "candidate_profile.json"
    destination.write_text("old content", encoding="utf-8")

    service.save(profile, destination)

    assert service.load(destination).model_dump(mode="json") == (
        profile.model_dump(mode="json")
    )


def test_save_preserves_original_file_if_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ProfileService()
    profile = service.load(EXAMPLE_PROFILE)
    destination = tmp_path / "candidate_profile.json"
    original_content = '{"original": true}\n'
    destination.write_text(original_content, encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("Simulated replacement failure")

    monkeypatch.setattr(
        "career_agent.services.profile_service.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="Simulated replacement failure"):
        service.save(profile, destination)

    assert destination.read_text(encoding="utf-8") == original_content
    assert list(tmp_path.iterdir()) == [destination]
