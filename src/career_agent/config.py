"""Application settings loaded from environment variables and optional `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings from `.env` and the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,
    )

    profile_path: Path = Field(
        default=Path("data/candidate_profile.json"),
        validation_alias=AliasChoices("CAREER_AGENT_PROFILE_PATH", "profile_path"),
    )
    data_dir: Path = Field(
        default=Path("data"),
        validation_alias=AliasChoices("CAREER_AGENT_DATA_DIR", "data_dir"),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("CAREER_AGENT_LOG_LEVEL", "log_level"),
    )
    autonomy_level: int = Field(
        default=1,
        ge=1,
        le=3,
        validation_alias=AliasChoices("CAREER_AGENT_AUTONOMY_LEVEL", "autonomy_level"),
    )
    telegram_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TELEGRAM_BOT_TOKEN",
            "CAREER_AGENT_TELEGRAM_BOT_TOKEN",
            "telegram_bot_token",
        ),
    )
    telegram_allowed_user_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TELEGRAM_ALLOWED_USER_ID",
            "CAREER_AGENT_TELEGRAM_ALLOWED_USER_ID",
            "telegram_allowed_user_id",
        ),
    )

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def empty_token_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("telegram_allowed_user_id", mode="before")
    @classmethod
    def empty_user_id_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
