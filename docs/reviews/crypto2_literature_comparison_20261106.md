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
