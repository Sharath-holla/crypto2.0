# Testing and Validation

## Organization

The repository has 77 Python test files at handoff. Phase-specific suites preserve earlier
research, while `tests/phase7/` covers the current system and `tests/operations/` covers VM
supervision. Contract tests freeze approved source/config identity; Phase 7.2 tests prove its
additive capabilities do not interfere with baseline science.

| Contract | Representative tests |
| --- | --- |
| Config/identity/holdout | `test_config_registry_universe.py`, `test_phase7_2_1_reproducibility.py`, `test_training_source_identity.py`, contract baseline freeze |
| Registry/universe/survivorship | `test_cold_start_universe.py`, discovery checkpoint/exclusion tests |
| Lifecycle and gaps | `test_acquisition_lifecycle.py`, `test_causal_segment_quarantine.py`, interval-boundary tests |
| Official reconciliation | archive-missing and acquisition-reconciliation tests |
| Features/targets/leakage | `test_features_targets_metrics.py`, pair-stats equivalence, hardening audit |
| HTF availability | `test_gold_htf_coverage_contract.py` |
| Models/economics/artifacts | `test_models_economics_artifacts.py`, training optimization/error classification |
| Gold/pipeline | `test_pretraining_integration.py`, Phase 7A Core20 tests |
| Checkpoint/resume | discovery/data/Gold and Phase 7A runner tests |
| Supervisor/watchdog | `tests/operations/test_phase7_vm_supervisor.py`, Phase 7A tests/scripts |
| Holdout | config, baseline, Gold, target cutoff, future-data perturbation tests |

Adversarial tests cover future perturbations, delayed admission, delisted retention, no retroactive
membership, fold-local context, exact timing, gaps, malformed coverage/weights, nonfinite values,
identity mismatch, incomplete artifacts, duplicate logical workers, and false-COMPLETE prevention.

## Known results

The latest complete Linux result preserved in the accepted recovery baseline is **584 passed**, with
Ruff lint/format passing. The requested possible result “608 passed” is **UNKNOWN / NOT VERIFIED**
because no accessible durable report in the stopped-VM/local hold package records it. Earlier
documents record other historical local suite sizes; they are not the current canonical count.

The documentation handoff run on Windows collected **608 tests**: 601 passed and 7 failed. Two
failures are byte-freeze checks reading CRLF-transformed working-tree bytes for
`src/crypto_ai/phase7/models.py`; normalizing CRLF back to the Git blob's LF gives the exact expected
SHA-256 `51444b70f14703384f990c13f6b4fc7f7e7faee284473eb625e4289a725789a6`. Five failures are the
Linux Bash log-rotation tests because no `bash` executable exists on this host. The focused Phase 7
plus supervisor run excluding those environment-only cases passed **238/238**; Ruff check passed
and Ruff format reported 205 files already formatted. These results do not replace a future Linux
full-suite run.

Windows remains useful for fast source tests but is not authoritative for Linux paths, process
signals, tmux/systemd, filesystem semantics, resource detection, or guest supervisors. After future
changes run targeted tests first, then full `pytest`, Ruff lint and format checks, config/frozen-
identity checks, and `git diff --check` on Linux before training.
