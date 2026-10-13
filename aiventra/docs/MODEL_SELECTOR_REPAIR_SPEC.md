# AIVENTRA OS — CRITICAL MODEL SELECTOR BUG FIX
## Remove Test-Generated Model Entries, Recover Real Provider Connections, Display Genuine AI Models and Improve the Entire Model Selection Experience

### EXISTING REPOSITORY

https://github.com/Sharath-holla/Aiventra.git

### EXISTING APPLICATION

http://localhost:3000

### PREVIOUSLY REPORTED STATUS

- Source commit: `ce1a647`
- Documentation commit: `822de8b`
- 405 backend tests passed
- 35 browser checks passed
- Six CI jobs passed
- SQLite active
- PostgreSQL compatibility preserved
- ZERO_COST_ONLY enforced
- Connected-model catalog and discovery UI implemented
- Lead AI and worker-model preferences implemented
- Automatic/manual/hybrid assignment implemented

Verify the actual current Git HEAD before changing anything.

---

# 0. CRITICAL PROBLEM — SCREENSHOT ANALYSIS

I have attached a screenshot of my current Aiventra application.

The screenshot shows:

**Page:** New Project → Choose AI Models

**Section:** Lead AI

The dropdown currently contains:

- `GPT-6.1 Sol · preferred, unavailable`
- `Browser vault contract 1791483886084`
- `Browser vault contract 1791484021978`
- `Browser vault contract 1791485310611`
- `Browser vault contract 1791485607374`
- Many more similarly named `Browser vault contract` entries

THIS IS NOT WHAT I WANT.

These entries appear to be test-generated provider/model records rather than genuine OpenAI, Grok or DeepSeek models.

Do not assume their origin solely from the names. Trace their exact persisted records, creation paths and provenance before making any changes.

My model dropdown must not be filled with browser-test artifacts or unrelated internal records.

I want to see the REAL MODELS associated with the providers I actually configured in Aiventra.

For example, if my OpenAI provider is genuinely configured and discovery succeeds, display the actual OpenAI model IDs returned by that provider.

If Grok is configured, display genuine xAI model IDs.

If DeepSeek is configured, display genuine DeepSeek model IDs.

If no providers are currently configured, show an honest empty state and a clear way to connect them.

**DO NOT HARDCODE FAKE MODEL NAMES TO MAKE THE DROPDOWN LOOK POPULATED.**

**DO NOT HIDE THE PROBLEM BY ONLY CHANGING CSS.**

**FIX THE UNDERLYING MODEL REGISTRY, TEST ISOLATION, PROVIDER SYNCHRONIZATION AND UI.**

---

# 1. IMMEDIATE PRIORITY — INVESTIGATE TEST DATA CONTAMINATION

Before further feature development, inspect the full source and database path involved in this issue.

Investigate:

- Model registry implementation
- Provider registry
- Encrypted provider vault
- Project creation options API
- Lead AI selector
- Worker model selector
- Model synchronization
- Browser test setup and teardown
- Playwright fixtures
- Backend pytest fixtures
- Browser vault contract test cases
- Test database initialization
- SQLite configuration
- Frontend/backend environment configuration
- Organization scoping
- Model registry persistence

Search for the exact string:

`Browser vault contract`

Also search for:
- Similar model-name generators
- Browser fixture factories
- Temporary provider configurations
- Timestamp-based fake names
- Test-generated model registrations
- Test-generated credential records
- Persistent browser test users
- Reusable seeded test organizations

Determine:

1. Which code creates these entries?
2. Are they model records or provider records?
3. Which database contains them?
4. Which organization owns them?
5. Are they generated during browser tests?
6. Why are they visible in the normal owner workspace?
7. Are browser tests writing into the actual development SQLite database?
8. Is test teardown incomplete?
9. Is model catalog querying missing organization or provenance filtering?
10. Are stale records surviving after tests finish?

Document the confirmed root cause.

Do not guess.

---

# 2. PROTECT EXISTING SQLITE RECORDS

I have explicitly chosen SQLite as Aiventra's active database.

DO NOT:
- Delete the SQLite database.
- Recreate the application database.
- Run destructive migrations.
- Reset the owner account.
- Delete existing projects.
- Delete chats.
- Delete requirements.
- Delete agent records.
- Delete approvals.
- Delete provider configurations.
- Delete real registered models.

Before modifying existing registry records:

1. Identify the actual active SQLite database file.
2. Confirm which process is using it.
3. Create a recoverable backup using SQLite's supported backup mechanism.
4. Verify backup integrity.
5. Run foreign-key integrity checks.
6. Preserve existing owner and organization data.

For suspicious entries:

- Determine their exact record IDs.
- Inspect related records and foreign keys.
- Identify their origin.
- Distinguish genuine owner-created data from automated fixtures.
- Determine whether removing or quarantining them would break saved project preferences.

Do not delete records based only on matching a name prefix.

If records are conclusively proven to be test-only and unused, quarantine or clean them through a controlled, audited process.

If an entry has legitimate references or uncertain ownership, preserve it and exclude it from production model choices only when safely justified.

For a destructive cleanup of existing ambiguous records, prepare a reviewable cleanup plan and require my approval.

Provide:
- Record count.
- Affected tables.
- Proposed action.
- Backup reference.
- Referential-integrity impact.
- Recovery method.

Never run a blanket DELETE based on `Browser vault contract%`.

---

# 3. PREVENT TEST RECORDS FROM APPEARING IN THE APPLICATION

Implement robust separation between:

- Real owner-created provider records
- Real discovered model records
- Saved model preferences
- Automated test fixtures
- Deterministic development simulation records

Test entries must never appear as real connected AI models.

## Required Registry Changes

Reuse existing data structures where possible.

If necessary, add explicit provenance metadata such as:

- Source type
- Test fixture identifier
- Discovery source
- Owner registration
- Provider account reference
- Created by
- Environment
- Organization
- Verification status

Possible source classifications:

- `provider_discovery`
- `owner_registered`
- `saved_preference`
- `test_fixture`
- `system_example`

Use project conventions and backward-compatible migrations.

Do not infer that a record is genuine simply because it exists in SQLite.

The real-user catalog must include only authorized records of appropriate provenance.

A fixture-only model must never be selectable for real inference.

Maintain fixture-model access in isolated test environments so existing tests continue working.

---

# 4. FIX THE BROWSER TEST DATABASE ISOLATION

This is a critical requirement.

A successful test suite must not pollute the normal application database.

Inspect Playwright and backend testing infrastructure.

Determine whether tests currently share:
- The developer's real SQLite database.
- The actual owner organization.
- Real provider registry records.
- Real provider vault.
- Real project drafts.
- Live user sessions.

If so, fix it.

## Test Database Requirements

Each test run must use an isolated, disposable database or explicitly scoped test environment.

Prefer:
- Temporary SQLite databases for local tests.
- Unique test organization identifiers.
- Disposable test accounts.
- Isolated test provider vault.
- Deterministic fixtures.
- Reliable setup and teardown.

Testing must never require deleting genuine user data.

Enforce a test-environment guard that prevents accidental use of the configured development/production database.

Ensure that environment detection is server-side, not just a frontend flag.

If a test database path resolves to the real application database, fail safely before writes occur.

Also verify:
- Test fixtures do not use live API keys.
- Tests cannot trigger paid inference.
- Tests cannot publish real PRs.
- Tests cannot mutate unrelated owner projects.
- Test cleanup does not remove records it did not create.
- Parallel tests cannot overwrite each other's data.

## Regression Test

Create a browser test that:

1. Records the existing development registry state.
2. Runs isolated browser-vault contract tests.
3. Verifies the development registry is unchanged.
4. Opens the normal model-selection page.
5. Confirms that no test-created entries appear.

Make this a durable regression test.

---

# 5. INVESTIGATE WHY MY CONNECTED PROVIDERS ARE MISSING

My previous Codex report said:

**The active encrypted provider vault contains zero saved provider credentials.**

This conflicts with my understanding that I had previously connected OpenAI, Grok and DeepSeek.

Investigate this carefully.

Inspect:
- Active SQLite path.
- Original configured database path.
- Provider vault tables.
- Provider configuration migrations.
- Active organization ID.
- Owner account ID.
- Encryption-key references.
- Provider API routes.
- Environment variables.
- Startup configuration.
- Database restore history where available.
- Credential-save implementation.
- Provider reconnect flow.

Determine whether:

1. Credentials were never saved.
2. Credentials were saved in a different SQLite database.
3. The application later switched database paths.
4. Provider configurations exist under a different organization.
5. Encryption keys changed.
6. Vault records exist but are unreadable.
7. The UI showed a successful connection even though the backend failed to save it.
8. Credentials were removed during migration or testing.
9. Provider metadata remains while secret records are missing.
10. The previous inspection was querying the wrong active database.

Do not search unrelated personal directories for secrets.

Do not print encryption keys or decrypted provider credentials.

Do not reconstruct or invent credentials.

If the keys are genuinely missing, clearly explain that I need to reconnect the providers through the secure Settings interface.

Do not automatically ask me to paste secrets into a chat or terminal.

---

# 6. IMPLEMENT RELIABLE PROVIDER CONNECTIONS

Reuse the existing encrypted vault.

Support:
- OpenAI
- xAI / Grok
- DeepSeek
- Ollama
- Other existing supported providers

When I configure a provider:

1. Select provider.
2. Enter credential using a secure password input.
3. Submit to backend over the existing authenticated channel.
4. Encrypt and persist the credential.
5. Save non-secret provider metadata.
6. Return a truthful result.
7. Make the connection visible in Settings.
8. Enable supported model discovery.
9. Preserve connection after restart.

## Credential Persistence

Verify credentials persist across:
- Browser refresh.
- Logout/login.
- API restart.
- Worker restart.
- Full application restart.

Never send credential values back to the browser.

Do not include credentials in:
- API responses
- Audit logs
- Error messages
- Screenshots
- Test reports
- Git commits
- Console logs

If an encrypted credential cannot be decrypted, show a safe reconnect-required status rather than pretending the provider is connected.

---

# 7. REAL PROVIDER MODEL DISCOVERY

After a provider is successfully configured, its model catalog should be obtainable through supported non-inference discovery interfaces.

## OpenAI

Use official supported catalog discovery where available.

Normalize actual provider identifiers.

Do not invent model names.

Do not assume model listing proves inference entitlement.

## xAI / Grok

Use its supported model listing interface if available.

Handle provider-specific metadata correctly.

## DeepSeek

Use supported catalog discovery where available.

If discovery is not supported for a particular configuration, provide an owner-controlled registration path using verified documented model IDs.

Distinguish owner registration from live discovery.

## Ollama

Check whether an existing Ollama endpoint is available.

If available, discover locally installed models.

If unavailable, show:

"No local models detected."

Do not install Ollama or download models without authorization.

## Discovery Safety

Discovery must:
- Have bounded timeouts.
- Handle rate limiting.
- Handle authentication failure.
- Cache valid results.
- Track freshness.
- Avoid duplicate entries.
- Avoid paid inference calls.
- Avoid exposing credentials.
- Preserve last known valid model data.
- Identify stale data honestly.

If an endpoint is not verified to be free of inference charges, do not call it automatically.

No unapproved live inference probes.

---

# 8. MODEL CATALOG DATA CONTRACT

Implement a normalized model catalog using the existing registry.

A model record should expose safe fields such as:

- Internal model ID
- Provider ID
- Provider display name
- Provider model identifier
- Model display name
- Model provenance
- Registered/discovered state
- Provider connection state
- Actual verified capability information
- Context limits when known
- Tool calling support when known
- Streaming support when known
- Local/remote classification
- Pricing verification state
- ZERO_COST_ONLY eligibility
- Blocked reason
- Last discovery timestamp
- Last live verification timestamp

Separate the concepts:

**Configured:** Provider metadata and accessible authorized credentials exist.

**Discovered:** The provider returned a valid model identifier.

**Registered:** A model record exists.

**Eligible:** The backend authorizes the model under the current policies.

**Live verified:** Actual authorized model inference was completed successfully.

Never conflate these.

A model may be displayed while execution is blocked.

A model must not be displayed as live verified based only on fixture tests.

---

# 9. REBUILD THE MODEL SELECTOR UX — NOT THE WHOLE APP

The screenshot shows a giant native dropdown with many unrelated entries.

I want a better UI.

Keep the current dark design and three-step project wizard.

Do not redesign the entire application.

Replace the problematic Lead AI selector with a searchable, accessible model-selection component.

## Required Appearance

Section:

**Choose your Lead AI**

Display a compact model picker.

Organize genuine entries by provider.

Example grouping structure:

OpenAI
- Actual discovered model
- Actual discovered model

Grok
- Actual discovered model

DeepSeek
- Actual discovered model

Local
- Actual installed model

These are illustrative groups, not instructions to create fake entries.

## Model Rows

Each model should display:

- Model name
- Provider
- Short capability description where verified
- Availability status
- Blocked reason when applicable

For example:

"Model XYZ"
"OpenAI · Paid API blocked"

Or:

"Model ABC"
"Local · Ready to use"

Use real model names and real status information.

## Search

The existing Search AI models field must actually filter the displayed results.

Support:
- Search by model name.
- Search by provider.
- Filter by provider.
- Show all registered/discovered models.
- Show ready-to-use models.
- Show unavailable models.

The UI must not load hundreds of options into an enormous native select without useful search or grouping.

Use a bounded-height list with scrolling or virtualization.

Ensure keyboard accessibility and mobile responsiveness.

## Show Only Relevant Models

By default, include models associated with:
- Configured providers in the current organization.
- Previously registered owner models that remain valid.
- Actual installed local models.
- Explicit saved preferences, shown separately if not verified.

Do not show:
- Browser test fixtures.
- Temporary QA provider records.
- Unrelated organizations' models.
- Internal contract-test placeholders.
- Arbitrary synthetic registry examples.
- Duplicates caused by repeated synchronization.

Never remove a genuine owner-created model just because its display name resembles a test entry.

---

# 10. GPT-6.1 SOL PREFERENCE

The screenshot currently shows:

`GPT-6.1 Sol · preferred, unavailable`

I want GPT-6.1 Sol as my preferred central Lead AI.

Keep this preference.

But do not pretend it is an executable registered model if the corresponding supported provider identifier or account entitlement is unverified.

The UI should distinguish:

**Preferred Lead AI**

GPT-6.1 Sol — Not currently available.

**Available connected models**

Actual models discovered or registered for my configured providers.

If GPT-6.1 Sol becomes eligible through an officially supported authorized integration, allow selecting its verified registry entry.

Otherwise, allow me to save the preference and select another eligible model explicitly.

Do not automatically replace GPT-6.1 Sol.

Do not bypass ZERO_COST_ONLY.

Do not assume my ChatGPT Plus subscription gives free OpenAI API inference.

---

# 11. WORKER MODEL SELECTION

Fix the worker-model controls at the same time.

The project wizard currently supports:
- Automatic
- Manual
- Hybrid

Preserve all three.

## Automatic

The Lead AI recommends eligible worker models per task.

The backend validates its recommendations.

## Manual

Allow me to select a real model for:
- Business Analyst
- Architect
- Backend Developer
- Frontend Developer
- Data Engineer
- Coding Agent
- QA Reviewer
- Security Reviewer
- DevOps Engineer
- Documentation Agent

Do not show every possible role if the project doesn't need it.

## Hybrid

Allow automatic suggestions with owner overrides.

## Persistent Selection

Store:
- Project ID
- Lead model preference
- Selected registry model ID, when available
- Allowed worker pool
- Assignment mode
- Manual overrides
- Routing rationale
- Eligibility state

Persist in SQLite.

Restore after refresh and restart.

Never permit a blocked model to execute simply because it was saved as a preference.

---

# 12. MODEL EXECUTION ENFORCEMENT

Preserve:

`AI_SPENDING_MODE=ZERO_COST_ONLY`

The model catalog is a display and selection feature.

The model router is an execution authority.

These must remain separate.

When I choose a model in the UI, that choice must not bypass backend eligibility checks.

Before every inference:

1. Verify the provider is configured.
2. Verify the registry model reference.
3. Verify capabilities.
4. Verify permissions.
5. Verify project scope.
6. Verify verified free entitlement or approved local execution.
7. Check concurrency and resource limits.
8. Check review-independence restrictions.
9. Confirm any required approval.

If eligibility fails, keep the task waiting with a meaningful explanation.

Do not make paid OpenAI, xAI or DeepSeek inference calls.

Do not silently enable a paid fallback.

Do not add paid API credits.

Do not install local models without authorization.

---

# 13. FIX MODEL DISCOVERY/REFRESH BUTTONS

The UI currently includes:

**Refresh model choices**

Make this button actually work.

It must:

- Refresh the authorized model catalog.
- Use existing provider connections.
- Call supported discovery endpoints when allowed.
- Synchronize valid registry entries.
- Update the selector without a full page reload.
- Display loading state.
- Display result count.
- Display last refresh status.
- Display sanitized errors.
- Preserve the user's selected model where valid.

If no providers are connected, show:

"No providers are connected yet. Open Settings to connect OpenAI, Grok or DeepSeek."

Provide a working navigation action.

Do not show a blank list or silent failure.

---

# 14. IMPROVE MODELS & PROVIDERS SETTINGS

In Settings create or refine:

**Models & Providers**

Show a clear provider list.

For each provider:

- Provider name
- Connection state
- Number of real discovered/registered models
- Last successful discovery
- Last error
- Configure/reconnect action
- Refresh models action
- View models action

The provider status must accurately distinguish:
- Not configured
- Configured
- Credential unavailable
- Discovery successful
- Discovery failed
- Catalog stale
- Models available
- Models blocked by cost policy

Do not display "Connected" simply because a provider label exists in SQLite.

---

# 15. HANDLE ALL EMPTY STATES

The application must remain understandable in every situation.

## No Providers Connected

Display:

"No AI providers are connected yet."

Action:

"Connect an AI provider"

## Configured Provider Without Discovered Models

Display:

"This provider is configured, but no models have been discovered."

Action:

"Discover models"

## Models Found but All Blocked

Display:

"Models are available in your catalog, but none can currently run under ZERO_COST_ONLY."

Show the actual models and blocking reasons.

## Discovery Error

Display a sanitized error, retry button and last successful result if available.

## Saved Unavailable Model

Show its saved preference separately, without implying it can execute.

## Only Test Records Exist

Do not present the test records as real model choices.

Show the genuine catalog empty state and provide the proper configuration path.

---

# 16. REQUIRED SECURITY CHECKS

Treat this as both a UI defect and a possible data-isolation defect.

Investigate whether browser test records are visible because of missing organization-scoped filtering.

Verify:
- Owner workspace isolation.
- Client isolation.
- Test-organization isolation.
- Provider credential scoping.
- Registry access control.
- Project-to-model permissions.
- Cross-organization model references.
- Unauthorized owner preferences.
- Safe handling of missing or corrupted secrets.

If a security boundary is broken, fix the backend authorization rather than just hiding records in React.

Run regression tests for cross-organization access.

Do not expose provider credentials during debugging.

---

# 17. DATABASE CLEANUP AND RECOVERY VERIFICATION

After isolating the cause:

1. Back up the active database.
2. Verify the backup.
3. Classify suspicious records.
4. Identify safe cleanup candidates.
5. Exclude test-only entries from real model selection.
6. Preserve legitimate records.
7. Verify foreign keys and references.
8. Restart the application.
9. Confirm test entries no longer appear in normal selectors.
10. Confirm original project data remains unchanged.

Any deletion of potentially legitimate records requires my review and approval.

If removing safe fixture records is unnecessary, prefer isolation and quarantine rather than destructive cleanup.

Ensure future CI and browser tests cannot repopulate the normal model catalog with synthetic records.

---

# 18. COMPLETE AUTOMATED TEST PLAN

Add regression coverage for the exact screenshot problem.

## Model Catalog Tests

1. Genuine model appears.
2. Configured provider with no model shows empty state.
3. Test-fixture model is excluded from real catalog.
4. Owner-registered model remains visible.
5. Paid model remains visible with a blocked status.
6. Unknown-price model is blocked from execution.
7. Disconnected provider status is accurate.
8. Duplicate discovery does not create duplicate models.
9. Saved unavailable preference is displayed separately.
10. Invalid model registry references are rejected.

## Browser-Test Isolation

11. Test suite uses isolated database.
12. Test provider records never appear in owner catalog.
13. Parallel tests remain isolated.
14. Cleanup does not remove real records.
15. Fixture-generated models cannot execute in live mode.
16. Tests refuse unsafe database configuration.

## Provider Vault

17. Credential save persists.
18. Vault can be read by authorized backend.
19. Credential value is never returned to browser.
20. Failed decryption is handled safely.
21. Incorrect SQLite path is detected.
22. Wrong organization scope is rejected.
23. Reconnection replaces only the authorized credential.
24. Service restart preserves provider configuration.

## Model Discovery

25. OpenAI response normalization.
26. xAI response normalization.
27. DeepSeek response normalization.
28. Provider timeout.
29. Invalid credentials.
30. Empty model catalog.
31. Rate limiting.
32. Stale-cache display.
33. Repeated refresh.
34. Provider-catalog reconciliation.

Use deterministic mocked provider responses for these tests.

Do not use paid model inference.

## Frontend

35. Model dropdown does not display Browser vault contract test entries.
36. Search filters model names.
37. Provider filter works.
38. Dropdown has bounded height.
39. Group labels appear correctly.
40. Model status is understandable.
41. Lead AI selection saves.
42. Worker model selection saves.
43. Manual overrides work.
44. Browser refresh restores selection.
45. API restart preserves selection.
46. No-provider state shows setup action.
47. Discovery failure shows retry.
48. Mobile layout works.
49. Keyboard navigation works.
50. Screen-reader labels are correct.

## Existing System Regression

Verify:
- Three-step project wizard.
- Requirement upload.
- Task-specific worker routing.
- Lead AI planning.
- Manual proposals.
- Agent messaging.
- Persistent memory.
- GitHub checkout.
- Restricted runner.
- QA.
- Owner approval.
- Phase 5 delivery.
- Client acceptance.
- SQLite restart recovery.
- PostgreSQL compatibility.
- ZERO_COST_ONLY enforcement.

---

# 19. TEST EXECUTION AND CI

Run:

- Full backend test suite.
- Focused provider-vault tests.
- Model registry tests.
- Browser tests.
- Security tests.
- SQLite integrity.
- SQLite restart recovery.
- TypeScript checks.
- Frontend build.
- Ruff.
- Formatting.
- Dependency audit.
- Secret scan.
- GitHub Actions.

Do not lower test coverage or remove failing assertions.

If a test fails, investigate the actual regression.

Keep the normal application database isolated from test execution.

Use the existing Docker and PostgreSQL CI checks where available.

Do not falsely claim that fixture-tested provider discovery proves live account access.

---

# 20. REQUIRED MANUAL BROWSER VERIFICATION

After implementation, open the actual running application.

URL:

http://localhost:3000

Log in as the existing owner.

Navigate to:

**New Project → Choose AI Models**

Verify visually:

1. The huge list of Browser vault contract entries is gone.
2. No synthetic model names appear.
3. GPT-6.1 Sol preference is displayed accurately.
4. Configured providers appear correctly.
5. Genuine registered models appear when present.
6. Search works.
7. Provider filtering works.
8. Lead AI can be selected.
9. Worker models can be selected.
10. Blocked models have explanations.
11. Preferences persist after refresh.
12. No unexplained empty dropdown remains.

If the credential vault is genuinely empty, the expected result is a clear provider-setup state, not a fabricated OpenAI/Grok/DeepSeek model catalog.

Take screenshots before and after the fix as verification evidence where supported.

Inspect the actual UI, not only test snapshots.

---

# 21. IMPLEMENTATION ORDER

Work in verified increments.

### Increment A — Diagnose

- Reproduce the screenshot issue.
- Trace Browser vault contract entries.
- Locate database origin.
- Determine whether test contamination or query scoping is responsible.
- Report evidence.

### Increment B — Isolate Tests

- Repair test environment separation.
- Add test DB guards.
- Ensure fixture provenance.
- Prevent future contamination.

### Increment C — Repair Model Registry

- Correct real-user catalog queries.
- Enforce organization and provenance scope.
- Preserve registered models.
- Handle duplicates and stale entries.

### Increment D — Provider Vault Recovery

- Trace currently configured providers.
- Verify actual SQLite path.
- Repair credential-save and persistence defects.
- Support secure reconnection when secrets are absent.

### Increment E — Real Model Discovery

- Normalize actual provider catalogs.
- Synchronize registry.
- Preserve model capability and billing status.
- Provide useful diagnostics.

### Increment F — UI Repair

- Replace enormous dropdown.
- Add grouped searchable model picker.
- Fix Refresh model choices.
- Show connected models.
- Show unavailable models separately.
- Support Lead and worker selection.

### Increment G — Persistence

- Save exact model references.
- Save owner preferences.
- Verify task routing.
- Verify browser and service restart.

### Increment H — Full Verification

- Backend regression.
- Browser regression.
- Security.
- SQLite recovery.
- Build/typecheck.
- Real UI inspection.
- CI.

### Increment I — GitHub Publication

- Update documentation.
- Inspect diff.
- Scan for secrets.
- Commit tested source.
- Push to existing repository.
- Verify GitHub Actions.

Do not start unrelated features before the model-selector problem is resolved.

---

# 22. DOCUMENTATION

Update:

- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- TEST_REPORT.md
- ARCHITECTURE.md
- MODEL_CONFIGURATION.md
- MODEL_ROUTING.md
- PROJECT_WIZARD.md
- SECURITY.md

If necessary create:

`MODEL_CATALOG_ISOLATION.md`

Document:
- Root cause.
- Affected database records.
- Test isolation fix.
- Provider-credential findings.
- Model discovery behavior.
- UI changes.
- Billing restrictions.
- Verification evidence.

---

# 23. FINAL REPORT TO ME

After implementation, provide a precise report.

## Root Cause

What generated the Browser vault contract entries?

Why did they appear in my normal Lead AI dropdown?

Was there actual test data contamination, missing provenance filtering, a scope issue or something else?

## Database Protection

- Active database path, without exposing secrets.
- Whether backup succeeded.
- Number of suspicious records.
- Cleanup/quarantine actions.
- Data preservation.
- Integrity verification.

## Provider Connection Status

For each provider:

- OpenAI
- Grok/xAI
- DeepSeek
- Ollama

Report:
- Configured or not configured.
- Discovery attempted or not.
- Number of genuine models.
- Sanitized errors.
- Last verified status.

Never include API keys.

## UI Status

Confirm:
- Browser contract entries no longer appear.
- Genuine model picker works.
- Search works.
- Provider groups work.
- Lead AI can be selected.
- Worker models can be selected.
- Preferences persist.
- Empty states are informative.

## Testing

Report:
- Backend tests.
- Browser tests.
- Security tests.
- SQLite integrity.
- Production build.
- PostgreSQL compatibility.
- CI status.

## Source Control

Report:
- Starting SHA.
- Final source SHA.
- Documentation SHA.
- GitHub Actions URL.
- Whether working tree is clean.

## Remaining Limitations

Clearly distinguish:
- Registered models.
- Connected providers.
- Verified inference eligibility.
- Fixture-tested discovery.
- Live model execution.
- Unsupported or missing credentials.

Do not claim any real AI call happened if none did.

---

# 24. NON-NEGOTIABLE REQUIREMENTS

DO NOT rebuild Aiventra.

DO NOT delete SQLite data.

DO NOT migrate to PostgreSQL.

DO NOT delete saved project histories.

DO NOT clear the encrypted vault.

DO NOT expose API keys.

DO NOT copy credentials into source code.

DO NOT fabricate model catalogs.

DO NOT populate the UI with static fake model names.

DO NOT allow browser test fixtures in the normal model selector.

DO NOT perform paid AI inference.

DO NOT bypass ZERO_COST_ONLY.

DO NOT automatically install Ollama.

DO NOT download model weights.

DO NOT publish generated PRs without owner approval.

DO NOT deploy cryptocurrency or other client applications.

DO NOT fake live AI verification.

DO NOT stop after writing a diagnostic report.

**FIX THE ACTUAL SOURCE CODE.**

---

# FINAL EXPECTED RESULT

When I open Aiventra at:

http://localhost:3000

And navigate:

**New Project → Choose AI Models**

I should see a clean, searchable, professional Lead AI selector.

I should NOT see dozens of entries named:

`Browser vault contract 179...`

Instead, I should see:

- Models genuinely associated with configured OpenAI accounts.
- Models genuinely associated with configured Grok accounts.
- Models genuinely associated with configured DeepSeek accounts.
- Installed local models, when available.
- Clear unavailable-model preferences.
- Clear billing eligibility.
- Clear provider-connection diagnostics.

If no providers are configured, I should see:

"No AI providers are currently connected."

And a working action:

**Connect AI Provider**

After I connect a provider through secure Settings and successfully discover its models, they should appear in this same picker without duplicate or synthetic entries.

I should be able to:
- Select the Lead AI.
- Select Automatic worker routing.
- Select Manual worker models.
- Override models in Hybrid mode.
- Save the project.
- Reopen it.
- See the same saved preferences.
- Use approved eligible models when execution is authorized.

All this must happen while preserving:

- SQLite
- Existing data
- PostgreSQL compatibility
- ZERO_COST_ONLY
- Model router enforcement
- Existing agent orchestration
- Phase 4 engineering
- Phase 5 delivery
- GitHub approval controls

**START IMMEDIATELY BY TRACING THE `Browser vault contract` RECORDS IN THE ACTUAL DATABASE AND TEST INFRASTRUCTURE.**

**THEN FIX MODEL CATALOG ISOLATION, REPAIR THE MODEL PICKER, VERIFY PROVIDER CONNECTIONS AND TEST THE REAL UI.**

**COMMIT, PUSH AND VERIFY ALL CHANGES.**