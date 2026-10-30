# OpenAI-backed answers and interview preparation

Production-selected OpenAI mode now drafts application-answer paraphrases instead of merely selecting exact sentences, and generates tailored interview questions instead of fixed templates. The default is OpenAI; development/test deterministic adapters remain explicitly selected fixtures. There is no automatic deterministic fallback after provider refusal, configuration failure, malformed output or outage.

## Evidence and review

- Answers cite immutable confirmed fact IDs. Structural checks and a separate model support review validate each paraphrase. Certificates bind to exact claims and fact snapshots; an ID by itself does not establish support.
- Generated answers remain drafts until candidate approval. Edits clear approval and validation, enqueue revision-bound validation, and cannot be approved while validation is pending. A late result cannot attach to newer edits. Approval checks current profile and job snapshot.
- Interview preparation receives reviewed requirements, confirmed facts, and explicitly labeled approved/submitted materials. Generated questions cite requirement IDs, fact IDs and optional historical material claim indices. A separate request reviews every question for invented premises. Invalid references, incomplete coverage, or unsupported premises prevent saving the preparation.
- OpenAI preparation requires explicit candidate review before any response is accepted. Questions remain immutable; source changes require new preparation. Saved responses do not update career facts.
- Feedback remains bounded, quote-backed coaching selected by OpenAI, not a hiring prediction or independent verification. Feedback quotations must be exact response substrings; fact links must be supported.
- Model review is imperfect, not a truth guarantee. Candidate review remains necessary.

## Verification boundaries

`tests/test_practice_openai.py` uses the actual OpenAI SDK with mocked HTTP transport. It verifies structured requests, paraphrasing with evidence certificates, independent question review, unsupported references/premises, refusals and API failure handling. API tests cover preparation review enforcement, isolation, edit invalidation and obsolete validation results. These are **not live OpenAI results**.

No credentials were provisioned by this change. Generation metadata identifies the selected adapter/model; an `openai` adapter record alone does not prove a live API test. Live verification must be separately run and recorded with configured server-only credentials and synthetic inputs.
