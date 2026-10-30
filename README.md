# Career Evidence — foundation and profile slice

A working local vertical slice: account creation/sign-in → private résumé upload → durable asynchronous parsing → source-bound fact proposals → accept/correct/reject/defer → candidate-confirmed profile.

**Development use only.** This is not a production-ready identity or document-security service. `APP_ENV` values other than `development` deliberately prevent API startup. No deployment has been performed.

## Run

Requirements: Docker with Compose. From this directory:

```sh
docker compose up --build
```

Open http://localhost:3000. API documentation is at http://localhost:8000/docs. Create a synthetic account with a password of at least 12 characters. Upload `fixtures/alex-morgan.docx`; the worker processes it independently. The conflict fixture has an alternative email and achievement percentage. All résumé content is fictional.

The Compose database password is explicitly local-only. Ports bind to loopback. API and worker run as an unprivileged user and share a private named volume. Original filenames are never used as storage paths. The migration service completes before API and workers start.

### Run processes directly

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci --prefix web
# Start the database first (or provide an existing development PostgreSQL URL):
docker compose up -d db
cd backend
export DATABASE_URL=postgresql+psycopg://career:local-development-only@localhost:5432/career
export STORAGE_ROOT=/absolute/path/to/career/private-storage
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --port 8000
```

In another terminal, use the same environment and backend working directory, then run `../.venv/bin/python -m app.outbox` as the relay and `../.venv/bin/celery -A app.celery_app:celery worker -Q documents,ai,maintenance --loglevel=WARNING` as the worker. Configure a reachable RabbitMQ server with `CELERY_BROKER_URL`. In `web`, run `npm run dev`. `WEB_ORIGIN` defaults to `http://localhost:3000`; `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` and is set at frontend build time. Do not mix localhost and 127.0.0.1 in browser URLs.

SQLite is a convenience default for isolated unit tests. PostgreSQL is the intended database and is required to validate concurrent worker behavior.

## Implemented boundaries

- **Identity:** local Argon2 password hashes, random opaque HttpOnly/SameSite session cookies; only token hashes are stored in the database; logout revokes the session. Strict origin checks on mutations protect cookie-authenticated requests. `COOKIE_SECURE=true` is required for HTTPS hosting. `AUTH_MODE` other than `local` fails closed instead of pretending managed identity works.
- **Ownership:** every exposed document, proposal, profile and retry operation is scoped to the authenticated owner. Unknown and foreign IDs return the same 404. Content deduplication is per account, never global. Storage keys and original file bytes are not exposed through public URLs.
- **Upload:** request-body and file-size caps, PDF/DOCX signature checks, DOCX expansion cap, generated private storage keys and restrictive local permissions. Failed persistence does not leave a database job. A crash after writing a file but before committing can leave an unreferenced private object; orphan cleanup is a remaining operations task.
- **Processing:** parser subprocess with Linux memory and CPU limits and a wall-clock timeout; text PDFs and DOCX paragraphs/tables supported. Scanned/empty/malformed inputs fail visibly. Text and original document bytes are immutable after successful processing. Character offsets refer to the extracted text snapshot, not PDF visual coordinates.
- **Durability:** job state and identifier-only `dispatch_events` commit together in PostgreSQL. A relay publishes persistent Celery messages to durable RabbitMQ queues with publisher confirms. Failed/lost dispatch is recovered; a crash after publish may repeat delivery. Workers claim rows using `FOR UPDATE SKIP LOCKED`, lease tokens fence stale completions, expired work is reclaimed, and proposals are unique per document/span. Transient failures use bounded retries; explicit retry resets failed work. This is at-least-once work, not exactly-once delivery.
- **Evidence:** deterministic extraction proposes verbatim passages. OpenAI is the default; the deterministic adapter requires explicit development/test selection. The OpenAI structured gateway classifies passages and extracts typed fields; all claims must still equal their complete supplied source passage and every field must match an exact source span. Source offsets are preserved. Acceptance creates a source-supported candidate-confirmed fact version. Corrections create `candidate_correction` versions and the UI explicitly says the source does not substantiate the edit. Nothing is labeled independently verified.
- **Review:** optimistic revision checks prevent lost updates; all decisions append audit events; confirmed versions are immutable. Rejecting/deferring a previously confirmed proposal removes it from the current profile without deleting its history. Accepting the original after correcting it creates another version.
- **Conflict handling:** differing email passages and highly similar statements are flagged for review. This is a conservative string-similarity heuristic, not semantic contradiction detection. Neither wins automatically. Users can still confirm conflicting passages; resolution policy and structured entity/date extraction are future work.

## Schema and code

`backend/app/models.py`: users, sessions, immutable document snapshots, durable outbox jobs, proposals, fact versions, review events. `migrations/versions/0001_schema.json` is a frozen schema snapshot consumed by Alembic; migrations do not import changing application models.

`main.py` contains the thin initial HTTP/auth/review boundary; `extraction.py` is the source-bound extraction adapter; `worker.py` owns job leasing and transactional completion; `parse_runner.py` isolates parser resource use; `limits.py` bounds bodies before multipart parsing. These can be separated into domain routers as the product grows.

`web/app/page.tsx` implements onboarding, processing status/retry, source-side-by-side review and confirmed profile. `style.css` includes desktop and mobile layouts.

## Tests

```sh
cd backend
../.venv/bin/python -m pytest -q
# Use ONLY a dedicated disposable test database: the fixture drops its tables.
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/career_test ../.venv/bin/python -m pytest -q
cd ../web
npm run build
npm run typecheck
npx playwright install chromium
# Start API, worker and web against a separate development database first:
npx playwright test
```

Backend coverage: all review decisions and immutable history; candidate-correction attribution; stale review rejection; account isolation; sign-in/logout; cross-origin denial; invalid/oversized uploads; disk-write failure; duplicate upload and delivery; parser failure/manual retry; bounded transient retry; expired lease recovery; stale worker fencing; conflicting emails and metrics; empty DOCX; concurrent PostgreSQL claims.

Browser coverage: create account, reject invalid upload, process a synthetic résumé with a real worker, all four review actions, corrected provenance, confirmed profile, isolated second account and sign back in; desktop/mobile screenshots.

## Remaining production integrations and scope

1. Managed identity adapter, verified email/recovery/MFA, distributed auth rate limiting and production session hardening. No identity-provider credentials were supplied.
2. Private object-storage adapter, encryption/retention, quarantine and malware scanning. Local filesystem storage and parser limits are not a malware sandbox. No cloud-storage or scanner credentials were supplied.
3. Live AI provider verification and extraction evaluation: the OpenAI structured gateway is implemented and tested through mocked provider HTTP responses. No live provider credentials were available; no live call was made. Candidate review remains necessary for classification or field-label errors.
4. Validate and provision production RabbitMQ durability, broker credentials/TLS, alerting and capacity. Celery with a transactional outbox is implemented; see `docs/CELERY_QUEUE.md`.
5. Database RLS and composite ownership constraints for additional defense; current enforcement is at the tested API query boundary. No RLS claim is made.
6. Structured conflict resolution, PDF page/bounding-box provenance, OCR, account export/deletion, observability/alerting, scanning sandbox, orphan cleanup and production deployment configuration.
7. Job-description input, evidence matching and tailored artifacts belong to the next slice and are not implemented here.

The frontend uses explicit TypeScript response types for this small slice; generated OpenAPI client/contract CI remains future work. No external service integration is represented as verified.


## Structured AI extraction gateway

`app/ai_gateway.py` calls the official OpenAI SDK Responses API with a strict JSON schema. Configure the **worker** with `EXTRACTION_ADAPTER=openai`, `OPENAI_MODEL=<your enabled structured-output model>` and `OPENAI_API_KEY` from server-side secrets. Do not place keys in `NEXT_PUBLIC_*` variables. No model is guessed by default. With missing configuration, work fails visibly and can be retried after configuration is fixed; there is no silent fallback. Compose defaults to `openai` and mounts `OPENAI_SECRET_FILE` only in the worker as `/run/secrets/openai_api_key`. Set `OPENAI_MODEL` and an absolute secret-file path outside this repository before starting Compose. No actual credential belongs in Compose or checked-in files. See [OpenAI setup](docs/OPENAI_SETUP.md).

Explicit `EXTRACTION_ADAPTER=deterministic` is a labeled development/test-only adapter, rejected outside those environments. The UI labels each proposal with its actual adapter, and AI proposals display their extracted fields next to the original source. Existing proposals retain their original adapter label.

The gateway constructs document-specific passage IDs from the text hash and offsets. The model selects passages, classifies employment/education/skills/achievements/contact facts, and extracts employer, role, date, institution, qualification, skill, metric, email or location fields. Every proposed claim must copy the **entire** selected passage, preserving negations and qualifiers. Every typed field must be an exact substring inside that same passage with valid absolute offsets. Unknown/foreign/duplicate citations, fabricated text, shortened claims, invalid fields and invalid schemas reject the entire extraction atomically; a valid citation alone never licenses a paraphrase. This intentionally restricts generated wording in the profile path. Category/field-label correctness still needs candidate review and future evaluation.

No tools are enabled for the model; résumé text is explicitly untrusted input. The provider request uses `store=False`, a 40,000-character input cap, 4,000 output-token cap, a 40-second request timeout, and no SDK retries. Queue policy owns bounded retries for network errors, rate limits and server errors. Refusals, incomplete outputs, invalid schema/evidence and configuration errors fail visibly without saving partial facts. Provider errors and refusal contents are not exposed to users or stored in audit metadata.

Migration `0002` adds typed proposal fields, adapter attribution and `generation_runs`. Each durable run records owner, document, job, adapter/model, prompt/schema versions, input hash, usage counts, elapsed time and a safe error code. It stores no credentials, raw provider errors, prompts or extra copies of résumé text. Model calls occur outside database transactions, and lease fencing still applies to success and failure commits. Remote calls may repeat after a crash; billing is not exactly-once.

Official reference used for the integration: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Live provider behavior remains unverified.

## Job matching and first tailored draft (release increment)

The authenticated workspace now includes job-description input, asynchronous
requirement extraction, requirement review/correction, evidence-linked matching,
and a versioned résumé draft with approval checks. Apply migration `0003` before
starting the API and existing worker process.

- `POST /opportunities` records an immutable pasted description and queues extraction.
- Review each requirement with accept/correct/reject/defer. Original source text and
  offsets remain visible. Resolve pending/deferred items before requesting matching.
- `POST /opportunities/{id}/match` freezes reviewed requirements and current confirmed
  fact versions. No rejected, deferred, pending or superseded fact enters the snapshot.
- Matching uses **conservative deterministic rules**, not an LLM hiring prediction.
  A small explicit-skill vocabulary can yield supported or explicitly not-met results;
  complex related conditions remain partial, absence of evidence remains unknown.
  Prospective, ambiguous or negated statements do not establish skill possession.
- `POST /opportunities/{id}/draft` requires a current match. In OpenAI mode, the model
  selects and orders exact confirmed facts; deterministic mode ranks by token overlap.
  Both modes remain **extractive**, not free-form résumé rewriting. Every claim cites
  its exact fact version, with original source and candidate-correction provenance.
- Editing creates a new version. Unsupported text, empty drafts, missing/foreign
  citations or changed profile/requirements block approval. Approval binds the exact
  version/content hash. Historical versions are retained; current stale status is
  calculated from the snapshot rather than erasing past content.
- Requirement/matching/draft work uses the existing **PostgreSQL durable polling
  job-state architecture**, in a separate `career_workflows` table. Execution now uses
  Celery and RabbitMQ through the shared transactional dispatch outbox. Tasks have leases, bounded retries, idempotent commands and atomic results.
  Existing at-least-once/provider-cost and 120-second lease limitations still apply.

The AI extraction and résumé adapters are exercised with mocked provider output.
No live OpenAI call or production deployment is claimed. DOCX/PDF export for these
new drafts is not included in this increment. Requirement corrections are candidate
interpretations, not edits to the original employer description. A source-backed
claim is not proof of independent factual verification.

## Application records, approvals and DOCX export

The application record now saves the exact approved résumé version, its immutable fact/job input snapshot, claim evidence, approval actor/time and content hash. Every job has one owner-scoped application. Version history remains readable after edits. Migration `0004` backfills applications for existing jobs; old résumé status alone is not an approval record, so legacy drafts must be explicitly approved before export.

- Approving a validated current version atomically records the approval and associates it with the application. Repeated approval is idempotent.
- Editing creates a new immutable version, marks the old approval invalid and requires fresh review/approval. The previous approved content and original fact/evidence snapshot remain available as history, not as an active exportable résumé.
- Profile or requirement changes and a newer generated draft invalidate current export eligibility. These changes are checked dynamically on every approval/export. Previously produced files are not remotely revocable.
- DOCX exports contain only the approved claim text in its approved order. The renderer reopens the DOCX and checks its paragraph text before storing the file. No inferred headings or candidate claims are added. Evidence stays in the application UI rather than being inserted into the résumé.
- Private export bytes are stored in PostgreSQL in this small slice, with SHA-256 file and claim-content hashes. A repeated export returns the same stored bytes. Routes are authenticated and owner-scoped, with `Cache-Control: private, no-store`; no public download URL is created. A production object-store adapter remains future work.
- Approval, edits, fact review and exports serialize on the owner row; exports also lock the job. This gives a defined ordering to concurrent edit/export requests. A download approved before a later edit cannot be recalled, but requests after that edit fail closed.
- Rendering failures roll back without storing a partial export and can be retried. Invalid citations, unsupported wording, changed snapshots, wrong versions/hashes and corrupted stored bytes block export.

API: `GET /applications`, `GET /applications/{id}`, `GET /artifacts/{id}` (including historical versions), and `POST /artifacts/{id}/export` with `{version, content_hash}` for DOCX bytes. The existing approval endpoint now returns `application_id` and `approval_id`.
