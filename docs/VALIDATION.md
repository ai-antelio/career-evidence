# Validation checkpoint — 2026-10-29

Executed in the provided workspace after adding the structured AI gateway:

| Check | Result |
| --- | --- |
| Backend against PostgreSQL 17 (`career_test`) | 38 passed |
| Backend against temporary SQLite | 37 passed, 1 PostgreSQL-only concurrency test skipped |
| Alembic on separate PostgreSQL database | upgrade through 0002 → downgrade base → upgrade through 0002 passed |
| Existing development database migration | upgrade from 0001 to 0002 passed |
| Next.js production build | passed, including TypeScript compilation |
| TypeScript `tsc --noEmit` | passed |
| Playwright Chromium browser journey | passed against the updated API, worker and frontend |
| Docker Compose configuration | valid |
| Python compile check | passed |

The browser journey uses a real Next.js server, FastAPI server, PostgreSQL database and separate worker process. It covers account creation, invalid uploads, asynchronous processing, all four review actions, correction provenance, confirmed profile, account isolation and sign-in recovery. Desktop/mobile screenshots were visually inspected in the local workspace; they are excluded from the Library source archive.

The AI tests call the actual installed OpenAI SDK against mocked HTTP transports. They assert strict schema requests, untrusted source boundaries, no tools, store=False, token limits, valid structured field extraction, unknown and foreign citations, duplicate citations, fabricated/shortened claims, changed quotations, wrong field offsets, fields from another passage, invalid schema/JSON, empty results, refusals, incomplete output, rate limits, server/auth errors, connection failures, timeouts, missing credentials and input-budget rejection. A worker integration test verifies invalid AI output saves no proposals, persists a safe audit failure, and can be retried successfully with valid evidence.

**Live OpenAI integration is unverified:** OPENAI_API_KEY was absent; no live model call or paid request was made. Tests do not establish real-model extraction quality. All model classifications and field labels still require candidate review. The default adapter remains explicitly labeled deterministic extraction.

The package lock and Python requirements record installed versions. Adding the official SDK installed httpx2, resolving the earlier TestClient deprecation warning. The npm cache was redirected into /tmp because the default home cache was not writable.

Container orchestration was configuration-validated, not fully built and run. The application was tested through native processes with a PostgreSQL Docker container. Managed identity, cloud storage, malware scanning, a Celery broker and production deployment remain unconfigured/unverified. Production mode remains deliberately disabled. No publishing or deployment occurred.
