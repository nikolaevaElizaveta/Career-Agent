# Agent and developer rules

These rules apply to humans and to AI assistants working in this repository.

## Product

- This is a **personal** job-search agent for Elizaveta Nikolaeva, not a generic demo.
- Autonomy Level 1 until a later stage is explicitly started.
- Do not implement Gmail, job scraping, or LLMs unless the current stage asks
  for them.

## Facts

- Candidate Profile is the only source of employment facts.
- Never invent experience, metrics, employers, or skills.
- Never use unconfirmed values on generated documents.
- Innotech start is confirmed as March 2026 at month precision. Never invent a day.
- Contact email in all new materials: only the address stored as confirmed in
  the private profile (the assignment specifies `[private email stored in local profile]`).
- Do not call the candidate Senior / Advanced / Expert.

## Ethics and matching

- Hard-exclude: government/military, gambling, surveillance/spyware, tobacco, adult.
- Crypto and oil/gas are allowed but lower priority.
- No unpaid jobs. Flag large take-home assignments.
- Unknown work authorization is `Unknown`, not `Eligible`.
- “Remote” is not automatically “hires from Russia”.

## Security

- Keep `data/candidate_profile.json`, `.env`, tokens, and databases out of Git.
- No Gmail passwords. OAuth only, later.
- No secrets in logs.
- Telegram must be allow-listed by user ID.
- No CAPTCHA/auth bypass. No LinkedIn automation.

## Engineering

- Python 3.12+, typed, Pydantic v2, small modules.
- Add dependencies only when a stage needs them.
- Tests for critical profile/matching logic; run them before claiming they pass.
- Async only where it helps (Telegram/HTTP later).
- Explain architecture in plain language after each stage.
- Do not install global Homebrew packages or change macOS settings without asking.
- Do not delete files destructively without asking.

## Git

- Do not commit the private profile.
- Do not skip hooks.
- Do not push unless asked.
