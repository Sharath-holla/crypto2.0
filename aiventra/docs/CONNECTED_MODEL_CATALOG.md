# Connected models: discovery, preferences and execution

The owner brief is preserved in CONNECTED_MODEL_CATALOG_SPEC.md. This increment extends the existing vault, registry, wizard, staffing and routing services; SQLite remains authoritative at Alembic head d45f80a6ce12. No schema migration or active record replacement is needed.

## Diagnosed causes

Discovery previously saved identifiers in ProviderProbe.models without registering ModelConfig records. The wizard then required configured reasoning/structured capabilities for every Lead option, and both the worker picker and preference validator required immediate execution eligibility. Consequently, undiscovered or metadata-unknown models vanished, and ZERO_COST_ONLY hid remote models rather than explaining their blocked execution. The official DeepSeek API host was also absent from the default/local endpoint allowlist.

Read-only inspection found **zero encrypted ProviderCredential records** in the active workstation database and no genuinely configured OpenAI, xAI or DeepSeek connection. Retained legacy registrations are labeled policy/browser fixtures or disabled unreachable endpoints. Previously typing a key did not establish a saved connection. No chat-disclosed credential was used, no credential was requested, and no owner configuration was deleted. Inspection reported safe configuration facts only.

## Discovery and durable synchronization

Owner POST /providers/{id}/discover reuses provider_catalog.py and the encrypted vault. OpenAI/xAI/compatible adapters use GET /models, Ollama GET /api/tags; existing Gemini/Anthropic pagination remains bounded. DeepSeek uses the existing compatible adapter with its official endpoint. No static model inventory, inference, installation or weight download is involved. Host allowlisting, redirects/proxy refusal, time/byte/page/identifier bounds and fixed sanitized error codes apply.

model_catalog.py upserts the existing provider/identifier identity and records discovery facts in a protected provider_catalog BusinessRecord. Repeated discovery preserves IDs, enablement, owner capability/quality/context/pricing configuration and preferences. Unknown metadata stays unknown. Missing identifiers remain stored with present=false and cannot invoke inference; restoration reuses the same record. Errors preserve the last good catalog, visibly stale. Credential changes invalidate freshness. Interrupted discovery can safely retry. A generation counter, configuration/credential fingerprint and fresh owner check reject stale overlapping responses or revoked authority. No database write lock spans external HTTP.

Catalog model rows expose IDs, provider identity/name, discovery provenance/times, capability source, unknown support metadata, current spending eligibility and recorded live-inference evidence. They exclude credentials, ciphertext and secret references. Positive model-list fixtures do not establish live account entitlement or inference.

## Connected controls and preference semantics

Settings → Models & Providers displays configured providers first, model counts, discovery/refresh, sanitized errors, stale/interrupted state, search/provider/capability/executable/blocked filters and actual enable/configure controls. An explicit checkbox exposes retained unconfigured registrations. The New Project wizard consumes the same normalized catalog, groups Lead choices by provider, and supports saved blocked Lead/worker/role preferences in automatic/manual/hybrid modes. GPT-6.1 Sol remains a separately labeled unverified favorite; no API ID is invented.

Project default policies reuse existing scoped model policies. Staffing task selectors use the shared catalog for live preferences. TaskRequirements.preferred_model_id is stored in existing revision JSON, copied into the exact approved task payload and checked against the approved source on every task admission. It may reference a blocked real registered model. Legacy model_override remains a strict eligible assignment; conflicting identities, foreign/mock preferences and overrides in automatic mode are rejected. Explicit deterministic staffing retains its separately labeled mock selector.

An exact saved preference constrains existing routing; it cannot silently fall back to another Lead or task model. Gateway and transport recheck capability, sensitivity, authorization, current catalog availability, finance and ZERO_COST_ONLY. Availability reads current database columns rather than a cached ORM catalog object, so another connection's completed removal is observed. A blocked choice produces WAITING_FOR_FREE_PROVIDER, no model run and no reservation. Independent reviewers retain their own selection/diversity gates. Registered/discovered, configured, eligible and live-inference-recorded are separate states.

## Verification boundaries

TEST_REPORT.md is the executed evidence ledger. Backend tests use synthetic vault credentials and GET-only HTTP fixtures, exercise the actual registry/API/wizard/task approval/routing code and SQLite persistence, and prohibit paid inference. Isolated browser journeys exercise actual API/worker/UI on disposable SQLite; positive provider responses are explicitly deterministic. scripts/verify_model_catalog_recovery.py compares persisted catalog/registry/preference digests across actual restarts. The same storage synchronization probe runs on SQLite and disposable PostgreSQL CI. Active SQLite is preserved; compatibility CI is not a production cutover.

Live provider discovery, account entitlement, local AI inference/quality, generated PR publication, deployment and client delivery remain unverified. No model installation or paid invocation is authorized. Production readiness is not claimed.

Official metadata references: [OpenAI model listing](https://developers.openai.com/api/reference/resources/models/methods/list), [xAI models](https://docs.x.ai/developers/rest-api-reference/inference/models), [DeepSeek model listing](https://api-docs.deepseek.com/api/list-models). Model listing establishes identifiers, not billing eligibility.
