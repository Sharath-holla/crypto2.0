# Crypto 2.0 — Full Project Review and Feasibility Assessment

Date: 21 November 2026 (IST). Reviewer: Claude, as research partner to the owner.

Scope: the repository docs (`MASTER_SPEC.md`, `CRYPTO_2_PROJECT_GUIDE_PHASES_1_TO_18.md`,
`PHASE5_RESULT.md`, `PHASE6_TARGET_RESEARCH.md`, `PHASE7_MODEL_ARCHITECTURES.md`,
`PHASE7_2_*`, `PHASE7_1_LITERATURE_REVIEW.md`, `FUTURE_TRADING_SYSTEM.md`, `AGENTS.md`), the
11 saved Phase 7A model files and their `train-result.json` reports, the live paper-trading run, and
one new cheap local probe on existing Gold data.

Nothing in this review trained a project model, spent cloud money, deleted artifacts or read July
2026 or the August holdout. One disclosure: the 10-minute live paper run on 21 Nov read live
November 2026 prices. No returns were scored and nothing was tuned on it, but live data is later
than the holdout start. It must never be used to choose or tune a model.

---

## Bottom line

1. **The current model has no measurable predictive edge on unseen data.** The Phase 7A
   test-window cross-coin IC averages **+0.003** over 9 folds (5 positive, 4 negative; t ≈ 0.4).
   This is the same conclusion Phase 5 reached on BTC with different features (direction ≈ 50.0%,
   every candidate INCONCLUSIVE).
2. **The software and validation process are mostly sound.** The failure is in the signal, not in
   leakage or plumbing. I found one modelling defect (early stopping on a noisy MSE target) and one
   calibration defect (an unstable linear calibrator on near-constant predictions). They make the
   results look worse *and* more random, but fixing them is unlikely to create a 14 bps edge by
   itself.
3. **Completing all 19 phases will not by itself make this profitable.** Phases 8–11 can add
   value only if they bring *new information* (different data or a different target), not more
   complex functions of the same OHLCV candles. Phases 12–19 reduce losses and make trading safe;
   they cannot create an edge.
4. **The cheap local probe found a real lead.** On the same 20 coins and features, LightGBM's
   cross-coin signal roughly triples from 1h to 24h (IC 0.007 → 0.020, positive in 15 of 18
   folds). It is still too weak to pay taker costs robustly, but 24h horizons with maker (limit)
   execution are close to break-even and worth a proper test.
5. **Recommendation:** do **not** train the remaining 7 folds or the other 47 specs of the
   60-minute study. Re-point Phase 7 to a 24h (and multi-day) horizon, a ranking objective, and a
   realistic maker/taker cost model. Test it locally first; pay for GPU only if it passes the
   go/no-go criteria below.

---

## A. Current state of Phase 7

### What Phase 7 is supposed to achieve

From `MASTER_SPEC.md` and `PHASE7_MODEL_ARCHITECTURES.md`: test whether a **multi-coin** LightGBM
model generalises better than BTC-only modelling, and which of four ways of sharing information
across coins works best. It is a *benchmark study*, not a trading-model release.

The full Phase 7A experiment is **48 specs per fold × 16 folds = 768 model runs**:
4 horizons (15/30/60/120 min) × 2 target types (raw, volatility-normalised) × 6 variants
(G0 balanced, G0 unbalanced, G0 + symbol ID, C0, P0, H0).

### What was actually completed

| Item | Done | Planned |
|---|---|---|
| Folds | 9 (0, 1, 2, 3, 4, 5, 6, 10, 15) | 16 |
| Specs per fold | **1** (`G0-A6-60m-raw`) | 48 |
| Model runs | 9 distinct (11 files; folds 0 and 4 were run twice and are bit-identical) | 768 |

So about **1.2% of the Phase 7A matrix** has been run. The architecture question (G0 vs C0 vs P0
vs H0) is still unanswered.

### Per-fold test results (from the saved reports)

| Fold | Trees kept (of 500) | Test pred. std (bps) | Real 60m move std (bps) | Test cross-coin IC | Direction | Calibrator slope | Trades | Net / trade @1.0× cost |
|---|---|---|---|---|---|---|---|---|
| 0 | 47 | 2.5 | 105 | −0.004 | 48.6% | −0.73 | 0 | — |
| 1 | **1** | 7.0 | 89 | −0.039 | 50.2% | **−9.76** | 146 | +3.4 bps |
| 2 | 14 | 0.7 | 101 | +0.037 | 51.5% | identity | 0 | — |
| 3 | 10 | 1.0 | 88 | +0.015 | 50.7% | identity | 0 | — |
| 4 | **1** | 13.4 | 89 | +0.012 | 51.6% | **+53.9** | 0 | — |
| 5 | 4 | 1.3 | 99 | −0.013 | 49.4% | **−14.5** | 0 | — |
| 6 | 25 | 7.8 | 117 | +0.014 | 52.0% | +2.06 | 0 | — |
| 10 | **1** | 0.3 | 108 | −0.008 | 49.1% | identity | 0 | — |
| 15 | 217 | 2.2 | 88 | +0.014 | 51.2% | +0.53 | 218 | −14.6 bps |
| **Mean** | | | | **+0.003** | **50.5%** | | | |

### Why the models fail to trade profitably — evidence, not assumption

1. **Early stopping killed most models.** With learning rate 0.02 and 50-round early stopping on
   validation MSE, 7 of 9 folds kept ≤ 25 trees and 3 kept **one tree**. A one-tree model at
   lr 0.02 outputs ~2% of a single tree's adjustment, which is close to a constant. That is why
   predictions are 0.3–13 bps wide when real moves are ~90–117 bps wide, why almost no prediction
   clears the 16 bps hurdle, and why the live run gave every coin nearly the same number.
   *Interpretation:* on raw 60-minute returns, the validation set says "more trees make MSE
   worse". That is itself evidence the signal is very weak, but MSE on fat-tailed raw returns is
   also a poor stopping metric for a ranking/threshold decision.
2. **The calibrator is unstable.** Linear calibration fitted on near-constant predictions gives
   slopes of −14.5, −9.8 and +53.9. A negative slope means the model was *anti*-correlated with
   outcomes on Cal-A and the calibrator flipped its sign. **Fold 1, the only profitable fold,
   traded on a sign-flipped ×9.8 calibration of a one-tree model**, and it had the worst test IC
   (−0.039). Its +3.4 bps/trade over 146 trades (t ≈ 0.4) is noise, and it turns negative at
   1.25× cost.
3. **Test-window signal is indistinguishable from zero.** Cross-coin IC +0.003 mean; direction
   50.5% mean.
4. **Costs dominate.** Round trip ≈ 14 bps (8 bps taker fees + spread + slippage). The best
   decile of predictions beat the worst decile by only ~2 bps on average (range −17 to +14).

### Corrections to what I told you earlier

- I said "8 of 9 folds beat Ridge". That comparison in the reports is **validation-only**
  (`scope: VALIDATION_ONLY`), on the same window LightGBM used for early stopping. It does not show
  out-of-sample superiority.
- I recommended "just go to 4h or 12h" based only on move sizes. Phase 6 had already tested this
  on BTC alone: IC *falls* with horizon (15m 0.069 → 1h 0.035 → 4h 0.014). Section F tests it on
  the multi-coin data, where the opposite happens: cross-coin signal *rises* with horizon. So the
  direction of my advice survives, but for a different reason and with much weaker economics than
  I implied.

### Live pipeline check (the 10-minute paper run)

- **Feature consistency:** I rebuilt features for 15 Jun 2026 12:00 UTC from Binance and compared
  them with Gold. **91 of 109 features match to 1e-6.** The rest differ for known reasons:
  market-wide/percentile features (the live universe has 15 coins, training had 19–20, because
  BLZ, FLM, HNT, OMG and STORJ are delisted), listing age (live used Binance `onboardDate`, Gold
  uses the registry's data start) and daily EMA-200 (Gold seeds it about 220 days before each
  chunk, so its value depends on chunking; minor train-side inconsistency).
- **Identical predictions across coins** are *not* a feature bug. They come from the one-tree
  models, whose top features are market-wide (`btc_return_4h`, `mark_index_basis`,
  `market_return_dispersion`), so every coin gets the same answer.
- **Duplicate weighting:** yes. Folds 0 and 4 each had two bit-identical files, so the 11-file
  average double-weighted them. Fix by averaging per fold.
- **Combining folds is not a valid backtest.** Later folds trained on earlier folds' test windows.
  For live use, the most recent fold model is the honest choice.

---

## B. The roadmap (19 phases)

`MASTER_SPEC.md` lists 19 phases. The project guide covers 1–18, and Phase 19 (gradual scale)
appears only in the master spec. The two are consistent. Older docs (`FUTURE_TRADING_SYSTEM.md`)
predate Phase 6 but match the same pipeline.

| # | Phase | Purpose | Status | Can it create edge? |
|---|---|---|---|---|
| 1 | BTC data foundation | Download/store Binance data | Done | No (infrastructure) |
| 2 | Data quality | Validate data | Done | No |
| 3 | Labels + baseline ML | 60m target, Ridge/LightGBM baselines | Done | Tested: no edge |
| 4 | Market intelligence + Main Model V2 | Features V2, backtest foundation | Done | Tested: no edge |
| 5 | Walk-forward + holdout | Proper OOS testing | Done | Result: all INCONCLUSIVE, direction ≈ 50% |
| 6 | Feature/target research | 12h/1d context, horizons, MFE/MAE | Done | 12h context weak KEEP; IC falls with horizon |
| 7 | Multi-asset expansion | G0/C0/P0/H0 LightGBM benchmark | ~1% run | So far: no edge |
| 8 | Advanced temporal models | TCN first, PatchTST second; TFT/iTransformer exploratory | Planned | Only if sequence order adds information |
| 9 | Regime Engine V2 | Trend/volatility/liquidity state | Planned | Indirect: filters when to trade |
| 10 | Ensemble + meta-labeling | Combine models; take/skip filter | Planned | Only if components are independently good |
| 11 | Event/sentiment | News, Fear & Greed, OI | Planned | **Yes, possibly**: genuinely new data |
| 12 | Portfolio + risk | Sizing, leverage limits, stops | Planned | No: reduces losses |
| 13 | Event-driven backtester | Realistic fills, funding, latency | Planned | No: measures truth more accurately |
| 14 | Paper trading | Live dry run | Planned | No: validation |
| 15 | Shadow mode | Production-shaped dry run | Planned | No: validation |
| 16 | Cloud deployment | Production infra | Planned | No |
| 17 | Monitoring + champion/challenger | Drift, model replacement | Planned | No |
| 18 | Tiny-capital trading | First real money | Planned | No: measures reality |
| 19 | Gradual scale | More capital | Planned | No |

**Key point:** only Phases 3–11 can produce predictive edge, and 3–7 have so far found none.
Phases 12–19 are essential for safety and honest measurement, but they multiply an edge; they
don't create one. `MASTER_SPEC.md` already says it: *"A later phase must not compensate for a broken
earlier phase."*

---

## C. The model architectures

### The "four architectures" are the Phase 7 G0/C0/P0/H0 variants, all LightGBM

They are four ways of sharing data across coins, not four different kinds of model:

| Code | Name | What it does | Purpose |
|---|---|---|---|
| G0 | Global | One model for all coins | Most data per model; tests whether patterns are universal |
| C0 | Cluster | One model per coin group (4 groups by liquidity/volatility/BTC beta) | Tests whether similar coins share patterns |
| P0 | Per-coin | One model per coin with enough history | Tests whether each coin is unique |
| H0 | Hybrid | Global model plus per-coin/cluster corrections | Best of both, if supported |

Only G0 has been run. Same inputs (109 A6 features), same targets. They answer a *structure*
question, so none of them adds new information on its own.

### Later model families

| Phase | Model | Inputs | What's different | Adds new information? |
|---|---|---|---|---|
| 7.2 | CatBoost / XGBoost | Same 109 features | Different tree algorithm | No; usually ±small vs LightGBM |
| 7.2 | 1-minute micro context (BTC/ETH) | 1m candles | Finer timing data | Somewhat: new resolution |
| 7.2 | Direct ranking (LambdaMART) | Same features | Optimises ranking, not MSE | No new data, but a better-aligned objective |
| 8 | TCN → PatchTST (TFT/iTransformer exploratory) | Sequences of the same features | Sees the order of recent bars | Only if order carries info that trees miss; low prior on 5m OHLCV |
| 9 | Regime engine | Volatility/trend/liquidity measures | Labels the market state | Mostly derived from the same data; useful as a filter |
| 10 | Ensemble + meta-label | Outputs of the models above | Combines and filters | No new data; meta-labeling helps only with a real primary signal |
| 11 | Event/sentiment | News, F&G, OI, funding | New data sources | **Yes**, if knowledge-time is verified |

### How one trade decision would eventually be made (example)

At 10:05 IST the 10:00–10:05 BTC 5-minute candle closes.

1. **Main model (Phase 7):** "BTC expected +22 bps over the next 4h, uncertainty ±80 bps."
2. **Temporal model (Phase 8):** "+15 bps." Ensemble (Phase 10): "+19 bps."
3. **Regime (Phase 9):** "Trending up, normal volatility": allowed.
4. **Meta-label (Phase 10):** "Similar setups paid off 56% of the time after costs": TAKE.
5. **Expected edge:** 19 bps forecast − 14 bps cost = +5 bps > 2 bps safety margin: pass.
6. **Liquidity gate (12):** BTC is deep: pass. **Risk engine (12):** daily loss budget fine,
   already long ETH (correlated): reduce size by half.
7. **Sizing/leverage (12):** 0.5% of capital, 1× leverage. **Execution (14+):** limit order at
   the bid, cancel if not filled in 1 minute.
8. **Trade management:** exit at 4h, or earlier on stop-loss / risk exit.

**Direction** comes from steps 1–2, **opportunity** from 4–5, **risk filtering** from 3 and 6–7,
**execution** from 7–8. Every step after 5 can only say "less" or "no". If step 1 has no edge,
the chain at best outputs NO_TRADE forever, which is exactly what we saw.

---

## D. Viability assessment

### Proven (evidence in this repo)

- The data pipeline, causal feature timing, purging/embargo, walk-forward geometry and holdout
  protection are carefully built and audited. This is a real asset.
- On Binance 5m OHLCV + taker-flow + funding/basis + 12h/1d context features, LightGBM and Ridge at
  15m–4h horizons show **at most tiny** predictive signal (IC 0.00–0.07, direction 50–52.5%).
  Four independent studies agree (Phases 3, 5, 6, 7A).
- At taker costs (~14 bps round trip), that signal does **not** survive. No fold, candidate or
  year has shown robust positive net expectancy.
- **Costs are slightly understated.** The config assumes a 4 bps taker fee per side. Binance's
  regular-user rate is 0.05% taker / 0.02% maker per side (0.045%/0.018% with the BNB discount),
  so a realistic taker round trip is ~11–18 bps, and a maker round trip is ~4 bps plus
  adverse-selection risk. Verify the live fee page before freezing.
- New (Section F): on 20 coins, LightGBM's cross-coin ranking signal grows with horizon and is
  statistically detectable at 24h (IC 0.020, t ≈ 4.2). Ridge does not see it.

### Plausible (reasonable but untested)

- A better-aligned objective (ranking or classification, cross-sectional/market-neutral targets,
  no MSE early stopping) could extract the small signal that does exist more reliably.
- **Lower costs** may matter more than a better model: maker (limit) execution, BNB fee discount
  or VIP tiers could cut round-trip cost from ~14 bps to ~4–8 bps. A 4 bps edge is useless at
  14 bps cost but viable at 4 bps.
- Genuinely new data (funding/OI positioning extremes, liquidations, order-book imbalance,
  cross-exchange basis) is where academic and practitioner evidence for crypto edge mostly comes
  from.

### Speculative (no evidence yet)

- That Transformers/TCNs will find sequence information in 5m OHLCV that trees miss. The repo's
  own literature review says the literature *does not* support this for tradable performance.
- That regime filtering will turn a zero-edge model positive. Filtering a zero-edge model
  mostly removes trades; it cannot create edge unless the edge exists inside some regime.
- That ensembling weak models will cross the cost threshold. Averaging reduces noise but does not
  increase the mean edge, which the live run showed directly.

### Is the architecture sound?

**The engineering architecture is sound. The research bet is the problem.** The system is
designed around one central assumption: that public candle data at 5m–4h horizons contains
predictable returns large enough to beat taker costs. Four phases of evidence now say it doesn't,
or only very weakly. Everything downstream depends on that assumption.

Retail-accessible crypto edges that do survive costs usually come from one of:
(a) cheaper execution (maker rebates, fee tiers),
(b) slower, larger moves where costs are small (daily/weekly trend or cross-sectional momentum
across many coins),
(c) structural carry (funding-rate / basis harvesting), or
(d) information not in candles (positioning, liquidations, order flow).
The current roadmap uses (b) only partially and none of (a), (c) or (d) yet.

---

## E. Phase 7 decision

| Option | Cost | Information value | Verdict |
|---|---|---|---|
| Train remaining 7 folds of the same spec | ~$6–10 GPU | Very low: 9 folds already show IC ≈ 0 | **Don't** |
| Run full 48-spec matrix | Large (~$100s) | Low: the same features at the same horizons | **Don't yet** |
| Fix early stopping + calibration, re-run locally on a subsample | ~$0 | Medium: rules out "the model was crippled" | **Do** |
| Horizon/target probe (4h/12h/24h, market-neutral) | ~$0 (done; see F) | High | **Done**: 24h is the best lead |
| Cost-model study (maker vs taker, fee tiers) | ~$0 | High: may change the hurdle by 2–3× | **Do** |
| New-data probes (funding extremes, OI, liquidations) | ~$0–small | High | **Do** |

---

## F. Horizon probe (local, existing Gold, no holdout)

Script: `scripts/research/horizon_probe.py`; results: `output/horizon_probe/fold_results.csv`.

**Setup:** the existing Phase 7A Gold (20 coins, 109 A6 features, research cutoff 1 Jul 2026), at
an hourly stride. Exact 4h/12h/24h returns were built by chaining 120m Gold returns. 18 rolling
folds: 24-month train, 3-month test, test windows Jan 2022 – Jun 2026, purge = horizon + 2h.
Fixed LightGBM settings (300 trees, lr 0.03, 15 leaves, no early stopping, no tuning) and a Ridge
control. Run time: about 2.5 hours on the Mac, $0.

| Horizon | Model | Cross-coin IC | IC > 0 folds | IC t-stat | Top-10% confident calls, gross bps | > 14 bps folds | Market-neutral long/short per leg, gross bps | Median \|move\| bps |
|---|---|---|---|---|---|---|---|---|
| 1h | LightGBM | 0.007 | 13/18 | 3.5 | 3.6 | 3 | 1.0 | 39 |
| 1h | Ridge | 0.001 | 9/18 | 1.0 | 1.6 | 1 | 0.2 | 39 |
| 4h | LightGBM | 0.008 | 15/18 | 2.7 | 6.3 | 6 | 1.4 | 78 |
| 4h | Ridge | 0.002 | 10/18 | 1.1 | 8.5 | 6 | 0.5 | 78 |
| 12h | LightGBM | 0.013 | 14/18 | 2.9 | 21.5 | 8 | 2.9 | 145 |
| 12h | Ridge | 0.002 | 9/18 | 0.5 | 21.5 | 8 | 1.9 | 145 |
| **24h** | **LightGBM** | **0.020** | **15/18** | **4.2** | **39.1** | **10** | **8.2** | 215 |
| 24h | Ridge | −0.001 | 8/18 | −0.1 | 37.3 | 10 | 1.8 | 215 |

Top-10% LightGBM confident-call gross edge per fold (bps):

| Test start | 22-Q1 | 22-Q2 | 22-Q3 | 22-Q4 | 23-Q1 | 23-Q2 | 23-Q3 | 23-Q4 | 24-Q1 | 24-Q2 | 24-Q3 | 24-Q4 | 25-Q1 | 25-Q2 | 25-Q3 | 25-Q4 | 26-Q1 | 26-Q2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 12h | 0 | 44 | −31 | −32 | 12 | 9 | −10 | 12 | 26 | 46 | 105 | 89 | 61 | 13 | −30 | 25 | 11 | 37 |
| 24h | 11 | 146 | −46 | 21 | 17 | 34 | −23 | −44 | 14 | 127 | 164 | 126 | 136 | 0 | −22 | 11 | 21 | 11 |

### What this shows

1. **Longer horizons do carry more signal on the multi-coin data.** LightGBM's cross-coin IC
   rises from 0.007 at 1h to **0.020 at 24h** (positive in 15/18 folds, t ≈ 4.2). This differs
   from Phase 6, which measured BTC alone. Ridge finds nothing, so the signal is non-linear.
2. **Ranking coins against each other is still too weak to pay taker costs.** The market-neutral
   long-top-3/short-bottom-3 earns 1–3 bps gross per leg up to 12h, and 8.2 bps at 24h. That is
   below the ~14 bps taker round trip, but close to a **maker** round trip (~4–6 bps).
3. **The confident directional calls clear costs on average at 12h/24h, but not robustly.** The
   24h top-10% edge of 39 bps gross (≈ +25 bps net) comes mostly from **four quarters,
   Apr 2024 – Mar 2025 (126–164 bps)**. Without them the average is about 10 bps, below cost.
   Ridge gets the same number, so it is mostly a simple market-timing effect, not a coin-picking
   skill. It fails the breadth rule.
4. **The 60-minute horizon chosen for Phase 7A is the worst of the four** on every measure.

### Caveats (why this is a lead, not a result)

- The top-10% cut uses each test fold's own prediction distribution. It's a diagnostic; a real
  policy must fix the threshold on Cal-B.
- 4 horizons × 2 models × several metrics were tried, so allow for multiple-testing luck. The
  24h IC t ≈ 4.2 would survive a Bonferroni correction over 8 comparisons; the economic numbers
  would not.
- Hourly entries with 12h/24h holds overlap heavily. Fold-level t-stats partly allow for this,
  but the effective sample is much smaller than the row count.
- Funding is not modelled (a 24h hold spans 3 funding payments, typically ±1–3 bps total).
- These test windows were already used by Phase 7A, so the Gold data is not pristine. The August
  holdout remains the only truly unseen data.

---

## G. Phase 8 / 9 strategy

- **Do not start Phase 8 (temporal models) until a tree model shows real out-of-sample edge.**
  The repo's own promotion policy says: "Neural/ensemble: each component qualifies alone." A
  Transformer on the same inputs is the most expensive way to test the least likely hypothesis.
- **Phase 9 (regime)** is cheap. Test it first as a *diagnostic*: is the existing signal positive
  inside any regime on Cal-B windows, and stable across folds? If not, a regime engine has nothing
  to filter.
- **Bring Phase 11's data forward.** Funding-rate extremes, open-interest changes, liquidations and
  long/short ratios are the most promising *new information*. Verify the history and knowledge
  time first; the repo already notes OI history is forward-only.
- **Bring cost reduction forward** (part of Phases 13/14): model maker-limit execution with
  realistic fill probability. This could be worth more than any model upgrade.

---

## H. Improvement plan (cheap, ordered by value per dollar)

1. **24h follow-up (Mac, free):** take the 24h LightGBM probe and add a proper Cal-B threshold
   (no test-based cut), non-overlapping trades, funding, and both taker (~14 bps) and maker
   (~5 bps) cost scenarios. Report per-fold net with the 2024 bull quarters both in and out. This
   one experiment decides whether a 24h Phase 7 rerun is worth paying for.
2. **Fix the model mechanics (Mac, free, subsample):** larger learning rate or fixed tree count
   instead of MSE early stopping; volatility-normalised or cross-sectionally demeaned targets;
   ranking objective; clip or remove the linear calibrator when prediction variance is tiny.
3. **Market-neutral cross-sectional test:** rank coins against each other each hour/day instead of
   predicting the absolute direction. This removes the BTC-direction bet, which is the hardest
   part to predict.
4. **Slower strategies:** daily cross-sectional momentum/reversal across the full Binance
   universe (hundreds of coins, not 20). Costs become ~5% of a daily move.
5. **Funding/basis carry probe:** test whether extreme funding predicts reversal over 8–24h, and
   whether pure funding carry (delta-neutral) is positive after costs.
6. Only after a pass on 1–5: choose **one** spec and pay for full 16-fold GPU training.

---

## Go / No-Go criteria for spending more money

Before any further GPU spend, a candidate must show, on retrospective walk-forward test windows
(never the holdout):

| Criterion | Threshold |
|---|---|
| Net expectancy at 1.0× cost | > 0 in ≥ 10 of 16 folds (already preregistered in `hardening_config`: `success_min_net_positive_folds = 10`) |
| Net expectancy at 1.5× cost | > 0 pooled |
| Sample size | ≥ 300 non-overlapping trades pooled, ≥ 30 in each traded fold |
| Statistical significance | Pooled net expectancy t-stat ≥ 2 with block bootstrap; Deflated Sharpe > 0 after counting every trial tried |
| Signal | Test cross-coin IC > 0 in ≥ 11 of 16 folds; beats Ridge **on test**, not validation |
| Breadth | No single coin > 25% or single quarter > 30% of total profit |
| Drawdown | Max drawdown < 3× average monthly profit |
| Calibration | Calibrator slope positive and within 0.3–3 in every fold |
| Stability | No year with materially negative net result |

Only after all of these pass would it be reasonable to open the August holdout once, as the final
exam, and then move to paper trading.

---

## Final answer

**If we complete all 19 phases as currently designed, do we have a realistic chance of a
consistently profitable system?**

**Not with the current information source and cost structure.** The engineering is good enough to
support a profitable system, but the evidence says the inputs it is built around (public 5m
candles traded with taker orders) do not contain enough predictable movement to pay the costs.
Adding Transformers, regimes, ensembles and risk engines on top would make a sophisticated
system that correctly concludes NO_TRADE.

**There is one concrete lead:** the 24h cross-coin signal in Section F is real by statistical
standards, though not yet by economic ones. A 24h horizon plus maker execution is the cheapest
path to a first genuinely positive result, and it can be tested on the Mac for free.

**It can still become viable if** the next research step finds edge in one of the places where
crypto edge actually tends to exist: lower costs (maker execution), slower cross-sectional
strategies over a broad coin universe, funding/basis carry, or genuinely new data (positioning,
liquidations, order flow). Each of these can be tested on your Mac for little or no money, using the
excellent validation machinery you already have.

The roadmap is worth keeping as a *skeleton*, but its order should change: **find the edge first
(cheap research), then build Phases 8–19 around whatever survives.**
