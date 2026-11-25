"""Telegram command handlers. Profile facts come from ProfileService."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from career_agent.config import Settings
from career_agent.config_loader import load_job_search_config
from career_agent.domain.job_posting import (
    JobPosting,
    LinkCheckStatus,
    ListingStatus,
)
from career_agent.integrations.job_sources.factory import build_sources
from career_agent.integrations.job_sources.rate_limit import (
    DEFAULT_SEARCH_COOLDOWN,
    SqliteSearchCooldown,
)
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository
from career_agent.services.application_evidence_builder import (
    ApplicationEvidenceReport,
    build_application_evidence,
)
from career_agent.services.job_candidate_assessment import (
    assess_candidate_job,
)
from career_agent.services.job_candidate_fit import CandidateFitStatus
from career_agent.services.job_description import clean_job_description
from career_agent.services.job_discovery import DiscoveryReport, JobDiscoveryService
from career_agent.services.job_link_checker import check_job_link
from career_agent.services.job_relevance import RelevanceStatus
from career_agent.services.job_requirements import extract_job_requirements
from career_agent.services.profile_service import ProfileService

START_TEXT = (
    "Привет! Я твой карьерный помощник.\n\n"
    "Ищу и анализирую вакансии, сравниваю требования с твоим профилем.\n"
    "Отправь /help, чтобы посмотреть доступные команды."
)

HELP_TEXT = (
    "Что я умею:\n"
    "/start — приветствие\n"
    "/help — список команд\n"
    "/whoami — твой Telegram ID\n"
    "/status — состояние бота\n"
    "/profile — краткая сводка профиля\n"
    "/search — обновить базу вакансий (не чаще раза в 6 часов)\n"
    "/jobs — подборка QA-вакансий\n"
    "/job ID — подробности вакансии\n"
    "/assess ID — насколько вакансия подходит твоему профилю\n"
    "/prepare ID [full] — краткая сводка или подробная карта"
)

PROFILE_ERROR = (
    "Не удалось прочитать профиль или он содержит ошибки. "
    "Проверь его командой: python -m career_agent profile validate"
)

logger = logging.getLogger(__name__)
SOURCE_NAMES = {
    "himalayas": "Himalayas",
    "remotive": "Remotive",
    "adzuna": "Adzuna",
}


def _execute_job_search(
    settings: Settings,
) -> tuple[DiscoveryReport | None, timedelta | None]:
    """Run discovery with a persistent cooldown and a short-lived DB session."""
    engine = make_engine(settings.database_path)

    try:
        session_factory = make_session_factory(engine)

        with session_factory() as session:
            search_config = load_job_search_config(
                settings.job_search_config_path
            )
            sources = build_sources(settings, search_config, session)

            cooldown = SqliteSearchCooldown(session, DEFAULT_SEARCH_COOLDOWN)
            remaining = cooldown.reserve()

            if remaining is not None:
                return None, remaining

            repository = JobRepository(session)
            report = JobDiscoveryService(repository, sources).search()
            return report, None
    finally:
        engine.dispose()


def _format_search_cooldown(remaining: timedelta) -> str:
    total_minutes = max(1, math.ceil(remaining.total_seconds() / 60))
    hours, minutes = divmod(total_minutes, 60)

    if hours and minutes:
        wait = f"{hours} ч {minutes} мин"
    elif hours:
        wait = f"{hours} ч"
    else:
        wait = f"{minutes} мин"

    return (
        f"Новый поиск будет доступен через {wait}. "
        "Это ограничение нужно, чтобы не отправлять слишком частые запросы "
        "к площадкам с вакансиями."
    )


def _format_discovery_report(report: DiscoveryReport) -> str:
    fetched = sum(item.fetched for item in report.summaries)
    saved = sum(item.saved for item in report.summaries)
    updated = sum(item.updated for item in report.summaries)
    duplicates = sum(item.duplicates for item in report.summaries)
    probable = sum(item.probable_duplicates for item in report.summaries)

    lines = [
        "Поиск завершён.",
        "",
        f"Получено объявлений: {fetched}",
        f"Новых вакансий сохранено: {saved}",
        f"Обновлено существующих вакансий: {updated}",
        f"Не изменились: {duplicates}",
    ]

    if probable:
        lines.append(f"Возможных дублей: {probable}")

    lines.extend(["", "По источникам:"])

    for item in report.summaries:
        source_name = SOURCE_NAMES.get(item.source, item.source)

        if item.skipped:
            reason = (item.skip_reason or "").casefold()

            if "rate limit" in reason or "429" in reason:
                status = "достигнут лимит запросов"
            elif "disabled" in reason:
                status = "отключён в настройках"
            else:
                status = "пропущен"

            lines.append(f"• {source_name}: {status}")
            continue

        details = (
            f"получено {item.fetched}, "
            f"новых {item.saved}, "
            f"обновлено {item.updated}, "
            f"без изменений {item.duplicates}"
        )

        if item.probable_duplicates:
            details += f", возможных дублей {item.probable_duplicates}"

        if item.error:
            details += "; часть данных получить не удалось"
        elif item.fetched == 0:
            details = "новых объявлений не найдено"

        lines.append(f"• {source_name}: {details}")

    if not report.summaries:
        lines.append("Источники поиска не настроены.")

    return "\n".join(lines)


def _split_message(text: str, limit: int = 3900) -> list[str]:
    """Split long text into Telegram-safe chunks."""
    chunks = []
    remaining = text.strip()

    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _short_text(value: str, limit: int = 170) -> str:
    """Normalize and shorten a text fragment."""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _human_fit(value: object) -> str:
    return {
        "target_fit": "Подходит по целевой роли и уровню",
        "potential_stretch": "Можно рассмотреть: уровень выше целевого",
        "needs_review": "Нужно проверить вручную",
        "out_of_scope": "Не подходит по целевому уровню",
    }.get(_enum_value(value), "Требуется дополнительная проверка")


def _human_seniority(value: object) -> str:
    return {
        "internship": "стажировка",
        "junior": "начальный уровень",
        "middle": "средний уровень",
        "senior": "старший уровень",
        "lead": "ведущая позиция",
        "principal": "экспертная позиция",
        "manager_executive": "руководящая позиция",
        "unknown": "уровень не указан",
    }.get(_enum_value(value), "уровень не указан")


def _human_role(value: object) -> str:
    return {
        "software_qa": "тестирование программного обеспечения",
        "manual_qa": "ручное тестирование",
        "api_qa": "тестирование API",
        "integration_qa": "интеграционное тестирование",
        "qa_automation": "автоматизация тестирования",
        "ai_evaluation": "оценка качества AI",
        "business_process_qa": "контроль бизнес-процессов",
        "localization_qa": "локализация и языковое тестирование",
        "system_testing": "системное тестирование",
        "unknown": "направление не определено",
    }.get(_enum_value(value), "тестирование")


def _human_workplace(value: object) -> str:
    return {
        "remote": "удалённо",
        "hybrid": "гибридный формат",
        "onsite": "работа в офисе",
        "unknown": "формат не указан",
    }.get(_enum_value(value), "формат не указан")


def _human_listing_status(job: object) -> str:
    status_getter = getattr(job, "listing_status", None)
    status = (
        status_getter()
        if callable(status_getter)
        else ListingStatus.UNKNOWN
    )

    if status is ListingStatus.EXPIRED:
        description = "Срок публикации истёк по данным площадки."
    elif status is ListingStatus.WITHIN_LISTED_PERIOD:
        description = "Срок публикации не истёк по данным площадки."
    else:
        description = "Площадка не указала дату окончания публикации."

    return (
        f"{description} "
        "Это не подтверждает, что работодатель ещё принимает отклики."
    )


def _human_link_check(job: object) -> str:
    status = _enum_value(
        getattr(job, "link_check_status", LinkCheckStatus.UNKNOWN)
    )
    http_status = getattr(job, "link_check_http_status", None)
    checked_at = getattr(job, "link_checked_at", None)

    if status == LinkCheckStatus.REACHABLE.value:
        if http_status is not None and 300 <= http_status < 400:
            message = (
                f"Страница площадки перенаправляет запрос (HTTP {http_status})."
            )
        else:
            code = f" (HTTP {http_status})" if http_status is not None else ""
            message = f"Страница площадки отвечает{code}."

    elif status == LinkCheckStatus.NOT_FOUND.value:
        code = f" (HTTP {http_status})" if http_status is not None else ""
        message = (
            f"Страница не найдена{code}. Возможно, объявление снято с публикации."
        )

    elif status == LinkCheckStatus.RESTRICTED.value:
        code = f" (HTTP {http_status})" if http_status is not None else ""
        message = (
            f"Площадка ограничила автоматическую проверку{code}; "
            "доступность объявления неизвестна."
        )

    elif status == LinkCheckStatus.ERROR.value:
        message = (
            "Не удалось проверить ссылку из-за сетевой или серверной ошибки; "
            "доступность объявления неизвестна."
        )

    elif status == LinkCheckStatus.UNSUPPORTED.value:
        message = "Автоматическая проверка этой ссылки не поддерживается."

    else:
        message = "Ссылка ещё не проверялась."

    if checked_at is not None:
        message += f" Проверено: {checked_at:%d.%m.%Y}."

    return message


def _human_short_link_check(job: object) -> str:
    """Compactly display the last saved provider-page check."""
    status = _enum_value(
        getattr(job, "link_check_status", LinkCheckStatus.UNKNOWN)
    )
    http_status = getattr(job, "link_check_http_status", None)
    checked_at = getattr(job, "link_checked_at", None)

    if status == LinkCheckStatus.REACHABLE.value:
        if http_status is not None and 300 <= http_status < 400:
            result = f"перенаправляет (HTTP {http_status})"
        elif http_status is not None:
            result = f"доступна (HTTP {http_status})"
        else:
            result = "доступна"
    elif status == LinkCheckStatus.NOT_FOUND.value:
        code = f" (HTTP {http_status})" if http_status is not None else ""
        result = f"не найдена{code}"
    elif status == LinkCheckStatus.RESTRICTED.value:
        code = f" (HTTP {http_status})" if http_status is not None else ""
        result = f"проверка ограничена{code}"
    elif status == LinkCheckStatus.ERROR.value:
        result = "не удалось проверить"
    elif status == LinkCheckStatus.UNSUPPORTED.value:
        result = "автопроверка не поддерживается"
    else:
        result = "не проверена"

    if checked_at is not None:
        result += f" · {checked_at:%d.%m.%Y}"

    return f"Ссылка: {result}"


def _human_experience_level(value: str | None) -> str:
    normalized = (value or "").strip().casefold()
    return {
        "entry-level": "начальный уровень",
        "entry level": "начальный уровень",
        "junior": "начальный уровень",
        "intern": "стажировка",
        "internship": "стажировка",
        "mid-level": "средний уровень",
        "mid level": "средний уровень",
        "middle": "средний уровень",
        "senior": "старший уровень",
        "senior-level": "старший уровень",
        "lead": "ведущая позиция",
    }.get(normalized, value or "не указан")


def _assessment_note(assessment) -> str:
    for item in getattr(assessment, "experience_matches", []):
        if item.priority != "required":
            continue

        if _enum_value(item.status) == "below_minimum":
            required = math.ceil(item.min_years * 12)
            area = item.area or "профильного"
            return (
                f"Не хватает стажа: {item.confirmed_min_months} "
                f"из {required} месяцев ({area})."
            )

        if _enum_value(item.status) == "needs_confirmation":
            return "Часть опыта нужно подтвердить."

    if _enum_value(assessment.match_score.status) == "weak_match":
        return "Есть существенные пробелы в навыках или задачах."

    if _enum_value(assessment.match_score.status) == "needs_review":
        return "Некоторые требования нужно проверить вручную."

    return "Есть совпадения с твоим профилем."


def _format_assessment_summary(assessment, job) -> str:
    """Human-readable, compact Telegram assessment."""
    score = assessment.match_score

    if score is None or score.observed_score is None:
        score_line = "Оценка совпадения пока недоступна."
    else:
        score_line = (
            f"Предварительная оценка совпадения: "
            f"{score.observed_score:.1f}/100"
        )

    lines = [
        f"{assessment.title} — {assessment.company}",
        "",
        score_line,
        f"По роли и уровню: {_human_fit(assessment.candidate_fit.status)}.",
        (
            f"Направление: {_human_role(assessment.relevance.role_type)} · "
            f"{_human_seniority(assessment.relevance.seniority)}."
        ),
        "",
    ]

    coverage = assessment.skill_coverage
    lines.append(
        f"Обязательные навыки: подтверждено в профиле "
        f"{coverage.confirmed} из {coverage.total_required}."
    )

    missing = [
        item.requirement
        for item in assessment.skill_matches.required_skills
        if _enum_value(item.status) == "missing"
    ]

    unverified = [
        item.requirement
        for item in assessment.skill_matches.required_skills
        if _enum_value(item.status)
        not in {"confirmed", "missing"}
    ]

    for group in assessment.skill_matches.alternative_groups:
        if _enum_value(group.priority) != "required":
            continue

        if _enum_value(group.status) == "missing":
            missing.append(" или ".join(group.skills))
        elif _enum_value(group.status) != "confirmed":
            unverified.append(" или ".join(group.skills))

    if missing:
        lines.append("Не хватает: " + ", ".join(missing[:5]) + ".")
    elif not unverified:
        lines.append("Все найденные обязательные навыки подтверждены в профиле.")

    if unverified:
        lines.append(
            "Нужно проверить: " + ", ".join(unverified[:4]) + "."
        )

    preferred_missing = [
        item.requirement
        for item in assessment.skill_matches.preferred_skills
        if _enum_value(item.status) == "missing"
    ]

    if preferred_missing:
        lines.append(
            "Желательные навыки, не указанные в профиле: "
            + ", ".join(preferred_missing[:4]) + "."
        )

    for item in assessment.experience_matches:
        if item.priority != "required":
            continue

        required_months = math.ceil(item.min_years * 12)
        area = item.area or "профильного опыта"
        status = _enum_value(item.status)

        if status == "below_minimum":
            lines.append(
                f"Стаж: {item.confirmed_min_months} из "
                f"{required_months} требуемых месяцев ({area})."
            )
        elif status == "meets_minimum":
            lines.append(f"Требование по стажу выполнено: {area}.")
        elif status == "needs_confirmation":
            lines.append(f"Стаж требует подтверждения: {area}.")
        elif status == "area_not_evidenced":
            lines.append(f"Не найден подтверждённый опыт: {area}.")

    if assessment.duty_matches:
        statuses = [_enum_value(item.status) for item in assessment.duty_matches]
        confirmed = sum(
            status in {"confirmed_experience", "confirmed_skill_evidence"}
            for status in statuses
        )
        partial = statuses.count("partial")
        missing_duties = sum(
            status in {"no_evidence", "unclassified"}
            for status in statuses
        )
        lines.extend([
            "",
            (
                f"По рабочим задачам: {confirmed} совпадают, "
                f"{partial} совпадают частично, "
                f"{missing_duties} пока без подтверждений."
            ),
        ])

    authorization = assessment.eligibility.legal_work_authorization
    if authorization == "unknown":
        lines.append(
            "Оформление: возможность найма из твоей страны "
            "нужно уточнить у работодателя."
        )
    elif authorization == "eligible":
        lines.append("Оформление: ограничений по найму не выявлено.")
    else:
        lines.append(f"Оформление: {authorization}.")

    url = job.application_url or job.job_url
    if url:
        lines.extend(["", f"Вакансия и отклик: {url}"])

    return "\n".join(lines)






def _format_application_evidence_summary(
    report: ApplicationEvidenceReport,
    job: JobPosting,
) -> str:
    """Format a compact overview of application evidence."""
    skill_categories = {
        "required_skill",
        "preferred_skill",
        "unspecified_skill",
        "alternative_skills",
    }

    capability_names = {
        "test_data_preparation": "подготовка тестовых данных",
        "acceptance_testing": "приёмочное тестирование",
        "test_automation": "автоматизация тестирования",
        "release_participation": "участие в релизах",
        "test_project_maintenance": "сопровождение тестового проекта",
        "api_testing": "тестирование API",
        "manual_testing": "ручное тестирование",
        "regression_testing": "регрессионное тестирование",
        "test_documentation": "тестовая документация",
        "requirements_analysis": "анализ требований",
        "defect_reporting": "описание дефектов",
    }

    confirmed_skills: list[str] = []

    for item in report.items:
        if (
            item.category.value not in skill_categories
            or item.status.value != "confirmed"
        ):
            continue

        facts = [
            fact.text
            for fact in item.evidence
            if fact.usable_in_documents and fact.claim_scope == "skill"
        ]

        confirmed_skills.extend(facts or [item.requirement])

    confirmed_skills = list(dict.fromkeys(confirmed_skills))

    partial_items = [
        item
        for item in report.items
        if (
            item.status.value == "partial"
            and item.category.value != "experience"
        )
    ]

    needs_confirmation = [
        item.requirement
        for item in report.items
        if item.status.value == "needs_confirmation"
    ]

    no_evidence = [
        item.requirement
        for item in report.items
        if item.status.value == "no_evidence"
    ]

    lines = [
        "Краткая карта подготовки отклика",
        f"{job.title} — {job.company}",
        "",
        (
            f"✅ Подтверждено: {report.confirmed_count}/{len(report.items)} · "
            f"🟡 частично: {report.partial_count} · "
            f"🔎 уточнить: {report.needs_confirmation_count} · "
            f"⚪ без доказательств: {report.no_evidence_count}"
        ),
        f"Фактов для документов: {len(report.document_ready_facts)}",
    ]

    if confirmed_skills:
        lines.extend([
            "",
            "Сильные стороны профиля:",
            _short_text(", ".join(confirmed_skills), 650),
        ])

    if partial_items:
        lines.extend(["", "Частичные совпадения:"])

        for item in partial_items[:5]:
            missing = [
                capability_names.get(capability, capability.replace("_", " "))
                for capability in item.missing_capabilities
            ]

            detail = (
                ", ".join(missing)
                if missing
                else "требуется уточнить подтверждения"
            )
            lines.append(
                f"• {_short_text(item.requirement, 115)} — не хватает: {detail}"
            )

        if len(partial_items) > 5:
            lines.append(f"И ещё частичных совпадений: {len(partial_items) - 5}.")

    if needs_confirmation:
        lines.extend(["", "Требует проверки:"])

        for requirement in needs_confirmation[:5]:
            lines.append(f"• {_short_text(requirement, 130)}")

        if len(needs_confirmation) > 5:
            lines.append(
                f"И ещё требований для проверки: {len(needs_confirmation) - 5}."
            )

    if no_evidence:
        lines.extend(["", "Пока нет подтверждений:"])

        for requirement in no_evidence[:5]:
            lines.append(f"• {_short_text(requirement, 130)}")

        if len(no_evidence) > 5:
            lines.append(
                f"И ещё требований без подтверждений: {len(no_evidence) - 5}."
            )

    for item in report.items:
        if item.category.value != "experience":
            continue

        duration_facts = [
            fact
            for fact in item.evidence
            if fact.claim_scope == "confirmed_experience_duration"
            and fact.usable_in_documents
        ]

        if not duration_facts:
            continue

        fact = duration_facts[0]
        months_match = re.search(
            r"(\d+)\s+подтверждённых полных месяцев",
            fact.text,
        )
        minimum_match = re.search(
            r"минимум\s+(\d+(?:[.,]\d+)?)\s+года?",
            item.requirement,
        )
        area_match = re.search(
            r"в направлении\s+(.+)$",
            item.requirement,
        )

        if months_match and minimum_match:
            confirmed_months = int(months_match.group(1))
            minimum_months = round(
                float(minimum_match.group(1).replace(",", ".")) * 12
            )
            area = f" ({area_match.group(1)})" if area_match else ""

            lines.extend([
                "",
                (
                    f"Подтверждённый стаж{area}: "
                    f"{confirmed_months} из {minimum_months} месяцев."
                ),
            ])
        else:
            lines.extend(["", f"Стаж: {fact.text}"])

        break

    if report.warnings:
        lines.extend([
            "",
            "Примечание: часть данных профиля пока не используется "
            "как подтверждённые доказательства.",
        ])

    url = job.application_url or job.job_url
    if url:
        lines.extend(["", f"Вакансия: {url}"])

    lines.extend([
        "",
        "Подробности: /prepare " + job.id[:8] + " full",
        "Отклики не отправляются автоматически.",
    ])

    return "\n".join(lines)


def _format_application_evidence_report(
    report: ApplicationEvidenceReport,
    job: JobPosting,
    *,
    detailed: bool = False,
) -> str:
    """Format either a compact summary or the full evidence map."""
    if not detailed:
        return _format_application_evidence_summary(report, job)

    category_names = {
        "required_skill": "Обязательный навык",
        "preferred_skill": "Желательный навык",
        "unspecified_skill": "Дополнительный навык",
        "alternative_skills": "Альтернативные навыки",
        "responsibility": "Рабочая задача",
        "experience": "Опыт работы",
        "education": "Образование",
    }
    status_names = {
        "confirmed": "подтверждено",
        "partial": "частично подтверждено",
        "needs_confirmation": "нужно уточнить",
        "no_evidence": "нет подтверждений",
    }
    status_markers = {
        "confirmed": "✅",
        "partial": "🟡",
        "needs_confirmation": "🔎",
        "no_evidence": "⚪",
    }
    scope_names = {
        "skill": "Навык",
        "commercial_experience": "Коммерческий опыт",
        "work_responsibility": "Рабочая обязанность",
        "confirmed_experience_duration": "Продолжительность опыта",
        "education": "Образование",
    }

    lines = [
        "Подробная карта подготовки отклика",
        f"{job.title} — {job.company}",
        "",
        f"Всего требований: {len(report.items)}",
        (
            f"Подтверждено: {report.confirmed_count} · "
            f"частично: {report.partial_count} · "
            f"уточнить: {report.needs_confirmation_count} · "
            f"без доказательств: {report.no_evidence_count}"
        ),
        f"Фактов, разрешённых для документов: {len(report.document_ready_facts)}",
        "",
        "Проверка требований:",
    ]

    for item in report.items:
        category = category_names.get(item.category.value, item.category.value)
        status = item.status.value

        lines.append(
            f"{status_markers[status]} {category}: {item.requirement} "
            f"— {status_names[status]}"
        )

        if not item.evidence:
            if status == "no_evidence":
                lines.append("   • Подтверждения в профиле не найдены.")
            elif status == "needs_confirmation":
                lines.append("   • Требуется дополнительная проверка.")

        for fact in item.evidence:
            scope = scope_names.get(fact.claim_scope, fact.claim_scope)
            availability = (
                "можно использовать в документах"
                if fact.usable_in_documents
                else "пока нельзя использовать в документах"
            )
            detail = f"   • {scope}: {fact.text} — {availability}"

            if fact.context:
                detail += f" ({fact.context})"

            lines.append(detail)

            if fact.limitation:
                lines.append(f"     Ограничение: {fact.limitation}")

        if item.missing_capabilities:
            missing = ", ".join(item.missing_capabilities)
            lines.append(f"   Не покрыты компетенции: {missing}")

        if item.note:
            lines.append(f"   Примечание: {item.note}")

    if report.warnings:
        lines.extend(["", "Важные ограничения:"])
        lines.extend(f"• {warning}" for warning in report.warnings)

    url = job.application_url or job.job_url
    if url:
        lines.extend(["", f"Вакансия: {url}"])

    lines.extend([
        "",
        "Это подробная предварительная карта доказательств. "
        "Отклики не отправляются автоматически.",
    ])

    return "\n".join(lines)


class TelegramHandlers:
    def __init__(self, settings: Settings, profile_service: ProfileService) -> None:
        self.settings = settings
        self.profile_service = profile_service
        self._search_in_progress = False

    def _load_jobs(self, job_id: str | None = None) -> list[JobPosting]:
        """Load vacancies using a short-lived database session."""
        engine = make_engine(self.settings.database_path)

        try:
            session_factory = make_session_factory(engine)

            with session_factory() as session:
                repository = JobRepository(session)

                if job_id is not None:
                    return repository.find_by_id_or_prefix(job_id)

                return repository.all_jobs()
        finally:
            engine.dispose()

    def _load_valid_profile(self):
        report, profile = self.profile_service.validate_path(
            self.settings.profile_path
        )

        if profile is None or not report.valid:
            return None

        return profile

    @staticmethod
    def _command_argument(message: Message) -> str | None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return None
        return parts[1].strip() or None

    @staticmethod
    async def _answer_long_text(message: Message, text: str) -> None:
        for chunk in _split_message(text):
            await message.answer(chunk)

    @staticmethod
    def _format_job(job: JobPosting) -> str:
        lines = [
            f"{job.title} — {job.company}",
            (
                f"{_human_experience_level(job.experience_level)} · "
                f"{_human_workplace(job.workplace_type)}"
            ),
            _human_listing_status(job),
            _human_link_check(job),
        ]

        if job.location and job.location.casefold() not in {
            "unknown",
            "worldwide",
        }:
            lines.append(f"Местоположение: {job.location}")
        elif job.location and job.location.casefold() == "worldwide":
            lines.append("Можно работать из любой страны — по данным площадки.")

        if job.salary_min is not None or job.salary_max is not None:
            low = job.salary_min if job.salary_min is not None else "?"
            high = job.salary_max if job.salary_max is not None else "?"
            currency = job.salary_currency or ""
            lines.append(f"Зарплата: {low}–{high} {currency}".strip())
        else:
            lines.append("Зарплата в объявлении не указана.")

        requirements = extract_job_requirements(job.description)
        duties = requirements.responsibilities[:4]

        if duties:
            lines.extend(["", "Что предстоит делать:"])
            lines.extend(f"• {_short_text(duty)}" for duty in duties)

            remaining = len(requirements.responsibilities) - len(duties)
            if remaining:
                lines.append(f"• И ещё {remaining} задач.")
        else:
            clean_description = clean_job_description(job.description)
            description_lines = [
                line for line in clean_description.splitlines() if line.strip()
            ][:3]

            if description_lines:
                lines.extend(["", "О вакансии:"])
                lines.extend(_short_text(line) for line in description_lines)

        lines.extend(["", f"Номер вакансии: {job.id[:8]}"])
        lines.append(f"Оценить соответствие профилю: /assess {job.id[:8]}")

        url = job.application_url or job.job_url
        if url:
            lines.append(f"Подробнее и отклик: {url}")

        return "\n".join(lines)

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
        report, profile = self.profile_service.validate_path(
            self.settings.profile_path
        )

        if profile is None:
            await message.answer(PROFILE_ERROR)
            return

        summary = self.profile_service.format_telegram_summary(profile)
        extra = "" if report.valid else "\n\nWarning: profile validation reported errors."
        await message.answer(summary + extra)

    async def cmd_search(self, message: Message) -> None:
        """Search enabled job sources with a persistent global cooldown."""
        if self._search_in_progress:
            await message.answer("Поиск уже выполняется. Дождись его завершения.")
            return

        if self._command_argument(message):
            await message.answer("Используй просто /search, без дополнительных аргументов.")
            return

        self._search_in_progress = True

        try:
            await message.answer(
                "Проверяю ограничения источников и запускаю поиск вакансий…"
            )

            report, remaining = await asyncio.to_thread(
                _execute_job_search,
                self.settings,
            )

            if remaining is not None:
                await message.answer(_format_search_cooldown(remaining))
                return

            if report is None:
                raise RuntimeError("Job search returned neither report nor cooldown")

            await self._answer_long_text(
                message,
                _format_discovery_report(report),
            )
        except FileNotFoundError:
            logger.exception("Job search configuration file was not found")
            await message.answer(
                "Не удалось найти файл настроек поиска. "
                "Проверь config/job_search.yaml."
            )
        except Exception:
            logger.exception("Telegram job search failed")
            await message.answer(
                "Не удалось завершить поиск из-за внутренней ошибки. "
                "Подробности записаны в журнал приложения."
            )
        finally:
            self._search_in_progress = False

    async def cmd_jobs(self, message: Message) -> None:
        """Show a short, human-readable QA vacancy shortlist."""
        profile = self._load_valid_profile()

        if profile is None:
            await message.answer(PROFILE_ERROR)
            return

        jobs = self._load_jobs()
        if not jobs:
            await message.answer(
                "Пока нет сохранённых вакансий. "
                "Запусти поиск командой /search."
            )
            return

        fit_order = {
            CandidateFitStatus.TARGET_FIT: 0,
            CandidateFitStatus.POTENTIAL_STRETCH: 1,
            CandidateFitStatus.NEEDS_REVIEW: 2,
        }

        fit_labels = {
            CandidateFitStatus.TARGET_FIT: "✅ Целевая роль и уровень",
            CandidateFitStatus.POTENTIAL_STRETCH: "🟠 Можно рассмотреть",
            CandidateFitStatus.NEEDS_REVIEW: "🔎 Нужно проверить",
        }

        included = []
        excluded_count = 0
        expired_count = 0
        relevant_count = 0
        counts = {
            CandidateFitStatus.TARGET_FIT: 0,
            CandidateFitStatus.POTENTIAL_STRETCH: 0,
            CandidateFitStatus.NEEDS_REVIEW: 0,
        }

        for job in jobs:
            assessment = assess_candidate_job(job, profile)

            if assessment.relevance.status is RelevanceStatus.IRRELEVANT:
                continue

            relevant_count += 1

            listing_status = getattr(job, "listing_status", None)
            if (
                callable(listing_status)
                and _enum_value(listing_status()) == ListingStatus.EXPIRED.value
            ):
                expired_count += 1
                continue

            fit_status = assessment.candidate_fit.status

            if fit_status is CandidateFitStatus.OUT_OF_SCOPE:
                excluded_count += 1
                continue

            counts[fit_status] = counts.get(fit_status, 0) + 1
            score = assessment.match_score
            observed = score.observed_score if score is not None else None

            included.append((
                fit_order.get(fit_status, 2),
                observed,
                job,
                assessment,
            ))

        included.sort(
            key=lambda item: (
                item[0],
                -(item[1] if item[1] is not None else -1),
                item[2].title.casefold(),
            )
        )

        if not included:
            lines = [
                "Пока не нашлось актуальных вакансий в твоём целевом направлении "
                "и диапазоне опыта."
            ]

            if expired_count:
                lines.append(
                    f"Исключено по истёкшему сроку публикации: {expired_count}."
                )

            await message.answer("\\n".join(lines))
            return

        lines = [
            "Подборка QA-вакансий",
            f"В базе найдено: {relevant_count}",
            (
                f"Целевая роль и уровень: {counts[CandidateFitStatus.TARGET_FIT]} · "
                f"Можно рассмотреть выше уровня: "
                f"{counts[CandidateFitStatus.POTENTIAL_STRETCH]} · "
                f"Нужна проверка: {counts[CandidateFitStatus.NEEDS_REVIEW]} · "
                f"Не подходят по уровню: {excluded_count}"
            ),
            f"Исключено по истёкшему сроку публикации: {expired_count}",
            "",
            "Оценка приблизительная: важнее проверить требования и стаж.",
            "",
        ]

        limit = 5

        for _rank, _observed, job, assessment in included[:limit]:
            fit_status = assessment.candidate_fit.status
            score = assessment.match_score

            lines.append(fit_labels[fit_status])
            lines.append(f"{job.title} — {job.company}")
            lines.append(
                f"{_human_seniority(assessment.relevance.seniority)} · "
                f"{_human_workplace(job.workplace_type)}"
            )
            lines.append(_human_short_link_check(job))

            # Avoid presenting an unreviewed score as a reliable recommendation.
            if score is not None and score.observed_score is not None:
                if (
                    _enum_value(score.status) != "needs_review"
                    or fit_status is CandidateFitStatus.TARGET_FIT
                ):
                    lines.append(
                        f"Предварительная оценка: {score.observed_score:.1f}/100"
                    )

            lines.append(_assessment_note(assessment))
            lines.extend([
                f"Вакансия: /job {job.id[:8]}",
                f"Оценка: /assess {job.id[:8]}",
            ])
            lines.append("")

        if len(included) > limit:
            lines.append(f"И ещё {len(included) - limit} вакансий в подборке.")

        await message.answer("\n".join(lines).strip())

    async def cmd_job(self, message: Message) -> None:
        """Show a compact vacancy card by full ID or unique prefix."""
        job_id = self._command_argument(message)

        if job_id is None:
            await message.answer("Usage: /job <job_id>")
            return

        matches = self._load_jobs(job_id)

        if not matches:
            await message.answer("No job found for this ID.")
            return

        if len(matches) > 1:
            await message.answer(
                "This ID matches several jobs. Please provide a longer ID."
            )
            return

        job = matches[0]

        try:
            checked_job = await asyncio.to_thread(
                check_job_link,
                self.settings.database_path,
                job.id,
            )
            if checked_job is not None:
                job = checked_job
        except Exception:
            # A failed status check must never prevent the user from seeing the card.
            logger.exception("Job link check failed job_id=%s", job.id)

        await message.answer(self._format_job(job))

    async def cmd_assess(self, message: Message) -> None:
        """Show a compact profile assessment for one stored vacancy."""
        job_id = self._command_argument(message)

        if job_id is None:
            await message.answer("Usage: /assess <job_id>")
            return

        matches = self._load_jobs(job_id)

        if not matches:
            await message.answer("No job found for this ID.")
            return

        if len(matches) > 1:
            await message.answer(
                "This ID matches several jobs. Please provide a longer ID."
            )
            return

        profile = self._load_valid_profile()
        if profile is None:
            await message.answer(PROFILE_ERROR)
            return

        job = matches[0]
        assessment = assess_candidate_job(job, profile)
        summary = _format_assessment_summary(assessment, job)

        await message.answer(summary)



    async def cmd_prepare(self, message: Message) -> None:
        """Build a compact or detailed evidence map for an application."""
        parts = (message.text or "").split()

        if (
            len(parts) not in {2, 3}
            or (len(parts) == 3 and parts[2].casefold() != "full")
        ):
            await message.answer(
                "Использование: /prepare <job_id> [full]\n"
                "Добавь full, чтобы открыть подробную карту."
            )
            return

        job_id = parts[1]
        detailed = len(parts) == 3

        matches = self._load_jobs(job_id)

        if not matches:
            await message.answer("Не удалось найти вакансию по этому ID.")
            return

        if len(matches) > 1:
            await message.answer(
                "Этот ID соответствует нескольким вакансиям. "
                "Укажи более длинный ID."
            )
            return

        profile = self._load_valid_profile()
        if profile is None:
            await message.answer(PROFILE_ERROR)
            return

        job = matches[0]

        try:
            report = build_application_evidence(job, profile)
            result = _format_application_evidence_report(
                report,
                job,
                detailed=detailed,
            )
            await self._answer_long_text(message, result)
        except Exception:
            logger.exception(
                "Application evidence preparation failed job_id=%s",
                job.id,
            )
            await message.answer(
                "Не удалось подготовить карту доказательств. "
                "Подробности записаны в журнал приложения."
            )

def build_router(settings: Settings, profile_service: ProfileService) -> Router:
    handlers = TelegramHandlers(settings, profile_service)
    router = Router(name="telegram_commands")

    router.message.register(handlers.cmd_start, Command("start"))
    router.message.register(handlers.cmd_help, Command("help"))
    router.message.register(handlers.cmd_whoami, Command("whoami"))
    router.message.register(handlers.cmd_status, Command("status"))
    router.message.register(handlers.cmd_profile, Command("profile"))
    router.message.register(handlers.cmd_search, Command("search"))
    router.message.register(handlers.cmd_jobs, Command("jobs"))
    router.message.register(handlers.cmd_job, Command("job"))
    router.message.register(handlers.cmd_assess, Command("assess"))
    router.message.register(handlers.cmd_prepare, Command("prepare"))

    return router
