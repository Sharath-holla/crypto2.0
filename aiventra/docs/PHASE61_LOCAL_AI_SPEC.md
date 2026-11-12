# AIVENTRA OS — PHASE 6.1
## Authorized Ollama + Qwen3 Installation, Real Local AI Integration, Lead AI Orchestration and Live Verification

# 0. EXPLICIT OWNER AUTHORIZATION

I am explicitly authorizing the following operations:

1. Install or repair Ollama on my Windows computer if necessary.
2. Use my existing Ollama installation if it is already working.
3. Download the official Ollama model `qwen3:0.6b`.
4. Run `qwen3:0.6b` locally.
5. Connect this model to my existing Aiventra OS application.
6. Register it in the existing AI model catalog.
7. Configure it as an eligible local model under `ZERO_COST_ONLY`.
8. Perform bounded real local inference tests.
9. Perform a limited Lead AI → specialist-agent handoff using actual model inference.
10. Run safe benchmarks and integration tests.
11. Update and push verified Aiventra application changes.

**THIS AUTHORIZATION APPLIES ONLY TO OLLAMA AND THE MODEL `qwen3:0.6b`.**

Do not download additional AI models.

Do not install alternative inference runtimes.

Do not perform paid external API inference.

Do not enable paid model fallback.

Do not publish generated GitHub PRs, deploy client applications or execute unapproved development scopes.

Keep the existing security and approval mechanisms active.

---

# 1. EXISTING PROJECT

Repository:

https://github.com/Sharath-holla/Aiventra.git

Local application:

http://localhost:3000

Previously reported:

- Source commit: `40af179`
- Evidence commit: `73706be`
- 426 backend tests passed
- 67 browser checks passed
- Six CI jobs passed
- Existing SQLite database preserved
- PostgreSQL compatibility retained
- Model-catalog isolation implemented
- Automatic/manual/hybrid model routing implemented
- Lead AI preferences implemented
- Restricted Docker runner implemented
- Phase 5 delivery workflows implemented
- ZERO_COST_ONLY enforced

Verify the actual current Git HEAD.

The current system has mainly been tested with deterministic model fixtures.

**The objective is now to verify actual AI inference using the downloaded local model.**

Do not rebuild Aiventra.

Reuse existing provider adapters, model registry, agent orchestration, durable workflow execution, workforce allocation and project memory.

---

# 2. FIRST — VERIFY MY WINDOWS COMPUTER

Before installation or download, inspect the current machine.

My machine was previously reported to have:

- Windows 11
- AMD Ryzen 5 5600H
- Approximately 8 GB RAM
- AMD Radeon RX 6500M with approximately 4 GB VRAM

Verify the current configuration instead of relying only on historical information.

Check:

- CPU
- Total memory
- Currently available memory
- GPU
- Available VRAM
- Free disk space
- Installed Ollama version
- Ollama background service status
- Existing downloaded models
- Existing model processes
- Local Ollama API availability

Do not make unnecessary system changes.

Do not terminate unrelated user processes.

If there is insufficient disk space or an unsafe resource shortage, explain the issue and stop before downloading.

---

# 3. VERIFY OR INSTALL OLLAMA

I have already installed Ollama manually.

First run:

```powershell
ollama --version
```

Then:

```powershell
ollama list
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Expected behavior:

- Ollama executable is available.
- Ollama service responds locally.
- Existing installed models can be listed.

If Ollama works, DO NOT reinstall it.

If Ollama is installed but the executable is not on PATH:

- Find its legitimate installation path.
- Correct the environment configuration safely.
- Do not download another copy unnecessarily.

If the service is not running:

- Start the existing Ollama service using supported methods.
- Do not launch duplicate server instances.
- Wait for the local API to become ready.

If Ollama genuinely is not installed or is corrupted, I authorize installation or repair using its official trusted Windows distribution.

Do not download installers from unofficial mirrors.

Do not disable Windows security controls.

Do not expose the Ollama server publicly.

Use localhost access.

---

# 4. DOWNLOAD QWEN3 0.6B

The ONLY authorized model is:

`qwen3:0.6b`

Official Ollama library:

https://ollama.com/library/qwen3:0.6b

Before downloading, check whether it already exists.

If it is already installed, reuse it.

Otherwise, execute:

```powershell
ollama pull qwen3:0.6b
```

The advertised model package is approximately 523 MB, but verify the actual reported size.

Wait until the download finishes successfully.

Verify:

```powershell
ollama list
```

The exact `qwen3:0.6b` model must appear.

Record:

- Model identifier
- Reported model size
- Model digest
- Ollama version
- Download status
- Local installation path, when appropriate
- Verification timestamp

Do not download:
- Qwen3 1.7B
- Qwen3 4B
- Qwen3 8B
- Qwen Coder
- Llama
- DeepSeek local models
- Any other model

Only `qwen3:0.6b` is authorized.

---

# 5. TEST QWEN DIRECTLY BEFORE CONNECTING AIVENTRA

Run the model locally:

```powershell
ollama run qwen3:0.6b
```

Send a simple prompt:

"You are an AI assistant. Explain what a software development task is in three short sentences."

Verify that a genuine model response is generated.

Exit the interactive session when finished.

Next test the Ollama HTTP API.

Use the existing Ollama API endpoint:

`http://127.0.0.1:11434`

Perform a bounded request through:

`POST /api/generate`

Example request:

```json
{
  "model": "qwen3:0.6b",
  "prompt": "Reply with exactly one short sentence explaining what an API is.",
  "stream": false,
  "options": {
    "num_predict": 128,
    "num_ctx": 2048,
    "temperature": 0.2
  }
}
```

Use actual response fields from the installed Ollama version.

Verify:

1. HTTP request succeeds.
2. Correct local model is selected.
3. Response is not empty.
4. Inference completes within a bounded timeout.
5. Tokens are actually generated.
6. No external paid API is invoked.
7. Model response metadata is captured.

Use safe, limited prompts.

Do not run unlimited inference loops.

---

# 6. RESOURCE MANAGEMENT

Because this laptop has limited RAM, optimize for low memory usage.

Initially configure:

- One concurrent local inference request.
- Small bounded prompts.
- Context length around 2048 tokens where supported.
- Bounded generated output.
- Conservative timeouts.
- No parallel model loading.
- No unnecessary background model processes.

Measure actual:
- Startup latency
- Response latency
- Generated token count
- Tokens per second, when available
- Peak process memory where measurable
- CPU usage
- GPU utilization where available
- Timeout/error frequency

Do not assume the Radeon GPU is being used.

If Ollama uses CPU inference, record that accurately.

If Windows becomes resource constrained, stop the benchmark and report the limitation.

Do not change GPU drivers or system-level performance settings automatically.

---

# 7. CONNECT OLLAMA TO AIVENTRA OS

This is the main integration requirement.

Use the existing Ollama provider adapter.

Do not create a separate AI integration system.

Inspect:

- Ollama provider adapter
- Model gateway
- Model registry
- Provider discovery
- Provider availability checks
- Model routing
- ZERO_COST_ONLY eligibility
- Lead AI configuration
- Agent runtime
- Task execution
- API responses
- Frontend model selector

Configure the local Ollama endpoint.

Default:

`http://127.0.0.1:11434`

If Aiventra's API runs directly on Windows, use the host-local endpoint.

If Aiventra's API runs inside Docker, determine the correct supported host connection, such as `host.docker.internal`, and validate it.

Do not assume `localhost` inside a container refers to the Windows host.

Do not publicly expose the inference server just to fix connectivity.

Restrict local-model endpoints to explicitly authorized destinations. Do not permit arbitrary user-supplied URLs that could introduce server-side request forgery.

Reuse existing security and network policies.

---

# 8. REGISTER QWEN IN THE EXISTING MODEL CATALOG

After confirming Ollama works, use the existing model-discovery and registry-synchronization service.

The registered model must be:

Provider: Ollama<br>
Model ID: `qwen3:0.6b`<br>
Execution type: Local<br>
Paid API charge: None<br>
Availability: Based on actual local checks<br>
Live verification: Based on real inference evidence

Store:

- Model registry ID
- Provider ID
- Ollama model identifier
- Model digest
- Discovery timestamp
- Local availability
- Last successful inference timestamp
- Supported verified capabilities
- Resource constraints
- Eligibility status

Do not create duplicate records.

Do not register it as an OpenAI, Grok or DeepSeek model.

Do not hardcode a fake catalog entry.

Use the actual locally installed model metadata.

If a model record already exists, reconcile or update it safely.

---

# 9. ZERO_COST_ONLY INTEGRATION

Keep:

`AI_SPENDING_MODE=ZERO_COST_ONLY`

Local Ollama inference may be allowed because it does not incur a paid provider inference API request.

However, the backend must verify:

1. The provider is Ollama.
2. The endpoint is authorized as local.
3. The model is installed.
4. The model identifier matches `qwen3:0.6b`.
5. The request does not route to an external provider.
6. The task is authorized.
7. Resource limits are respected.

Do not allow an arbitrary remote endpoint to qualify as free merely because it is registered under the name Ollama.

External paid models must remain blocked.

Preserve the existing protected requested-versus-attempted model receipts.

Record the actual model used for every live request.

---

# 10. MAKE QWEN VISIBLE IN THE UI

Open:

http://localhost:3000

Navigate to:

Settings → Models & Providers

The Ollama section should show:

- Ollama installed/running.
- Local server reachable.
- Qwen3 0.6B installed.
- Actual model identifier.
- Local eligibility.
- Last discovery.
- Last successful inference.

Next navigate to:

New Project → Choose AI Models

I want to see:

**Qwen3 0.6B — Ollama — Local**

The model should be selectable where it satisfies the required capability.

Keep my previous GPT-6.1 Sol Lead AI preference.

Do not delete or overwrite it.

If I want to use Qwen as the temporary Lead AI, allow me to explicitly select it for the testing project.

If GPT-6.1 Sol remains unavailable, display its restriction clearly.

Do not silently replace GPT-6.1 Sol globally.

---

# 11. FIRST REAL MODEL-GATEWAY TEST

Use the existing Aiventra model gateway.

Submit a bounded task to Qwen.

Example:

"Explain the difference between frontend and backend development."

Verify:

- Actual model invocation.
- Correct model ID.
- Correct provider.
- Response content.
- Stream completion or non-stream response.
- Timeout handling.
- Cancellation behavior.
- Metadata persistence.
- SQLite audit receipt.
- No paid API usage.

The backend must distinguish:

- Requested model.
- Selected effective model.
- Attempted model.
- Successful execution model.

Do not report a fixture result as a successful live model call.

---

# 12. STRUCTURED JSON OUTPUT TEST

Next test whether Qwen can produce a valid structured response.

Example requirement:

"Create a short development plan for a basic task-management application."

Expected schema:

```json
{
  "project_name": "string",
  "summary": "string",
  "tasks": [
    {
      "task_name": "string",
      "description": "string",
      "priority": "low|medium|high"
    }
  ]
}
```

Use supported Ollama structured-output features where appropriate.

Validate the actual response using the existing Pydantic/schema system.

Test:
- Correct JSON
- Required fields
- Unexpected fields
- Invalid values
- Missing fields
- Malformed output
- Retry limits

If Qwen fails schema validation, record the failure.

Allow only a small bounded retry or repair where supported.

Do not modify production validators merely to make the small model pass.

---

# 13. TEST QWEN AS A TEMPORARY LEAD AI

Create a small disposable Aiventra project.

Project:

**Task Management API — Local AI Test**

Requirement:

"Analyze the requirements for a basic task-management API with create, read, update, complete and delete operations. Produce a simple architecture and divide the work into development tasks."

For this TEST project only:

Lead AI: `qwen3:0.6b`

Worker selection: Automatic, using only eligible installed models.

The goal is to verify real planning behavior.

The Lead AI should attempt to:

1. Understand requirements.
2. Identify missing information.
3. Propose an architecture.
4. Identify required roles.
5. Create a simple task breakdown.
6. Recommend suitable workers.
7. Produce a structured planning artifact.

Use existing agent orchestration and planning contracts.

If the model cannot handle the full schema, report the limitation honestly.

Do not call the project successfully planned unless validation passes.

---

# 14. FIRST REAL LEAD AI → SPECIALIST HANDOFF

After the initial smoke test passes, test a bounded handoff.

Example:

Lead AI
→ Business Analyst
→ CTO

Use actual model inference for both roles if authorized and technically supported.

Since only one model is installed, different logical agents may temporarily use the same Qwen model.

Clearly identify this as:

**Multiple logical agents using one shared model.**

Do not claim model-level independence.

Do not claim that this proves multi-model orchestration.

## Lead AI

Task:

"Analyze the task-management requirements and prepare an instruction for the Business Analyst."

Save actual output.

## Business Analyst

Task:

"From these requirements, produce three functional requirements and acceptance criteria."

Save actual output.

## CTO

Task:

"Review the analyst's requirements and propose a simple implementation architecture."

Save actual output.

Verify:

- Each invocation actually occurred.
- Model identity was recorded.
- Agent identity was recorded.
- Handoff artifacts were persisted.
- Agent messages were linked correctly.
- Correct task context was passed.
- No cross-project information leaked.
- Responses were validated.
- Execution could be resumed after a restart.

Keep the workflow bounded.

Do not trigger the entire 136-agent workforce.

---

# 15. BENCHMARK QWEN3 0.6B

Create a small repeatable local benchmark.

Test categories:

1. Simple instruction following.
2. JSON generation.
3. Requirement summarization.
4. Basic task decomposition.
5. Short Python code explanation.
6. Simple bug identification.

Use a modest bounded number of inference requests.

Record:

- Prompt
- Model
- Response
- Response validity
- Latency
- Token counts when available
- Throughput when available
- Error status
- Peak memory where measurable

Use a small repeatable evaluation set with objective assertions where possible.

Do not invent quality scores.

Differentiate structural validity from correctness.

Do not repeatedly execute a failing benchmark without limits.

Do not perform large stress tests on this laptop.

---

# 16. DETERMINE MODEL SUITABILITY

Based on actual measured results, classify Qwen3 0.6B's suitability for:

- Simple chat.
- Requirement summarization.
- Basic planning.
- Structured JSON.
- Basic programming questions.
- Architecture decisions.
- Advanced debugging.
- Autonomous coding.
- Independent QA.
- Security-critical work.

Be conservative.

This small model is primarily for verification of local inference and orchestration plumbing.

Do not assign it production-critical tasks merely because it returned a valid sentence.

If it is unable to complete a complex task, leave that task waiting for a more capable eligible model.

Do not automatically download or switch to another model.

---

# 17. SQLITE PERSISTENCE AND RECOVERY

Keep SQLite active.

Do not migrate to PostgreSQL.

Preserve existing records.

Store:

- Ollama provider metadata.
- Model registry entry.
- Actual inference receipts.
- Model selection.
- Project model preferences.
- Lead AI execution records.
- Agent handoffs.
- Response artifacts.
- Benchmark results.
- Validation errors.
- Timestamps.
- Waiting states.

Avoid storing oversized or sensitive raw prompts without the existing project retention and access rules.

Run a real service restart test.

Verify:
- Qwen registration remains.
- Model preferences remain.
- Inference receipts remain.
- Project state remains.
- Agent handoff history remains.
- Existing records are intact.
- Foreign keys remain valid.

Keep PostgreSQL compatibility.

---

# 18. FRONTEND IMPROVEMENTS

Do not redesign the entire frontend.

Extend the current simplified UI.

In Settings show:

**Local AI Models**

- Local server status.
- Installed models.
- Model availability.
- Verified model capability.
- Last inference.
- Resource warnings.

In the project wizard:

- Show Qwen3 0.6B.
- Allow temporary Lead AI selection.
- Display model eligibility.
- Preserve GPT-6.1 Sol preference.
- Display clear warnings when a capability is not verified.

In the project dashboard:

- Show actual Lead AI task status.
- Show the real model executing.
- Show actual agent handoffs.
- Show validation errors.
- Show benchmark results when applicable.

Use human-readable statuses.

Examples:

"Qwen is analyzing requirements."

"Business Analyst response saved."

"Architecture review failed validation."

"Local model is unavailable."

Do not display fake progress.

---

# 19. SECURITY REQUIREMENTS

Ensure:

- Ollama is not exposed to the public internet.
- No unapproved network listeners are added.
- Local endpoint requests use an explicit allowlist.
- Provider credentials remain encrypted.
- No API keys enter logs.
- ZERO_COST_ONLY remains active.
- Local inference receipts cannot be fabricated by the frontend.
- Project memory remains permission-filtered.
- Uploaded requirements remain untrusted data.
- Prompt injection cannot grant agent tools.
- Model outputs are validated before workflow actions.
- Owner approval remains required before coding and publication.
- Cancellation is respected.
- Resource limits are enforced.

Do not let Qwen execute shell commands merely because the model's response contains instructions.

Treat model-generated text as data until an authorized workflow validates and permits the related action.

---

# 20. INTEGRATION WITH EXISTING ENGINEERING PIPELINE

Inspect how the new local model could later work with:

- Business Analyst.
- CTO.
- Project Manager.
- Coding Agent.
- QA.
- Restricted Docker runner.
- GitHub worktrees.
- Diff generation.
- Candidate commits.
- Final review.

For this milestone, implement any missing safe integration needed to route real model output through existing tasks.

However:

**Do not perform unapproved autonomous coding or external publication.**

A limited code suggestion or isolated disposable fixture is acceptable if it is clearly scoped, bounded and does not modify my production repositories.

Do not let a small local model claim final engineering or security approval automatically.

If it lacks sufficient capability, report that separately.

---

# 21. AUTOMATED TESTING

Preserve the entire existing test suite.

Add tests covering:

## Ollama Discovery

1. Ollama installed.
2. Ollama not installed.
3. Service unavailable.
4. Service available.
5. Model installed.
6. Model missing.
7. Invalid local endpoint.
8. Model registry synchronization.
9. Duplicate discovery.
10. Local-only endpoint authorization.

## Model Gateway

11. Valid inference response.
12. Empty response.
13. Timeout.
14. Cancellation.
15. Model not found.
16. Incorrect response format.
17. Structured output success.
18. Structured output failure.
19. Zero-cost enforcement.
20. Requested-versus-attempted receipt correctness.

## Lead AI

21. Lead model selection persistence.
22. Unavailable preferred GPT-6.1 Sol retained.
23. Explicit project-level Qwen selection.
24. Requirement parsing.
25. Planning output validation.
26. Invalid plan rejection.
27. Bounded retry.
28. Task assignment persistence.

## Handoffs

29. Lead → Business Analyst.
30. Business Analyst → CTO.
31. Correct context transfer.
32. Persistent output artifacts.
33. Separate logical-agent attribution.
34. No false independent-model claim.
35. Cross-project access rejection.
36. Restart recovery.

## UI

37. Qwen appears in the model catalog.
38. Model availability is accurate.
39. Lead AI can be selected.
40. Manual worker selection works.
41. Preferences persist after refresh.
42. Local-inference results display.
43. Errors display.
44. Model blocked/unavailable states work.
45. Browser tests remain isolated.

## Regression

Preserve:
- Model catalog isolation.
- Provider vault.
- SQLite persistence.
- PostgreSQL compatibility.
- AI routing.
- Agent orchestration.
- Restricted coding runner.
- Phase 4 approvals.
- Phase 5 delivery.
- ZERO_COST_ONLY.

Run all applicable backend, browser, build, typecheck, lint, security and database tests.

Do not weaken test assertions.

---

# 22. LIVE VERIFICATION REPORT

This milestone must include real local inference evidence.

If Qwen runs successfully, document:

- Exact installed model.
- Model digest.
- Ollama version.
- API endpoint type.
- Date/time of verification.
- Number of actual inference requests.
- Number of successful requests.
- Number of failed requests.
- Mean/median latency where measured.
- Model response validity.
- Resource usage where measured.
- Agent handoff results.
- SQLite persistence.
- Restart recovery.

Do not label fixture tests as live model tests.

Use distinct status labels such as:

- `FIXTURE_TESTED`
- `LOCAL_INFERENCE_VERIFIED`
- `LOCAL_HANDOFF_VERIFIED`
- `LIVE_CODING_NOT_VERIFIED`
- `PRODUCTION_DELIVERY_NOT_VERIFIED`

If some tests fail, report the failures and limitations.

Do not conceal small-model capability problems.

---

# 23. UPDATE DOCUMENTATION

Update the existing documentation where relevant:

- README.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- TEST_REPORT.md
- MODEL_CONFIGURATION.md
- MODEL_ROUTING.md
- LEAD_AI_ORCHESTRATION.md
- LOCAL_MODEL_READINESS.md
- SECURITY.md

Add if needed:

`OLLAMA_LOCAL_INFERENCE_REPORT.md`

Document:
- Installation verification.
- Model download.
- Registry integration.
- Zero-cost eligibility.
- Model selection.
- Actual inference results.
- Benchmark measurements.
- Agent handoff evidence.
- Errors and limitations.

Do not include sensitive credentials or unnecessary personal system details.

---

# 24. GITHUB COMMIT AND PUSH

After implementation:

1. Inspect the working tree.
2. Run full relevant tests.
3. Fix regressions.
4. Verify SQLite integrity.
5. Scan source for secrets.
6. Inspect changes.
7. Commit tested source.
8. Push normally to the existing Aiventra repository.
9. Verify GitHub Actions.
10. Update final test evidence.

Do not commit:
- Ollama model weights.
- Local inference caches.
- SQLite database files.
- SQLite backups.
- Provider secrets.
- Large generated benchmark artifacts.
- Unnecessary machine-specific paths.

Do not force push.

If CI fails, repair the issue and verify the corrected commit.

---

# 25. REQUIRED FINAL STATUS REPORT

At the end provide:

## A. Ollama

- Was it already installed?
- Was repair needed?
- Version.
- API availability.
- Local-only security status.

## B. Qwen

- Was `qwen3:0.6b` downloaded?
- Exact installed identifier and digest.
- Actual reported size.
- Did it generate a real response?

## C. Aiventra Integration

- Is Ollama registered?
- Does Qwen appear in Settings?
- Does Qwen appear in the project wizard?
- Can it be selected as a Lead AI?
- Can it be selected as a worker?
- Are model preferences saved?
- Is ZERO_COST_ONLY still active?

## D. Real AI Verification

- Actual successful inference calls.
- Structured JSON results.
- Validation failures.
- Real Lead AI handoff results.
- Latency.
- Token throughput.
- Memory usage.
- Model capability limitations.

## E. Tests

- Backend test count.
- Browser test count.
- Build.
- Typecheck.
- Security checks.
- SQLite recovery.
- PostgreSQL compatibility.
- GitHub CI.

## F. Source Control

- Starting commit.
- Final commit.
- Push status.
- Working-tree status.

## G. Remaining Work

Clearly identify what still needs to be done before:

- A strong Lead AI can orchestrate a complex project.
- Multiple different AI models can collaborate.
- A real coding agent can modify a project.
- Independent QA can review it.
- Owner-approved PR publication can occur.
- A real client project can be delivered.
- Aiventra v1.0 can be released.

---

# 26. FINAL ACCEPTANCE CRITERIA

When this task finishes, I should be able to:

1. Open Ollama on my Windows computer.
2. See `qwen3:0.6b` installed.
3. Send a real prompt to Qwen.
4. Receive a real local inference response.
5. Open Aiventra at `http://localhost:3000`.
6. See Ollama listed in Models & Providers.
7. See Qwen3 0.6B in the model catalog.
8. Create a new testing project.
9. Select Qwen3 0.6B as the temporary Lead AI.
10. Choose Automatic Worker Selection.
11. Submit simple requirements.
12. Execute one real bounded Lead AI planning attempt.
13. See the actual model identity and result.
14. Execute a real specialist handoff if the previous test passes.
15. See the actual handoff output in the project workspace.
16. Confirm that all records remain saved after restart.
17. Confirm that ZERO_COST_ONLY remains active.
18. Confirm that external paid providers were not invoked.
19. Review measured benchmarks and any failures.

If Qwen cannot satisfy a required planning schema, record the failed attempt rather than pretending the planning workflow succeeded.

Do not treat multiple logical agents sharing Qwen as multiple independent models.

Do not attempt complex autonomous engineering unless separately authorized and supported by the model's demonstrated capabilities.

---

# FINAL INSTRUCTION

**I AUTHORIZE OLLAMA SETUP/REPAIR AND THE DOWNLOAD OF `qwen3:0.6b` ONLY.**

**START BY VERIFYING THE EXISTING OLLAMA INSTALLATION.**

**THEN DOWNLOAD OR REUSE QWEN3 0.6B.**

**VERIFY REAL INFERENCE DIRECTLY THROUGH OLLAMA.**

**CONNECT QWEN TO AIVENTRA'S EXISTING MODEL GATEWAY, REGISTRY AND PROJECT WIZARD.**

**VERIFY ONE REAL BOUNDED LEAD AI → SPECIALIST WORKFLOW.**

**MEASURE PERFORMANCE AND DOCUMENT ACTUAL RESULTS.**

**PRESERVE SQLITE, POSTGRESQL COMPATIBILITY, ZERO_COST_ONLY, EXISTING DATA AND ALL OWNER APPROVALS.**

**RUN TESTS, FIX REGRESSIONS, COMMIT VERIFIED SOURCE AND PUSH TO THE EXISTING GITHUB REPOSITORY.**

Do not stop after writing instructions. Execute the authorized implementation and report real results.
