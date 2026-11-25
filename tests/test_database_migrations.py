import json
from datetime import UTC, datetime

from sqlalchemy import inspect, text

from career_agent.repositories.db import make_engine, make_session_factory


def test_legacy_database_recovers_expiry_from_raw_payload(tmp_path) -> None:
    engine = make_engine(tmp_path / "legacy.sqlite")
    expiry_timestamp = 1797577277

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE job_postings ("
                    "id VARCHAR(36) PRIMARY KEY, "
                    "source VARCHAR(64) NOT NULL, "
                    "discovered_at DATETIME NOT NULL, "
                    "raw_payload JSON NOT NULL"
                    ")"
                )
            )

            connection.execute(
                text(
                    "INSERT INTO job_postings "
                    "(id, source, discovered_at, raw_payload) "
                    "VALUES (:id, :source, :discovered_at, :payload)"
                ),
                [
                    {
                        "id": "legacy-himalayas",
                        "source": "himalayas",
                        "discovered_at": "2026-11-20 12:00:00",
                        "payload": json.dumps({
                            "provider": "himalayas",
                            "job": {"expiryDate": expiry_timestamp},
                        }),
                    },
                    {
                        "id": "legacy-remotive",
                        "source": "remotive",
                        "discovered_at": "2026-11-20 12:00:00",
                        "payload": json.dumps({
                            "provider": "remotive",
                            "job": {"publication_date": "2026-11-19"},
                        }),
                    },
                ],
            )

        make_session_factory(engine)

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("job_postings")
        }
        assert "last_seen_at" in columns
        assert "expires_at" in columns

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, last_seen_at, expires_at "
                    "FROM job_postings"
                )
            ).mappings().all()

        records = {row["id"]: row for row in rows}

        himalayas = records["legacy-himalayas"]
        remotive = records["legacy-remotive"]

        expected_expiry = datetime.fromtimestamp(
            expiry_timestamp,
            tz=UTC,
        ).replace(tzinfo=None)

        assert himalayas["last_seen_at"] is not None
        assert datetime.fromisoformat(
            himalayas["expires_at"]
        ) == expected_expiry

        assert remotive["last_seen_at"] is not None
        assert remotive["expires_at"] is None

    finally:
        engine.dispose()
