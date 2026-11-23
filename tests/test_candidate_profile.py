from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_agent.domain.dates import DatePrecision, PartialDate
from career_agent.domain.fields import VerificationStatus
from career_agent.main import main
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
PRIVATE_PROFILE = ROOT / "data" / "candidate_profile.json"


def test_example_profile_confirms_innotech_month() -> None:
    service = ProfileService()
    report, profile = service.validate_path(EXAMPLE_PROFILE)

    assert profile is not None
    assert report.schema_ok is True
    assert report.valid is True
    assert report.missing_required == []
    assert report.needs_confirmation == []

    innotech = next(
        item for item in profile.experience if item.company.value == "Innotech"
    )
    assert innotech.start_date.status is VerificationStatus.CONFIRMED
    assert innotech.start_date.value == PartialDate(
        year=2026, month=3, precision=DatePrecision.MONTH
    )
    assert innotech.start_date.value.day is None
    assert innotech.start_date.value.as_text() == "2026-03"
    assert not any("start_date" in issue.path for issue in report.needs_confirmation)


def test_confirmed_month_is_exported_without_a_day() -> None:
    service = ProfileService()
    profile = service.load(EXAMPLE_PROFILE)
    facts = service.facts_for_documents(profile)

    innotech = next(
        item for item in facts["experience"] if item["company"] == "Innotech"
    )
    assert innotech["start_date"]["year"] == 2026
    assert innotech["start_date"]["month"] == 3
    assert innotech["start_date"]["day"] is None
    assert innotech["start_date"]["precision"] == "month"
    assert facts["contact"]["email"] == "you@example.com"
    assert innotech["responsibilities"] == [None] * len(innotech["responsibilities"])


def test_partial_date_rejects_a_day_at_month_precision() -> None:
    with pytest.raises(ValidationError):
        PartialDate(year=2026, month=3, day=1, precision=DatePrecision.MONTH)


def test_partial_date_rejects_yyyy_mm_dd_strings() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        PartialDate.parse("2026-03-01")


def test_missing_email_is_an_error(tmp_path: Path) -> None:
    payload = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    payload["contact"]["email"] = {"value": None, "status": "unknown"}
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report, profile = ProfileService().validate_path(path)
    assert profile is not None
    assert report.valid is False
    assert "contact.email" in report.missing_required


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    report, profile = ProfileService().validate_path(path)
    assert profile is None
    assert report.valid is False
    assert report.schema_ok is False


def test_missing_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "absent.json"
    report, profile = ProfileService().validate_path(path)
    assert profile is None
    assert report.valid is False


def test_unknown_skill_proficiency_is_not_treated_as_filled() -> None:
    profile = ProfileService().load(EXAMPLE_PROFILE)
    python_skill = next(skill for skill in profile.skills if skill.name == "Python")
    assert python_skill.proficiency.status is VerificationStatus.UNKNOWN
    assert python_skill.proficiency.usable_in_documents() is False
    assert python_skill.commercial_experience.usable_in_documents() is False


def test_cli_validate_example_profile_exits_zero() -> None:
    assert main(["profile", "validate", "--path", str(EXAMPLE_PROFILE)]) == 0


def test_private_profile_innotech_start_is_confirmed_month() -> None:
    if not PRIVATE_PROFILE.exists():
        return
    profile = ProfileService().load(PRIVATE_PROFILE)
    assert profile.contact.email.status is VerificationStatus.CONFIRMED
    assert profile.contact.email.usable_in_documents()
    innotech = next(
        item for item in profile.experience if item.company.value == "Innotech"
    )
    assert innotech.start_date.status is VerificationStatus.CONFIRMED
    assert innotech.start_date.value is not None
    assert innotech.start_date.value.as_text() == "2026-03"
    assert innotech.start_date.value.day is None
