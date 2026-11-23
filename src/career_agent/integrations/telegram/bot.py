"""Build the aiogram bot and dispatcher. Does not start network polling."""

from __future__ import annotations

from aiogram import Bot, Dispatcher

from career_agent.config import Settings
from career_agent.integrations.telegram.handlers import build_router
from career_agent.integrations.telegram.middleware import AccessControlMiddleware
from career_agent.services.profile_service import ProfileService


def create_bot(token: str) -> Bot:
    return Bot(token=token)


def create_dispatcher(
    settings: Settings,
    profile_service: ProfileService | None = None,
) -> Dispatcher:
    service = profile_service or ProfileService()
    dispatcher = Dispatcher()
    dispatcher.message.middleware(AccessControlMiddleware(settings.telegram_allowed_user_id))
    dispatcher.include_router(build_router(settings, service))
    return dispatcher
