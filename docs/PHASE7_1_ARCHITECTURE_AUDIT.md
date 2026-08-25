# Phase 7.1 full architecture re-audit

Audit date: 2026-08-24. Repository baseline HEAD:
`dd978b964a8abe1df2ad0b4e1fdbcb0f51724c2c`. The supplied instruction text
ended mid champion/challenger workflow; this audit executes every complete
requirement present and does not invent the missing tail.

## Baseline and immutable-artifact control

The starting worktree was clean. Source/config/test inventory before edits was
100 non-cache source files, 18 config files and 47 test files. The exact default
pytest command initially encountered Windows ACL denial in the host pytest temp
directory after 215 passes; this was infrastructure, not a test assertion. With
a repository-scoped `--basetemp` and cache provider disabled, the clean baseline
was 280 passed, 0 failed, 0 skipped. Ruff lint/format, compileall, lock check and
`git diff --check` passed. Safe `--validate-config`, `--plan`, `--dry-run`, and
`--test-universe` checks passed without network or private API access. The
configuration hash is now `68e4b39899f8c9f0542d227b` after the explicit v2
decision-latency field, and the plan derives 16 folds.

`artifact_fingerprint_v1` is now the canonical read-only preservation method:

1. recursively enumerate files under each supplied repository-contained root;
2. use repository-relative POSIX paths and ordinal sorting;
3. SHA-256 each file's bytes;
4. encode each record as UTF-8
   `relative_path<TAB>file_size<TAB>sha256<LF>`;
5. SHA-256 concatenated records per root, then all roots sorted by root path.

The pre-change ad-hoc inventory reported:

| Root | Files | Bytes | Aggregate SHA-256 |
|---|---:|---:|---|
| `data` | 16,754 | 1,955,207,062 | `c6b9c2245e311ab37639a7629e111d2486cd707ac7a023cbce9f20a3ffef3000` |
| `local_artifacts` | 2,131 | 919,871,730 | `81685b4fcded56dabec3792d6b512ae122f091a0053d57216620c40a0e886cb6` |
| combined | 18,885 | 2,875,078,792 | `11a00ed1e8b05ea6e37a9fc1feef8e88f700278458207a17a36aa9ec426f06b9` |

The implementation is `python -m crypto_ai.audit.artifacts --root data --root
local_artifacts`. It rejects escaping roots and symlinks and writes nothing.
The final canonical v1 inventory reproduced every count and byte total but not
the ad-hoc aggregate hashes:

| Root | Files | Bytes | Canonical v1 SHA-256 |
|---|---:|---:|---|
| `data` | 16,754 | 1,955,207,062 | `c2060c9ec37917df8cbc31eab0dd437523eaebbef01ba0e74fb5b911d6e510d2` |
| `local_artifacts` | 2,131 | 919,871,730 | `c6121785ca4d07bd6278199d706df4b9e582b4f064b299f7478c87a3d1d50af8` |
| combined | 18,885 | 2,875,078,792 | `ad44fe62a5bae2df4c9b21f3d39f02b2141fe4dd6db7db022bb3fe6ee62103f1` |

No artifact has a modification time later than 2026-08-20, while this audit ran
on 2026-08-24, and all task commands were read-only for these roots. A diagnostic
tested ordinal/casefold sorting, repository/root-relative paths, POSIX/Windows
separators, lower/upper/raw file digests, and LF/CRLF/no terminators without
reproducing the ad-hoc hashes.

On 2026-08-25, the independent reviewer accepted the exact canonical v1 values
above as the authoritative artifact-preservation baseline going forward. R-13
is therefore
`RESOLVED_BY_REVIEWER_ACCEPTANCE_OF_CANONICAL_FINGERPRINT_V1`. The unchanged
counts/bytes, pre-audit mtimes, clean artifact Git diff, and absence of evidence
of mutation support that decision. The old undocumented `c6b9c224...`,
`81685b4f...`, and combined `11a00ed1...` digests remain historical metadata
only. They are not directly comparable with `artifact_fingerprint_v1` and must
not be used as its pass/fail baseline.

## Boundary and lineage audit

- Phase 1–6 code/artifacts are immutable; the audit does not rewrite them.
- Phase 7 research range ends at the exclusive
  `2026-07-01T00:00:00Z`; `feature_time` and `label_end_time` are asserted below
  it.
- All July 2026 is an unused buffer.
- The prospective holdout starts `2026-08-01T00:00:00Z`, remains
  `LOCKED_UNUSED`, `prospective_holdout_used=false`, and
  `prospective_holdout_evaluation_authorized=false`.
- Bronze is immutable, exact-decimal source identity remains separated by
  market, missing candles are reported/not filled, and Gold/checkpoints bind
  registry, universe, config, feature/target and source hashes.

## Information and feature timing

For a 5m row opened at `t`, candle OHLCV/trade/taker values become usable at
`t+5m`, which is `feature_time`. Coin-local rolling features use only current
and earlier completed rows and reset across gaps. BTC/ETH anchors use exact
timestamps; missing anchors remain missing. 12h/1d values are available at
their candle open plus interval and are joined as-of with
`availability_time <= feature_time`. Funding is event-time as-of with a 24h
age limit; mark/index context has a 5m age limit. F&G/OI are absent from the
training allowlist.

The static feature inventory is 54 columns before optional higher-timeframe
columns: 24 base coin-local, 11 coin/context, 11 BTC/ETH anchor and 8 market
context. With configured direct 12h/daily context it is 109 columns (22 + 33
higher-timeframe columns). The code-derived formula/timing/allowlist catalog is
`PHASE7_1_FEATURE_CATALOG.md`. Classification:

| Family | Count | Phase 7 status | Rationale |
|---|---:|---|---|
| Returns/range/ATR/EMA/volatility/volume/trades/taker flow and causal normalized ratios | 21 | BASELINE | Scale-aware, completed-candle, gap-reset inputs. |
| Funding z-score and mark/index/contract basis | 3 | A6 OPTIONAL | Official causal derivatives context; missingness preserved. |
| Listing/history, cross-sectional percentiles, beta/correlation/relative strength | 11 | CONTROLLED | Requires point-in-time registry and fold-bound membership. |
| BTC/ETH anchors | 11 | A1/A2 CONTROLLED | Exact-time anchors; no forward fill. |
| Market breadth/context | 8 | A3 CONTROLLED | Recomputed only from frozen fold active symbols in v2. |
| Completed 12h/daily | dynamic | A4/A5 OPTIONAL | Availability-time as-of, independent joins. |
| Fear & Greed | 0 enabled | REJECTED NOW | Historical knowledge time unverified. |
| Open interest | 0 enabled | REJECTED NOW | Recent/forward-only official availability. |
| CryptoPanic/Arkham/Reddit/on-chain | 0 | OUT OF SCOPE | No approved point-in-time dataset or implementation. |

## Universe and cross-sectional audit

`core_universe_v1` remains the stable pre-2022 benchmark. Expansion is a causal
policy evaluated at each fold's TRAIN end from descriptors whose source maximum
time is strictly earlier. `fold_active_symbols` equals eligible core plus
eligible cap-selected expansion. Listing, availability, history, coverage,
higher-timeframe quality and causal trailing liquidity may admit/exclude;
future survival/liquidity/returns/profit/model/TEST may not.

The audit found and fixed one leakage path: Gold was built over the union of
symbols needed by any fold, and acquisition-time breadth/percentiles could
therefore include a symbol before that fold admitted it. Feature/context
versions are now v2. Gold preserves raw cross-sectional source values and tags
union values `ACQUISITION_UNION_PREVIEW`. Fold slicing filters membership first,
then deterministically replaces all percentiles/breadth/dispersion/count/hash
values and tags them `FOLD_ACTIVE_SYMBOLS`. Perturbation tests compare this
binding against a dataset in which the non-admitted symbol never existed.

## Target timing audit

For a completed prediction candle `i`, `feature_time=open[i+1]`. Target v2
reserves one complete 5-minute decision-latency bar and references entry at
`open[i+2]`; inference and intent creation occur in the interval before that
open. Horizons are measured from entry:

| Horizon | feature time | v2 entry reference | label end | Expected path | Status |
|---|---|---|---|---|---|
| 15m | `open[i]+5m` | `open[i+2]`, five minutes later | `open[i+5]` | entry bars `i+2..i+4` | Valid post-signal reference. |
| 30m | same | same | `open[i+8]` | entry bars `i+2..i+7` | Valid post-signal reference. |
| 60m | same | same | `open[i+14]` | entry bars `i+2..i+13` | Valid post-signal reference. |
| 120m | same | same | `open[i+26]` | entry bars `i+2..i+25` | Valid post-signal reference. |
| 240m | — | — | — | — | Not supported/configured in Phase 7. |

Every expected interval through label end is required; gaps invalidate the
row. Boundary purging uses each row's actual `label_end_time`, and 120m embargo
protects Train→Validation, Validation→Cal-A, Cal-A→Cal-B and Cal-B→TEST.
`multiasset_targets_v1` remains available only to reproduce its same-boundary
construction. The configured target identity and manifests use v2; no existing
dataset, Phase 1–6 label, or historical artifact was modified.

## Split/model ownership audit

- TRAIN: parameters, symbol balancing, cluster/scaler, liquidity tiers.
- Validation: LightGBM early stopping and declared H0 residual structure.
- Cal-A: prediction calibration and P0 maturity/coverage eligibility.
- Cal-B: frozen threshold/policy selection only.
- TEST: one-time evaluation after model/calibrator/policy identity freeze.

The audit corrected P0's previous Cal-A+Cal-B eligibility count. Matched
architecture comparisons intersect identical TEST `(symbol, feature_time)`
coverage; macro, micro, symbol, cluster, age, cross-sectional IC, cost,
concentration and no-trade reporting remain explicit. H0 Validation residual
fitting and multiple-comparison burden remain open research risks.

## Safe future-system extraction

Only exchange-independent pure logic was added: canonical artifact hashing and
deterministic order/position aggregates with idempotent commands, optimistic
version checks, cumulative fills, stale/duplicate/gapped event handling,
fill-cancel race semantics, reconciliation snapshots, explicit unprotected
safe-error state and monotonic stops. All 35 required race simulations are
implemented and pass. It cannot connect to Binance or access an account. The
future dashboard is a read-mostly control plane; exchange plus durable event
state are authoritative. Detailed state, reconciliation, paper/shadow, drift
and champion/challenger design is in `PHASE7_1_CONTROL_PLANE_DESIGN.md`.

## Research conclusion

The external benchmark does not compare returns. Our research integrity and
artifact controls are strong relative to the reviewed documented capabilities;
our execution/risk/reconciliation stack is intentionally absent. Literature
supports the current boosted-tree baseline and causal global/cross-sectional
research, but not a claim that a Transformer, sentiment feed or RL agent will
improve tradable performance. LightGBM stays baseline; TCN then PatchTST are
future sequence challengers; RL is reserved for constrained execution/sizing
research.

## Final verification record

- Complete repository suite after reviewer acceptance: **328 passed, 0 failed,
  0 skipped**, one harmless joblib physical-core detection warning, in 34.42s.
  The exact `uv run pytest` required no pytest temp workaround.
- Phase 7/7.1 targeted suite: **102 passed, 0 failed, 0 skipped**, the same one
  joblib warning, in 13.26s. The 35-case race matrix is included.
- `ruff check`: pass; `ruff format --check`: 148 files already formatted.
- `compileall -q src tests`: pass; `uv lock --check`: 30 packages resolved.
- `git diff --check`: pass (Windows line-ending notices only).
- Safe CLI validation/plan/dry-run/test-universe: all pass; config hash
  `68e4b39899f8c9f0542d227b`, target `multiasset_targets_v2`, latency one bar,
  16 folds, 54 native dry-run features, and 11,308 fixture target rows; no
  network, private API, files written or heavy training; guard not enabled.
- Credential, hard-coded Windows path, concrete GCS bucket, debugger and
  temporary-file scan: clean. The documented guard warning is intentional.
- No commit, push, cloud start, heavy acquisition/training, holdout access or
  live/private exchange action occurred.

The target-specific scientific blocker is resolved by v2, and the independent
reviewer has resolved R-13 by accepting the canonical v1 fingerprint. Subject
to the final rerun recorded above, the verdicts are **REPOSITORY VERIFICATION:
PASS**, **SOURCE-CONTROL VERDICT: SAFE TO COMMIT**, and **CLOUD RESEARCH
VERDICT: READY FOR CLOUD BASELINE**. This audit does not itself commit, push,
start cloud resources, enable the cloud guard, or run acquisition/training.
