# Salesoorja Production Architecture Freeze

## Supported Production Flow

Salesoorja's supported production path is:

1. Serper discovers public evidence under a hard daily budget.
2. Bright Data is the reserved next integration point for narrow public-page retrieval; no Bright Data adapter exists in this checkpoint.
3. DeepSeek, using the Hive transport, performs bounded reasoning with Gemini as fallback.
4. Deterministic company, facility, person, authority, contact-confidence, and outreach gates make every qualification decision.
5. Apollo runs only after a person passes the existing enrichment eligibility gates.
6. Rediff SMTP/IMAP handles controlled email and reply or enquiry tracking.

LLM output is advisory and cannot override deterministic gate failures. Search or reasoning providers cannot mark a contact verified, qualify an opportunity, authorize Apollo, or authorize outbound activity by themselves.

## Caller Map

| Area | Decision | Production caller or reason |
| --- | --- | --- |
| FastAPI routes and services | Keep | `backend/main.py` registers the live API surface. |
| Celery worker and beat | Keep | Scheduled discovery, inbox checks, and reporting use Redis and Celery. |
| Serper provider, cache, and budget | Keep | `research_provider.py` is the sole live search router. |
| Company, facility, person, and opportunity gates | Keep | These deterministic services enforce evidence and truth requirements. |
| Apollo enrichment | Keep | Contact enrichment remains post-identification and gate-controlled. |
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

Future production-provider changes must update this document, provider inventory tests, configuration, Compose, and targeted truth-gate tests together. Bright Data integration must preserve the same evidence provenance, budgets, deterministic gates, and read-only discovery boundaries.
