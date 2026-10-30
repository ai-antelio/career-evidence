# Reviewed answers and interview practice

The first practice workflow is deliberately grounded and constrained:

- Application answers select exact confirmed career facts; candidate review is required and unsupported edits cannot be approved. Answers retain evidence, revision history and a content hash. Fact/job changes invalidate approval for reuse.
- Interview preparation selects reviewed job requirements and confirmed fact references. Questions are constructed from fixed templates and preserve source passages. Recorded submitted application materials take priority, with their immutable job, artifact/version/hash and evidence. Otherwise available approved materials are labeled approved, not submitted.
- Responses are candidate-authored immutable practice records. They never become career facts automatically. Repeated identical response submissions are idempotent.
- OpenAI feedback selects exact response quotes and rubric categories. Any fact reference requires the full confirmed fact to occur in the cited quote. Suggestions are fixed, bounded coaching guidance; there is no fabricated proficiency score, hiring prediction or implied verification of candidate statements.
- All model work uses server-side structured_call, strict schema, budgets, no tools, safe errors, and source validation. `EXTRACTION_ADAPTER=deterministic` supplies visibly labeled local practice. A configured OpenAI provider is needed for live AI selection.
- All work uses CareerWorkflow, transactional queue handling and duplicate-safe result commits. Existing workflow retry supports failures.

Targeted tests initially passed: 9 SQLite tests covering full answer review/edit invalidation, interview response/history, exact quotation evidence, isolation, stale facts, unreviewed inputs, invalid model citations and quotes, safe failure/retry and approved/submitted-material snapshots. Full PostgreSQL/integration totals are recorded in the consolidated release validation.

Limits: answers and résumé claims remain extractive, question phrasing is template-based, and feedback is initial quote-backed coaching rather than a validated assessment. Real provider quality/cost and real-browser interaction must be verified separately. No live API credentials were required or stored for these tests.
