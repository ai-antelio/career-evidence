# Integrated PostgreSQL release validation

Validation ran inside dot's VM using an unprivileged PostgreSQL 17.11 runtime from official Debian packages, TCP-only loopback access, and dedicated disposable databases. No application authentication/privacy settings were changed.

## Migrations

The complete migration chain passed `upgrade head → downgrade base → upgrade head` on an empty disposable PostgreSQL database. The resulting revision is `0007`.

## Integration issue found and fixed

A real-PostgreSQL test exposed a lock-order/lifetime bug absent on SQLite. Returning an idempotent duplicate interview response retained a request-owned user row lock, while post-response audit middleware tried to insert an owner-linked audit event in a separate transaction before dependency cleanup. The audit insert waited on its own request's lock. The fix uses the existing request session and rolls back residual transaction state before recording the audit, avoiding lock contention and preventing audit recording from committing uncommitted application changes. Tests cover duplicate responses and rollback of failed request writes.

## Test boundaries

PostgreSQL, SQLAlchemy, FastAPI test clients, migrations, document parsing and exports use real components. Tests that call worker helpers directly do not themselves prove Celery/broker transport; see REAL_BROKER_VALIDATION.md for separate real-broker results. OpenAI responses are mocked or the explicitly labeled deterministic adapter is used; no live API credential is exercised. Browser rendering is not established by these tests.

The initial disposable cluster used SQL_ASCII encoding and caused psycopg version-string decoding errors. Recreating test databases with explicit UTF8 resolved that environment setup issue without application changes.

## Final result

Final integrated PostgreSQL suite after the audit fix: **95 passed, 1 skipped in 43.95 seconds**. The skipped test is the opt-in live RabbitMQ worker round trip, run separately by the broker validation harness. PostgreSQL concurrency tests were enabled, not skipped. The local server was stopped after verification.
