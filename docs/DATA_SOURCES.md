# Data sources

Stage 3 implements two adapters behind the same `JobSource` interface.

## Rules

1. Free and officially documented interfaces first.
2. No paid product without an explicit yes.
3. No closed/private APIs, no CAPTCHA bypass, no session hijacking.
4. No automated LinkedIn scraping or messaging.
5. Deduplicate by `source + source_job_id`, then by company + title + URL.
6. Do not republish Remotive listings on other public aggregators.

Search keywords and enabled sources live in `config/job_search.yaml`. Change that
file instead of editing Python.

## Remotive (enabled, no API key)

- Docs: https://remotive.com/remote-jobs/api
- Endpoint: `https://remotive.com/api/remote-jobs?category=qa`
- Public JSON API. Jobs are delayed about **24 hours** by Remotive.
- Limits we enforce locally: **at most 2 requests per minute** and **4 per 24 hours**.
- Always keep the original Remotive URL.
- Always display the source as **Remotive**.
- `candidate_required_location` of `Worldwide` is stored as `remote_scope=worldwide`.
  That is **not** treated as “hires from Russia”.
- If location is missing, `remote_scope` stays `unknown`.

## Adzuna (adapter ready, optional keys)

- Docs: https://developer.adzuna.com/docs/search
- Needs `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in local `.env`.
- Planned markets: `gb`, `es`, `au` (see YAML).
- If keys are missing, Adzuna is **skipped** and the rest of the app still runs.
- A 404 for a country is treated as “market unavailable”, not as a crash.
- Do not paste Adzuna keys into Cursor or ChatGPT.

## Deduplication

1. Exact: same `source` and `source_job_id` → do not insert again.
2. Probable: same normalized company **and** title, or equivalent job URL, across
   sources → insert with `duplicate_of_id` and keep both original URLs.
3. Same job title at two different companies is **not** a duplicate.

## Storage

SQLite file `data/career_agent.sqlite` (gitignored). Path:
`CAREER_AGENT_DATABASE_PATH`.

## Not in this stage

- LinkedIn automation
- Manual URL import / CSV (later)
- Matching, cover letters, applications
