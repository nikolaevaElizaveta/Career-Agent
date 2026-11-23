# Data sources (plan, not implemented in stage 1)

Stage 1 does **not** call the network. This file records what we will consider
later so Job Discovery stays legal and cheap.

## Rules

1. Free and officially documented interfaces first.
2. No paid product without an explicit yes.
3. No closed/private APIs, no CAPTCHA bypass, no session hijacking.
4. No automated LinkedIn scraping or messaging.
5. Deduplicate the same posting across sites (canonical URL + company + title).

## Likely first sources (to evaluate in stage 3)

| Source | Why it is a candidate | Caution |
|---|---|---|
| Manual URL | Always allowed; user pastes a link | Parsing quality varies |
| CSV import (later) | User-exported search results | Need a stable column map |
| Public Greenhouse / Lever / Ashby job JSON | Many companies expose public boards | Company list must be curated; still check geo |
| RSS where a board publishes it | Simple, polite | Incomplete fields |
| Documented public job APIs (e.g. some remote-job indexes) | No login | Read terms; many US-only or “anywhere” flags are sloppy |

Each source adapter will implement the same interface, roughly:

- `fetch()` → raw postings
- `normalize()` → `Job` domain model
- `source_name` for provenance

## Not in the first discovery set

- LinkedIn Easy Apply automation
- HeadHunter / other sites if it requires login bypass
- Paid aggregators
- Anything that needs a foreign credit card to create an API key

## Fields we must store per job (later)

Title, company, country, city, URL, posted date, discovered date, salary +
currency, level, work mode, tech, experience, work-permit requirements,
relocation, description, source.

Work authorization and salary stay `unknown` when the posting is silent.
