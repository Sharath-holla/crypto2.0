# Checkpoint and Resume Architecture

## Layers

| Layer | Durable object | Current Phase 7A state |
| --- | --- | --- |
| Registry | registry artifact + stage checkpoint/identity | Complete; validate before use |
| Discovery | per-symbol evidence/checkpoint files | 507/507 complete; canonical backup in GCS |
| Universe | Core/expansion policy/membership artifacts + hashes | Complete; Core20 hash recorded |
| Acquisition | data checkpoint + manifest | Complete and valid; known SHA-256 values |
| Candles | 20 symbols × 5m/12h/1d manifests/checkpoints | 60 validated |
| Gold | checkpoint, manifest, partition list/hashes | 7/7 complete; hash must be re-read from disk |
| Fold membership/splits | fold plan and causal membership identity | Constructed when training enters a fold |
| Prepared matrices | **No durable artifact/checkpoint** | Missing; current blocker |
| Model | per-spec joblib bundle written temp→replace | 0 models for Fold 1 |
| Report | per-spec immutable JSON/Parquet result | 0/48 Fold-1 reports |
| Fold summary | completed-spec/fold summary | Fold 1 incomplete; no fold complete |

## Correct completeness semantics

`CheckpointStore` records stage identity and required files. JSON/Parquet/model writes use a
temporary path and atomic replacement; immutable writers refuse silent overwrite. A file's
presence is insufficient: identity, source hashes, schema, required outputs, ranges, row counts,
and holdout flags must validate. A partial model/report/matrix is never `COMPLETE`, and a
preparation checkpoint must never falsely mark the train/fold stage complete.

Resume should validate and reuse registry, discovery, universe, acquisition, candle, and Gold
layers. It should recompute only an invalid interrupted atomic unit. Any cache must bind config,
source fingerprint, Gold/manifest hashes, universe/view/fold, exact segment boundaries, horizon,
target, ordered feature schema, purge/embargo, preprocessing, and library/schema versions.

## Why work repeated

Current per-spec resume starts after matrix/fold preparation. Interrupted workers had scanned
partitioned Gold, filtered/sliced rows, rebound cross-sectional context, prepared segments, and
converted Arrow to NumPy, but no validated artifact captured that state. Every new attempt repeated
the preparation before the first estimator/model/report. This missing boundary is the first future
engineering target; see [21_FOLD1_PREPARATION_BOTTLENECK.md](21_FOLD1_PREPARATION_BOTTLENECK.md).
