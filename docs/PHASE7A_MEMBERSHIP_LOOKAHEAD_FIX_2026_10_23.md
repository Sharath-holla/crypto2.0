# Phase 7A — future quality evidence leaking into TRAIN membership

Date: 2026-10-23. Severity: **P1 scientific correctness**. Status: locally corrected
and verified: **886 tests passed, 5 Linux-only skips, zero failures**. Real Linux/data
qualification and training authorization remain separate requirements.

## Confirmed major defect

A symbol's membership for a fold was frozen at `train_end` in name, but the gap
quality gate inspected the entire required range through **TEST end**. A failed
partition occurring months after TRAIN could therefore remove that symbol from
TRAIN, change its cross-sectional context, alter clusters/cost tiers, and change
the model's training population using future information.

Concrete synthetic reproduction: freeze membership on July 1, 2024, then add a
December 2024 gap inside that same fold. The old code could remove BTCUSDT from the
CORE training universe or NEWUSDT from EXPANDING. Even an expansion symbol not
selected for CORE could change CORE's membership hash via future exclusion metadata.

The previous tests protected folds ending **before** a future gap, but missed the
case where TRAIN ends before the gap and TEST ends after it. One older rejection
test actually expected this noncausal exclusion. That test's fixture now places its
corruption in the TRAIN history window, preserving its original strict rejection
assertions. Separate adversarial tests cover future evidence explicitly.

This is a demonstrated code defect, not proof that a real trained model suffered
this leakage. No real Gold, cache or model artifacts were inspected or evaluated.
The handoff's incomplete 0/48 Fold-1 result remains incomplete, not bad performance.
The owner's exact external symptom remains unconfirmed without a traceback/example.

## Implementation

| Component | Change |
| --- | --- |
| `phase7/universe.py` | Bound the gap gate to the required TRAIN history window ending no later than `train_end`. Only gap intervals fully elapsed by TRAIN end may contribute to membership/exclusion evidence. |
| Membership metadata | Both exclusion decisions and member `unusable_segments` use the same historical evidence; future evidence cannot change the hash indirectly. Historical partition IDs are sorted/deduplicated so input order/duplicates do not change identity. |
| Policy identity | New memberships explicitly carry `gap_gate_policy=TRAIN_HISTORY_ONLY_V2`, included in their hash. |
| Historical compatibility | A historical artifact with no policy field is read as `FULL_FOLD_REQUIRED_RANGE_V1`, using its original hash algorithm. Reading it does not promote it to V2 or rewrite its bytes. |
| `phase7/folds.py` | Preserve TRAIN membership but block the entire fold with a `ValueError` if an active symbol has a known post-TRAIN gap. Never call this `INELIGIBLE` or a completed result. Other full-fold gap details remain labelled **coverage diagnostics, not membership-selection inputs**. Record the selected membership policy. |
| `phase7/segments.py` | Empty/reversed half-open query ranges have no intersection. Previously a zero-length range inside a gap could incorrectly intersect. |

An interval straddling TRAIN end is not treated as completed historical partition
evidence. This avoids using an error that may occur later in that partition to
choose earlier symbols. Interval end is a conservative boundary for this gate, not
a newly invented acquisition/publication timestamp. TRAIN coverage/integrity
descriptors, strict source validation, missing-row rules and causal feature/target
construction still apply independently.

This is an intentional scientific correction, not a promise of equivalence with
the defective universe policy. The version and source identity separate results.
No frozen Core20 selection, configuration, original model, report or historical
membership artifact was overwritten. HNT remains in the frozen Core20; XPIN is not
forced. CORE/EXPANDING caps, fold dates, 109 features, targets, latency, purge,
embargo, calibration and threshold ownership remain unchanged.

## What the fix does not permit

- Future missing/corrupt rows are not repaired, fabricated or forward-filled.
- Bad source data still must not enter trusted Silver/Gold, and features/labels
  must not bridge missing history. Existing gap-reset and no-bridge tests remain.
- A known post-TRAIN gap for an active symbol **blocks the fold before fitting**;
  it cannot retroactively select an earlier training population. This preserves
  strict quality without silently evaluating an incomplete active-symbol history.
- The new membership policy does not bypass Gold, checkpoint or runtime gates.

## Regression evidence

New module: `tests/phase7/test_membership_gap_causality.py` (**32 cases**).

- 20 perturbation cases: CORE/EXPANDING × BTCUSDT/NEWUSDT × straddling TRAIN end,
  exactly at TRAIN end, and future Validation/Calibration/TEST dates.
- Completed historical corruption still excludes affected core/expansion symbols,
  including a gap ending exactly at TRAIN end.
- Extending only the future required range leaves earlier membership unchanged.
- Gap ordering, duplicates, out-of-window history and empty intersections are tested.
- Historical V1 artifacts remain readable under their original identity; V2 differs.
- A tiny Arrow fixture compares the normal fold path with the membership-dependent
  context/matrix path after adding future gap metadata. TRAIN/Validation tables,
  clusters, liquidity tiers, membership hash and NumPy inputs remain identical.
  Four cases then prove that the full fold entrypoint blocks known corruption at
  TRAIN end, in Validation, in Calibration and in TEST, as a data error rather than
  an eligibility result. No LightGBM is fitted; only tiny synthetic descriptor
  clustering runs. This is not real-data cached/uncached equivalence proof.

Before the fix, the initial new module had **23 failures and 2 passes**: all 20
future cases failed, plus ordering, empty intersection and future-window extension.
The first corrected gate passed 68 cases. The larger gate initially had 103 passes
and one test-fixture failure: synthetic Cal-B rows were placed before the exact
Oct-1-noon midpoint. The fixture moved to Oct 2; no split/purge/embargo rule was
weakened and no earlier-phase code changed.
The subsequent quality review preserved strict post-TRAIN rejection as a whole-fold
data error instead of a noncausal symbol filter. The first full run was deliberately
interrupted for that change and is not claimed as a completed pass; the final full
gate starts afresh on the corrected code.

Final checks:

| Check | Result |
| --- | --- |
| Targeted causality, quarantine, cold-start, registry, cache and debug suites | 107 passed in 15.69 s; one non-fatal Windows joblib core-discovery warning |
| Full suite on final source | 886 passed, 5 skipped, zero failures/errors, one non-fatal Windows joblib warning; 374.19 s |
| Ruff lint / format | PASS; 252 files checked |
| Compilation | PASS |
| Offline lockfile check | PASS; 31 packages, no dependency changes |
| Git whitespace diff check | PASS; informational Windows LF/CRLF notices only |
| Linux, real Gold/cache equivalence, GPU and real model performance | NOT RUN / NOT QUALIFIED |

Artifacts:
[red reproduction](../local_artifacts/phase7/verification/gap-causality-red-20261023.xml),
[targeted final gate](../local_artifacts/phase7/verification/gap-causality-targeted-release-v2-20261023.xml),
[full final gate](../local_artifacts/phase7/verification/gap-causality-full-final-v2-20261023.xml).

Reproducible local verification (PowerShell, from the existing checkout):

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp local_artifacts/gap-causality-full-final-v2-20261023 --junitxml local_artifacts/phase7/verification/gap-causality-full-final-v2-20261023.xml
.\.venv\Scripts\ruff.exe check --no-cache src tests integration scripts
.\.venv\Scripts\ruff.exe format --check --no-cache src tests integration scripts
.\.venv\Scripts\python.exe -B -m compileall -q src/crypto_ai scripts tests
uv lock --check --offline
git diff --check
```

Use a fresh, dedicated basetemp for another run. Tiny synthetic fixtures and local
software tests do not authorize production acquisition, preparation or training.

## Identity, preservation and remaining gates

Current uncommitted checkout: `integration/aiventra-crypto-os`, HEAD
`b8a574d62213bddab0eca356bdb903ebd4c2973f`. No reset, branch change, commit or push.

- Scientific source manifest:
  `0a094ec3d4b499adc9f561f4b4f2eef9464bcd01bf35f039fa85d0d7e797db32`.
- Execution source manifest:
  `0ca737d09c5c3b1b80a78b642985b8edf7dd57277a0974b86bbbdcdeff8efca9`.
- Dependency compatibility:
  `11c7722c2d289762066135d20fd4f10d4f9e4a7ab402342bfde38161c38f61ba`.

New source and membership hashes conservatively reject incompatible prepared/model
resume. Do not change a real checkpoint's policy field/hash to force acceptance;
no automatic recomputation or cache migration is authorized. Preserve valid
discovery/acquisition/candle/Gold artifacts and verify their normal identities before
reuse. Actual remote state remains UNKNOWN from this local session.

Final configuration inspection confirmed the unchanged hash
`93f987736b1a79d26b773957`, 16 folds, 48 primary specifications, 109 features, and
locked/false prospective-holdout flags. Git diff review found no changes to frozen
configurations, Phases 1–6, or Aiventra runtime/production adapter code. The five
Windows skips are Bash/Linux log-rotation checks, not evidence of a passing Linux gate.

Phases 1–6 and Aiventra runtime/production adapter remain untouched. The amended
engine is not newly approved for integration launch. July remains unused; August
remains `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.

The project remains **ON HOLD**. No real training, cloud compute action, data rebuild,
account/order access or holdout evaluation was performed. Before any real Fold 1,
complete the Linux gate, checkpoint inventory, real prepared-matrix equivalence and
resource profiling, then obtain a fresh owner-approved cost/deadline contract.
