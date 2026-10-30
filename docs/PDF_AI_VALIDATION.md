# PDF export and server-side AI configuration

## Implemented

The existing version/hash-bound export endpoint accepts `format: "pdf"` or `"docx"` (default DOCX). PDF uses real selectable text with a bundled, licensed DejaVu Sans font. It contains only approved claim text in approved order. A readback using pypdf compares normalized text before persistence; whitespace differs solely for wrapping. Unknown glyphs fail closed rather than silently substituting squares. The same approval validity, ownership, stale input and exact-version checks apply to both formats. Each format has its own immutable byte cache and SHA-256 hash.

`provider_config.py` loads `OPENAI_API_KEY_FILE` from a server-side mounted secret file, or `OPENAI_API_KEY` from the worker environment. It is never exposed by a route or stored in application tables. No credential was supplied during this run. The client is pinned to `https://api.openai.com/v1`, ignoring ambient arbitrary base-URL redirection. SDK/HTTP logging is disabled so debug-level transport logging cannot copy prompts or headers. Gateway exceptions contain safe codes, not raw provider response/error text. Model identifiers are validated before audit persistence. AI tasks have input/output budgets, explicit refusals and schema validation; career runs include hashes and schema/prompt versions.

## Verified

- Seven new focused tests passed: PDF selectable text/order, repeated bytes, foreign access, edit invalidation, separate format caches, invalid format, rendering rollback/retry, Unicode, multipage wrapping and unsupported glyph rejection.
- Secret configuration tests cover mounted secret file, fixed official endpoint, suppressed transport logging, safe missing-secret errors, and prevention of a key-like model setting leaking into audit metadata.
- Existing extraction and artifact tests passed after gateway/export changes (28 passed, four PostgreSQL-only skips in the focused SQLite run).
- A synthetic exported PDF was rendered with Poppler and visually inspected: readable, no clipping or overlap. Layout is intentionally plain claim paragraphs with consistent margins, not a polished branded résumé template.

## Limits

Live OpenAI responses and billing were not verified because no credentials were present. Tests use mocked provider responses and local deterministic adapters. PDF visual inspection uses Poppler, not every reader/printer. The font does not cover every writing system; unsupported glyphs produce a retryable rendering failure and DOCX remains available. Application deployment and browser download UI are separate verification steps.
