Continue development of Aiventra from the current HEAD.

Current verified state:
- Source checkpoint: 0b3df92
- Verification/documentation checkpoint: f240412
- Application currently runs on localhost:3000
- SQLite is active
- PostgreSQL compatibility must remain supported
- ZERO_COST_ONLY must remain enabled
- No paid AI inference
- No model installation
- No real client delivery claims
- Agent execution/delivery remain deterministic-fixture tested unless explicitly live-verified

Already implemented:
1. Automatic/manual/hybrid task-model assignment
2. Exact model overrides
3. Saved routing explanations
4. Bounded fallback behavior
5. DOCX project-document imports
6. Document replacement/removal
7. Provenance
8. Approved project-memory access
9. Read-only GitHub repository/branch analysis
10. GitHub integration in the UI
11. Restart persistence
12. Docker isolation
13. PostgreSQL compatibility/recovery

Verified baseline:
- 343 backend tests
- 25 browser journeys
- 4 isolated delivery journeys
- all 6 CI jobs passed

DO NOT regress any existing behavior.

==================================================
NEXT INCREMENT
==================================================

Implement these three areas:

1. ISOLATED GITHUB CHECKOUT INTO RESTRICTED RUNNER
2. SECURE PDF INGESTION
3. PROJECT HISTORY-LOADING IMPROVEMENTS

Do them carefully and incrementally.

==================================================
1. ISOLATED GITHUB CHECKOUT
==================================================

Current GitHub integration is READ-ONLY repository/branch analysis.

Extend it so an authorized project can obtain a temporary checkout of a
configured GitHub repository/branch for analysis/execution inside the
restricted runner.

SECURITY REQUIREMENTS:

- Never clone directly into the main application filesystem.
- Repository checkout must happen inside an isolated temporary workspace.
- Use a project/job-specific directory.
- Prevent path traversal.
- Prevent symlink breakout.
- Prevent repository content from writing outside the isolated workspace.
- Do not execute repository hooks.
- Do not automatically execute repository code after clone.
- Do not expose host environment secrets to repository code.
- Do not expose unrelated project credentials.
- Do not persist GitHub tokens inside the checkout.
- Redact credentials from logs/errors.
- Delete or clean temporary checkout state when appropriate.
- Enforce configurable repository-size/file-count limits.
- Enforce timeout limits.
- Handle malformed/oversized repositories safely.
- Branch/ref selection must be explicitly validated.
- Prefer immutable commit SHA resolution after branch selection.
- Persist provenance:
    repository
    requested branch/ref
    resolved commit SHA
    checkout timestamp
    project
    requesting operation
- Checkout must remain read-only with respect to GitHub.
- DO NOT create commits, branches, pushes or PRs.

Credential requirements:

- Use a scoped GitHub credential abstraction.
- Do not hard-code credentials.
- No token in URLs stored in the database.
- No token in stdout/stderr.
- Existing operation must continue functioning when no credential is configured,
  but authenticated repository operations should clearly report that a scoped
  credential is required.

RUNNER:

Integrate checkout with the existing restricted runner/isolation architecture.

Make the checked-out repository available to permitted project operations only.

Do not weaken Docker/restricted-runner isolation.

Add tests for:
- successful checkout
- branch checkout
- SHA provenance
- invalid branch/ref
- nonexistent repository
- missing credentials
- credential redaction
- timeout
- repository-size limit
- cleanup
- path traversal
- malicious filenames
- symlink escape attempts
- isolation between two projects/jobs
- restart behavior where applicable

==================================================
2. SECURE PDF INGESTION
==================================================

Extend the existing project-document system that currently supports DOCX.

Add PDF support.

PDF ingestion must use the SAME provenance/approval/project-memory model as DOCX.

Requirements:

- Accept valid PDF uploads.
- Validate using actual file structure/signature, not extension alone.
- Reject malformed PDFs cleanly.
- Enforce configurable upload-size limits.
- Enforce page-count/content limits.
- Protect against decompression/resource-exhaustion cases.
- Do not execute embedded JavaScript/actions.
- Do not follow arbitrary external links.
- Do not execute embedded files.
- Do not trust document metadata.
- Sanitize filenames.
- Maintain project isolation.
- Preserve original upload metadata/provenance.

Extract:
- textual content
- page number association where possible
- document metadata only when safe/useful

Store enough provenance to answer:
- which project document supplied information
- which PDF
- which page/range if known
- current document version

Document operations must support:
- upload
- replace
- remove
- re-index/re-process
- existing approval model
- project-memory access

Replacing a PDF must not leave stale searchable chunks from the old version.

Removing it must remove its searchable/indexed content consistently.

PDF failures must not break other project documents.

Do not add OCR unless necessary.
For image-only PDFs, report that usable text was not extracted rather than
silently inventing content.

Add tests for:
- ordinary text PDF
- multi-page PDF
- empty PDF
- malformed PDF
- wrong extension/MIME
- oversized PDF
- replacement
- removal
- provenance
- page provenance
- project isolation
- restart persistence
- mixed DOCX/PDF projects

==================================================
3. HISTORY LOADING
==================================================

Improve project/chat/task history loading without redesigning the entire UI.

Goals:

- History should load predictably after restart.
- Recent project activity should be immediately useful.
- Large histories must not make initial page load excessively heavy.
- Preserve chronological ordering.
- Avoid duplicate messages/events.
- Maintain task/model assignment explanations.
- Maintain imported-document provenance references.
- Maintain GitHub analysis provenance.
- Maintain delivery/approval state.

Implement bounded/paginated history loading.

Prefer:
- recent items initially
- explicit older-history loading
or
- another simple bounded approach consistent with the current UI architecture.

Requirements:

- deterministic ordering
- stable IDs
- pagination/cursor correctness
- no duplicates across pages
- project isolation
- correct behavior after restart
- compatible SQLite and PostgreSQL behavior

Do NOT build an unnecessarily complicated event-sourcing system unless the
existing architecture genuinely requires it.

Add API and browser coverage for:
- initial history
- loading older history
- empty history
- large history
- restart persistence
- no duplicate entries
- concurrent/new activity while older history is loaded
- switching projects

==================================================
UI / UX
==================================================

Keep the existing Aiventra design language.

Do not perform a broad redesign.

Add only the UX necessary for:

GitHub:
- repository checkout status
- selected branch/ref
- resolved commit SHA
- clear failure messages

Documents:
- PDF upload
- processing status
- replacement/removal
- type indicator
- provenance/page information where relevant

History:
- bounded initial history
- simple way to load older history

Keep advanced/security details out of the main UI unless the user needs them.

==================================================
BACKWARD COMPATIBILITY
==================================================

Do not break:

- existing project creation
- task planning
- staffing
- model assignment
- manual/hybrid overrides
- specialist consultation
- project stages
- DOCX ingestion
- project memory
- GitHub read-only analysis
- persistence
- SQLite
- PostgreSQL
- Docker
- approval gates
- ZERO_COST_ONLY

==================================================
NO FALSE CLAIMS
==================================================

Maintain strict distinction between:

- deterministic fixture testing
- isolated runner testing
- authenticated live GitHub verification
- live AI execution
- actual PR publication
- real client delivery

Do not label simulated/fixture behavior as live.

Do not add paid model/API dependencies.

==================================================
IMPLEMENTATION PROCESS
==================================================

First inspect the existing architecture.

Then give a concise implementation plan.

After that implement the increment.

Run the relevant existing test suites throughout development.

At completion run:

- full backend tests
- browser/E2E tests
- isolated delivery/runner tests
- build/type checks
- security checks
- SQLite restart persistence
- PostgreSQL compatibility/recovery checks
- Docker isolation checks

Fix regressions rather than weakening tests.

If a live GitHub credential is unavailable:
- fully test through mocks/fixtures
- preserve existing authenticated behavior
- clearly mark live checkout verification as pending

Do not fabricate verification.

==================================================
FINAL REPORT
==================================================

When finished report:

1. What was implemented
2. Important files changed
3. Security controls added
4. Database/schema changes
5. New API behavior
6. UI changes
7. Test counts and results
8. CI results
9. What was fixture-tested
10. What was genuinely live-verified
11. Remaining limitations
12. Exact commits created
13. Whether the git working tree is clean

Then stop.
Do not begin the next major feature without approval.