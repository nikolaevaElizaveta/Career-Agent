# Project specification — Personal Career Agent

This document is the product specification for the first design pass (stage 0).
It records what we are building, for whom, and which facts are still unconfirmed.

## Purpose

Personal Career Agent is a **local** tool that helps Elizaveta Nikolaeva move from
job discovery to interviews and an international offer.

Success is measured by **interviews and a job offer**, not by the number of
applications sent.

The first implemented version is **Autonomy Level 1 (Assistant)**:
the agent searches, analyses, and prepares drafts. The user confirms every
external action (apply, send email, send a networking message).

## Candidate snapshot (source of truth: Candidate Profile)

Use only facts stored in the Candidate Profile. Do not invent metrics, companies,
technologies, or achievements.

| Area | Confirmed from this assignment | Still open |
|---|---|---|
| Name | Elizaveta Nikolaeva | — |
| Job-search email | `[private email stored in local profile]` only | — |
| Telegram | `@nikolaevalizza` | Numeric Telegram user ID for bot allow-list |
| LinkedIn | public profile URL in the private profile | — |
| Citizenship | Russian Federation | — |
| Languages | Russian (native), English B2 | — |
| Education | Innopolis University, BSc Computer Science, 2022–2026 | — |
| Current roles | QA Engineer at Innotech (from March 2026); Analyst at NOO Online School | Day of Innotech start (month/year only) |
| Skills | listed testing / API / tools skills, no seniority labels | proficiency per technology |
| Salary floor | 100 000 RUB **net** / month | — |
| Work permit abroad | none | — |
| Residence permit abroad | none | — |

**Innotech start is confirmed as March 2026** (`PartialDate` with `precision=month`).
Do not invent a calendar day (no `2026-03-01`). Generated CVs may print `2026-03`.

Do not use any previous email address in templates, settings, or generated documents.

Do not label the candidate Senior, Advanced, or Expert. Do not claim commercial
experience with a technology only because it appears in the skills list.

## Target roles (priority order)

1. Manual QA / QA Engineer
2. API QA / API Testing
3. Integration Testing / Integration QA
4. Junior QA Automation (realistic junior/AQA only — not “experienced AQA”)

Match on **duties and stack**, not only on the job title.

Experience band: mainly **0–2 years** / junior / entry-level. 2–3 years is
acceptable when the rest of the role fits. One extra requirement is not an
automatic reject.

## Geography and hiring path

Priority countries: Spain, United Kingdom, Australia. Other countries are allowed
when work conditions, safety, social rights, and relocation look attractive.

Two hiring stages:

1. **Work from Russia** — foreign employers that can actually hire a Russian
   resident (remote + a real contract path). The word “Remote” is not enough.
2. **Relocation** — visa sponsorship, relocation help, EOR, or a transfer.

Always classify work authorization separately:

- Can work from Russia
- Can work only after relocation
- Needs a work permit in the employer’s country
- Unknown — needs a human check

Unknown must stay `Unknown`, never `Eligible`.

## Compensation and contract

Minimum: **100 000 RUB net per month**. Preferred currencies: EUR, USD, GBP, AUD.
RUB is acceptable. Missing salary is `unknown`, not a hard reject.

Never treat gross as net. Do not invent tax rates.

Accepted engagement models: local employment, EOR, B2B, independent contractor,
direct contractor. Remote is preferred; hybrid/office only with a realistic
relocation path.

## Hard ethical exclusions

Never recommend:

- government / military
- gambling / betting
- surveillance / spyware
- tobacco
- adult industry

Lower priority (not banned): cryptocurrency, oil and gas.

No unpaid internships or unpaid work. A short take-home (a few hours) is OK;
a large unpaid work sample must be flagged.

## Functional modules (later stages)

| Module | Role |
|---|---|
| Job Discovery | Legal sources, career pages, RSS/open APIs, manual URL, later CSV. Deduplicate. |
| Job Matcher | Weighted score, hard ethical filters, explain match/gaps/unknowns. |
| Application Assistant | Tailored CV and cover letter from **confirmed** facts only. Preview before send. |
| Application Tracker | Status pipeline; `applied` only after the user confirms a real send. |
| Networking | Public contacts and personal drafts; no LinkedIn scraping or mass send. |
| Gmail | Official Gmail API + OAuth 2.0, later. Filter recruiter mail in-app. |
| Telegram | Primary UI. Allow-listed user ID only. Long polling for local use. |

LinkedIn: store URLs and draft messages the user sends by hand. No automated
LinkedIn scraping or messaging.

## Autonomy

- **Level 1 (now):** drafts only.
- **Level 2:** scheduled search, Gmail drafts, reminders; sends still confirmed.
- **Level 3:** limited automation later. Never auto-negotiate salary, accept an
  offer, sign a contract, share extra personal data, or send legal documents.

## Technical constraints

- Local-first on Apple Silicon macOS, ~16 GB RAM.
- Free stack; external spend at most $10/month, preferably $0. No architecture
  that **requires** a foreign bank card.
- Modular monolith in Python. No microservices.
- LLM is optional and pluggable (local Ollama or a future API). Core matching
  must work without a paid model. Do not send personal data to an external LLM
  without explicit consent.
- A sleeping Mac does not run a 24/7 searcher. Cloud hosting is stage 8.

## Out of scope for stage 1

Telegram, Gmail, job sources, matcher service, LLM, Playwright, FastAPI HTTP API,
and schedulers are **not** implemented yet.
