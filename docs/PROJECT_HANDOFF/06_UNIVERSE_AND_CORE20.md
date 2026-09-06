# Universe and Core20

## Realized `core_universe_v1`

The hold artifacts record this exact deterministic list:

1. **BTCUSDT** — mandatory anchor
2. **ETHUSDT** — mandatory anchor
3. ZRXUSDT
4. NEOUSDT
5. FLMUSDT
6. KNCUSDT
7. ONTUSDT
8. BLZUSDT
9. HNTUSDT
10. UNIUSDT
11. TRXUSDT
12. KSMUSDT
13. COMPUSDT
14. IOTAUSDT
15. STORJUSDT
16. OMGUSDT
17. ZECUSDT
18. FILUSDT
19. BCHUSDT
20. DOGEUSDT

Core universe hash: `f71cdf65d161466037b34420`.

## Deterministic selection

The target is 20 symbols at the exclusive cutoff `2022-01-01T00:00:00Z`, which equals Fold 1's
TRAIN end. BTCUSDT and ETHUSDT are required anchors. Candidates need at least 365 days of verified
point-in-time history, required 5m/12h/1d evidence, minimum trailing discovery coverage 0.995
(warning below 0.999), and integrity/availability at the cutoff. Descriptors use the prior 90 days
and persist `source_max_time < as_of`.

Eligible symbols are stratified by causal quote-volume liquidity, realized volatility, and history
length. Deterministic round-robin selection across three-dimensional buckets creates a varied
benchmark; ties use coverage, history, and symbol. Returns, later performance, current popularity,
market capitalization, later survival, and holdout data are forbidden inputs.

## Point-in-time existence and expansion

A symbol exists at `t` only when `available_from <= t < available_until`. Every fold recomputes
eligibility at `fold.train_end`. `expansion_universe_v2` may add at most ten non-core symbols, with
a maximum of 30 active symbols, using causal history, coverage, integrity, liquidity, and current-at-
that-fold lifecycle only. Acquisition may contain their bounded union, but that union is not model
membership. Phase 7A disables the EXPANDING evaluation view only; it does not alter the full Phase
7 policy.

## HNT and survivorship protection

HNTUSDT was eligible at the 2022 cutoff and selected normally. It later delisted. Removing it after
learning that fact would introduce survivorship bias, so it remains in Core20 for historical folds;
rows after validated `available_until` are legitimate lifecycle absence. Commit `be3a164` fixed the
general lifecycle intersection without an HNT-specific branch.

## XPIN

`XPINUSDT` was not forced into Core20. The project-hold evidence records only that owner-forcing was
not applied and the list above remained the deterministic result. Exact XPIN listing,
`causal_available_from`, Silver status, and cutoff eligibility are **UNKNOWN / NOT VERIFIED** in
the local repository/hold package available while the VM is terminated. Do not invent those
values, force XPIN, or rerun discovery merely to populate this document.

## Scientific reason this matters

A current exchange list would discard dead contracts and overstate historical model coverage.
Frozen causal membership allows apples-to-apples CORE comparison while a separately labeled
EXPANDING view can test newer assets. Neither view may use future status, liquidity, quality,
returns, TEST results, July, or August to change earlier membership.
