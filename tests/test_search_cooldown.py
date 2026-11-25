from datetime import UTC, datetime, timedelta

from career_agent.integrations.job_sources.rate_limit import (
    SearchRunLog,
    SqliteSearchCooldown,
)
from career_agent.repositories.db import make_engine, make_session_factory


def test_search_cooldown_persists_between_sessions(tmp_path) -> None:
    engine = make_engine(tmp_path / "career.db")
    session_factory = make_session_factory(engine)
    start = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    cooldown = timedelta(hours=6)

    try:
        with session_factory() as session:
            limiter = SqliteSearchCooldown(session, cooldown)
            assert limiter.reserve(start) is None

        # A new session sees the previous search and blocks another run.
        with session_factory() as session:
            limiter = SqliteSearchCooldown(session, cooldown)
            remaining = limiter.reserve(start + timedelta(hours=5))

            assert remaining == timedelta(hours=1)

        # The search is allowed again after the full cooldown.
        with session_factory() as session:
            limiter = SqliteSearchCooldown(session, cooldown)
            assert limiter.reserve(start + cooldown) is None

        with session_factory() as session:
            assert len(list(session.query(SearchRunLog))) == 1
    finally:
        engine.dispose()


def test_search_cooldown_accepts_naive_datetime(tmp_path) -> None:
    engine = make_engine(tmp_path / "career.db")
    session_factory = make_session_factory(engine)

    try:
        with session_factory() as session:
            limiter = SqliteSearchCooldown(
                session,
                timedelta(hours=6),
            )
            assert limiter.reserve(datetime(2026, 11, 23, 12, 0)) is None
    finally:
        engine.dispose()



def test_cli_search_respects_global_cooldown(monkeypatch, tmp_path, capsys) -> None:
    from career_agent.config import Settings
    from career_agent.main import main

    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "cli.db",
    )

    engine = make_engine(settings.database_path)
    session_factory = make_session_factory(engine)

    try:
        with session_factory() as session:
            limiter = SqliteSearchCooldown(
                session,
                timedelta(hours=6),
            )
            assert limiter.reserve() is None
    finally:
        engine.dispose()

    monkeypatch.setattr(
        "career_agent.main.get_settings",
        lambda: settings,
    )

    def unexpected_build_sources(*_args, **_kwargs):
        raise AssertionError("Sources must not be initialized during cooldown")

    monkeypatch.setattr(
        "career_agent.main.build_sources",
        unexpected_build_sources,
    )

    assert main(["jobs", "search"]) == 0
    assert "Search cooldown is active" in capsys.readouterr().out
