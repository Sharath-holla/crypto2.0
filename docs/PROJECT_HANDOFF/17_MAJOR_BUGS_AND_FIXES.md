# Major Bugs and Fixes

## 1. Discovery/full-range HTF evidence contamination

**Symptom.** BCHUSDT strict 1d acquisition appeared to start on 2021-10-03 although official
history existed from 2020-01-01.

**Root cause.** Short discovery/Core-selection daily evidence was reusable under the identity for
full-range HTF acquisition, so a bounded observation contaminated a stronger coverage claim.

**Scientific risk.** Silent loss of older causal context, biased coverage/eligibility, and false
checkpoint reuse.

**Fix.** Commit `88af25f` separates discovery-window evidence from strict full-range acquisition
identity. Pre-listing outer absence remains legitimate; missing interior active-period rows still
fail closed.

**Tests.** `tests/phase7/test_gold_htf_coverage_contract.py`, acquisition/range/coverage regression
tests. **Status: FIXED.**

## 2. Post-delisting Gold lifecycle failure

**Symptom.** HNTUSDT Gold construction failed when the 2025 chunk requested data after HNT's
validated lifecycle ended in May 2024; Gold stopped at 5/7.

**Root cause.** The loader understood wholly pre-listing absence but treated wholly post-delisting
absence as missing active data.

**Scientific risk.** Removing HNT retroactively would introduce survivorship bias; pretending rows
exist would fabricate data; treating legitimate absence as corruption blocked valid Gold.

**Fix.** Commit `be3a164` applies `requested_window ∩ validated_lifecycle`. Wholly outside is
lifecycle absence, partial overlap loads only the intersection, and missing active-period data
fails. There is no HNT-specific branch.

**Tests.** `tests/phase7/test_acquisition_lifecycle.py` plus Gold/pipeline regressions. A 2025
validation produced 1,997,280 feature rows and 7,989,120 target rows for 19 active symbols, with
zero post-lifecycle HNT rows. **Status: FIXED.**

## 3. Worker/session disappearance

**Symptom.** A detached worker and later its tmux session appeared to disappear during overnight
execution.

**Root cause.** Durable evidence showed the Python worker first exited on the HNT lifecycle
exception. tmux then ended because its child had exited; tmux was not the original failure.

**Scientific risk.** Misdiagnosing supervision could prompt unsafe duplicate restarts or loss of
the exact exception.

**Fix.** Incident evidence/status was preserved, supervisors count logical workers and fail closed,
and restart procedures require zero stale workers plus checkpoint validation. The underlying HNT
exception was fixed generally by `be3a164`; logical-worker counting was hardened in `e4a496b`.

**Tests.** `tests/operations/test_phase7_vm_supervisor.py`, Phase 7 supervisor/progress tests.
**Status: FIXED for known incident; future unattended runs still require observation.**

## 4. Fold-1 launcher issues

**Symptom.** One launch depended on absent `/usr/bin/time`; another systemd unit constructed an
invalid nested Python invocation. Runtime was consumed without a healthy scientific worker.

**Root cause.** Operational preflight did not validate the observability binary, and the service
combined interpreter/command layers incorrectly.

**Scientific risk.** No methodology change, but false confidence, wasted budget, and possible
incorrect worker-state reporting.

**Fix.** Validate required binaries before authority creation, invoke through `uv run python`,
create authority only after worker/supervisor health, and retain independent shutdown guards.

**Tests/evidence.** Supervisor/watchdog tests and hold timeline/ledger. Exact dedicated launcher
commit is **UNKNOWN / NOT VERIFIED**; one-shot incident scripts remain untracked evidence and must
not be reused. **Status: OPERATIONAL PATTERN CORRECTED.**

## 5. Missing official derivative archives

**Symptom.** Some requested Binance derivative archive objects genuinely did not exist.

**Root cause.** Absence at the official archive source was previously indistinguishable from an
unexpected acquisition failure.

**Scientific risk.** A permissive fix could synthesize funding/mark/index history; a strict but
uninformed fix could block every valid symbol.

**Fix.** Commit `0894e6c` records missing source evidence explicitly and continues only where the
contract permits. It never creates synthetic candles or index rows.

**Tests.** `test_archive_missing_reconciliation.py`, `test_acquisition_reconciliation.py`, causal
segment tests. **Status: FIXED.**

## 6. Completed acquisition repeated on resume

**Symptom.** Recovery could unnecessarily reacquire already completed symbol families.

**Root cause.** Resume handling did not fully accept validated per-symbol completion state.

**Fix.** Commit `35f20d6` validates and reuses completed acquisition identities. **Status: FIXED.**

## 7. Fold-1 preparation bottleneck — unresolved

**Symptom.** About 6h21m across interrupted Fold-1 attempts, including one 3h45m42s healthy
session, yielded 0/48 reports and zero models.

**Root cause.** Exact hot substage is **UNKNOWN / NOT VERIFIED**. Gold scan, fold/context binding,
filtering, segmentation, and Arrow→NumPy preparation occur before the first durable artifact and
lack detailed timing/persistence.

**Scientific risk.** Primarily operational/cost; an unsafe cache could also cross identities or
change rows.

**Required fix/tests.** Instrument every substage, find the single-core/IO/memory bottleneck, add an
atomic identity-safe prepared-matrix cache, test invalidation/crash/resume, and prove bitwise or
tolerance-defined row/schema/prediction equivalence. Do not reduce science as a shortcut.

**Status: OPEN — `FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING`.**
