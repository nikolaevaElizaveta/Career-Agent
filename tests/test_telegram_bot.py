from __future__ import annotations

import asyncio
from pathlib import Path

from career_agent.config import Settings
from career_agent.integrations.telegram.auth import (
    ACCESS_DENIED_MESSAGE,
    ACCESS_NOT_CONFIGURED_MESSAGE,
    decide_access,
    extract_bot_command,
)
from career_agent.integrations.telegram.handlers import TelegramHandlers
from career_agent.integrations.telegram.middleware import AccessControlMiddleware
from career_agent.integrations.telegram.runner import MISSING_TOKEN_MESSAGE, run_bot
from career_agent.main import main
from career_agent.services.profile_service import ProfileService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = ROOT / "data" / "candidate_profile.example.json"
OWNER_ID = 111
STRANGER_ID = 999


class FakeUser:
    def __init__(self, user_id: int | None) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int | None, text: str) -> None:
        self.from_user = FakeUser(user_id) if user_id is not None else None
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, **_kwargs: object) -> None:
        self.answers.append(text)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "profile_path": EXAMPLE_PROFILE,
        "telegram_bot_token": "test-token",
        "telegram_allowed_user_id": OWNER_ID,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_extract_command_strips_bot_suffix() -> None:
    assert extract_bot_command("/whoami@career_agent_bot") == "whoami"
    assert extract_bot_command("/profile") == "profile"
    assert extract_bot_command("hello") is None


def test_owner_is_allowed_when_id_is_configured() -> None:
    assert decide_access(OWNER_ID, "profile", OWNER_ID).allowed is True
    assert decide_access(OWNER_ID, "status", OWNER_ID).allowed is True


def test_stranger_is_denied_when_id_is_configured() -> None:
    decision = decide_access(STRANGER_ID, "profile", OWNER_ID)
    assert decision.allowed is False
    assert decision.reply == ACCESS_DENIED_MESSAGE
    assert decision.reply is not None
    assert "Elizaveta" not in decision.reply
    assert "example.com" not in decision.reply


def test_without_allowed_id_only_whoami_is_open() -> None:
    assert decide_access(STRANGER_ID, "whoami", None).allowed is True
    blocked = decide_access(STRANGER_ID, "profile", None)
    assert blocked.allowed is False
    assert blocked.reply == ACCESS_NOT_CONFIGURED_MESSAGE
    start_blocked = decide_access(OWNER_ID, "start", None)
    assert start_blocked.allowed is False


def test_after_allowlist_stranger_cannot_use_whoami() -> None:
    decision = decide_access(STRANGER_ID, "whoami", OWNER_ID)
    assert decision.allowed is False
    assert decision.reply == ACCESS_DENIED_MESSAGE


def test_middleware_blocks_stranger_from_profile() -> None:
    middleware = AccessControlMiddleware(OWNER_ID)
    message = FakeMessage(STRANGER_ID, "/profile")
    called = False

    async def handler(_event: object, _data: dict[str, object]) -> str:
        nonlocal called
        called = True
        return "secret"

    result = asyncio.run(middleware(handler, message, {}))  # type: ignore[arg-type]
    assert result is None
    assert called is False
    assert message.answers == [ACCESS_DENIED_MESSAGE]


def test_middleware_allows_owner() -> None:
    middleware = AccessControlMiddleware(OWNER_ID)
    message = FakeMessage(OWNER_ID, "/profile")

    async def handler(_event: object, _data: dict[str, object]) -> str:
        return "ok"

    result = asyncio.run(middleware(handler, message, {}))  # type: ignore[arg-type]
    assert result == "ok"
    assert message.answers == []


def test_profile_is_hidden_before_allowlist() -> None:
    middleware = AccessControlMiddleware(None)
    message = FakeMessage(OWNER_ID, "/profile")

    async def handler(_event: object, _data: dict[str, object]) -> str:
        raise AssertionError("profile handler must not run before allow-list is set")

    asyncio.run(middleware(handler, message, {}))  # type: ignore[arg-type]
    assert message.answers == [ACCESS_NOT_CONFIGURED_MESSAGE]
    combined = "\n".join(message.answers)
    assert "you@example.com" not in combined
    assert "Innopolis" not in combined


def test_whoami_works_before_allowlist() -> None:
    handlers = TelegramHandlers(_settings(telegram_allowed_user_id=None), ProfileService())
    message = FakeMessage(STRANGER_ID, "/whoami")
    asyncio.run(handlers.cmd_whoami(message))  # type: ignore[arg-type]
    assert message.answers == [f"Your Telegram user ID: {STRANGER_ID}"]


def test_authorized_profile_uses_candidate_profile() -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    message = FakeMessage(OWNER_ID, "/profile")
    asyncio.run(handlers.cmd_profile(message))  # type: ignore[arg-type]
    assert len(message.answers) == 1
    text = message.answers[0]
    assert "Candidate Name" in text
    assert "you@example.com" in text
    assert "Innotech" in text
    assert "2026-03" in text
    assert "2026-03-01" not in text


def test_missing_token_is_a_clear_error(monkeypatch, capsys) -> None:
    polling_started = False

    def fake_run(_coro: object) -> None:
        nonlocal polling_started
        polling_started = True

    monkeypatch.setattr("career_agent.integrations.telegram.runner.asyncio.run", fake_run)
    code = run_bot(_settings(telegram_bot_token=None))
    captured = capsys.readouterr()
    assert code == 1
    assert polling_started is False
    assert "TELEGRAM_BOT_TOKEN" in captured.err
    assert MISSING_TOKEN_MESSAGE.splitlines()[0] in captured.err


def test_cli_bot_run_without_token_does_not_poll(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "career_agent.main.get_settings",
        lambda: _settings(telegram_bot_token=None, telegram_allowed_user_id=None),
    )
    monkeypatch.setattr(
        "career_agent.integrations.telegram.runner.asyncio.run",
        lambda _coro: (_ for _ in ()).throw(AssertionError("polling must not start")),
    )
    assert main(["bot", "run"]) == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_cli_profile_validate_still_works() -> None:
    assert main(["profile", "validate", "--path", str(EXAMPLE_PROFILE)]) == 0


def test_status_does_not_print_token() -> None:
    handlers = TelegramHandlers(
        _settings(telegram_bot_token="super-secret-token"),
        ProfileService(),
    )
    message = FakeMessage(OWNER_ID, "/status")
    asyncio.run(handlers.cmd_status(message))  # type: ignore[arg-type]
    text = message.answers[0]
    assert "super-secret-token" not in text
    assert "configured" in text


def test_create_dispatcher_registers_auth_middleware() -> None:
    from career_agent.integrations.telegram.bot import create_dispatcher
    from career_agent.integrations.telegram.middleware import AccessControlMiddleware

    dispatcher = create_dispatcher(_settings())
    registered = list(dispatcher.message.middleware)
    assert any(isinstance(item, AccessControlMiddleware) for item in registered)
