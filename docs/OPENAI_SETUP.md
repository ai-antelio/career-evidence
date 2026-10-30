# Server-side OpenAI configuration

The default AI adapter is **OpenAI** across résumé extraction, requirement extraction, matching, résumé tailoring, reviewed answers and interview preparation. Missing credentials or an unconfigured model cause a visible failed job; there is no automatic deterministic fallback. Successful transport alone does not approve generated content: validation and candidate review still apply.

## Configure the worker

Select a structured-output-capable model available to your account using `OPENAI_MODEL`. Model identifiers are validated; no model is guessed. Provision the API key through a server-side secret manager or a mounted file outside the repository. Do not paste it into chat, source, `.env` files committed to version control, CLI arguments, URLs, browser storage, frontend variables, logs, or the application database.

For the included local-development Compose configuration:

1. Provision the secret as a private file outside the project with your deployment secret tooling.
2. Set `OPENAI_SECRET_FILE` to that absolute path and `OPENAI_MODEL` to the enabled model identifier. These variables contain a path and model name, not the credential.
3. Start the normal Compose stack. Compose mounts the file only in the worker at `/run/secrets/openai_api_key`; API, web, relay and database services do not receive it. A missing secret file prevents worker setup rather than falling back.

Outside Compose, the worker accepts `OPENAI_API_KEY_FILE` (absolute mounted path) or a server-injected `OPENAI_API_KEY`. A configured unreadable secret file fails closed rather than falling back to the environment key. Avoid environment-based secrets where process inspection policy makes file mounts safer. Credentials are read at provider-client creation; rotation does not require database changes.

Provider routing is pinned to the official OpenAI API endpoint. SDK transport logging is suppressed, request bodies are not included in application audit metadata, provider errors are converted to safe codes, and provider state storage is disabled with `store=False`. This does not guarantee zero provider retention; review the provider's data controls and your privacy obligations before real candidate data.

## Explicit offline testing

`EXTRACTION_ADAPTER=deterministic` may be explicitly selected only with development/test `APP_ENV`. It is never the default. Test fixtures select it deliberately; mocked SDK tests use `EXTRACTION_ADAPTER=openai` with synthetic responses and no real request. Deterministic and mocked runs are not evidence of a live API pass. Use the adapter/model and validation details displayed on saved results to distinguish their origin.

The application still intentionally refuses production startup until managed identity, production storage and malware-scanning prerequisites are configured. Enabling a real provider does not remove that guard.

## Verification boundary

`tests/test_provider_defaults.py` checks default selection, missing-key failures, forbidden offline production mode, secret-file precedence and worker-only Compose secret mounts. These tests do not contact OpenAI. A live provider test requires separately provisioned credentials and must be reported distinctly, using synthetic candidate data first. Do not print environment variables or secret file contents to diagnose setup.
