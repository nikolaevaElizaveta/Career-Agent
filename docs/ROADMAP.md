# Roadmap

Work in sequence. Do not implement later stages “because they are interesting”.

## Stage 0 — Design (this pass)

- [x] Inspect the project folder
- [x] Record architecture, security, sources, and agent rules
- [x] List unconfirmed facts (Telegram numeric ID, skill levels). Innotech start
      is now confirmed as March 2026 (month precision).

## Stage 1 — Infrastructure and Candidate Profile (this pass)

- [x] Python package, `pyproject.toml`, gitignore, `.env.example`
- [x] Pydantic Candidate Profile
- [x] Safe example JSON + private local JSON
- [x] `python -m career_agent profile validate`
- [x] Tests for validation and confirmation status

**Done when:** install works on the Mac, profile validates, tests pass, private
profile is gitignored.

## Stage 2 — Telegram bot (this pass)

- [x] Allow-list by Telegram user ID
- [x] Commands: `/start`, `/help`, `/whoami`, `/profile`, `/status`
- [x] Long polling locally (`python -m career_agent bot run`)
- [x] Until `TELEGRAM_ALLOWED_USER_ID` is set, only `/whoami` works
- [ ] Owner sets BotFather token and numeric user ID in local `.env`

No Gmail, no job scraping.

## Stage 3 — Job Discovery

- Source interface
- Manual add-by-URL
- First legal free sources (see `DATA_SOURCES.md`)
- Parse, deduplicate, store
- No LinkedIn scraping

## Stage 4 — Job Matcher

- Hard ethical filters
- Weighted score with unknown-aware logic
- Explanation: matches, gaps, blockers, recommended action
- User-editable weights

## Stage 5 — Application Assistant and Tracker

- Tailored CV and cover letter from confirmed facts
- Preview + user confirmation
- Tracker statuses; `applied` only after confirmed send
- Flag oversized take-home tests

## Stage 6 — Gmail (official API)

- Explain mailbox-wide read scope **before** OAuth
- Keychain (or equivalent) for tokens
- Read → classify → drafts → send only after confirm
- Never log mail bodies or tokens

## Stage 7 — Networking

- Public company pages and public contacts
- Personal drafts (RU vs EN by audience)
- Manual send; no LinkedIn automation

## Stage 8 — Scheduler and optional hosting

- APScheduler while the Mac is awake
- Honest limit: sleep/shutdown stops the agent
- Backup of SQLite + profile
- Cost check before any server

## Explicitly not in v1

Autonomy Level 3, paid job APIs, Playwright unless a specific allowed flow needs
it, FastAPI, Ollama, and any cloud LLM.
