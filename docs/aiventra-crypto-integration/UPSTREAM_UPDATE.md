# Updating the vendored Aiventra snapshot

Do not modify or push to the external Aiventra repository from this workstream.
The current pinned source is documented in `AIVENTRA_SOURCE.md`. There is no nested
`.git`, submodule or Aiventra remote in Crypto. An upstream version update requires
separate review; it is not an automatic startup action.

1. Work only on a reviewed Crypto integration/update branch; preserve scientific refs.
2. Acquire upstream read-only in a disposable directory outside Crypto. Record exact
   branch, commit, timestamp and tracked archive hash. Inspect AGENTS/instructions,
   license/NOTICE, dependency changes and secrets before import.
3. Compare the old pinned tracked snapshot against the proposed upstream commit and
   local integration patch. Do not copy `.git`, owner data/config, node_modules, virtual
   environments or generated outputs. Never overwrite the local integration blindly.
4. Reapply/review the narrow config/router/domain/UI changes and dedicated browser
   fixtures. Keep SQLite active unless an independently authorized migration says otherwise.
5. Rerun Crypto tests, both Python lint scopes, complete Aiventra backend and all browser
   suites, frontend type/format/build checks, migration check and dependency/security scan.
   Test exact approvals, tenant binding, no arbitrary shell, missing receipts, source
   changes, safe stops, interrupted worker recovery and holdout protections.
6. Inspect/stage only intended paths, scan staged bytes without printing secrets, record
   provenance and limitations, commit on Crypto only. Push only that explicitly authorized
   Crypto branch after all required checks pass. Never merge into scientific branches
   or push an upstream Aiventra change as part of this procedure.

Preserve upstream PostgreSQL/Docker compatibility files. Their CI results are not a
substitute for fresh integration checks, nor proof of this laptop's target-host readiness.
