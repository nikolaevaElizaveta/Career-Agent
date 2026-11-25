"""SQLite engine and session factory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{database_path}",
        echo=False,
        future=True,
    )


def _migrate_job_postings_schema(engine: Engine) -> None:
    """Add new columns and recover expiry dates from stored provider payloads."""
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("job_postings")
    }

    with engine.begin() as connection:
        if "last_seen_at" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE job_postings "
                    "ADD COLUMN last_seen_at DATETIME"
                )
            )

        if "expires_at" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE job_postings "
                    "ADD COLUMN expires_at DATETIME"
                )
            )

        if "link_checked_at" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE job_postings "
                    "ADD COLUMN link_checked_at DATETIME"
                )
            )

        if "link_check_status" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE job_postings "
                    "ADD COLUMN link_check_status VARCHAR(32) "
                    "NOT NULL DEFAULT 'unknown'"
                )
            )

        if "link_check_http_status" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE job_postings "
                    "ADD COLUMN link_check_http_status INTEGER"
                )
            )

        connection.execute(
            text(
                "UPDATE job_postings "
                "SET last_seen_at = discovered_at "
                "WHERE last_seen_at IS NULL"
            )
        )

        # Older Himalayas records already contain expiryDate in raw_payload.
        # Recover it rather than treating all existing listings as unknown.
        if {"source", "raw_payload"}.issubset(columns):
            rows = connection.execute(
                text(
                    "SELECT id, raw_payload FROM job_postings "
                    "WHERE source = 'himalayas' AND expires_at IS NULL"
                )
            ).all()

            updates = []

            for row in rows:
                try:
                    payload = row.raw_payload
                    if isinstance(payload, str):
                        payload = json.loads(payload)

                    if not isinstance(payload, dict):
                        continue

                    job_data = payload.get("job")
                    if not isinstance(job_data, dict):
                        continue

                    timestamp = job_data.get("expiryDate")
                    if isinstance(timestamp, bool) or not isinstance(
                        timestamp, (int, float)
                    ):
                        continue

                    expiry = datetime.fromtimestamp(
                        float(timestamp),
                        tz=UTC,
                    ).replace(tzinfo=None)

                    updates.append({
                        "id": row.id,
                        "expires_at": expiry.isoformat(sep=" "),
                    })
                except (KeyError, TypeError, ValueError, OverflowError, OSError):
                    continue

            if updates:
                connection.execute(
                    text(
                        "UPDATE job_postings "
                        "SET expires_at = :expires_at "
                        "WHERE id = :id AND expires_at IS NULL"
                    ),
                    updates,
                )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # Import models so metadata includes all tables before create_all.
    from career_agent.integrations.job_sources import rate_limit as _rate_limit  # noqa: F401
    from career_agent.repositories import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    _migrate_job_postings_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
