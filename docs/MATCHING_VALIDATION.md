# Matching increment validation

All implementation and checks were performed inside dot's VM.

## Executed

- Final PostgreSQL 17.11 suite: **54 passed** (including concurrent workflow claims).
- Final SQLite suite: **52 passed, 2 PostgreSQL-only skips**.
- SQLite Alembic: upgrade head, downgrade to 0002, upgrade head passed.
- PostgreSQL Alembic: upgrade head, downgrade base, upgrade head passed.
- Next.js production build and TypeScript checks passed (frontend worker).
- Browser execution was attempted but blocked by VM Chromium socket restrictions; the new browser test was not executed.
- Python compilation passed.

New tests cover reviewed requirement gating, source-preserving corrections,
correction attribution after subsequent accept, all four match categories,
conservative skill evidence (aspirations/recruitment/unrelated negations),
current confirmed facts only, snapshot staleness, cross-account route isolation,
foreign/unsupported citations, empty draft rejection, approval invalidation,
duplicate commands, lease recovery, failed-work retry, exact-source OpenAI
requirement checks and unsupported OpenAI draft blocking.

## Boundaries

- Matching is a conservative rules-based baseline with a limited skill vocabulary;
  no performance or hiring-outcome claim is made.
- Résumé tailoring selects/reorders exact confirmed facts. Free paraphrase is blocked
  until confirmed as a new profile fact; this is intentional safety, not semantic AI
  verification.
- Provider responses are mocked; live credentials were not configured.
- PostgreSQL runtime tests used an ephemeral, VM-local PostgreSQL instance. No external infrastructure was used.
- Full Docker Compose runtime, live provider calls, and production deployment were not run.
