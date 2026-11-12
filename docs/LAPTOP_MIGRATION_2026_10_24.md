# Laptop migration and repository restoration

Date: 24 October 2026, Asia/Calcutta. Purpose: preserve the current project before replacing
the owner's laptop. This is a source-code migration, not permission to resume research compute.

## Read this first

The project remains **ON HOLD**. Do not start, resize, create, or modify cloud compute. Do not
run real Phase 7 training or multi-symbol acquisition on the new laptop. Do not run legacy
trading entry points or access an exchange account. July remains unused for Phase 6/7; August
remains `LOCKED_UNUSED`, `used=false`, and `evaluation_authorized=false`.

**A successful Git push is not a complete backup of the laptop.** GitHub preserves committed
source and the explicitly included documentation. Ignored market data, frozen model/prediction
artifacts, local application databases, secrets, test output, and transient incident workspaces
require separate custody. Do not erase the old laptop until required private files have been
transferred and verified on the replacement.

## Branches and which one to restore

| Reference | Meaning | Restoration rule |
| --- | --- | --- |
| `codex/laptop-migration-20261024` | Latest tested root working state, October remediation, project guide, and migration instructions | Use this branch for the full latest checkout |
| `main` | Existing standalone lineage, including six previously unpublished commits through `4ef91d5` | Preserved as its own lineage; not automatically merged with integration or migration work |
| `integration/aiventra-crypto-os` | Earlier integration snapshot at `b8a574d` | Preserved unchanged; later standalone fixes are on the migration branch |
| `codex/laptop-checkpoint-wip-20261024` | Snapshot of the older dirty discovery-checkpoint worktree based on `e4a496b` | Archival unverified work in progress; never use it to run research or merge blindly |
| `codex/phase7-discovery-checkpoint` | Original older worktree base | Retained for ancestry; WIP snapshot is a separate branch |
| `codex/phase7-workload-optimization` | Existing optimization work | Preserved without rewriting it |
| `phase7a-pre-lightning-hardening-20261003` | Remote independently advanced to `0597a4d` during inventory | Remote additions were preserved; no force push or automatic merge |
| `crypto2.0-handoff-20260906`, `phase7a-hold-20260906` | Historical frozen handoff tags | Preserve unchanged |
| `laptop-migration-20261024` | Annotated tag for the final root migration snapshot | Use as the stable recovery point; compare remote tag and commit identities |

The migration branch contains the existing integration source because it starts from the current
checkout. No application service, adapter, account, or order path was activated. Root Python
installation remains the standalone research package. The friend-facing Phase 1–18 guide excludes
the separate application integration.

## What is included on GitHub

- Existing committed project history, versioned configs, lockfiles, tests, documentation, and
  integration source already present in the checkout.
- Previously uncommitted Phase 7 remediation in training, costs, folds, universe membership,
  prepared caches, preflight, environment compatibility, resource gates, and runtime reporting.
- The new `environment.py` and `training_metrics.py` modules, their regression tests, and the
  integration identity-test adjustment needed for the current scientific source tree.
- October audit/remediation reports and the complete Phase 1–18 Markdown project guide.
- `output/pdf/Crypto_2_Project_Guide_Phases_1_to_18.pdf`, an intentionally included small final
  documentation artifact, not a raw dataset or model checkpoint.
- This migration runbook, an explicit verification record, and a small sanitized manifest.
- A separate Git branch containing the 18-file historical checkpoint WIP, clearly marked unverified.

The old incident directories and patch stacks are not promoted into the active source package.
Their historical scripts can start compute or mutate research state and must never be run as
restoration commands. `.gitignore` now excludes these local workspaces and generated pytest
directories so `git add .` is not mistaken for a backup procedure. Nothing was deleted.

## What GitHub does not preserve

| Local item | Required treatment before retiring the laptop |
| --- | --- |
| `data/bronze`, `data/silver`, `data/gold`, quality/quarantine and legacy generated data | Preserve required authorized research files privately with original paths and checksums; never Git-add market data or open protected periods |
| `local_artifacts/experiments`, `phase4`, `phase4_1`, `phase5`, `phase5_hardening`, `phase6`, `phase7` | Preserve immutable models, predictions, folds, trades, manifests and reports; do not regenerate them as a substitute for a backup |
| `models/`, relevant logs and local hold archives | Preserve needed evidence privately, scan for secrets, and verify hashes after transfer |
| `.codex_*`, `.freebuff`, `.hardening_src`, `.phase7_workload_bench`, root patch/diff files | Historical incident scratch, not authoritative source; preserve privately if needed, never execute blindly |
| `.env`, ignored credential-bearing scratch such as `ask_gpt.py`, SSH/Git/cloud credentials | Do not upload to GitHub or a public archive; reauthenticate or migrate through an approved private secret-management process and rotate exposed credentials |
| `.venv`, caches, `node_modules`, pytest temporary trees | Rebuild environments from lockfiles; do not rely on copying platform-specific binaries |
| Separate application's ignored database, uploads and encrypted provider state | Use its documented consistent database/private-state backup procedure if those records are needed; preserve matching encryption secrets privately, never commit them |
| Documents or chat attachments outside this repository | Not captured by this Git operation; export or transfer them separately if required |

A local safe-text scratch archive and a Git bundle may be created under
`local_artifacts/laptop_migration_20261024/`. They are **not uploaded by Git push**. The scratch
archive excludes market data, databases, credentials, existing opaque archives, environments,
cache trees, and raw logs. It is not a full private-state backup. Check the local manifest for
the actual files produced and copy that directory to trusted external storage if needed.

### The stopped cloud machine is a separate preservation issue

The frozen September record says Gold has 50,352,548 rows across 138 partitions, with 7/7 Gold
checkpoints and 60 validated candle checkpoints. Fold 1 remains 0/48 completed specifications,
zero saved models, and 0/16 completed folds. The latest local session did not freshly verify
remote storage, billing, or machine state.

The handoff says Gold's only current copy is on the stopped VM's persistent boot disk and that
the disk has `autoDelete=true`. **Do not delete the VM or disk.** A laptop migration and GitHub
push do not preserve that disk. Consult `PROJECT_HANDOFF/20_CURRENT_STATE.md` and the resume
runbook. No cloud operation was authorized or performed by this migration task.

## Restore on the new laptop

Install Git, Python compatible with `pyproject.toml` (the recorded development setup uses Python
3.12), and uv. Authenticate to the owner's GitHub account using the normal credential manager
or SSH setup; never place a personal token in the clone URL, a script, or a tracked file.

From a new parent directory, clone the exact recovery branch:

```powershell
git clone --branch codex/laptop-migration-20261024 https://github.com/Sharath-holla/crypto2.0.git
Set-Location crypto2.0
git fetch origin --tags
git status --short
git log -1 --oneline
git rev-parse HEAD
git rev-list -n 1 laptop-migration-20261024
```

The last two identities should match for the original tagged migration snapshot. If the branch
later advances, inspect the new commits rather than resetting files. No force reset or forced
tag rewrite is required. Git's checked-out source and manifests are the reference, not an old
copied virtual environment.

Read `AGENTS.md`, `PROJECT_CONTEXT.md`, this guide, and the complete project handoff package.
The September handoff's missing-cache descriptions are historical: October local code implements
that boundary, but real Linux/cache-equivalence/resource gates remain unfinished. Do not rebuild
the cache feature from scratch or assume local unit tests already proved real-data equivalence.

Create the root environment using the checked-in lockfile:

```powershell
uv sync --frozen --extra dev
uv run --frozen python --version
uv run --frozen python -c "import crypto_ai; print('Research package import OK')"
```

These commands install/import software only. They do not acquire market data or train. No Binance
API key is required for the public-data research package. Do not run a download example merely
to test the new laptop, and never use the protected July/August periods.

Restore the privately transferred authorized artifacts to their original relative locations.
Compare hashes with their existing manifests before reuse. Do not edit IDs to make mismatching
checkpoints load. Files created by incompatible scientific or dependency versions must fail closed.

Run local software checks with a fresh disposable test-output directory:

```powershell
uv run --frozen pytest -q --tb=short -p no:cacheprovider --basetemp local_artifacts/new-laptop-software-check
uv run --frozen ruff check src tests integration scripts
uv run --frozen ruff format --check src tests integration scripts
uv lock --check --offline
git diff --check
```

Do not reuse an existing pytest basetemp containing valuable files; pytest may clear that directory.
These tests use bounded fixtures and are not an expensive real Phase 7 run. A Windows pass does
not satisfy the full Linux verification gate. New hardware and dependency environments require
their own verification; do not copy the old test result as proof that the new laptop passed.

The separate application has its own lockfiles and state instructions. Root research restoration
does not require launching its API, worker, database, or browser. Recreating the historical WIP
worktree is optional and must not replace the main migration checkout.

## Safe continuation prompt

> Read AGENTS.md, PROJECT_CONTEXT.md, docs/LAPTOP_MIGRATION_2026_10_24.md and the linked handoff.
> This checkout restores codex/laptop-migration-20261024. The project remains on hold. Do not
> start compute, acquire data, train, open July/August, or launch trading/application services.
> Verify the checkout, environment and preserved checkpoint identities first. October local
> cache/metrics/Cal-B/universe fixes already exist; Linux real-data equivalence and profiling
> remain pending. Preserve frozen Phases 1–6 and the independent remote recovery branch.

## Verification and completion evidence

See `LAPTOP_MIGRATION_VERIFICATION_2026_10_24.md` and
`migration/laptop-migration-20261024.json` for the actual check results and source-file identities.
Publication is complete only after `git ls-remote` confirms the intended remote branches/tag and
a fresh clone reproduces the snapshot. A local commit or a queued push is not proof of upload.

The final user-facing report must separately state whether ignored/private files have actually
been transferred. Until the owner confirms that transfer, the old laptop must not be wiped.
