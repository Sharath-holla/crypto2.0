# Combined local closure — 2026-11-08

**Local code: READY_FOR_RUNPOD_VERIFICATION. Pipeline: NOT_READY_FOR_SMOKE.**

Claude's completed work and the independent review fixes are integrated in source commit
`7a64ee0da53961940932dacaddb5022be7b299bb`. The proposed Ridge block-size guard is applied and tested. The four earlier
fixes are present. This closes the concurrent-edit/source-freeze issue for this exact source.
No cloud resource, real-data training job, or real prepared cache was started. July remains unused;
August remains `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.

## Independent verification

| Check | Executed result |
| --- | --- |
| Targeted observer, regression, identity, and estimator tests | **142 passed** |
| Locked dependency sync | PASS; 31 resolved / 27 checked, no dependency-file changes |
| Full suite from committed export without `.git` | **1,471 passed; zero failures, errors, or skips; 167.61 s** |
| Ruff from that export | Lint PASS; **744 files already formatted** |
| Export inventory before and after tests | PASS; **1194 committed files** |
| Package checksum after tests | PASS; unchanged |
| Six repository/export identities | PASS, using the existing relocated Gold/sidecar copies |
| Unrelated existing review documents and files | Preserved; left unstaged/unmodified |

The export's modules were selected with its `src` on `PYTHONPATH`; the existing locked Mac virtual
environment was reused. This establishes Mac source-export portability, not a clean Linux runtime.
The tests' small synthetic fits/cache fixtures are not real research training or real-cache qualification.

Evidence: [pytest log](evidence_combined_closure_20261108/pytest_committed_export.log),
[JUnit](evidence_combined_closure_20261108/pytest_committed_export.xml),
[lint](evidence_combined_closure_20261108/ruff_export_check.log),
[format](evidence_combined_closure_20261108/ruff_export_format.log), and
[source verification](evidence_combined_closure_20261108/source_export_verification.json).

The bare `git archive` failures in Claude's transcript omitted the required `source-freeze.json`.
The verified package includes it; no test was skipped or relaxed to pass the export.

## What is integrated

- Validation-only raw-unit LONG/SHORT diagnostics, including correct normalized-target inversion
  and explicit undefined values/support counts, wired into fitting and reports.
- Observer predictions pinned to the fit's CPU thread budget; incremental GBDT monitoring,
  deterministic report views, JSONL telemetry and degraded-monitoring behavior.
- Read-only fit-boundary checks, including their source in the experiment-control identity.
- Matched full-TRAIN weighted Ridge baseline v3, with the old approximation explicitly retained.
- Threshold-underflow rejection, bounded whole-timestamp sampling, correctly scoped prediction
  distributions, and the Ridge block-size guard.

No Gold/sidecar feature or target semantics were changed. The preparation, Gold, sidecar and
selection-protocol identities are unchanged from the prior verified closure. Scientific/control
identities changed with the new source and baseline/diagnostic definitions, as intended.

| Identity | Verified value |
| --- | --- |
| EXPERIMENT_CONTROL_DIGEST | `2022b988a5cb05d85f8ff659870896615ac22ca4dd00a4a342dabb38c7a75a3a` |
| GOLD_MANIFEST_SHA | `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711` |
| PREPARATION_DIGEST | `07b510b1ebacdf80e22ad142861318b1052387973260605cdea509d2a9b31581` |
| SCIENTIFIC_SOURCE_DIGEST | `978a97e8b62869c9246fe4797a26c1ff04ec8deab2cf86dc7996a3c56bf483bf` |
| SELECTION_PROTOCOL_DIGEST | `562dbf8203f476e446cd9968d336fa74b022924c01e5b1c34f3167c065c73826` |
| SIDECAR_SHA | `ea5f25a2a7c009c79a9ecbbe795960234b67074d36d2db7c21424724fabc2048` |

Evidence: [repository identities](evidence_combined_closure_20261108/identity_mac.json) and
[export identities](evidence_combined_closure_20261108/identity_export.json).
Local identity equality does not establish Mac-versus-RunPod equality; that external gate is pending.

## Exact local handoff

Source package:
[crypto2-source-7a64ee0da539.tar.gz](/Users/cortex/Crypto2Data/reports/combined-local-closure-20261108T073250Z/crypto2-source-7a64ee0da539.tar.gz)

- Source commit: `7a64ee0da53961940932dacaddb5022be7b299bb`.
- Package size: **5,557,587 bytes**.
- SHA-256: `b60eaffb1d4272aed053cc48c5c3b2b47537b1ac33513b02862db936910851d8`.
- Committed content inventory: `a89c7c6a739639a51a22bf7e0be4cf462dec1f9b06435e5474f891a6990b004e`.
- Includes `source-freeze.json`; excludes `.git`, `.venv`, macOS resource-fork files and
  untracked Claude outputs. Created before tests; test caches/logs are outside the package.

The existing immutable staged data is reused through a new **data-only** file list:
**2,777 files / 10,998,003,736 bytes**. Presence/size were checked again; expected content hashes
come from the prior verified inventory. Bulk market-data checksums were not recomputed during
this source-only closure. Verify them during the actual transfer/target qualification.
The old source and old `identity.expected.json` entries are deliberately excluded from that list;
use this source package and the new identity values together.

[Handoff metadata](evidence_combined_closure_20261108/handoff.json),
[data-only list](evidence_combined_closure_20261108/runpod_data_only_files.txt), and
[data inventory](evidence_combined_closure_20261108/runpod_data_only_manifest.json).
The source package and reused data are separate handoff components. No remote transfer occurred.
A later documentation/evidence commit does not change this verified source commit/package.

## Remaining work and limits

The code can proceed to later owner-authorized RunPod verification. It cannot yet proceed to a
real cache or model fit. Required gates remain: fresh owner cost/deadline and stop controls,
actual Linux/x86_64 software checks, the intended local filesystem's rename/fsync/lock checks,
cross-host identity/data verification, resource admission, and one measured real prepare/reload
equivalence run. The conservative floor remains 64 GiB effective RAM, 8 effective CPUs and
150 GB local disk; this 16 GiB Mac does not meet it.

On the already authorized Linux host, after input/identity and mount selection checks, run:

```bash
bash scripts/closure/verify_linux_external.sh /tmp/phase7-smoke-local/verification
```

Use the intended pod-local filesystem, not an assumed provider mount. This is software/filesystem
verification only. Prepare-only and training each require the corresponding exact owner contract.
Only after all smoke-critical gates pass may one CPU G0/A6/60m/raw Fold-0 smoke be authorized.
The full 48-specification/16-fold grid remains `NOT_AUTHORIZED`.

Existing disclosed limitations remain: Python metric overhead needs measurement at real scale;
Ridge fairness for C0/P0 is partial; the broad cache key may cause unnecessary rebuilds; the round
cap needs observation without opportunistic tuning; funding, fill/portfolio realism and model
tradability are not established. No new model-skill or profitability claim is supported.

Detailed development account: [Claude report](CLAUDE_PRE_RUNPOD_CODE_AND_ARCHITECTURE_REVIEW_20261108.md).
Measured data/scientific baseline: [master report](CRYPTO2_FINAL_MASTER_READINESS_REPORT_20261106.md).
[Machine-readable status](evidence_combined_closure_20261108/final_status.json).
