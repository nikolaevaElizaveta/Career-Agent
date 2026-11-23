"""Telegram command handlers. Profile facts come from ProfileService, not here."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from career_agent.config import Settings
from career_agent.services.profile_service import ProfileService

START_TEXT = (
    "Personal Career Agent is running locally.\n\n"
    "This bot is private. After you set TELEGRAM_ALLOWED_USER_ID, only you can use it.\n"
    "Job search, Gmail, and applications are not connected yet.\n\n"
    "Send /help for commands."
)

HELP_TEXT = (
    "Available commands:\n"
    "/start — welcome\n"
    "/help — this list\n"
    "/whoami — your numeric Telegram user ID\n"
    "/status — whether the bot and configuration look ready\n"
    "/profile — short Candidate Profile summary (owner only)\n\n"
    "Until TELEGRAM_ALLOWED_USER_ID is set, only /whoami works."
)


class TelegramHandlers:
    def __init__(self, settings: Settings, profile_service: ProfileService) -> None:
        self.settings = settings
        self.profile_service = profile_service

    async def cmd_start(self, message: Message) -> None:
        await message.answer(START_TEXT)

    async def cmd_help(self, message: Message) -> None:
        await message.answer(HELP_TEXT)

    async def cmd_whoami(self, message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        if user_id is None:
            await message.answer("Could not read your Telegram user ID.")
            return
        await message.answer(f"Your Telegram user ID: {user_id}")

    async def cmd_status(self, message: Message) -> None:
        token_set = bool(self.settings.telegram_bot_token)
        allow_set = self.settings.telegram_allowed_user_id is not None
        profile_exists = self.settings.profile_path.exists()
        lines = [
            "Career Agent status",
            "Bot process: running",
            f"TELEGRAM_BOT_TOKEN: {'configured' if token_set else 'missing'}",
            (
                "TELEGRAM_ALLOWED_USER_ID: "
                f"{'configured' if allow_set else 'not set (only /whoami is open)'}"
            ),
            f"Candidate Profile file: {'found' if profile_exists else 'missing'}",
            f"Autonomy level: {self.settings.autonomy_level} (assistant)",
        ]
        await message.answer("\n".join(lines))

    async def cmd_profile(self, message: Message) -> None:
        report, profile = self.profile_service.validate_path(self.settings.profile_path)
        if profile is None:
            await message.answer(
                "Candidate Profile is not available. Check that the JSON file exists "
                "and run: python -m career_agent profile validate"
            )
            return
        summary = self.profile_service.format_telegram_summary(profile)
        extra = "" if report.valid else "\n\nWarning: profile validation reported errors."
        await message.answer(summary + extra)


def build_router(settings: Settings, profile_service: ProfileService) -> Router:
    handlers = TelegramHandlers(settings, profile_service)
    router = Router(name="telegram_commands")
    router.message.register(handlers.cmd_start, Command("start"))
    router.message.register(handlers.cmd_help, Command("help"))
    router.message.register(handlers.cmd_whoami, Command("whoami"))
    router.message.register(handlers.cmd_status, Command("status"))
    router.message.register(handlers.cmd_profile, Command("profile"))
    return router
