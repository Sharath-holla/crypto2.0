# Provider configuration and model routing

Place credentials in the server's private environment or a secret manager, never in a request, prompt, repository or browser form. Restart API/worker after changing their environment. Root `.env` is loaded without overwriting explicitly supplied environment variables.

In Models & Providers, create a connection using the adapter and base endpoint:

| Adapter | Base endpoint | Credential reference | Interface |
|---|---|---|---|
| openai | `https://api.openai.com/v1` | `OPENAI_API_KEY` | Responses, `text.format` JSON schema |
| anthropic | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` | Messages, `output_config.format` |
| gemini | `https://generativelanguage.googleapis.com/v1beta` | `GEMINI_API_KEY` | generateContent, responseJsonSchema |
| ollama | `http://localhost:11434` | `LOCAL_API_KEY` (unused) | generate, `format` schema, no stream |
| compatible | An explicitly allowlisted HTTPS endpoint | Dedicated `*_API_KEY` | Chat completions, provider-supported JSON schema |

Use an actual model ID available to your account. Enter its supported capabilities, context window, allowed sensitivity, quality and reliability assessments and source-backed token prices. Values are owner supplied; quality is not automatically benchmarked. There is no automatic discovery or live certification yet. Compatible providers must support the requested payload; interoperability is not assumed.

Prices are integer microdollars per million tokens: $2.50 / 1M tokens is `2500000`. Prices expire for routing after 30 days. A successful request's token usage is priced deterministically and displayed as a **computed estimate**. Cache charges are conservatively approximated at ordinary input rates. Provider invoices may differ; invoice ingestion is pending.

The router first excludes models that fail mode, capability, minimum quality, context, sensitivity, availability and price freshness. Economy chooses lowest eligible configured cost. Balanced, quality-first and fastest policies change ordering. Fallback uses at most three distinct eligible models and retains every run. It never uses fixture models for a live request.

Timeouts and malformed/ambiguous usage responses keep the reservation and stop the workflow. Reconcile the recorded charge with provider billing before authorizing a retry. Provider-side idempotency is not assumed. Safe rejected requests and validated quality failures can fall back with bounded attempts.

Official interfaces checked on October 8, 2026:

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Ollama generate](https://docs.ollama.com/api/generate)

Contract tests exercise these wire formats with HTTP fixtures. **Live verification is pending credentials.** Some models have provider-specific restrictions on schema keywords, output limits or reasoning settings; configure and verify each selected model before trusting its availability.

## Current provider controls

The owner can save an encrypted write-only API key, test/discover an account catalog and run a capped inference probe. API keys never appear in returned configuration. An independent PROVIDER_SECRET_KEY is required for vault writes; environment fallback remains optional. Supported catalogs include xAI in addition to the existing five adapter kinds. Catalog success and inference evidence are distinct; documented model capabilities/prices must still be configured. See MODEL_ROUTING.md and SECURITY.md. Native token streaming and tool-call interfaces are not yet implemented.
