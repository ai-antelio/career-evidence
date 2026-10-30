# Real broker verification

Verified inside dot's VM on 2026-10-30, with official Debian packages extracted unprivileged under `/tmp`; no system installation or security-setting changes.

## Real components

- RabbitMQ 4.0.5, Erlang 27.3.4.1, local loopback listener.
- PostgreSQL 17.11 in a separate disposable UTF-8 test database.
- Actual Celery consumer and persistent AMQP publisher, application transactional outbox, synthetic DOCX parser and fact proposals.
- Live OpenAI was not involved; extraction used the deterministic test adapter.

## Passed checks

1. Repository `tests/test_broker_queue.py::test_live_rabbitmq_worker_round_trip`: **1 passed in 12.26 seconds**. An authenticated synthetic upload produced an outbox event; a real AMQP publish and Celery consumer completed the document job and saved proposals.
2. Additional temporary recovery harness: **1 passed in 24.80 seconds** using PostgreSQL and RabbitMQ. It published a document dispatch with publisher confirmation before a consumer was running, stopped RabbitMQ, restarted it with the same data directory, and then started Celery. The persisted queued message completed the job. A duplicate real AMQP dispatch did not duplicate proposals or increase the completed job's attempt count.

The first PostgreSQL harness attempt used an SQL-ASCII database and failed in SQLAlchemy's server-version parsing; recreating the disposable database as UTF-8 fixed the test setup. A later interrupted invocation had no retained final result, so it was rerun and the passing result captured.

## Limits

This proves a local persistent-message restart and real consumer round trip, not broker clustering, production TLS, multi-node failover, sustained-load behavior, or externally hosted infrastructure. Broker shutdown was graceful, not a power-loss simulation. Queue failure/outbox retry/fencing are additionally covered by the repository's unit and PostgreSQL integration tests; do not describe all of those as real broker-failure tests. No deployment occurred.

Temporary evidence: `/tmp/career-rabbit/final-pg-broker.log`, `/tmp/career-rabbit/test_real_runtime.py`, `/tmp/career-rabbit/recovery.log`. Test server processes were stopped at the end.
