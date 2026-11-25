# Architecture — Personal Career Agent

## Why a modular monolith

We need one local Python process that is easy to run, debug, and extend.
Microservices would add network, deployment, and operational cost with no benefit
for a single-user agent on a Mac.

A **modular monolith** means:

- one package (`career_agent`);
- clear folders for domain, services, integrations, and workflows;
- modules talk through Python interfaces, not HTTP (FastAPI appears only when a
  real HTTP surface is needed).

## Recommended stack (stage 1 vs later)

| Need | Choice | Why |
|---|---|---|
| Language | Python 3.12+ (local default: **3.13**) | Specified; 3.13 is installed and more mature than 3.14 for libraries |
| Data shapes | Pydantic v2 | Validation of the Candidate Profile and later job records |
| Settings | pydantic-settings | Typed config from `.env` without extra frameworks |
| CLI | stdlib `argparse` | Enough for `profile validate`; no Click yet |
| Tests | pytest | Specified |
| Lint | Ruff | Fast, one tool for format + lint |
| DB (stage 3) | SQLite + SQLAlchemy 2 | Local file; Alembic later if schema churns |
| Telegram (stage 2) | aiogram 3 + long polling | Personal UI; allow-listed user ID |
| HTTP (stage 3) | HTTPX | Timeouts, no infinite retries |
| Mail (later) | Gmail API + OAuth 2.0 | No passwords; secrets stay off Git |
| Secrets (later) | `.env` now, macOS Keychain for OAuth tokens | Tokens must not be committed |
| LLM (later) | Interface + optional Ollama | Core logic must run without an LLM |

**Python 3.14 is installed** via Homebrew as `python3`. Packaging support can lag
on brand-new versions, so the documented local interpreter is **Python 3.13**
(`/opt/homebrew/bin/python3.13`).

Dependencies are added **only when a module needs them**. Stage 3 adds `httpx`,
`SQLAlchemy`, and `PyYAML`. Still no FastAPI, Gmail, or LLM libraries.

## Package layout

```text
career-agent/
├── docs/                      # Stage 0 design (this folder)
├── data/
│   ├── candidate_profile.example.json   # safe template (in Git)
│   └── candidate_profile.json           # real profile (gitignored)
├── src/career_agent/
│   ├── config.py              # settings from environment
│   ├── config_loader.py       # YAML job-search settings
│   ├── main.py                # CLI entry
│   ├── domain/                # Candidate Profile + JobPosting
│   ├── services/              # profile + job discovery
│   ├── repositories/          # SQLite job store
│   ├── integrations/telegram/
│   ├── integrations/job_sources/  # Remotive, Adzuna
│   └── workflows/
└── tests/
```

### How data flows (target design)

```text
Candidate Profile (JSON, private)
        │
        ▼
  ProfileService  ── validates, hides unconfirmed facts from documents
        │
        ├── Job Discovery (stage 3) ──► SQLite job_postings
        │         │
        │         ▼
        ├── Job Matcher (later) ──► score + explanation
        │         │
        │         ▼
        ├── Application Assistant (later) ──► CV / letter drafts
        │         │
        │         ▼
        └── Application Tracker (later)
                  │
      Telegram UI (stage 2)     Gmail (later, read then drafts)
```

Stage 2 adds a **local Telegram bot** on top of the Candidate Profile. Handlers
call `ProfileService`; they do not parse the JSON themselves.

Telegram layout:

```text
integrations/telegram/
├── auth.py         # who is allowed to run which command
├── middleware.py   # one access check for every message
├── handlers.py     # /start /help /whoami /status /profile
├── bot.py          # Bot + Dispatcher factory
└── runner.py       # long polling; missing-token exit
```

## Domain rules that every module must follow

1. **Candidate Profile is the only source of facts.** If a field is missing,
   mark it; do not fill it with a guess.
2. **Verification status** on fields: `confirmed`, `imported_from_cv`,
   `needs_confirmation`, `unknown`.
3. Document generation (later) may use **`confirmed` values only**.
   `imported_from_cv` needs an explicit user confirmation step before it
   appears in a tailored CV. Dates with month precision (Innotech: 2026-03) must
   not be expanded to a fake day.
4. **Unknown ≠ eligible.** Work authorization, salary, and visa flags default
   to unknown.
5. Ethical hard exclusions beat any match score.
6. Duplicate jobs are one job (later, via canonical URL + company + title).
7. No irreversible external action without user confirmation at Level 1–2.

## Match weights (stored in profile preferences, used from stage 4)

Default weights, user-editable later:

| Criterion | Weight |
|---|---:|
| Role and duties fit | 25 |
| Technical skills fit | 25 |
| Geography and hiring feasibility | 25 |
| Salary and contract | 15 |
| Ethics | 10 |

## Integration boundaries

| System | Allowed now | Never |
|---|---|---|
| Job boards | Remotive public API; Adzuna with keys | CAPTCHA bypass, closed APIs, login circumvention |
| LinkedIn | Store URLs; draft text for manual send | Scraping, automated InMail |
| Gmail | Later: OAuth, read, then drafts | Password login; deleting mail; changing Gmail settings |
| Telegram | Local long polling, allow-listed user ID | Logging tokens or message bodies |
| LLM | Later: optional, consent for PII | Silent upload of CV/mail to a vendor |

Gmail OAuth with mail-read scope can see **the whole mailbox**, not only
recruiter mail. Application-level filters come after that. This must be
explained again before connecting Gmail.

## Persistence plan

- Stage 1: JSON file for the profile.
- Next persistence: SQLite file under `data/` (gitignored).
- PostgreSQL only if we outgrow SQLite (multi-device / server in stage 8).

## Process model

One CLI process. `python -m career_agent bot run` uses Telegram long polling and
only works while this Mac is awake. Periodic search (APScheduler) waits until a
later stage. Do not promise background search while the Mac is asleep.

## Alternatives considered

| Topic | Alternative | Why we did not take it now |
|---|---|---|
| App framework | FastAPI from day one | No HTTP clients yet; extra surface |
| DB | PostgreSQL immediately | Needs a running server; SQLite is enough locally |
| Profile storage | YAML | JSON matches Pydantic dump/load with less ambiguity |
| Package manager | uv | Not installed; stdlib venv + pip needs no extra global tool |
| LLM-first matching | Always call a model | Cost, PII, and RAM; rules-based matching must work offline |
