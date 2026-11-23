"""Access control for the personal Telegram bot.

Authorization lives here so command handlers do not each re-check the user ID.
"""

from __future__ import annotations

from dataclasses import dataclass

SETUP_ONLY_COMMAND = "whoami"

ACCESS_DENIED_MESSAGE = "You do not have access to this bot."
ACCESS_NOT_CONFIGURED_MESSAGE = (
    "Access is not configured yet. Send /whoami to get your numeric Telegram user ID, "
    "then add TELEGRAM_ALLOWED_USER_ID to your local .env file. "
    "Do not paste the bot token into chat."
)


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reply: str | None = None


def extract_bot_command(text: str | None) -> str | None:
    """Return the command name without slash or bot suffix, or None."""
    if not text:
        return None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    first = stripped.split()[0]
    name = first[1:].split("@", 1)[0].strip().lower()
    return name or None


def decide_access(
    user_id: int | None,
    command: str | None,
    allowed_user_id: int | None,
) -> AccessDecision:
    """Decide whether this Telegram user may run this command.

    - Until an allow-list ID is set, only `/whoami` is permitted (so the owner
      can discover their numeric ID).
    - After it is set, every command including `/whoami` is limited to that ID.
    - Unknown users get a neutral denial. Profile data is never included.
    """
    if user_id is None:
        return AccessDecision(allowed=False, reply=ACCESS_DENIED_MESSAGE)

    if allowed_user_id is None:
        if command == SETUP_ONLY_COMMAND:
            return AccessDecision(allowed=True)
        return AccessDecision(allowed=False, reply=ACCESS_NOT_CONFIGURED_MESSAGE)

    if user_id != allowed_user_id:
        return AccessDecision(allowed=False, reply=ACCESS_DENIED_MESSAGE)

    return AccessDecision(allowed=True)
