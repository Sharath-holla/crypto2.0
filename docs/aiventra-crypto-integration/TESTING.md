# Verification

All checks are local integration/research-code tests, not target-host scientific
qualification. No real acquisition, Gold scan, prepared-matrix build, model fit,
holdout evaluation, cloud lifecycle or paid inference was run.

## Commands

From the Crypto root (use `.venv/bin/python` on Linux):

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests integration
.venv/Scripts/python.exe -m ruff format --check integration/crypto_aiventra tests/integration/test_crypto_aiventra.py
cd aiventra
.venv/Scripts/python.exe scripts/configure.py
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check apps/api tests scripts infrastructure/database/migrations
.venv/Scripts/python.exe -m ruff format --check apps/api tests scripts infrastructure/database/migrations
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m pip_audit
cd apps/web
npm run format:check
npm run typecheck
$env:AIVENTRA_TEST_BUILD='production'
$env:NEXT_TELEMETRY_DISABLED='1'
npm run build
npm audit --omit=dev
npx playwright test
npx playwright test --config playwright.phase5.config.ts
npm run test:crypto
```

Playwright requires installed Chromium. Set `BROWSER_FIXTURE_PYTHON` and
`PHASE5_FIXTURE_PYTHON` to the separate Aiventra Python path on Linux. Fixtures create
disposable databases/artifacts and synthetic owner credentials, never copy live owners
or expose real tokens. Tests call real UI/API/adapter code; they do not replace Crypto
responses with invented metrics. Model inference/external network is denied in the
Crypto fixture; its only permitted backend transport is the private loopback adapter.
The current owner registry is snapshotted and checked unchanged by ordinary/Crypto
browser suites. The demo badge is mandatory and heavy fixture jobs are blocked.

## Results and evidence

- Crypto full release gate: 793 passed, 5 expected Bash/Linux log-rotation skips.
  This comprises 751 preserved tests plus 42 new adapter/worker/scanner tests.
- Aiventra full backend gate: 610 passed, one pre-existing Starlette/httpx deprecation
  warning (590 preserved tests plus 20 new owner/tenant/approval tests).
- Ordinary browser regressions: 32 passed. The one changed navigation assertion now
  verifies all seven primary destinations, explicitly including Crypto 2.0; no old
  workflow assertion was removed.
- Preserved delivery browser regressions: 9 passed.
- New Crypto browser checks: 3 checks cover all views, 48 canonical specifications,
  16 folds, absent metrics, locked holdout, exact approval, browser-independent health
  completion, bounded logs, blocked training, unsafe inputs and mobile no-overflow.
  Final exact-path/gate-bound hardened run: 3 passed in 30.0 seconds.
- Both Python lint scopes pass; Aiventra formatter check passes. Frontend type/build
  checks pass; final formatting is checked after Next.js generated type-path updates.
- SQLite Alembic check: no new upgrade operations. Python audit: no known vulnerabilities;
  unpublished local `ai-company-os` is explicitly unauditable via PyPI. npm production
  audit: zero vulnerabilities.
- Upstream acquisition: 386 tracked blobs scanned with zero findings; all tracked source
  retained, no nested Git. Staged integration bytes are scanned again before committing.

Final closeout XML/log identities: `local_artifacts/aiventra-verification/crypto-closeout.xml`,
`local_artifacts/aiventra-closeout-output.txt`,
`aiventra/data/aiventra-closeout-final.xml`,
`aiventra/data/aiventra-closeout-final-output.txt`,
`aiventra/data/aiventra-closeout-browser.txt`,
`aiventra/data/aiventra-closeout-delivery-browser.txt`,
`aiventra/data/aiventra-closeout-crypto-browser.txt`,
`aiventra/data/aiventra-closeout-real-browser.txt`, and
`local_artifacts/aiventra-closeout-real-api.txt`.
The authenticated real-mode smoke check passed: 48 specifications, 16 folds, zero
observed jobs, Gold awaiting evidence, lineage not verified and holdout locked/unused.

Detailed logs/XML remain ignored under `local_artifacts/aiventra-verification`,
`local_artifacts/aiventra-*-output.txt` and `aiventra/data/*-output.txt`; screenshots
are ignored under `aiventra/artifacts`. They are not training artifacts or fabricated
scientific results. See the final report for the exact release evidence filenames.

## Failures encountered, not hidden

The initial untouched Crypto baseline had two Windows temporary-directory rename
failures; both affected modules passed a permission recheck (16 tests). A later full
rerun hit another Windows fixture rename failure while memory was low. A fresh complete
release gate using disposable temporary files outside repository watchers passed; no
scientific/test behavior was weakened or changed to mask the filesystem failure.

The untouched Aiventra baseline had two subprocess setup failures from absent private
bootstrap configuration. Running its documented `scripts/configure.py` resolved them;
the affected modules passed 16 tests, followed by the complete 610-test gate.

The new browser harness initially kept login cookies in an API context separate from
the browser; the fixture setup was corrected. A subsequent hardened health job correctly
blocked when available laptop RAM was below the requested 1 GiB floor. The UI now
exposes CPU/RAM/disk contract inputs. The health-only test explicitly requests 0.1 GiB;
the scientific default/gates are unchanged and no scientific job is authorized by it.

The staged scanner initially flagged the public `GITHUB_PUBLICATION_TOKEN_ENV`
indirection name as a configured credential. Its integration wrapper now distinguishes
that specific schema field from actual credential values; tests prove that real token,
password and JWT values remain detected, including the same text under an actual token
field. No real credential was removed, printed or exempted. The reviewed staged scan
passed with zero findings. Five upstream Markdown hard-break whitespace warnings were
converted to rendering-equivalent `<br>` tags so the staged diff check also passes.

Docker runner isolation, PostgreSQL/pgvector execution, Linux operational scripts and
real prepared-cache equivalence were NOT run here. Their upstream historical results
are not this integration's certification. Do not infer scientific readiness from tests.

## Requested current-state closeout

No re-import, reset, scientific change or integration rebuild was performed. The exact
Windows liveness case `[1-MODEL_ONLY]` passed in isolation (8.14 seconds) with task-owned
services stopped and their ports clear, followed by the full Crypto closeout gate:
793 passed / 5 expected skips (246.13 seconds).

Fresh ordinary/delivery/Crypto browser checks passed 32 + 9 + 3. The full Aiventra rerun
uses `--basetemp=data/pytest-temp/closeout-full`, inside the configured private fixture
boundary. An initial invocation outside that prefix was correctly rejected by six
deployment crash probes. All six passed (76.38 seconds) after correcting only the
invocation; no probe, deployment or safety logic was changed. The final report records
the complete backend result, authenticated real-mode browser checks and publication.
The complete closeout backend run passed 610 tests in 1288.48 seconds. Authenticated
real-mode desktop/mobile checks passed with 48 specs, 16 folds, zero jobs, missing
Gold/lineage, real CPU samples and locked/unused holdout; inspected screenshots are
`crypto-real-desktop.png` and `crypto-real-mobile.png` under ignored Aiventra artifacts.
