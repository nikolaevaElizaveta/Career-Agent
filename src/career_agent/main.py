"""Command-line interface for Career Agent."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from career_agent.cli.job_assessment import format_candidate_assessment
from career_agent.cli.jobs import (
    format_eligible_jobs,
    format_job_detail,
    format_job_list,
    format_relevant_jobs,
    format_report,
)
from career_agent.cli.profile import format_profile_skills
from career_agent.cli.profile_review import run_profile_review
from career_agent.config import Settings, get_settings
from career_agent.config_loader import load_job_search_config
from career_agent.integrations.job_sources.factory import build_sources
from career_agent.integrations.job_sources.rate_limit import (
    DEFAULT_SEARCH_COOLDOWN,
    SqliteSearchCooldown,
)
from career_agent.integrations.telegram.runner import run_bot
from career_agent.repositories.db import make_engine, make_session_factory
from career_agent.repositories.job_repository import JobRepository
from career_agent.services.job_candidate_assessment import assess_candidate_job
from career_agent.services.job_discovery import JobDiscoveryService
from career_agent.services.profile_service import ProfileService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="career-agent",
        description="Personal Career Agent — local job-search assistant.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile", help="Candidate Profile commands")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    validate = profile_sub.add_parser("validate", help="Validate the local profile JSON")
    validate.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to profile JSON (default: CAREER_AGENT_PROFILE_PATH)",
    )
    skills = profile_sub.add_parser(
        "skills",
        help="Show candidate skills and verification statuses",
    )
    skills.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to profile JSON (default: CAREER_AGENT_PROFILE_PATH)",
    )

    review = profile_sub.add_parser(
        "review",
        help="Interactively review candidate skills",
    )
    review.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to profile JSON (default: CAREER_AGENT_PROFILE_PATH)",
    )

    bot = subparsers.add_parser("bot", help="Telegram bot commands")
    bot_sub = bot.add_subparsers(dest="bot_command", required=True)
    bot_sub.add_parser("run", help="Start the Telegram bot (local long polling)")

    jobs = subparsers.add_parser("jobs", help="Job discovery commands")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    search = jobs_sub.add_parser("search", help="Fetch jobs from enabled sources")
    search.add_argument(
        "--source",
        choices=["remotive", "himalayas", "adzuna"],
        default=None,
        help="Limit the run to one source",
    )
    listing = jobs_sub.add_parser("list", help="Show stored jobs")
    listing.add_argument("--limit", type=int, default=20, help="Maximum rows to show")
    jobs_sub.add_parser(
        "relevant",
        help="Show relevant and review-needed vacancies",
    )
    jobs_sub.add_parser(
        "eligible",
        help="Show QA vacancies compatible with source-level Russia restrictions",
    )
    show = jobs_sub.add_parser("show", help="Show one stored job")
    show.add_argument("job_id", help="Full job id or a unique prefix")
    assess = jobs_sub.add_parser(
        "assess",
        help="Assess one vacancy against the Candidate Profile",
    )
    assess.add_argument(
        "job_id",
        help="Full job id or a unique prefix",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(message)s")

    # HTTPX logs full request URLs at INFO. Adzuna credentials
    # are passed as query parameters, so keep transport logs quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


    if args.command == "profile" and args.profile_command == "validate":
        return _validate_profile(args.path or settings.profile_path)
    if args.command == "profile" and args.profile_command == "skills":
        return _show_profile_skills(args.path or settings.profile_path)
    if args.command == "profile" and args.profile_command == "review":
        return run_profile_review(args.path or settings.profile_path)
    if args.command == "bot" and args.bot_command == "run":
        return run_bot(settings)
    if args.command == "jobs":
        return _jobs_command(args, settings)
    return 1


def _validate_profile(path: Path) -> int:
    service = ProfileService()
    report, _profile = service.validate_path(path)
    print(service.format_report(report))
    return 0 if report.valid else 1


def _show_profile_skills(path: Path) -> int:
    service = ProfileService()
    report, profile = service.validate_path(path)

    if profile is None:
        print(service.format_report(report), file=sys.stderr)
        return 1

    if not report.valid:
        print(
            "Warning: Candidate Profile has validation issues. "
            "Skills are displayed, but the profile should be reviewed.",
            file=sys.stderr,
        )

    print(format_profile_skills(profile))
    return 0


def _jobs_command(args: argparse.Namespace, settings: Settings) -> int:
    session_factory = make_session_factory(make_engine(settings.database_path))
    session = session_factory()
    try:
        repository = JobRepository(session)

        if args.jobs_command == "search":
            remaining = SqliteSearchCooldown(
                session,
                DEFAULT_SEARCH_COOLDOWN,
            ).reserve()

            if remaining is not None:
                total_minutes = max(
                    1,
                    (int(remaining.total_seconds()) + 59) // 60,
                )
                hours, minutes = divmod(total_minutes, 60)

                if hours and minutes:
                    wait = f"{hours}h {minutes}m"
                elif hours:
                    wait = f"{hours}h"
                else:
                    wait = f"{minutes}m"

                print(f"Search cooldown is active. Try again in {wait}.")
                return 0

            search_config = load_job_search_config(settings.job_search_config_path)
            sources = build_sources(settings, search_config, session)
            report = JobDiscoveryService(repository, sources).search(args.source)
            print(format_report(report))
            return 0

        if args.jobs_command == "list":
            limit = max(args.limit, 0)
            print(format_job_list(repository.list_jobs(limit=limit)))
            return 0

        if args.jobs_command == "relevant":
            print(format_relevant_jobs(repository.all_jobs()))
            return 0

        if args.jobs_command == "eligible":
            profile_report, profile = ProfileService().validate_path(
                settings.profile_path
            )

            if profile is None or not profile_report.valid:
                print(
                    "Cannot assess candidate fit: Candidate Profile is invalid. "
                    "Run 'python -m career_agent profile validate'.",
                    file=sys.stderr,
                )
                return 1

            print(
                format_eligible_jobs(
                    repository.all_jobs(),
                    profile.career_preferences,
                )
            )
            return 0

        if args.jobs_command == "assess":
            matches = repository.find_by_id_or_prefix(args.job_id)

            if not matches:
                print(
                    f"No job found for id '{args.job_id}'.",
                    file=sys.stderr,
                )
                return 1

            if len(matches) > 1:
                print(
                    f"Id prefix '{args.job_id}' matches "
                    f"{len(matches)} jobs. Use a longer id.",
                    file=sys.stderr,
                )
                return 1

            profile_report, profile = ProfileService().validate_path(
                settings.profile_path
            )

            if profile is None or not profile_report.valid:
                print(
                    "Cannot assess candidate fit: Candidate Profile is invalid. "
                    "Run 'python -m career_agent profile validate'.",
                    file=sys.stderr,
                )
                return 1

            assessment = assess_candidate_job(matches[0], profile)
            print(format_candidate_assessment(assessment))
            return 0

        if args.jobs_command == "show":
            matches = repository.find_by_id_or_prefix(args.job_id)

            if not matches:
                print(
                    f"No job found for id '{args.job_id}'.",
                    file=sys.stderr,
                )
                return 1

            if len(matches) > 1:
                print(
                    f"Id prefix '{args.job_id}' matches "
                    f"{len(matches)} jobs. Use a longer id.",
                    file=sys.stderr,
                )
                return 1

            print(format_job_detail(matches[0]))
            return 0

        return 1
    finally:
        session.close()

if __name__ == "__main__":
    sys.exit(main())
