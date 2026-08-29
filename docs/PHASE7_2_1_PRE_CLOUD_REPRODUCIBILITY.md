# Phase 7.2.1 pre-cloud reproducibility correction

Phase 7.2.1 is a narrow configuration-identity correction and boundary proof.
It adds no feature, target, model, fold, universe, threshold, execution, cloud,
or leverage behavior.

## Cross-platform configuration identity

The prior Phase 7 identity used Pydantic JSON output containing native
`pathlib.Path` separators. The same logical path therefore serialized with
backslashes on Windows and forward slashes on Linux. The former observed hash
`68e4b39899f8c9f0542d227b` is retained as historical Windows metadata only.

`Phase7Config.configuration_identity_payload()` now canonicalizes only the
actual path-typed logical fields to POSIX separators before deterministic JSON
hashing. It does not rewrite arbitrary strings, resolve paths, consult the
working directory, or inspect the filesystem. The authoritative portable hash
is `cc550337f1f4ee4654124bf6` on Windows and Linux.

## Target and boundary proof

For a candle opening at `T`, the feature is available at `T+5m`; the v2 entry
is `T+10m`, exactly five minutes after feature time. Label end is measured from
entry, so the configured feature-time spans are 20, 35, 65, and 125 minutes for
the 15, 30, 60, and 120-minute targets.

At every Train→Validation, Validation→Cal-A, Cal-A→Cal-B, and Cal-B→TEST
boundary, production purging keeps an earlier row only when its actual
`label_end_time < next_segment_start`. Thus a 120-minute row at boundary−125m
touches the boundary and is purged, while boundary−130m ends at boundary−5m and
is retained. The separate embargo acts on the later segment's `feature_time`
and removes `[boundary, boundary+120m)`. A later row at boundary+120m enters at
boundary+125m. The decision-latency bar therefore does not require a
125-minute embargo; its 125-minute earlier-label span is already handled by
actual-label-end purging.

Verdict: `EMBARGO_120_CORRECT`.

## Cross-sectional IC

Timestamp-level cross-sectional Spearman IC is already implemented by
`crypto_ai.phase7.metrics.cross_sectional_ic`, called by
`evaluate_predictions`, and covered by
`tests/phase7/test_hardening_audit.py::test_cross_sectional_ic_is_grouped_by_timestamp`.
No duplicate metric was added.
