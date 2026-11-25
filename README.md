# Personal Career Agent

Local assistant for international job search: profile, Telegram UI, later job
discovery, matching, applications, and Gmail.

This repository currently includes **stages 0–3**: design, Candidate Profile,
a personal Telegram bot, and Job Discovery (Remotive + optional Adzuna).
Gmail and language models are **not** connected yet.

## What works today

- Structured Candidate Profile (JSON) with a verification status on each fact.
- Validate the profile:

```bash
python -m career_agent profile validate
```

- Local Telegram bot (`/start`, `/help`, `/whoami`, `/status`, `/profile`, `/jobs`)
  locked to your numeric user ID.
- Job search from the terminal (Remotive public API; Adzuna if keys are set).

The command prints whether the profile file is valid, which required data is
missing, and which values still need confirmation.

**Innotech start date** is confirmed as **March 2026**. Only the month and year
are stored (`2026-03`). The agent will not invent a day of the month.

## Requirements (this Mac)

Checked on this machine:

| Tool | Found | Notes |
|---|---|---|
| macOS | 26.6.2, Apple Silicon (`arm64`) | Fits the project target |
| Python 3.13.7 | `/opt/homebrew/bin/python3.13` | **Use this** |
| Python 3.14.3 | `/opt/homebrew/bin/python3` | Installed, but 3.13 is the safer default |
| Git | 2.51.0 | Present |
| uv / Ruff (global) | not installed | Ruff is installed **inside** the project venv |

The project requires **Python 3.12 or newer**. Do not install extra Homebrew packages
unless we agree to that.

## Install (once)

From the project folder:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If `python -m career_agent` says `No module named career_agent`, macOS may have marked a setuptools file as hidden (Python 3.13 then skips it). Use either:

```bash
export PYTHONPATH=src
python -m career_agent profile validate
```

or reinstall in compatibility mode:

```bash
python -m pip install -e ".[dev]" --config-settings editable_mode=compat
```

The private profile is already at `data/candidate_profile.json` on this computer.
That file is listed in `.gitignore` so Git will not publish email, Telegram, or LinkedIn.

If you clone the repo on another machine, create a private profile from the template:

```bash
cp data/candidate_profile.example.json data/candidate_profile.json
```

Then edit the copy. Do not put real contacts into the example file.

```bash
cp .env.example .env
```

Fill Telegram values in `.env` locally. **Do not paste the bot token into Cursor
or ChatGPT.**

## Commands

```bash
source .venv/bin/activate

# Validate the private profile
python -m career_agent profile validate

# Validate the safe template
python -m career_agent profile validate --path data/candidate_profile.example.json

# Start the Telegram bot (needs TELEGRAM_BOT_TOKEN in .env)
python -m career_agent bot run

# Job discovery
python -m career_agent jobs search
python -m career_agent jobs search --source remotive
python -m career_agent jobs list --limit 10
python -m career_agent jobs show <id>

# Tests
pytest

# Lint (optional)
ruff check src tests
```

Exit code `0` on `profile validate` means the profile is usable. Warnings about
`needs_confirmation` do **not** fail the command by themselves. Missing email,
name, or a broken JSON file fails with exit code `1`.

If the bot token is missing, `bot run` prints a short instruction and exits
with code `1` — it does not start polling.

If Adzuna keys are missing, `jobs search` still runs Remotive and prints why
Adzuna was skipped.

## Job discovery

Keywords, countries, and enabled sources: `config/job_search.yaml`.

| Source | Key | Notes |
|---|---|---|
| Remotive | none | QA category, max 4 calls / day and 2 / minute, 24h publish delay |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional. Markets `gb`, `es`, `au` |

Jobs are stored in `data/career_agent.sqlite` (gitignored).

Dedup: the same `source` + `source_job_id` is stored once. The same company and
title (or the same URL) from two boards is kept as a probable duplicate with
both links. Two companies with the same title are not merged.

Unknown salary, unknown remote eligibility, and “Remote” in the text are **not**
treated as a match for working from Russia.

Telegram `/jobs` only points to these CLI commands until we review the listings.

## Telegram bot setup

This is a **personal** bot. Anyone who finds the username can send it a message,
so access is limited by numeric user ID.

### 1. Create the bot in Telegram

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts (display name and username).
3. BotFather replies with a token that looks like `123456:ABC...`.
4. Copy that token **only** into your local `.env` file (next step).
5. Do not commit it. Do not paste it into this chat.

### 2. Store the token

In the project folder:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
TELEGRAM_BOT_TOKEN=paste_the_token_here
TELEGRAM_ALLOWED_USER_ID=
```

Leave `TELEGRAM_ALLOWED_USER_ID` empty for the first start.

### 3. Start the bot

```bash
source .venv/bin/activate
python -m career_agent bot run
```

Leave this terminal open. Long polling works only while the Mac is awake and
this process is running.

### 4. Learn your numeric user ID

In Telegram, open **your** bot and send `/whoami`.

The bot replies with a number, for example `123456789`. That number is the user
ID. `@nikolaevalizza` is a username, not the ID.

Until the ID is saved, `/whoami` is the only working command. `/profile` stays
blocked so a stranger cannot read the CV during setup.

### 5. Lock the bot to you

Stop the bot (`Ctrl+C`). In `.env` set:

```bash
TELEGRAM_ALLOWED_USER_ID=123456789
```

Use **your** number from `/whoami`. Start the bot again.

### 6. Check that access is protected

- From your account: `/start`, `/help`, `/status`, `/profile` should work.
- `/profile` should show a short summary from Candidate Profile (name, email,
  roles including Innotech from 2026-03).
- From another Telegram account, or before the ID is set, `/profile` must **not**
  show personal data. Other people should see a short “no access” message.

If you ever leak the token, revoke it in BotFather (`/revoke`) and put a new
token in `.env`.

## How the profile works

Every important fact is stored as `{ "value": ..., "status": "..." }`.

| Status | Meaning | Used on a generated CV? |
|---|---|---|
| `confirmed` | You stand behind this fact | Yes |
| `imported_from_cv` | Copied from a resume | Not until you confirm it |
| `needs_confirmation` | Conflict or gap | Never |
| `unknown` | We do not know | Never — and never treated as “yes” |

Employment dates can be stored with **month precision** (`PartialDate`), so
March 2026 is `2026-03`, not `2026-03-01`.

## Privacy

Never commit:

- `data/candidate_profile.json`
- `.env`
- Telegram bot tokens
- Gmail tokens (later)
- SQLite databases (later)

See `docs/SECURITY.md`.

## Documentation

- `docs/PROJECT_SPEC.md` — what we are building
- `docs/ARCHITECTURE.md` — how the code is organized
- `docs/ROADMAP.md` — stages 0–8
- `docs/DATA_SOURCES.md` — legal job sources (future)
- `AGENTS.md` — rules for later development

## Next stage

Stage 4: Job Matcher. Not started yet.
