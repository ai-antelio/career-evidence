# OpenAI matching and résumé tailoring

Matching and résumé generation now use server-side OpenAI Responses requests with strict structured schemas. Production defaults to OpenAI; deterministic rules remain an explicitly selected test/development adapter, never an automatic failure fallback.

## Grounding and review

- Inputs contain only owner-scoped, confirmed current fact versions and reviewed requirements in immutable snapshots.
- Matching uses a generation request followed by independent assessment review. Missing evidence is `unknown`; `not_met` requires explicit contradictory evidence. References and requirement coverage are checked in code. Disagreement cannot upgrade a result to supported or not-met.
- Résumé generation can select and paraphrase facts, but must cite fact versions. Structural validation blocks foreign or missing references and ungrounded numbers/dates. A separate semantic verification request evaluates every non-extractive claim with exact quoted source evidence.
- Verifier verdicts are bound to the exact claim and fact snapshot hashes. They are backend-produced validation records, not user-editable attestations. Uncertain/unsupported claims remain visible but cannot be approved.
- Candidate edits remove prior verification and enqueue asynchronous validation; no model call occurs while holding an approval transaction. Approval and exports recheck the hashes, current snapshot, references and saved verdict. Candidate approval remains mandatory.
- API records expose generation and verification provenance; provider errors fail closed and never silently fall back to deterministic output.

Semantic verification is an imperfect model check, not independent proof or a guarantee of truth. Candidate confirmation and review remain central. Snapshot policy identifiers force prior deterministic drafts to be regenerated rather than represented as OpenAI outputs.

## Verification

`tests/test_ai_career.py` uses the actual SDK with mocked HTTP. It covers structured generation and a separate verifier, unsupported/uncertain verdicts, fabricated verifier quotes, missing/foreign citations, invented metrics, invalid match output, provider failure, exact-hash binding and asynchronous edit revalidation. These are mocked transport tests, not live OpenAI verification.
