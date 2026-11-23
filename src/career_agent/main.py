"""Command-line interface for Career Agent."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from career_agent.config import get_settings
from career_agent.integrations.telegram.runner import run_bot
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

    bot = subparsers.add_parser("bot", help="Telegram bot commands")
    bot_sub = bot.add_subparsers(dest="bot_command", required=True)
    bot_sub.add_parser("run", help="Start the Telegram bot (local long polling)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(message)s")

    if args.command == "profile" and args.profile_command == "validate":
        return _validate_profile(args.path or settings.profile_path)
    if args.command == "bot" and args.bot_command == "run":
        return run_bot(settings)
    return 1


def _validate_profile(path: Path) -> int:
    service = ProfileService()
    report, _profile = service.validate_path(path)
    print(service.format_report(report))
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())
