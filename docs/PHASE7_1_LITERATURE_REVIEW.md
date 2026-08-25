# Phase 7.1 structured literature review

The catalog distinguishes peer-reviewed evidence, preprints, official system
papers and practitioner claims. A result is not transferable merely because it
uses financial or crypto data. Validation design, availability time, universe,
costs and execution assumptions control relevance.

## Topic disposition (A–AH)

| Topics | Disposition | Project implication |
|---|---|---|
| A–E leakage, purging, overfit, multiple testing, walk-forward | REQUIRED | Keep temporal folds; add family-aware SPA/Reality Check, DSR/PBO and dependent bootstrap. |
| F–H global/cross-sectional/normalization | PROMISING | Phase 7 G0/H0 and causal fold-local context are justified; never use eventual-universe normalization. |
| I–J regimes and state space | PHASE 9 CANDIDATE | Start with observable volatility/trend/liquidity regimes; HMM only as a challenger with stable state interpretation. |
| K–L boosted trees | REQUIRED BASELINE | Keep LightGBM; add matched XGBoost/CatBoost challengers after target timing is fixed. |
| M–P TCN/RNN/TFT/Transformers | PHASE 8 CANDIDATE | Small causal TCN first, PatchTST second; TFT/iTransformer exploratory and capacity-controlled. |
| Q crypto forecasting | MIXED | Many papers use one coin, short samples, shuffled splits or weak costs; architecture evidence transfers more reliably than reported returns. |
| R–T funding/OI/positioning | PROMISING BUT DATA-LIMITED | Funding/basis can remain causal features. OI is forward-only until verifiable history exists; never fabricate it. |
| U microstructure | LATER | Needs order-book/event data and executable latency modeling, outside Phase 7. |
| V–W news/Fear sentiment | OPTIONAL/UNVERIFIED | Effects are unstable and often reverse-causal; historical knowledge time must be proven. Current F&G remains disabled. |
| X on-chain flows | INSUFFICIENT FOR PHASE 7 | Venue/chain timestamp and publication-lag controls are unresolved. |
| Y–Z drift/online learning | REQUIRED OPERATIONS LATER | Detect, quarantine and shadow; do not autonomously retrain/promote. |
| AA–AD probabilistic/calibration/uncertainty/conformal | PROMISING | Quantile or distributional challengers plus fold-local calibration; coverage must be time-dependent and cost-aware. |
| AE transaction costs | REQUIRED | Report full turnover/cost/funding/latency grids and no-trade cases. |
| AF meta-labeling | OPTIONAL | Only after a valid executable primary signal; avoid using TEST to define the filter. |
| AG RL trading | NOT PRIMARY FORECASTER | Later constrained sizing/execution research only, in simulator then shadow mode. |
| AH portfolio/risk | REQUIRED LATER | Separate forecasting from allocation, exposure limits, liquidation distance and kill switches. |

## Paper catalog

Compact fields: asset/frequency; target/model; validation; costs; code; result,
limitation and relevance.

| Paper | Evidence and project assessment |
|---|---|
| White, 2000, *Econometrica*, [Reality Check](https://doi.org/10.1111/1468-0262.00152) | General/time-series; best-rule performance; stationary-bootstrap test; costs depend on application; code no. Corrects data snooping across a declared family. Required, but power depends on candidate set and dependence assumptions. |
| Hansen, 2005, *JBES*, [SPA](https://doi.org/10.1198/073500105000000063) | General/time-series; superior predictive ability; studentized multiple-model test; costs application-specific; code no. Often more powerful than Reality Check. Required family-level robustness, not a cure for biased backtests. |
| Bailey & López de Prado, 2014, *Journal of Portfolio Management*, [Deflated Sharpe](https://doi.org/10.3905/jpm.2014.40.5.094) | Asset-management performance; selection-adjusted Sharpe; analytical/Monte Carlo; costs upstream; code not official. Useful reporting diagnostic; trial accounting must be honest. |
| Bailey et al., 2017, *Journal of Computational Finance*, [PBO](https://doi.org/10.21314/JCF.2016.322) | Strategy configurations; probability of backtest overfitting; combinatorially symmetric CV; costs application-specific. Useful diagnostic, but CSCV is not a substitute for chronological execution tests. |
| Politis & Romano, 1994, *JASA*, [Stationary bootstrap](https://doi.org/10.1080/01621459.1994.10476870) | Dependent stationary data; sampling distribution; random blocks; costs N/A. Required for dependence-aware intervals; block sensitivity must be reported. |
| Diebold & Mariano, 1995, *JBES*, [Predictive accuracy](https://doi.org/10.1080/07350015.1995.10524599) | Forecast errors; equal predictive accuracy; HAC variance; costs not intrinsic. Good paired loss test with overlapping-horizon variance; not a trading-profit test. |
| Ke et al., 2017, NeurIPS, [LightGBM](https://proceedings.neurips.cc/paper/6907-lightgbm-a-highly-efficient-gradient-boosting-decision-tree) | General tabular benchmarks; GBDT; held-out benchmarks; costs N/A; code yes. Efficient baseline, but finance generalization must be established locally. |
| Chen & Guestrin, 2016, KDD, [XGBoost](https://doi.org/10.1145/2939672.2939785) | General tabular/sparse data; boosted trees; benchmark validation; costs N/A; code yes. Strong matched challenger with different regularization/system tradeoffs. |
| Prokhorenkova et al., 2018, NeurIPS, [CatBoost](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html) | General tabular/categorical data; ordered boosting; benchmarks; costs N/A; code yes. Relevant for symbol/category handling; ordered target statistics must remain causal. |
| Bai, Kolter & Koltun, 2018, arXiv, [TCN evaluation](https://arxiv.org/abs/1803.01271) | Generic sequence tasks; sequence prediction; TCN vs RNN; standard benchmarks; costs N/A; code yes. Supports TCN as a simple sequence baseline, not a claim about crypto returns. |
| Lim et al., 2021, *International Journal of Forecasting*, [TFT](https://doi.org/10.1016/j.ijforecast.2021.03.012) | Multi-domain, multi-horizon; quantiles; temporal fusion; rolling/held-out benchmarks; costs N/A; code available. Useful for static covariates and uncertainty, but high capacity and no direct crypto-economics evidence. |
| Nie et al., 2023, ICLR, [PatchTST](https://openreview.net/forum?id=Jbdc0vTOcol) | Multivariate forecasting benchmarks; long-horizon values; patched channel-independent Transformer; benchmark splits; costs N/A; code yes. Promising compact challenger; finance targets/noise differ sharply. |
| Liu et al., 2024, ICLR, [iTransformer](https://openreview.net/forum?id=JePfAI8fah) | Multivariate forecasting benchmarks; long-horizon values; inverted Transformer; benchmark splits; costs N/A; code yes. Exploratory only; cross-asset variates and missing/listing histories need bespoke masks. |
| Zhang, Zohren & Roberts, 2019, *IEEE TSP*, [DeepLOB](https://doi.org/10.1109/TSP.2019.2907260) | Equity limit-order books/high frequency; short-horizon direction; CNN-LSTM; anchored train/test; transaction costs not the primary target; code available. Supports microstructure modeling later, not candle-only Phase 7. |
| Sirignano & Cont, 2019, *Quantitative Finance*, [Universal features](https://doi.org/10.1080/14697688.2019.1622295) | Multi-asset LOB/high frequency; price movement; deep nets; cross-instrument tests; costs limited. Supports shared multi-asset representations; venue microstructure transfer is uncertain. |
| Gu, Kelly & Xiu, 2020, *Review of Financial Studies*, [Empirical asset pricing via ML](https://doi.org/10.1093/rfs/hhaa009) | US equities/monthly; expected returns; trees/nets; expanding OOS tests; economic portfolios; code available. Strong evidence for nonlinear/cross-sectional comparisons, but frequency and market differ. |
| Hamilton, 1989, *Econometrica*, [A new approach to the economic analysis of nonstationary time series](https://doi.org/10.2307/1912559) | Macroeconomic time series; latent regime/state inference; likelihood-based validation; costs N/A; code no. Foundational Markov-switching evidence, but estimated states are model-dependent and should be a Phase 9 challenger rather than labels fitted on the full sample. |
| Hochreiter & Schmidhuber, 1997, *Neural Computation*, [Long short-term memory](https://doi.org/10.1162/neco.1997.9.8.1735) | Generic sequences; sequence learning; LSTM; benchmark validation; costs N/A; code ecosystem yes. Supports an RNN reference baseline, not financial superiority; GRU/LSTM capacity and state warm-up must be fold-local. |
| Garcia & Schweitzer, 2015, *EPJ Data Science*, [Social signals and Bitcoin](https://doi.org/10.1140/epjds/s13688-015-0058-4) | Bitcoin/daily; returns/trading; social signals; rolling simulation; costs considered; code/data partial. Suggestive, but platform behavior and historical availability are unstable. |
| Siganos, Vagenas-Nanos & Verwijmeren, 2021, *Finance Research Letters*, [Bitcoin sentiment robustness](https://doi.org/10.1016/j.frl.2020.101494) | Bitcoin/intraday; returns; StockTwits sentiment; time-frequency analysis; economic profits assessed; code no. Small/bubble-concentrated effect and no economic profit supports keeping sentiment optional. |
| Guo et al., 2017, ICML, [Neural calibration](https://proceedings.mlr.press/v70/guo17a.html) | Image/text classification; probability calibration; temperature scaling; held-out calibration; costs N/A; code available. Establishes calibration need, but regression/trading calibration requires local methods and temporal splits. |
| Salinas et al., 2020, *International Journal of Forecasting*, [DeepAR](https://doi.org/10.1016/j.ijforecast.2019.07.001) | Many related series; probabilistic forecasts; autoregressive RNN; rolling benchmarks; costs N/A; code yes. Supports global probabilistic forecasting; heavy tails and selection still require crypto validation. |
| Zaffran et al., 2022, ICML, [Adaptive conformal predictions for time series](https://proceedings.mlr.press/v162/zaffran22a.html) | General time series; sequential interval coverage; adaptive conformal methods; rolling experiments; costs N/A; code available. Promising uncertainty challenger, but dependence/distribution shift weaken ordinary exchangeable conformal guarantees and coverage alone does not imply tradable value. |
| Almgren & Chriss, 2001, *Journal of Risk*, [Optimal execution of portfolio transactions](https://doi.org/10.21314/JOR.2001.041) | Equities/execution schedules; cost-risk frontier; impact model; theoretical/empirical calibration; explicit temporary/permanent costs; code no. Establishes why bar-level spread/slippage assumptions are not a production fill model; later execution research needs size, impact, latency, and uncertainty. |
| Ackerer, Hugonnier & Jermann, 2026, *Mathematical Finance*, [Perpetual futures pricing](https://doi.org/10.1111/mafi.70018) | Perpetual futures/crypto examples; no-arbitrage pricing and funding; theoretical/empirical illustration; execution costs not central; code not established. Supports treating funding/basis as contract mechanics, not guaranteed return alpha; venue conventions and observability remain essential. |
| FinRL authors, 2020–2024, [official repository](https://github.com/AI4Finance-Foundation/FinRL) | Stocks/crypto examples; portfolio/trading reward; DRL; train-validation-test pipelines; cost support varies; code yes. Useful environment pattern; simulator/reward assumptions dominate and production use is not established by examples. |
| Liu et al., 2026, [FinRL-X](https://arxiv.org/abs/2603.21330) | Multi-market trading; agentic/RL platform; system paper; evaluation described by authors; costs/system integration; code linked. Relevant architecture benchmark, but recent preprint evidence needs independent replication. |
| Vyetrenko et al., 2020, NeurIPS workshop, [Financial Gym](https://arxiv.org/abs/1911.10601) | Markets; RL environments; standardized simulation; benchmark framing; costs configurable; code yes. Reinforces that RL claims are only as credible as environment realism. |

## Bad-practice screen

Reject or downgrade studies with random shuffled time-series splits, normalization
fit on the full sample, exact same-boundary fills, eventual-survivor universes,
zero costs, tiny/single-regime tests, unreported HPO/trial counts, no turnover or
slippage, or conclusions drawn from one coin and one period. Preprints and
vendor/system claims remain useful for design discovery but are not promotion
evidence. This audit preserved the flagged same-boundary v1 only for
reproducibility and moved configured Phase 7 research to a post-signal v2; that
fix still does not turn candle-level cost assumptions into production fills.
