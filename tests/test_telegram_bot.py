from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from career_agent.config import Settings
from career_agent.domain.fields import VerificationStatus
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
from career_agent.services.application_evidence_builder import (
    ApplicationEvidenceCategory,
    ApplicationEvidenceItem,
    ApplicationEvidenceReport,
    ApplicationEvidenceSource,
    ApplicationEvidenceStatus,
    EvidenceFact,
)
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

def test_jobs_command_shows_relevant_vacancies_and_scores(monkeypatch) -> None:
    from types import SimpleNamespace

    from career_agent.services.job_candidate_fit import CandidateFitStatus
    from career_agent.services.job_relevance import RelevanceStatus

    handlers = TelegramHandlers(_settings(), ProfileService())

    def make_job(job_id: str, title: str):
        return SimpleNamespace(
            id=job_id,
            title=title,
            company="Example Company",
            location="Worldwide",
            workplace_type=SimpleNamespace(value="remote"),
            link_check_status=SimpleNamespace(value="reachable"),
            link_check_http_status=200,
            link_checked_at=None,
            application_url="https://example.com/jobs/qa",
            job_url="https://example.com/jobs/qa",
        )

    target_job = make_job("12345678" + "a" * 32, "Junior QA Engineer")
    stretch_job = make_job("22222222" + "b" * 32, "Middle QA Engineer")
    excluded_job = make_job("33333333" + "c" * 32, "Lead QA Engineer")

    def make_assessment(fit_status, score):
        return SimpleNamespace(
            relevance=SimpleNamespace(
                status=RelevanceStatus.RELEVANT,
                role_type=SimpleNamespace(value="software_qa"),
                seniority=SimpleNamespace(value="junior"),
            ),
            candidate_fit=SimpleNamespace(status=fit_status),
            match_score=SimpleNamespace(
                observed_score=score,
                status=SimpleNamespace(value="potential_match"),
            ),
        )

    assessments = {
        target_job.id: make_assessment(CandidateFitStatus.TARGET_FIT, 84.2),
        stretch_job.id: make_assessment(
            CandidateFitStatus.POTENTIAL_STRETCH, 99.9
        ),
        excluded_job.id: make_assessment(
            CandidateFitStatus.OUT_OF_SCOPE, 100.0
        ),
    }

    monkeypatch.setattr(
        handlers,
        "_load_jobs",
        lambda: [stretch_job, excluded_job, target_job],
    )
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.assess_candidate_job",
        lambda job, _profile: assessments[job.id],
    )

    message = FakeMessage(OWNER_ID, "/jobs")
    asyncio.run(handlers.cmd_jobs(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    result = message.answers[0]
    assert result.index("Junior QA Engineer") < result.index("Middle QA Engineer")
    assert "Lead QA Engineer" not in result
    assert "84.2/100" in result
    assert "99.9/100" in result
    assert "Ссылка: доступна (HTTP 200)" in result
    assert "/job 12345678" in result
    assert "/assess 12345678" in result
    assert "Целевая роль и уровень: 1" in result
    assert "Можно рассмотреть выше уровня: 1" in result
    assert "Не подходят по уровню: 1" in result


def test_job_command_shows_vacancy_details(monkeypatch) -> None:
    from types import SimpleNamespace

    handlers = TelegramHandlers(_settings(), ProfileService())
    job = SimpleNamespace(
        id="12345678" + "a" * 32,
        title="Junior QA Engineer",
        company="Example Company",
        display_source=lambda: "Himalayas",
        eligible_countries=["Worldwide"],
        location="Worldwide",
        workplace_type=SimpleNamespace(value="remote"),
        remote_scope=SimpleNamespace(value="worldwide"),
        employment_type="Full Time",
        experience_level="Junior",
        salary_min=None,
        salary_max=None,
        application_url="https://example.com/jobs/qa",
        job_url="https://example.com/jobs/qa",
        link_check_status=SimpleNamespace(value="reachable"),
        link_check_http_status=200,
        link_checked_at=None,
        description=(
            "<h2>Responsibilities</h2>"
            "<ul><li>Test APIs and report defects.</li></ul>"
        ),
    )

    monkeypatch.setattr(
        handlers,
        "_load_jobs",
        lambda job_id=None: [job] if job_id == "12345678" else [],
    )

    checked_jobs = []

    def fake_check(database_path, job_id):
        checked_jobs.append((database_path, job_id))
        return job

    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.check_job_link",
        fake_check,
    )

    message = FakeMessage(OWNER_ID, "/job 12345678")
    asyncio.run(handlers.cmd_job(message))  # type: ignore[arg-type]

    assert checked_jobs == [(handlers.settings.database_path, job.id)]
    assert len(message.answers) == 1
    assert "Junior QA Engineer" in message.answers[0]
    assert "Example Company" in message.answers[0]
    assert "Test APIs and report defects." in message.answers[0]
    assert "<li>" not in message.answers[0]
    assert "<h2>" not in message.answers[0]
    assert "Что предстоит делать:" in message.answers[0]
    assert "Страница площадки отвечает (HTTP 200)." in message.answers[0]
    assert "https://example.com/jobs/qa" in message.answers[0]


def test_job_command_requires_an_id() -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    message = FakeMessage(OWNER_ID, "/job")

    asyncio.run(handlers.cmd_job(message))  # type: ignore[arg-type]

    assert message.answers == ["Usage: /job <job_id>"]


def test_assess_command_sends_compact_summary(monkeypatch) -> None:
    from types import SimpleNamespace

    handlers = TelegramHandlers(_settings(), ProfileService())
    job = SimpleNamespace(id="12345678")
    assessment = object()
    summary = "QA Engineer @ Example Company\\nMatch: 84.2/100 · needs_review"

    monkeypatch.setattr(
        handlers,
        "_load_jobs",
        lambda job_id=None: [job] if job_id == "12345678" else [],
    )
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.assess_candidate_job",
        lambda _job, _profile: assessment,
    )
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers._format_assessment_summary",
        lambda _assessment, _job: summary,
    )

    message = FakeMessage(OWNER_ID, "/assess 12345678")
    asyncio.run(handlers.cmd_assess(message))  # type: ignore[arg-type]

    assert message.answers == [summary]


def test_search_command_reports_saved_jobs_and_source_limits(monkeypatch) -> None:
    from career_agent.services.job_discovery import DiscoveryReport, SourceSummary

    handlers = TelegramHandlers(_settings(), ProfileService())
    report = DiscoveryReport(
        summaries=[
            SourceSummary(
                source="himalayas",
                fetched=10,
                saved=3,
                duplicates=7,
            ),
            SourceSummary(
                source="remotive",
                skipped=True,
                skip_reason="remotive rate limit reached",
            ),
        ]
    )

    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers._execute_job_search",
        lambda _settings: (report, None),
    )

    message = FakeMessage(OWNER_ID, "/search")
    asyncio.run(handlers.cmd_search(message))  # type: ignore[arg-type]

    result = "\\n".join(message.answers)
    assert "Поиск завершён." in result
    assert "Получено объявлений: 10" in result
    assert "Новых вакансий сохранено: 3" in result
    assert "Himalayas: получено 10, новых 3" in result
    assert "Remotive: достигнут лимит запросов" in result


def test_search_command_respects_global_cooldown(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())

    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers._execute_job_search",
        lambda _settings: (None, timedelta(hours=1, minutes=15)),
    )

    message = FakeMessage(OWNER_ID, "/search")
    asyncio.run(handlers.cmd_search(message))  # type: ignore[arg-type]

    result = "\\n".join(message.answers)
    assert "через 1 ч 15 мин" in result
    assert "Поиск завершён." not in result


def test_search_command_rejects_arguments(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    called = False

    def unexpected_search(_settings):
        nonlocal called
        called = True
        return None, None

    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers._execute_job_search",
        unexpected_search,
    )

    message = FakeMessage(OWNER_ID, "/search himalayas")
    asyncio.run(handlers.cmd_search(message))  # type: ignore[arg-type]

    assert called is False
    assert len(message.answers) == 1
    assert "без дополнительных аргументов" in message.answers[0]



def test_jobs_command_excludes_expired_listings(monkeypatch) -> None:
    from types import SimpleNamespace

    from career_agent.domain.job_posting import ListingStatus
    from career_agent.services.job_candidate_fit import CandidateFitStatus
    from career_agent.services.job_relevance import RelevanceStatus

    handlers = TelegramHandlers(_settings(), ProfileService())

    def make_job(job_id, title, status):
        return SimpleNamespace(
            id=job_id,
            title=title,
            company="Example Company",
            workplace_type=SimpleNamespace(value="remote"),
            listing_status=lambda: status,
        )

    expired_job = make_job(
        "11111111-expired",
        "Expired QA Engineer",
        ListingStatus.EXPIRED,
    )
    active_job = make_job(
        "22222222-active",
        "Current QA Engineer",
        ListingStatus.WITHIN_LISTED_PERIOD,
    )

    def make_assessment(_job, _profile):
        return SimpleNamespace(
            relevance=SimpleNamespace(
                status=RelevanceStatus.RELEVANT,
                role_type=SimpleNamespace(value="software_qa"),
                seniority=SimpleNamespace(value="junior"),
            ),
            candidate_fit=SimpleNamespace(
                status=CandidateFitStatus.TARGET_FIT,
            ),
            match_score=SimpleNamespace(
                observed_score=99.0,
                status=SimpleNamespace(value="potential_match"),
            ),
        )

    monkeypatch.setattr(
        handlers,
        "_load_jobs",
        lambda: [expired_job, active_job],
    )
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.assess_candidate_job",
        make_assessment,
    )

    message = FakeMessage(OWNER_ID, "/jobs")
    asyncio.run(handlers.cmd_jobs(message))  # type: ignore[arg-type]

    result = "\\n".join(message.answers)

    assert "Current QA Engineer" in result
    assert "Expired QA Engineer" not in result
    assert "Исключено по истёкшему сроку публикации: 1" in result

def _prepare_test_job():
    from types import SimpleNamespace

    return SimpleNamespace(
        id="12345678" + "a" * 32,
        title="Junior QA Engineer",
        company="Example Company",
        application_url="https://example.com/jobs/qa",
        job_url="https://example.com/jobs/qa",
    )


def test_prepare_command_formats_detailed_evidence_report(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    job = _prepare_test_job()
    profile = object()

    report = ApplicationEvidenceReport(
        job_id=job.id,
        title=job.title,
        company=job.company,
        items=[
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.REQUIRED_SKILL,
                requirement="Postman",
                status=ApplicationEvidenceStatus.CONFIRMED,
                evidence=[
                    EvidenceFact(
                        source=ApplicationEvidenceSource.CANDIDATE_SKILL,
                        text="Postman",
                        verification_status=VerificationStatus.CONFIRMED,
                        usable_in_documents=True,
                        claim_scope="skill",
                    )
                ],
            ),
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.RESPONSIBILITY,
                requirement="API testing",
                status=ApplicationEvidenceStatus.NEEDS_CONFIRMATION,
                note="Нужно проверить рабочий контекст.",
            ),
        ],
        warnings=["Некоторые сведения профиля пока не используются."],
    )

    monkeypatch.setattr(handlers, "_load_jobs", lambda _job_id: [job])
    monkeypatch.setattr(handlers, "_load_valid_profile", lambda: profile)
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.build_application_evidence",
        lambda _job, _profile: report,
    )

    message = FakeMessage(OWNER_ID, "/prepare 12345678 full")
    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    result = "\n".join(message.answers)

    assert "Подробная карта подготовки отклика" in result
    assert "Junior QA Engineer" in result
    assert "Postman" in result
    assert "можно использовать в документах" in result
    assert "API testing" in result
    assert "нужно уточнить" in result
    assert "Некоторые сведения профиля" in result
    assert "https://example.com/jobs/qa" in result
    assert "не отправляются автоматически" in result



def test_prepare_command_uses_compact_summary_by_default(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    job = _prepare_test_job()

    report = ApplicationEvidenceReport(
        job_id=job.id,
        title=job.title,
        company=job.company,
        items=[
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.REQUIRED_SKILL,
                requirement="Postman",
                status=ApplicationEvidenceStatus.CONFIRMED,
                evidence=[
                    EvidenceFact(
                        source=ApplicationEvidenceSource.CANDIDATE_SKILL,
                        text="Postman",
                        verification_status=VerificationStatus.CONFIRMED,
                        usable_in_documents=True,
                        claim_scope="skill",
                    )
                ],
            ),
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.RESPONSIBILITY,
                requirement="Preparing test data",
                status=ApplicationEvidenceStatus.PARTIAL,
                missing_capabilities=["test_data_preparation"],
            ),
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.UNSPECIFIED_SKILL,
                requirement="Go",
                status=ApplicationEvidenceStatus.NO_EVIDENCE,
            ),
            ApplicationEvidenceItem(
                category=ApplicationEvidenceCategory.EXPERIENCE,
                requirement="Стаж: минимум 1.0 года в направлении QA",
                status=ApplicationEvidenceStatus.PARTIAL,
                evidence=[
                    EvidenceFact(
                        source=ApplicationEvidenceSource.EXPERIENCE_RESPONSIBILITY,
                        text="7 подтверждённых полных месяцев опыта (QA)",
                        verification_status=VerificationStatus.CONFIRMED,
                        usable_in_documents=True,
                        claim_scope="confirmed_experience_duration",
                    )
                ],
            ),
        ],
    )

    monkeypatch.setattr(handlers, "_load_jobs", lambda _job_id: [job])
    monkeypatch.setattr(handlers, "_load_valid_profile", lambda: object())
    monkeypatch.setattr(
        "career_agent.integrations.telegram.handlers.build_application_evidence",
        lambda _job, _profile: report,
    )

    message = FakeMessage(OWNER_ID, "/prepare 12345678")
    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    result = "\n".join(message.answers)

    assert "Краткая карта подготовки отклика" in result
    assert "Подтверждено: 1/4" in result
    assert "Postman" in result
    assert "Частичные совпадения" in result
    assert "подготовка тестовых данных" in result
    assert "Пока нет подтверждений" in result
    assert "Go" in result
    assert "7 из 12 месяцев" in result
    assert "Фактов для документов: 2" in result
    assert "/prepare 12345678 full" in result
    assert "Ограничение:" not in result
    assert "можно использовать в документах" not in result


def test_prepare_command_rejects_unknown_mode() -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    message = FakeMessage(OWNER_ID, "/prepare 12345678 detailed")

    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    assert "Использование: /prepare" in message.answers[0]

def test_prepare_command_requires_job_id() -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    message = FakeMessage(OWNER_ID, "/prepare")

    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    assert "Использование: /prepare" in message.answers[0]


def test_prepare_command_handles_missing_job(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    monkeypatch.setattr(handlers, "_load_jobs", lambda _job_id: [])

    message = FakeMessage(OWNER_ID, "/prepare missing")

    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    assert "Не удалось найти вакансию" in message.answers[0]


def test_prepare_command_handles_ambiguous_job_id(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    first_job = _prepare_test_job()
    second_job = _prepare_test_job()
    second_job.id = "87654321" + "b" * 32

    monkeypatch.setattr(
        handlers,
        "_load_jobs",
        lambda _job_id: [first_job, second_job],
    )

    message = FakeMessage(OWNER_ID, "/prepare 123")

    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    assert "более длинный ID" in message.answers[0]


def test_prepare_command_requires_valid_profile(monkeypatch) -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    job = _prepare_test_job()

    monkeypatch.setattr(handlers, "_load_jobs", lambda _job_id: [job])
    monkeypatch.setattr(handlers, "_load_valid_profile", lambda: None)

    message = FakeMessage(OWNER_ID, "/prepare 12345678")

    asyncio.run(handlers.cmd_prepare(message))  # type: ignore[arg-type]

    assert len(message.answers) == 1
    assert "profile validate" in message.answers[0]


def test_help_mentions_prepare_command() -> None:
    handlers = TelegramHandlers(_settings(), ProfileService())
    message = FakeMessage(OWNER_ID, "/help")

    asyncio.run(handlers.cmd_help(message))  # type: ignore[arg-type]

    assert "/prepare ID [full]" in message.answers[0]


def test_router_registers_prepare_command() -> None:
    from career_agent.integrations.telegram.handlers import build_router

    router = build_router(_settings(), ProfileService())
    callbacks = {
        handler.callback.__name__
        for handler in router.message.handlers
    }

    assert "cmd_prepare" in callbacks
