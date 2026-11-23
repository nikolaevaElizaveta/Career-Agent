"""Start local long polling. Missing token must not produce a traceback."""

from __future__ import annotations

import asyncio
import logging
import sys

from career_agent.config import Settings, get_settings
from career_agent.integrations.telegram.bot import create_bot, create_dispatcher

logger = logging.getLogger(__name__)

MISSING_TOKEN_MESSAGE = (
    "Telegram bot token is missing.\n"
    "Copy .env.example to .env and set TELEGRAM_BOT_TOKEN.\n"
    "Create the token in Telegram with BotFather. "
    "Do not paste the token into Cursor or ChatGPT."
)


def run_bot(settings: Settings | None = None) -> int:
    """CLI entry: return 0 on clean shutdown, 1 if configuration is incomplete."""
    resolved = settings or get_settings()
    token = resolved.telegram_bot_token
    if not token:
        print(MISSING_TOKEN_MESSAGE, file=sys.stderr)
        return 1
    asyncio.run(_start_polling(token, resolved))
    return 0


async def _start_polling(token: str, settings: Settings) -> None:
    logger.info("Starting Telegram long polling. The bot token is not logged.")
    bot = create_bot(token)
    dispatcher = create_dispatcher(settings)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Telegram polling stopped.")
