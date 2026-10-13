# Model catalog isolation and selector repair

Phase 6 follow-up: actual signed-in owner catalog and provider-configuration navigation succeeded before the managed-service restart, with no genuine connected provider choices. The new readiness/waiting screens passed private browser tests; after restarting local services the user tab returned to a cached connection-error page which browser URL policy refused. Manual tab reload is pending for final owner-tab screen inspection; API/web health checks return 200. Fixture catalog, credential and live-inference boundaries remain unchanged. New protected invocation receipts prevent historical local cost labels from counting as live verification.

Continuation starts at **822de8b** (application source ce1a647). SQLite remains authoritative; PostgreSQL cutover, model installation, paid inference and generated PR publication are not authorized.

## Confirmed cause

The ordinary Playwright configuration pointed to the existing localhost:3000 application, read the owner's `.env` login and had no disposable API/database fixture. `agent-work.spec.ts` created timestamped Browser vault contract providers and Unreachable local catalog providers. Its finally block revoked the synthetic credential and disabled providers, but did not remove records. `native-execution.spec.ts` and `zero-cost.spec.ts` also persisted synthetic models. Tests therefore wrote into the sole existing organization in `data/company.db`.

The shared catalog already scoped queries to that organization and excluded mock adapters, but had no fixture provenance boundary. It included every non-mock provider (including disabled ones), and the native Lead dropdown rendered their provider optgroups even when they contained no models. Browser vault contract entries are **provider records, with no models**. The screenshot was not evidence of genuine discovered OpenAI models. This was actual test contamination and missing provenance filtering, rather than a demonstrated cross-organization query leak.

## Database protection and quarantine

Managed API/worker/web services were stopped. SQLite's supported online backup created `data/backups/registry-before-quarantine-83f2dce9-1297-4737-a73d-2d894492e58a.db`; backup integrity and foreign-key checks passed. Active integrity remains `ok`, with zero foreign-key violations.

`scripts/quarantine_browser_registry.py` defaults to a reviewable dry run. It matches exact test credential references, endpoint/kind, timestamped registration audits and appropriate revoke/model-registration/source evidence. A name alone never qualifies. Existing vault or populated environment credentials, unexpected models and incomplete evidence cause refusal. The resulting private plan records exact provider/model/audit IDs in `data/catalog-quarantine-plan.json` and its application receipt in `data/catalog-quarantine-applied.json`.

**115 providers / 53 models** were classified as test fixtures. No provider/model/project/credential/preference/history record was deleted, disabled or rewritten. Protected registry_provenance BusinessRecords and append-only audit events were added. Comparison against the backup confirmed **49,399 original rows in 57 tables (including Alembic)** remained identical, excluding only organization audit_head/version advanced by the new audit events. All original foreign keys and JSON references survive. Historical preferences are retained but quarantined entries cannot authorize live execution or new normal-workspace choices.

Retained affected references include 53 model-to-provider foreign keys and 62 provider probes. No saved project draft referenced the quarantined models at inspection. The active registry still contains 116 providers (including the explicit mock adapter), 55 models and zero vault records; these retained historical counts do not represent connected genuine models. Final read-only registry digests match the ordinary browser suite's pre-run snapshot.

Recovery: keep the private backup and receipt. Do not overwrite a running database. An explicitly reviewed full restore must stop writers and account for all subsequent changes; selective reversal should append a new provenance/audit decision after owner review rather than deleting history. No ambiguous record is destructively cleaned automatically.

## Credential investigation

The active database, both older root-level SQLite snapshots and all six project-owned backup databases inspected contain **zero provider vault records**. There is one organization and one owner. All 31 credential-store audits refer to the exact browser-test credential reference, with 62 corresponding revoke audits; no store audit for another provider was found. The configured SQLite path matches the managed launcher/default configuration. The encrypted vault is empty, rather than populated but failing decryption. There is no evidence in these inspected records of a saved genuine OpenAI, xAI or DeepSeek key, a cross-organization vault, or a key-loss event. This does not prove credentials never existed elsewhere.

OpenAI, Grok/xAI and DeepSeek have no genuine connected configuration/model in this active workspace. All non-mock registry entries were confirmed fixtures. Ollama has no verified genuine installed model here; failed port-9 catalog checks were browser fixtures. No genuine account discovery/inference was attempted. Reconnect through Settings → Models & Providers → Provider connections using the password input; never paste secrets in chat. Existing AES-GCM encrypted persistence and safe reconnect-required errors remain in use.

| Provider | Genuine configured connection | Genuine discovered models | Live discovery in this repair |
| --- | --- | --- | --- |
| OpenAI | None found | 0 | Not attempted |
| Grok/xAI | None found | 0 | Not attempted |
| DeepSeek | None found | 0 | Not attempted |
| Ollama | None verified | 0 | Not attempted; historical port-9 error was a test fixture |

The authenticated running catalog and project options each return zero normal choices, with ZERO_COST_ONLY enforced. There is no live provider error to report because no genuine discovery was attempted. Successful listing alone would not authorize remote inference when zero-cost entitlement cannot be enforced.

## Boundaries and UI

Authenticated provider registrations now receive protected source/environment/creator provenance. Legacy registrations remain visible rather than being guessed fake by name. Discovered IDs retain discovery facts; fixture provenance takes precedence over discovery. Normal catalog, state-backed selectors, project/task preferences and provider discovery reject quarantined fixtures. Both gateway and inference transport use the fresh persistent spending guard; fixture entries cannot become live Ollama candidates through metadata edits. Explicit mock adapters still support deterministic workflows.

Ordinary browser runs use a UUID directory under data/pytest-temp, private fixture.db, separate synthetic owner/vault, ports 8002/3002 and network-denied transports. Tests no longer read owner login settings or reuse the active application. A server-side guard refuses unsafe paths/backends/environments before connecting. Fixture visibility is allowed only in explicitly fenced isolated test environments, while live inference stays blocked. Test runs preserve their disposable evidence; no cleanup touches user records. The suite captures read-only development registry digests before and after execution and fails if provider/model/vault records changed. Separate Phase 5 fixtures use the same provenance fencing.

The Lead selector is a bounded provider-grouped radio list with native keyboard/screen-reader controls, real search/provider/availability filters and a separate GPT-6.1 Sol preference. Selected historical missing references are labeled separately. Worker pools are bounded; automatic/manual/hybrid and saved role overrides remain. Initial analysis roles are shown; owners can add participating roles when needed. Refresh model choices performs bounded existing non-inference discovery for configured enabled providers, reloads the shared catalog, reports counts/sanitized errors and preserves selections. Empty states link to actual provider Settings. Registration, discovery, configuration, eligibility and successful live inference remain separate facts.

## Evidence boundary

Positive provider and picker paths use explicit deterministic, network-denied fixtures. ZERO_COST_ONLY remains mandatory; remote credentials/listing never establish free inference entitlement. No paid AI call, model installation/download, real generated PR, deployment or client delivery is claimed. Exact regression/build/restart/CI outcomes are recorded in TEST_REPORT.md after execution.

The CI integration additionally retains every ordinary browser journey and service/database recovery check against actual PostgreSQL. `compose.browser-ci.yaml` creates a separate `browser_ci_<run>_<attempt>` database and synthetic browser owner; PostgreSQL fixture startup requires CI=true, the exact matching database identity, the internal database hostname and test mode. The alternate Playwright configuration refuses ordinary local use and checks that container fence before browser writes. The default local configuration always launches its disposable SQLite services. No recovery assertions were removed when fixing local isolation.
