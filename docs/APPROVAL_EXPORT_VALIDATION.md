# Application approval and export validation

Implementation: application and approval records, immutable version/evidence history, authenticated DOCX export, edit invalidation and replay-safe stored bytes. All work and checks ran inside dot's VM. No deployment or live provider access.

Tests cover exact exported paragraph text and order, file/content hashes, repeat-export identity, repeat-approval identity, edit invalidation with preserved historical evidence, wrong version/hash, cross-account reads and exports, profile staleness, renderer failure/rollback/retry, corrupt bytes, and concurrent PostgreSQL export idempotency. Existing matching, profile and queue recovery checks are retained.

SQLite: 57 passed, 3 PostgreSQL-specific skips before the three additional PostgreSQL-only race tests; those new race tests were verified on PostgreSQL. PostgreSQL: 63 passed, including three additional deterministic edit/export and approve/edit race tests. Alembic upgrade head → downgrade base → upgrade head passed against a separate disposable PostgreSQL database.

DOCX supports readable editable paragraph content; a broad visual office-suite compatibility/ATS certification is not claimed. Renderer self-verification and python-docx parse tests passed; visual office rendering is not yet verified. Browser checks are separately reported by frontend validation.

Race checks force lock overlap: export-before-edit returns only the approved pre-edit text; edit-before-export returns 409 with no export row; approve-before-edit saves an approval that the subsequent edit atomically invalidates.
