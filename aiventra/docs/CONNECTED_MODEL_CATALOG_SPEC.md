# AIVENTRA OS — COMPLETE CONNECTED AI MODEL DISCOVERY, REGISTRATION AND UI SELECTION

## PRIMARY OBJECTIVE

Continue developing my EXISTING Aiventra OS repository.

**GitHub:** https://github.com/Sharath-holla/Aiventra.git

I have already submitted the separate development task for:
- Intelligent task decomposition
- Workforce allocation
- Task-specific model routing
- Document uploads
- Repository import

Do not abandon, duplicate or rebuild that functionality.

**MY IMMEDIATE PROBLEM: I HAVE ALREADY CONFIGURED AI PROVIDERS IN AIVENTRA, BUT THEIR MODELS ARE NOT APPEARING IN THE USER INTERFACE.**

I want all genuinely available, registered or discoverable models associated with my configured providers to appear in the model-selection UI.

I want to select:
1. The Lead AI / Master Orchestrator.
2. Worker AI models.
3. Task-specific models.
4. Default models for a project.

The selected models must be saved and used by the existing model routing and orchestration services when execution is authorized.

This must be a fully functional implementation, not a static dropdown.

---

# 1. EXISTING PROJECT CONTEXT

Aiventra already has:

- Next.js frontend
- FastAPI backend
- Encrypted provider vault
- Provider adapters
- Model registry
- Model routing
- Zero-cost enforcement
- Persistent SQLite storage
- PostgreSQL compatibility
- Agent runtime
- Dynamic workforce planning
- Three-step project creation wizard
- Lead AI selection
- Worker model preferences
- Task-specific orchestration under development
- Phase 4 engineering workflows
- Phase 5 delivery and approval workflows

Previously reported source:
`eeb0e6d`

Previously reported documentation HEAD:
`93a8111`

These are historical references.

Inspect actual Git HEAD before making changes.

**DO NOT rebuild the application.**

**DO NOT delete working provider configurations.**

**DO NOT delete or expose saved credentials.**

**DO NOT migrate SQLite to PostgreSQL.**

**DO NOT weaken ZERO_COST_ONLY.**

---

# 2. CURRENT CONFIGURED PROVIDERS

I previously configured credentials for:

1. OpenAI
2. xAI / Grok
3. DeepSeek

Inspect the existing encrypted credential vault.

Determine which of these providers are currently configured and whether their associated model registrations exist.

Do not assume a credential was successfully saved merely because I entered it previously.

Do not assume a valid API key proves that every model is accessible.

Do not ask me to re-enter valid credentials unnecessarily.

Do not print, return, export or log API keys.

I want Aiventra to identify my configured providers and present their models inside the application.

If a provider is configured but model discovery fails, display the provider and explain the exact sanitized error.

---

# 3. FIRST PRIORITY — FIND THE ROOT CAUSE OF THE EMPTY MODEL LIST

Before developing additional features, diagnose the current model-picker failure.

Inspect:

- Provider vault records
- Provider configuration database tables
- Model registry tables
- Model catalog discovery
- Provider adapter contracts
- Model capability records
- Model enable/disable flags
- Provider eligibility policy
- ZERO_COST_ONLY filters
- Project creation API
- Three-step wizard
- Lead AI selector
- Specialist model selector
- Frontend API client
- React state management
- Authentication
- Owner permissions
- SQLite persistence

Trace the complete data path:

Encrypted Provider Vault
→ Configured Providers
→ Model Discovery
→ Model Registry
→ Model Availability
→ Frontend API
→ UI Model Picker
→ Saved Project Preferences.

Determine exactly where the models disappear.

Investigate these failure conditions:

1. Provider configured but no models registered.
2. Model discovery never executed.
3. Model discovery endpoint unsupported.
4. Model discovery response parsing failure.
5. Registered models filtered out by ZERO_COST_ONLY.
6. Only executable models returned by the backend.
7. Model capability requirements eliminating every model.
8. Frontend loading an incorrect API endpoint.
9. Frontend discarding blocked models.
10. Incorrect provider-to-model association.
11. Owner/project scope filtering problem.
12. Missing database records or migrations.
13. Provider authentication errors.
14. API returning an empty list without an explanation.
15. React rendering, cache or state synchronization problems.

Identify the root cause with test evidence.

Do not solve this by hardcoding a fake list of OpenAI, Grok and DeepSeek models.

---

# 4. IMPLEMENT CONNECTED PROVIDER MODEL DISCOVERY

Create or complete a reliable provider-model discovery and synchronization service.

The service must use the existing provider adapters and credential vault.

## 4.1 OpenAI

For the configured OpenAI provider:

- Reuse the stored credential securely.
- Use official supported model-listing or metadata interfaces.
- Retrieve model identifiers where available.
- Normalize provider responses.
- Associate models with the configured provider.
- Preserve supported capability metadata.
- Record discovery timestamp.
- Record catalog errors.

Do not assume every returned model can be used by my account.

Do not assume every model is free.

Do not assume ChatGPT Plus subscriptions cover standard OpenAI API usage.

Do not perform billable inference to test models.

## 4.2 xAI / Grok

For the configured Grok provider:

- Reuse existing credentials.
- Query supported model catalog endpoints.
- Extract model identifiers.
- Normalize model metadata.
- Save provider-model associations.
- Report unsupported or unavailable discovery operations.
- Display discovered or registered models.

Do not confuse Grok consumer chat access with API eligibility.

## 4.3 DeepSeek

For the configured DeepSeek provider:

- Reuse existing credentials.
- Attempt officially supported model discovery.
- Handle provider-specific catalog limitations.
- Normalize valid model identifiers.
- Persist discovered models.

If complete discovery isn't available, support owner registration of an officially documented model identifier.

Do not invent a model named DeepSeek V1 or DeepSeek 1 because I previously used that name.

Use actual provider identifiers.

## 4.4 Ollama

Preserve existing Ollama support.

If Ollama is installed:
- Discover installed models.
- Display installed models.
- Report model capabilities where verified.

If Ollama is not installed:
- Display a clear unavailable status.

Do not install Ollama or download model weights without my authorization.

---

# 5. AUTOMATIC MODEL REGISTRATION AND SYNCHRONIZATION

When model discovery succeeds, update the existing model registry.

Each model should have:

- Internal model record ID
- Provider ID
- Provider account/configuration ID
- Provider model identifier
- Display name
- Discovery source
- Discovery timestamp
- Model registration status
- Capability metadata
- Context information when known
- Streaming support
- Tool-calling support
- Structured-output support
- Pricing verification status
- Free eligibility status
- Model enable/disable state
- Last error
- Last successful discovery time

Use the existing database schema wherever possible.

Add migrations only where genuinely necessary.

## Synchronization Requirements

- Discover models from configured providers.
- Upsert model records.
- Do not duplicate existing entries.
- Preserve owner preferences.
- Preserve manual capability overrides where appropriate.
- Mark disappeared models as unavailable rather than silently deleting them.
- Track discovery provenance.
- Avoid overwriting stronger verified metadata with unknown values.
- Support repeated synchronization safely.
- Handle partial provider failures.
- Maintain the last successfully discovered catalog with a visible stale-data status.

Use a stable identity combining provider configuration and provider model ID.

## First-Time Discovery

After the owner configures a new provider, provide an explicit:

**Discover Models**

action.

When discovery succeeds, show the resulting models immediately.

Do not require the owner to restart the application.

Do not make potentially billable inference calls.

## Existing Providers

For the providers I have already configured, support an owner-initiated model refresh.

Do not require deleting and reconnecting the providers.

---

# 6. BUILD A FUNCTIONAL MODEL CATALOG UI

Create or improve:

**Settings → Models & Providers**

Display each configured provider clearly.

Example layout:

OPENAI
Connection: Configured
Models: [actual discovered count]

GROK
Connection: Configured
Models: [actual discovered count]

DEEPSEEK
Connection: Configured
Models: [actual discovered count]

OLLAMA
Connection: Not available, if no local endpoint exists.

These examples are UI structure only. Use actual database records and provider responses.

## Provider Controls

Each provider should support:

- View configuration status
- Discover Models
- Refresh Models
- View discovery errors
- View registered models
- Enable/disable eligible models
- View capability metadata
- Inspect last discovery time

Never reveal saved credentials.

## Model List

For each model display:

**Model Name**

Provider: OpenAI / Grok / DeepSeek / Ollama

Status:
- Registered
- Discovered
- Available for authorized execution
- Paid API blocked
- Unknown billing eligibility
- Unsupported capability
- Provider unavailable

Capabilities, where verified:
- Reasoning
- Coding
- General text
- Structured output
- Tool calling
- Streaming
- Long-context support

Do not invent benchmark scores or capability claims.

## Search and Filters

Implement:
- Search by model name
- Filter by provider
- Filter by capability
- Show all configured models
- Show executable models only
- Show blocked models

Default to showing the models associated with my configured providers.

Do not show unrelated provider catalogs as though I had connected those providers.

---

# 7. DISTINGUISH FOUR DIFFERENT STATES

This distinction is mandatory.

### A. Provider Configured

An encrypted credential or authorized endpoint configuration exists.

This does not prove that live inference works.

### B. Model Discovered / Registered

A model identifier has been obtained from supported discovery or verified owner registration.

This does not prove account entitlement.

### C. Model Eligible

The backend confirms that this model satisfies the current security, capability and spending policies.

### D. Live Inference Verified

An authorized real inference request was successfully performed and recorded.

Only display Live Verified if such execution evidence actually exists.

Do not combine these into a misleading single Connected badge.

A model can be visible even when it is not eligible to execute.

---

# 8. SHOW MODELS IN THE THREE-STEP PROJECT WIZARD

This is the central user-facing requirement.

Open:

http://localhost:3000

Navigate to:

New Project
→ Step 1: Requirements
→ Step 2: Choose AI Models

Here I must see the model catalog associated with my configured providers.

Reuse the same normalized model catalog powering Settings.

Do not create a second independent model registry.

## Lead AI Selector

Display:

**Choose your Lead AI**

Show the available registered/discovered models grouped by provider.

Allow searching.

For each option show:
- Model name
- Provider
- Capabilities
- Execution eligibility
- Blocked reason where applicable

My preferred model is GPT-6.1 Sol.

If this preference doesn't correspond to a verified registered model, show it separately as:

"Saved preference — model not yet verified or available."

Do not invent a real registry entry or assume the exact API model ID.

The selected Lead AI should persist in the project record.

## Worker Model Selection

Below Lead AI show:

**Choose Worker Models**

Options:

1. Automatic — Lead AI recommends specialist models.
2. Manual — I select models by role.
3. Hybrid — Lead AI recommends, I override selected roles.

### Automatic

Use available eligible models from the connected provider registry.

The Lead AI recommends models after evaluating task requirements.

The backend validates all assignments.

### Manual

Show role-specific selectors:

- Business Analyst
- Software Architect
- Backend Developer
- Frontend Developer
- Coding Agent
- Data Engineer
- QA Reviewer
- Security Reviewer
- DevOps Engineer
- Documentation Agent

Only display roles required by the project when available.

Allow me to choose any genuinely registered model as a saved preference, with clear restrictions on executing an ineligible selection.

### Hybrid

Show automatic recommendations plus override controls.

Overrides must be persisted and validated.

---

# 9. UI BEHAVIOR FOR BLOCKED MODELS

I want to SEE my connected models even if ZERO_COST_ONLY prevents their execution.

Do not remove paid models from the model catalog.

Instead display them with a clear status.

Example:

Model: [Actual discovered OpenAI model]
Status: Paid API blocked

Model: [Actual discovered Grok model]
Status: Free eligibility unverified

Model: [Actual discovered DeepSeek model]
Status: Billing eligibility unknown

Model: [Actual installed local model]
Status: Local available

Use real values and real statuses.

## Selection Behavior

Support two separate concepts:

**Preferred Model**
- A registered model or explicitly labeled saved preference.
- Can be stored even when unavailable.
- Does not authorize invocation.

**Active Execution Model**
- Must pass backend capability, permission and spending checks.
- Cannot execute if blocked.

If the preferred model is blocked:

- Save my preference.
- Clearly show the issue.
- Do not call the model.
- Allow me to choose another eligible model.
- Preserve the project.
- Put relevant execution in a waiting state.

Never silently substitute a different Lead AI.

---

# 10. BACKEND MODEL-CATALOG CONTRACT

Reuse current API routes where possible.

Only create new routes if the existing APIs cannot support the required behavior.

Expose a normalized, authorized catalog response containing:

- Provider information
- Provider configuration status
- Model internal ID
- Provider model ID
- Display name
- Capability metadata
- Catalog discovery source
- Last discovery time
- Registration status
- Availability state
- Zero-cost eligibility
- Eligibility reason
- Live verification state

Include enough information to let the frontend show all registered models without allowing blocked inference.

Do not expose:
- API keys
- Vault ciphertext
- Secret references
- Authentication tokens
- Internal credential metadata that should remain private

Do not use the executable-only routing pool as the sole source for the full model-selection catalog.

Maintain separate catalog display and execution eligibility views.

## Frontend Data Flow

The project wizard must request the catalog from the real backend.

Do not use static model arrays.

Do not maintain separate hardcoded OpenAI/Grok/DeepSeek lists in React.

Ensure:
- Proper authentication
- Loading state
- Refresh state
- Error state
- Empty state
- Model state synchronization
- Provider selection
- Accessible search
- Model preference persistence

Do not swallow API errors and replace them with an unexplained empty list.

---

# 11. FIX EMPTY MODEL STATES

An empty model picker is unacceptable without an explanation.

Handle these cases.

## Case A — No Providers Configured

Show:

"No AI providers are connected yet."

Action:

"Configure Provider"

## Case B — Providers Connected but No Models Registered

Show:

"Your providers are configured, but no models have been discovered yet."

Action:

"Discover Models"

## Case C — Discovery Failed

Show:

"Model discovery failed."

Display a sanitized error with provider name and retry control.

## Case D — Models Registered but Zero-Cost Blocked

Show:

"Your models are configured, but none is currently eligible for execution under ZERO_COST_ONLY."

Display the blocked model entries and explanations.

## Case E — Ollama Unavailable

Show:

"No local model server is running."

Do not prompt for automatic model downloads without authorization.

## Case F — Saved Model No Longer Available

Show its saved preference and availability warning.

Allow selecting a replacement while preserving previous project history.

---

# 12. CONNECT SELECTED MODELS TO REAL PROJECT EXECUTION

The selector must not only save a display label.

When I choose a Lead AI:

- Resolve and store the correct registry reference.
- Persist provider identity.
- Persist project scope.
- Persist selection mode.
- Preserve model preferences across refresh.
- Validate authorization.

When worker assignments are created:

- Use the current project model pool.
- Check capabilities.
- Apply ZERO_COST_ONLY.
- Validate task requirements.
- Enforce independent reviewer rules.
- Persist effective assignments.
- Record routing rationale.

Before each inference execution:

- Revalidate model eligibility.
- Check provider availability.
- Check authorization.
- Check current spending policy.
- Confirm the selected model still exists.

Reject stale or unavailable execution assignments safely.

Do not let frontend model selection bypass backend model routing.

---

# 13. SQLITE PERSISTENCE

Keep SQLite active.

Do not migrate to PostgreSQL.

Preserve PostgreSQL compatibility.

Persist:
- Configured provider metadata
- Model registry
- Discovery status
- Catalog synchronization metadata
- Model availability state
- Lead AI project selection
- Worker model preferences
- Manual overrides
- Routing decisions
- Relevant verification timestamps
- Discovery errors, with secrets redacted

Use existing migrations and schema conventions.

Never delete existing vault records.

Make catalog synchronization idempotent.

Verify all selected models survive:
- Browser refresh
- Logout/login
- API restart
- Worker restart
- Application restart

Preserve project isolation.

---

# 14. SECURITY AND ZERO-COST REQUIREMENTS

Keep:

`AI_SPENDING_MODE=ZERO_COST_ONLY`

Do not:
- Make paid OpenAI inference calls.
- Make paid Grok inference calls.
- Make paid DeepSeek inference calls.
- Automatically enable paid fallback.
- Install Ollama.
- Download models.
- Print provider keys.
- Commit secrets.
- Bypass owner approval.
- Change project execution authority.

Provider discovery should use officially supported non-inference interfaces where available.

If discovery has an uncertain billing impact, do not call it until verified safe.

Do not automatically execute model probes.

Do not assume ChatGPT Plus covers normal OpenAI API inference.

Model visibility must not grant permission to execute a billable request.

---

# 15. TEST THE COMPLETE FUNCTIONALITY

Add or extend real tests.

## Backend Tests

1. Provider configured, no models discovered.
2. Successful OpenAI catalog normalization.
3. Successful xAI catalog normalization.
4. Successful DeepSeek catalog normalization where supported.
5. Unsupported provider discovery.
6. Invalid credentials.
7. Provider API timeout.
8. Rate limiting.
9. Empty catalog.
10. Duplicate model synchronization.
11. Model removed from provider catalog.
12. Stale catalog cache.
13. Blocked model included in UI catalog.
14. Blocked model rejected for inference.
15. Unknown pricing rejected for inference.
16. Lead AI preference saved.
17. Worker preference saved.
18. Manual model override saved.
19. Unknown model rejected.
20. Cross-project access rejected.
21. Credential redaction.
22. Restart recovery.
23. SQLite migration compatibility.

## Browser Tests

1. Login to Aiventra.
2. Open Models & Providers.
3. See configured provider groups.
4. Discover registered models using controlled provider fixtures.
5. Open New Project.
6. Upload requirements.
7. Go to Choose AI Models.
8. See registered OpenAI models.
9. See registered Grok models.
10. See registered DeepSeek models.
11. See blocked models with explanations.
12. Search for a model.
13. Select Lead AI.
14. Select Manual Worker mode.
15. Assign a worker model.
16. Save project.
17. Refresh.
18. Verify saved selections.
19. Verify blocked inference cannot run.
20. Verify responsive mobile and desktop layouts.

## Integration Tests

Test the complete pipeline:

Existing Encrypted Provider Configuration
→ Catalog Discovery
→ Registry Synchronization
→ API Response
→ UI Model Picker
→ Model Selection
→ SQLite Persistence
→ Backend Routing Validation.

Use deterministic provider API fixtures for integration tests.

Do not report fixture discovery as a successful live provider account test.

## Regression Tests

All existing Phase 1–5 tests must continue passing.

Verify:
- Project wizard
- Workforce planning
- Model routing
- SQLite recovery
- Zero-cost enforcement
- Engineering approvals
- Delivery workflows
- GitHub operations

Run:
- pytest
- Ruff
- TypeScript typecheck
- Frontend formatting
- Production build
- Playwright
- SQLite migrations
- Security checks
- Secret scan

Fix all regressions.

---

# 16. USER EXPERIENCE REQUIREMENTS

This is an actual usability bug.

Prioritize simplicity.

A normal user should understand:

- Which providers are connected.
- Which models exist.
- Which models are available.
- Which models cost money.
- Which models cannot currently run.
- How to choose a Lead AI.
- How to select worker models.
- How to change an assigned model.

Avoid confusing terms like:
- Provider adapter instantiation
- Registry population state
- Runtime invocation eligibility

Use readable language.

For example:

"Connected provider"

"Models discovered"

"Ready to use"

"Unavailable under free-only mode"

"Choose this model"

"Save preferred model"

"Refresh models"

Make the status clear even to someone unfamiliar with AI APIs.

---

# 17. IMPLEMENTATION SEQUENCE

Execute in this order.

## Increment 1 — Diagnose Root Cause
- Inspect provider vault.
- Inspect model registry.
- Inspect frontend selector.
- Identify why the list is empty.
- Create regression tests reproducing the issue.

## Increment 2 — Repair Model Discovery
- Complete safe provider catalog discovery.
- Implement normalization.
- Reconcile registration.
- Preserve configured credentials.
- Handle unsupported discovery.

## Increment 3 — Repair Model Catalog API
- Return all authorized registered models.
- Preserve blocked models in the display catalog.
- Include availability and restriction reasons.

## Increment 4 — Repair Settings UI
- Show configured providers.
- Show discovered model lists.
- Implement Refresh Models.
- Show errors and empty states.

## Increment 5 — Repair Project Wizard
- Show models from configured providers.
- Support Lead AI selection.
- Support Automatic, Manual and Hybrid worker modes.
- Save selections.

## Increment 6 — Persist and Validate
- Save model references to SQLite.
- Apply model-routing validation.
- Preserve project-scoped preferences.
- Verify restart recovery.

## Increment 7 — Test and Verify
- Backend tests.
- Browser tests.
- Security tests.
- Migration checks.
- Production build.
- Existing workflow regressions.

## Increment 8 — GitHub
- Update documentation.
- Inspect diff.
- Run secret scan.
- Commit verified changes.
- Push to existing repository.
- Verify GitHub Actions.

Do not stop after providing a technical explanation.

Implement actual code.

---

# 18. REQUIRED FINAL CODEX REPORT

After implementation, report:

### Root Cause

Why was the model selector empty?

Identify the actual backend/frontend failure.

### Provider Status

Report only safe metadata:
- Provider name
- Configured/not configured
- Model discovery supported/not supported
- Number of models registered
- Catalog freshness
- Sanitized errors

Never reveal API keys.

### UI Result

Confirm:
- Models & Providers page shows actual configured models.
- Project wizard shows them.
- Lead AI can be selected.
- Worker models can be selected.
- Selections persist.
- Blocked models remain visible.
- Blocked inference remains blocked.

### Tests

- Backend tests
- Browser tests
- Migration checks
- Build
- Security
- CI

### Source Control

- Starting commit
- Final commit
- GitHub push status
- CI result

### Remaining Limitations

Clearly identify:
- Unverified provider account access
- Unknown model capabilities
- Paid models blocked under ZERO_COST_ONLY
- Unavailable local models
- Live inference not tested

---

# FINAL SUCCESS CRITERIA

When I open Aiventra:

http://localhost:3000

I go to Settings → Models & Providers.

I can see my genuinely configured OpenAI, Grok and DeepSeek providers.

I can see the models registered or discovered for those providers, or a clear diagnostic explaining why a provider has no models.

I click New Project.

I upload my project requirements.

I click Next.

In Choose AI Models, I see the same actual model catalog.

I select my preferred Lead AI.

I select Automatic or Manual worker selection.

If I choose Manual, I can select registered models for required agent roles.

I can save the selections.

I can reopen the project and see the exact saved preferences.

If a model is blocked because it would incur paid API charges, the UI explains the restriction.

The model remains visible without becoming executable.

The backend validates all real model invocations.

SQLite preserves the catalog and project preferences.

The existing workforce and engineering workflows continue working.

No paid inference is performed.

No credentials are exposed.

**FIX THE EMPTY AI MODEL LIST AS THE FIRST PRIORITY.**

**USE MY EXISTING CONNECTED PROVIDER CONFIGURATIONS.**

**SHOW THE GENUINE REGISTERED OR DISCOVERABLE MODELS IN THE UI.**

**ALLOW ME TO CHOOSE THE LEAD AI AND WORKER MODELS WHEN UPLOADING REQUIREMENTS.**

**PRESERVE ZERO_COST_ONLY, SQLITE AND ALL EXISTING APPROVAL CONTROLS.**

Implement, test, commit and push verified changes to the existing GitHub repository.