# Security

This agent will eventually read mail and hold a CV. Treat it as a personal
data system, not as a demo.

## Secrets

- Real values live in `.env` (gitignored) or, for OAuth tokens later, macOS Keychain.
- `.env.example` contains **names and placeholders only**.
- Never commit tokens, Gmail client secrets, SQLite dumps of private data, or
  `data/candidate_profile.json`.
- Never print tokens, passwords, Adzuna keys, or email bodies in logs.
- SQLite files under `data/` are gitignored. They must not be committed.

## Candidate profile

| File | Git | Contents |
|---|---|---|
| `data/candidate_profile.example.json` | yes | Placeholders, same shape |
| `data/candidate_profile.json` | **no** | Real name, email, Telegram, LinkedIn |

Copy the example file to create a new private profile. Do not paste the private
file into chats, GitHub, or issue trackers.

## Telegram (stage 2)

- Store `TELEGRAM_BOT_TOKEN` only in local `.env` (gitignored). Never put it in
  Git, logs, README, or a Cursor/ChatGPT chat.
- `TELEGRAM_ALLOWED_USER_ID` is the numeric user ID, not `@username`.
- Until that ID is set, the bot answers only `/whoami`. `/profile` and other
  personal commands are blocked.
- After the ID is set, **every** command is limited to that user. Everyone else
  gets a short “no access” message with no profile data.
- Access is enforced in middleware (`AccessControlMiddleware`), not copied into
  each handler.
- Do not log the token or the text of incoming messages. Logs may record the
  command name (`profile`, `whoami`) and whether access was allowed.
- Anyone who can guess an unrestricted bot username could message it. The
  allow-list is what keeps the CV private.

## Job APIs (stage 3)

- Remotive needs no key. Do not republish their jobs on other aggregators.
- Adzuna keys stay in `.env` as `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`.
- HTTP helpers must not log query strings (they can contain Adzuna keys).
- Discovery never submits applications.

## Gmail (stage 6) — important boundary

OAuth 2.0 is mandatory. **Never ask for the Gmail password.**

A typical Gmail read scope can access **all mail in the account**, not only
messages from recruiters. Filtering “recruiter vs other” happens **inside this
app** after the token is granted.

Before connecting Gmail, the human operator must see:

1. which Google scopes will be requested;
2. that the app can read mailbox content;
3. that tokens will not be committed to Git;
4. that the app will not delete mail or change Gmail settings.

Roll-out: read → drafts → send-after-confirm. No silent send in early versions.

## External LLM (optional, later)

Do not upload the CV, mail, or profile to a vendor model without explicit consent.
Default path: rules-based logic; local Ollama only if RAM allows (16 GB is tight
for large models).

## Web access

- No CAPTCHA solving, no auth bypass, no closed APIs.
- No LinkedIn scraping and no automated LinkedIn messaging.
- Respect robots/ToS of job platforms; prefer official boards and public APIs.

## Autonomy and irreversible actions

Levels 1–2 require confirmation for apply/send. Never auto-accept offers, sign,
or attach extra identity documents.

## Logging hygiene

Log event types (`profile_loaded`, `validation_failed`), not field values that
are emails, tokens, or letter text. If a path is logged, log the path, not the
file contents.
