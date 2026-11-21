> **Independent audit update:** The original text below was committed by another process at
> `c249e285248c12d6d97e1a9be3d4c4625b37f258` during this audit and is preserved.
> The appended independent assessment supersedes conflicting claims, ratings and recommendations.
> See the main report's independent assessment for executed checks and evidence limits.

# Crypto 2.0: literature and practitioner comparison (2026-11-06)

**How these sources were checked.** Each URL below came back from a web search this session, so the
work and link exist. In this session I did NOT re-read the full texts; the "main finding" column is
the standard characterisation of each work and should be re-checked against the paper before it is
quoted. Evidence levels: A peer-reviewed/authoritative; B strong preprint or official docs; C
credible practitioner article; D community anecdote. Sources I could not verify are omitted, not
guessed (Qlib, FinRL, vectorbt, CoinSwitch fee pages, individual X posts).

| Topic | Source (link) | Level | Main point | Does Crypto 2.0 follow it? | Adopt |
| --- | --- | --- | --- | --- | --- |
| Purging / embargo / CPCV | López de Prado, *Advances in Financial Machine Learning* (Wiley, ISBN 978-1-119-48208-6) https://www.lehmanns.de/isbn/978-1-119-48208-6 | A (book) | Purge overlapping labels, embargo after the test window, combinatorial CV for path distributions | Purge on actual `label_end_time` + 120-min embargo: yes. CPCV: no (walk-forward instead) | Optional later: CPCV paths for the finalist only |
| Selection bias in Sharpe | Bailey & López de Prado, *The Deflated Sharpe Ratio* https://papers.ssrn.com/abstract=2460551 | A | Adjusts Sharpe for number of trials, non-normality | Not implemented | Yes, for the one finalist, using the true trial count (48 x settings tried) |
| Backtest overfitting | Bailey, Borwein, López de Prado, Zhu, *The Probability of Backtest Overfitting* https://papers.ssrn.com/abstract=2326253 | A | CSCV estimate of the chance the in-sample best underperforms out-of-sample | Not implemented | Consider after a 16-fold x few-spec matrix exists; needs many trials |
| Data snooping | White, *A Reality Check for Data Snooping*, Econometrica 2000 https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping | A | Bootstrap test of the best of many rules vs a benchmark | Not implemented (Bonferroni only) | Only if implemented correctly; SPA is the sharper variant |
| Superior predictive ability | Hansen, *A Test for Superior Predictive Ability*, JBES 2005 (aggregator page) https://scilit.com/publications/3acb201045eb64ffec5aeeb2043454cc | A (paper) | Studentised, robust to poor alternatives | No | Same as above |
| Multiple testing in finance | Harvey, Liu, Zhu, *...and the Cross-Section of Expected Returns*, RFS 2016 https://nber.org/papers/w20592 | A | Raise the bar (t above ~3) because hundreds of factors were tried | Bonferroni is directionally consistent, cruder | Use a high bar and count all trials |
| Crypto factors | Liu, Tsyvinski, Wu, *Common Risk Factors in Cryptocurrency*, J. Finance 2022 https://papers.ssrn.com/abstract=3379131 (also https://www.nber.org/papers/w25882.pdf) | A | Market, size and momentum factors explain the cross-section of coin returns | Horizons (15-120 min) and 5m bars differ from their weekly/daily setting; only cross-sectional framing is shared | Add simple momentum/reversal/size-liquidity baselines |
| ML in asset pricing | Gu, Kelly, Xiu, *Empirical Asset Pricing via Machine Learning*, RFS 2020 https://nber.org/papers/w25398 | A | Trees and neural nets beat linear models modestly under a strict out-of-sample protocol (re-check the exact magnitudes before quoting) | Pooled out-of-sample protocol similar; no portfolio-level R2 test | Report out-of-sample R2 vs zero (already in spirit) |
| Trees vs deep learning on tabular data | Grinsztajn, Oyallon, Varoquaux, NeurIPS 2022 https://arxiv.org/abs/2207.08815 | A/B | Tree ensembles remain strong on medium-sized tabular data | LightGBM primary: consistent | Do not add deep models before a baseline signal |
| LightGBM tuning | https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html | B | Large `min_data_in_leaf`, bounded `num_leaves`, regularisation against overfitting | `min_child_samples=100` is on the low side for this data | Sensitivity grid |
| Funding mechanics | Binance, *Introduction to Binance Futures Funding Rates* https://www.binance.com/en/support/faq/360033525031 ; settlement-frequency announcement https://www.binance.com/en/support/announcement/3243c81a35bd4f0c86a37315c3dc96cc | B (official) | Perpetual funding is paid at fixed intervals; intervals have changed per contract | Funding not modelled | Add funding cost for holds crossing a settlement |
| Fees | Binance futures fee schedule https://www.binance.com/support/faq/360033544231 | B | Maker/taker rates depend on VIP tier/BNB; verify current numbers | Model uses 4 bps taker per side (assumption) | Confirm against the actual venue (CoinSwitch fees NOT verified here) |
| Look-ahead tooling | Freqtrade lookahead analysis https://www.freqtrade.io/en/latest/lookahead-analysis | C (docs) | Compares signals computed on truncated vs full data to detect look-ahead | Not used | Cheap synthetic equivalent: recompute features on a truncated series and compare |
| Crypto ML forecasting study | PeerJ CS, *Evaluating machine learning models for predictive accuracy in cryptocurrency price forecasting* https://peerj.com/articles/cs-2626 | A/B | Model comparison for price forecasting | Different target/horizon; weak relevance | Background only |

**Where the literature disagrees / is thin.** Evidence that 15-120-minute crypto returns are
predictable *net of realistic costs* is limited and much of it is low-rigour; cross-sectional
crypto results are mostly daily-to-weekly. Treat any claim of intraday net edge as unproven (OPINION).

**X/Twitter.** Search returned no accessible, attributable posts, so nothing is claimed. **Reddit.**
Search returned aggregator snapshots of r/algotrading, not usable primary threads; classified D and
not used as evidence. **GitHub/open source.** Only Freqtrade's documentation was verified; Qlib, FinRL
and vectorbt were not.


---

# Independent literature assessment — 6 November 2026

**RESEARCH-SUPPORTED unless identified as recommendation or community observation.** Sources below
were retrieved in this audit, including official pages, author manuscripts, publisher abstracts and
research abstracts. This is a critical comparison, not a claim to have replicated their results.
Full-text access varies; an abstract is explicitly insufficient to verify an empirical backtest.
A = peer-reviewed publication/book or authoritative primary institution; B = preprint/official
software documentation; C = project/firm implementation; D = anecdote. Evidence level describes the
source, not whether its findings transfer to 5m USD-M futures.

## Foundational methods and their specific consequences

| Work / authors / year / direct source | Level and checked scope | Finding relevant here | Project comparison and limitation / proposed adoption |
| --- | --- | --- | --- |
| Marcos López de Prado, *Advances in Financial Machine Learning*, 2018, [Wiley](https://www.wiley.com/en-gb/advances-in-financial-machine-learning-p-9781119482109) | A, publisher contents verified; not a fresh cover-to-cover reading | Separates label overlap, embargo and combinatorial validation | Actual-end purging is appropriate. Current chronological boundary gap is not identical to post-test embargo in two-sided K-fold. Keep walk-forward; CPCV is optional robustness, not a compulsory replacement. |
| Bailey, Borwein, López de Prado, Zhu, *The Probability of Backtest Overfitting*, [author manuscript](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), published 2017 | A, manuscript abstract/method checked | CSCV diagnoses selection degradation among competing strategies | Need aligned candidate-return observations. Sixteen fold summaries alone do not justify a calibrated project PBO; do not confuse CSCV selection analysis with causal walk-forward deployment. |
| Bailey & López de Prado, *The Deflated Sharpe Ratio*, 2014, [author manuscript](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | A, manuscript conclusions checked | Adjusts Sharpe inference for selection and non-normality | Apply only after defining a common time-based return series and recording trials. The current per-trade Sharpe is inadequate input; DSR is not automatically a posterior probability of real edge. |
| Halbert White, *A Reality Check for Data Snooping*, 2000, [DOI 10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152) | A, publisher citation/abstract verified | Tests predictive superiority of the best searched alternative against a benchmark | Applicable to a registered candidate family with aligned loss/return differentials and dependence-aware resampling; not a correction applied to an isolated winning Sharpe. |
| Peter Reinhard Hansen, *A Test for Superior Predictive Ability*, 2005, [author SSRN abstract](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569) | A publication; author abstract checked | Studentization reduces the influence of irrelevant poor alternatives relative to Reality Check | Useful only when there is a candidate search worth testing. Not required to debug one smoke fit. |
| Harvey, Liu, Zhu, *…and the Cross-Section of Expected Returns*, 2014 working paper / 2016 publication, [NBER DOI 10.3386/w20592](https://www.nber.org/papers/w20592) | A, primary abstract | Conventional single-test significance is insufficient in a mined factor family | Register all experiments and research changes. Do not borrow a universal “t > 3” cutoff as a guarantee for this dependent panel. |
| Bergmeir, Hyndman, Koo, *A note on the validity of cross-validation for evaluating autoregressive time series prediction*, 2018, [author page and DOI](https://southwest.robjhyndman.com/publications/cv-time-series/) | A, author abstract and assumptions | Ordinary CV can be justified in a restricted autoregressive setup with uncorrelated errors | This is a useful counterpoint to blanket prohibitions. Those assumptions are not established for overlapping multi-asset labels; no reason to replace the current chronological evaluation. |
| Gneiting & Raftery, *Strictly Proper Scoring Rules, Prediction, and Estimation*, 2007, [author manuscript](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf) | A, manuscript sections checked | Forecast evaluation must match the forecast object and scoring rule | A continuous return estimate is not a probability. Probability calibration methods and Brier scores do not directly validate these regressors. Select a point-forecast loss deliberately; distributional calibration requires a distributional model. |
| Gama, Žliobaitė, Bifet, Pechenizkiy, Bouchachia, *A survey on concept drift adaptation*, 2014, [DOI 10.1145/2523813](https://doi.org/10.1145/2523813) | A, publisher abstract | Separates drift detection, adaptation and evaluation | Two-year rolling TRAIN is one adaptation choice, not proof of stationarity. Compare uniform and one predeclared decay only later; no evidence currently selects a half-life. |

## Empirical finance and crypto: evidence is mixed and horizons matter

| Work | Checked dataset / period / horizon / method | OOS and cost evidence actually verified | Relevance and limits |
| --- | --- | --- | --- |
| Liu & Tsyvinski, *Risks and Returns of Cryptocurrency*, 2018 working paper / 2021 RFS, [NBER DOI 10.3386/w24877](https://www.nber.org/papers/w24877) | BTC, XRP, ETH; early histories through 2018; momentum and attention analysis | Abstract establishes predictability claims, not a verified 15–120m executable strategy | Supports investigating crypto-specific structure; it does not establish an edge in current Binance perpetuals. No attention features are proposed for this frozen study. |
| Liu, Tsyvinski, Wu, *Common Risk Factors in Cryptocurrency*, 2019 working paper / 2022 JF, [NBER manuscript](https://www.nber.org/papers/w25882.pdf) | 1,707 coins, 2014–2018; weekly cross-sectional returns, market/size/momentum factors | Historical factor research; not independently reproduced here | Motivates factor and market baselines and retaining dead coins. Weekly broad-coin evidence cannot be imported as net intraday CORE20 alpha. |
| Gu, Kelly, Xiu, *Empirical Asset Pricing via Machine Learning*, 2018 working paper / 2020 RFS, [primary manuscript](https://www.nber.org/papers/w25398.pdf) | Equity asset-pricing comparison; nonlinear trees and neural nets | Abstract supports comparative ML results; its exact transaction-cost model was not revalidated | Motivation for nonlinear interactions and strong linear controls. Equity risk-premium results are not evidence for sub-hour crypto forecasting. |
| Cakici, Shahzad, Będowska-Sójka, Zaremba, *Machine learning and the cross-section of cryptocurrency returns*, 2024, [DOI 10.1016/j.irfa.2024.103244](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001765) | Cross-sectional crypto model comparison; publisher abstract/highlights checked | Authors report cost-resilient results concentrated in small, illiquid, volatile coins; full cost schedule/period not verified from paywalled text | Positive evidence with important implementability limits. Do not quote a net return number or assume their assets/horizons match CORE20. |
| Schmeling, Schrimpf, Todorov, *Crypto carry*, 2023, revised October 2025, [BIS WP1087](https://www.bis.org/publ/work1087.pdf) | BTC/ETH spot/futures basis across venues; economic carry analysis | Author paper and institution summary checked; not a short-horizon forecast replication | Basis reflects financing demand and constrained arbitrage. Funding/basis features are plausible context; carry evidence does not establish directional 60m alpha. |
| Puoti, Pittorino, Roveri, *Quantifying Cryptocurrency Unpredictability*, accepted AIMLSystems 2024 / arXiv 2025, [paper](https://arxiv.org/abs/2502.09079), [DOI](https://doi.org/10.1145/3703412.3703420) | LTC, BNB, BTC, ETH, XRP; univariate forecasting and complexity; exact periods not verified from abstract | Authors report naive models outperforming complex alternatives; cost-tested strategy not established | Negative evidence against assuming complexity helps. Univariate price-level forecasting differs from this panel return problem, so it is not proof that all alpha is impossible. |
| Bysik & Ślepaczuk, *Machine Learning-Based Bitcoin Trading Under Transaction Costs: Evidence From Walk-Forward Forecasting*, 2026, [arXiv:2606.00060](https://arxiv.org/abs/2606.00060) | About 70k hourly BTC-USDT rows, 2018–2026, 27 walk-forward folds; XGBoost/LSTM/iTransformer | Abstract: naive sign rules fail at 10 bps; selected cost-filtered variants improve; bootstrap does not establish formal model dominance | Closest retrieved horizon/cost comparison, but a preprint with selected configurations. Supports testing decision conversion, not inheriting a claimed return or approving this model. |
| Frazzini, Israel, Moskowitz, *Trading Costs of Asset Pricing Anomalies*, 2012, [AQR primary paper page](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies) | Institutional equity trades, 19 developed markets, 1998–2011 | Measured execution costs rather than a universal flat penalty | Credible practitioner evidence for measuring impact/capacity. Equity estimates must not supply numeric crypto slippage. |

**INFERENCE:** Positive factor findings and negative forecasting findings can coexist because they
study different targets, assets, horizons and implementability constraints. No verified source
above estimates the probability of a durable net edge for this exact 109-feature, CORE20, 60m model.
No numeric prior of 10–20% is justified by this audit; the earlier preserved opinion is withdrawn
from the independent conclusions.

## Modern model comparison

Grinsztajn, Oyallon & Varoquaux (2022) find strong tree performance on their medium-sized tabular
benchmark ([paper](https://arxiv.org/abs/2207.08815)); Gorishniy, Rubachev, Khrulkov & Babenko
(2021) find no universally dominant family and establish strong neural baselines
([paper](https://arxiv.org/abs/2106.11959)). Neither benchmark is this dependent 50M-row panel.
**OPINION/RECOMMENDATION:** retain LightGBM and Ridge; neither “trees always win” nor “newer wins” is
an adequate selection argument.

Sequence-model sources verified for scope, not for crypto edge: Nie et al., PatchTST (ICLR 2023,
[arXiv:2211.14730](https://arxiv.org/abs/2211.14730)); Wu et al., TimesNet (ICLR 2023,
[arXiv:2210.02186](https://arxiv.org/abs/2210.02186)); Challu et al., N-HiTS (2022 preprint,
[arXiv:2201.12886](https://arxiv.org/abs/2201.12886)); Lim et al., TFT (2021,
[DOI](https://doi.org/10.1016/j.ijforecast.2021.03.012)). Their architectural forecasting results do
not resolve this project's selection or execution weaknesses. See the main report's model table
for proposed research priority and risks.

Hollmann et al., *Accurate predictions on small data with a tabular foundation model* (Nature,
2025, [DOI](https://doi.org/10.1038/s41586-024-08328-6)) evaluates a different scale from the current
full panel. The retrieved 2026 [TabPFN-3.5 technical report](https://arxiv.org/abs/2609.17895) expands
beyond the earlier small-table setting, including temporal/grouped benchmarks. **Recommendation:**
do not reject TabPFN using obsolete universal size claims, but do not substitute an unprofiled
foundation model without identical-row evidence, pretraining provenance and resource qualification.

## Official implementation and exchange sources

| Source | What was verified / project consequence |
| --- | --- |
| [LightGBM 4.7 estimator API](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html) | Defaults and wrapper parameter names; effective audit table in the training companion. |
| [LightGBM parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html) and [FAQ](https://lightgbm.readthedocs.io/en/latest/FAQ.html) | CPU deterministic controls and GPU numerical caveats. CPU remains the reference; equal seed is insufficient qualification. |
| [LightGBM early stopping](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.early_stopping.html) | Training eval set is ignored for stopping; first metric controls selection when configured. |
| [scikit-learn metrics](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics) | Regression score definitions are descriptive, not significance tests. |
| [scikit-learn persistence](https://scikit-learn.org/stable/model_persistence.html) | Pickle/joblib trusted-source restrictions; local hashes are not authentication. |
| [Binance official market-data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | Official old funding URL redirected to consolidated API. Contract endpoints and historical funding records are authoritative sources, not local assumptions. |
| [Binance public-data repository](https://github.com/binance/binance-public-data) | Official archive/checksum workflow; local implementation keeps source-domain identities separate. |
| [Binance funding explanation](https://www.binance.com/en/support/faq/detail/360033525031) | Funding applies to open positions at settlement; contract intervals can change, including hourly settlement. A universal 8h assumption is unsafe. |
| [Binance futures fees](https://www.binance.com/en/fee/futureFee) | Public page retrieved but numeric table returned “No records found”. Current maker/taker rates, discounts and owner tier remain UNKNOWN; 4 bps/side is an assumption, not a verified current account rate. No account access was attempted. |
| [RunPod storage](https://docs.runpod.io/pods/storage/types) | Container disk is ephemeral; a pod volume survives stops but not termination; network volumes are independent. Test actual mount semantics before trusting local POSIX lock behavior. |

CoinSwitch is deprecated by the repository's canonical-venue decision. Its fee/tax/account terms
were not researched as a dependency of Binance research; no CoinSwitch rate is silently imported.
No personal tax conclusion or account-specific fee claim is made.

## Open-source and practitioner comparison

| Primary project | Scope actually inspected | Appropriate lesson (OPINION/RECOMMENDATION) |
| --- | --- | --- |
| [Microsoft Qlib](https://github.com/microsoft/qlib) | README workflow/model/backtest structure, not full source security audit | Keep dataset/processor/experiment boundaries explicit. Do not import its equity calendars or copy example splits without label purging. |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | README research/RL structure | It is a different decision/environment formulation. An RL environment adds reward/execution-model degrees of freedom; it does not fix current validation. |
| [vectorbt](https://vectorbt.dev/api/portfolio/base/) | Portfolio simulation API including orders/fees/slippage | Distinguish signal arrays from cash-constrained portfolio accounting. Fast parameter grids can expand trial counts; speed is not validity. |
| [Backtrader slippage](https://www.backtrader.com/docu/slippage/slippage/) | Broker fill/slippage documentation | Specify when open/high/low matching and slippage allow a fill; a bar open is not a guaranteed executable price. |
| [Freqtrade lookahead-analysis source docs](https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md) | Full retrieved analysis explanation/caveats | Perturb/truncate data and compare observable features. A single-pair test may be inappropriate for cross-sectional features; preserve the known universe in project tests. |
| [FreqAI JOSS paper](https://joss.theoj.org/papers/10.21105/joss.04864.pdf) | Published architecture description | Separate data preparation, fitting and adaptive lifecycle. This is engineering precedent, not independent proof of profitable models. |

## X and Reddit

**PRACTITIONER-OBSERVATION / Level D:** X searches did not produce attributable technical posts.
Opening [López de Prado's public profile](https://x.com/lopezdeprado) returned HTTP 403. No tweet,
quotation or alleged consensus is used.

Public Reddit threads were retrievable: [walk-forward in practice](https://www.reddit.com/r/quant/comments/13q4qkk),
[CV disagreement](https://www.reddit.com/r/quant/comments/1701fzi), and
[slippage estimation](https://www.reddit.com/r/algotrading/comments/11dvm8j).
The observations concern validation choices and venue-dependent execution uncertainty. They are
anecdotal, unaudited accounts, not support for scientific validity or numerical cost estimates.
The independent review uses primary research above for all technical conclusions.
