"""aiogram middleware that applies Telegram access rules once per message."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from career_agent.integrations.telegram.auth import decide_access, extract_bot_command

logger = logging.getLogger(__name__)


class AccessControlMiddleware(BaseMiddleware):
    """Block unauthorized users before command handlers run."""

    def __init__(self, allowed_user_id: int | None) -> None:
        self.allowed_user_id = allowed_user_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message = _incoming_message(event)
        if message is None:
            return await handler(event, data)

        user_id = message.from_user.id if message.from_user else None
        command = extract_bot_command(message.text)
        decision = decide_access(user_id, command, self.allowed_user_id)
        if not decision.allowed:
            logger.info("telegram_access denied command=%s", command or "none")
            if decision.reply:
                await message.answer(decision.reply)
            return None
        logger.info("telegram_access allowed command=%s", command or "none")
        return await handler(event, data)


def _incoming_message(event: TelegramObject) -> Message | None:
    """Accept real aiogram messages and test doubles with the same attributes."""
    if isinstance(event, Message):
        return event
    if hasattr(event, "answer") and hasattr(event, "from_user") and hasattr(event, "text"):
        return event  # type: ignore[return-value]
    return None
