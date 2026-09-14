# Salesoorja Production Architecture Freeze

## Supported Production Flow

Salesoorja's supported production path is:

1. Serper discovers company, trigger, and facility evidence under a hard daily budget.
2. Apollo people search discovers identity-only candidates without revealing contact data.
3. Bright Data LinkedIn Profile verifies current employment, facility, function, and authority for at most three candidates.
4. DeepSeek, using the Hive transport, performs bounded reasoning with Gemini as fallback.
5. Deterministic company, facility, person, authority, contact-confidence, and outreach gates make every qualification decision.
6. Apollo contact enrichment runs only after a person passes the existing enrichment eligibility gates.
7. Rediff SMTP/IMAP handles controlled email and reply or enquiry tracking.

LLM output is advisory and cannot override deterministic gate failures. Search or reasoning providers cannot mark a contact verified, qualify an opportunity, authorize Apollo, or authorize outbound activity by themselves.

## Caller Map

| Area | Decision | Production caller or reason |
| --- | --- | --- |
| FastAPI routes and services | Keep | `backend/main.py` registers the live API surface. |
| Celery worker and beat | Keep | Scheduled discovery, inbox checks, and reporting use Redis and Celery. |
| Serper provider, cache, and budget | Keep | `research_provider.py` handles company, trigger, and facility research only. |
| Apollo person discovery | Keep | `apollo_adapter.py` returns identity-only candidates and never exposes email or phone during discovery. |
| Bright Data LinkedIn provider | Keep | `brightdata_linkedin_provider.py` verifies Apollo candidates by profile URL; Dataset Search remains optional fallback code. |
| Company, facility, person, and opportunity gates | Keep | These deterministic services enforce evidence and truth requirements. |
| Apollo enrichment | Keep | Contact enrichment remains post-verification, gate-controlled, sequential, and capped at three candidates. |
| Rediff SMTP/IMAP and reply tracking | Keep | Controlled email delivery and response classification are production functions. |
| DeepSeek and Gemini | Simplify | DeepSeek is primary through Hive; Gemini is the only fallback. |
| PostgreSQL models and migrations | Keep | They hold CRM, evidence, campaign, and audit state. |
| LinkedIn MCP | Remove | No longer part of the supported production path. |
| SearXNG | Remove | Serper is the only live search provider. |
| DeerFlow and browser automation | Remove | No browser sidecar or browser escalation path remains. |
| Crawl4AI and Playwright | Remove | Public-page browser extraction is not active production infrastructure. |
| Apify scraper route | Remove | It bypassed the supported evidence and enrichment flow. |
| Legacy LLM routers | Remove | Groq, OpenRouter, Cloudflare, UnoRouter, and OpenAI are unsupported. |
| Scratch, benchmark, and one-off scripts | Remove | They had no registered API, worker, or scheduler caller. |

## Runtime Services

The Compose runtime contains only PostgreSQL, Redis, backend, Celery worker, Celery beat, and frontend. Credentials remain environment-driven and `.env.example` contains placeholders only.

## Change Rule

Future production-provider changes must update this document, provider inventory tests, configuration, Compose, and targeted truth-gate tests together. Apollo discovery must remain identity-only. Bright Data profile verification must preserve evidence provenance, cache and request telemetry, deterministic gates, and read-only boundaries.
