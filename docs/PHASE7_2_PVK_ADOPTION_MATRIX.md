# Phase 7.2 P1/PVK adoption matrix

This matrix reviews two local research inputs dated 2026-08-28:
`P1 Model Technology Research Report` and its independent `Technical Review`.
They are architecture recommendations, not evidence that any challenger has
alpha in this repository. `Implement now` means a disabled contract or pure
utility may be checked in. `Activate now` means participation in the first
Phase 7 cloud baseline; every row is `NO` unless it is already part of that
approved baseline.

| Idea | Value | Evidence | Cost | Leakage Risk | Implement Now? | Activate Now? | Phase |
|---|---|---|---|---|---|---|---|
| 1-minute canonical data layer | A common fine grid can resolve intrabar behavior and support later context. It does not prove 1m training is superior. | Both reports strongly support canonical 1m data while separating data resolution from model resolution. | Medium storage and validation; high if scaled blindly. | Medium: partial bars, gaps and late rows. | ADOPT NOW as `canonical_market_1m_v1` schema and pure aggregation. | NO | 7.2 foundation; pilot after baseline |
| Causal multi-resolution features | Adds short context without multiplying 5m model rows. | Reports support completed-window pooling and explicit availability masks. | Low for a BTC/ETH pilot; high across all history/symbols. | High if incomplete windows or independently fetched bars are mixed. | PREPARE NOW as disabled `micro_1m_context_v1`. | NO | Post-baseline experiment 4 |
| LightGBM/CatBoost/XGBoost tree baselines | Strong tabular controls reduce the risk of attributing feature value to model complexity. | Both reports rate boosted trees as mandatory controls; this repository already uses LightGBM. | Low/medium. | Low when rows/folds are matched; high if a challenger gets extra coverage. | ADOPT current LightGBM; PREPARE matched CatBoost/XGBoost adapter contracts. | LightGBM only | Experiments 1–3 |
| Competing-risk UP/DOWN/NO-HIT targets | Coherent event competition and time-to-event can avoid contradictory horizon probabilities. | The reports identify this as the highest-value target hypothesis; transfer evidence is conceptual, not local profitability evidence. | Medium label/evaluation work. | High: barrier selection, future volatility and intrabar order. | PREPARE NOW as separate `competing_risk_targets_v1`; add coherence utilities. | NO | Post-baseline experiment 6 |
| MFE/MAE distributions | Describes favorable/adverse path magnitude beyond direction. | Strong recommendation; Phase 6 already contains isolated descriptive MFE/MAE research. | Medium. | Medium: overlapping paths and ambiguous bars. | PREPARE in competing-risk contract; retain existing Phase 6 isolation. | NO | Target challenger research |
| Cross-sectional ranking objectives | Answers which contemporaneously eligible asset is strongest. | Both reports strongly recommend direct ranking and warn about flat per-series forecasts. | Low for tree ranker; medium for panel neural head. | Critical if eventual or acquisition-union membership enters groups. | PREPARE NOW as `cross_asset_ranking_v1` grouped only by `feature_time` and `fold_active_symbols`. | NO | Post-baseline experiment 5 |
| OOD detection | Exposes feature extremes, unseen assets, young listings and degraded inputs. | Reports support interpretable OOD as one safety signal, not a regime-change solution. | Low. | Medium if fitted globally or treated as calibrated certainty. | ADOPT NOW as TRAIN-fitted robust monitor-only baseline. | NO | Independent diagnostic |
| Probability calibration | Proper probabilities matter more than raw accuracy for later decisions. | Mature calibration evidence and existing repository Cal-A/Cal-B ownership. | Low. | High if fitted on TRAIN/TEST or mixed with policy selection. | PREPARE common isotonic/Platt/temperature plan while retaining Cal-A vs Cal-B separation. | NO new calibrator | After probabilistic challenger exists |
| Conformal uncertainty | Can measure rolling empirical coverage and interval width. | Credible time-series research, but exchangeability is weak under drift. | Low/medium. | Medium if coverage is presented as timeless or guaranteed. | PREPARE interface and experiment criteria only. | NO | After calibrated distributions |
| Prospective OI collection | OI cannot legitimately be expanded into six years of history. | Binance retention limitations and both reports support forward-only capture. Existing collector is guarded, restart-safe and checksummed. | Low at 5m snapshots. | Critical if short forward history is blended with long historical training. | ADOPT existing forward-only collector and configurable frozen-universe symbol policy. | NO collection started; NO training | Future explicit prospective task |
| BBO/spread/depth/liquidation capture | Supports later tradability and microstructure studies with data that cannot be reconstructed reliably. | Reports recommend prospective capture, with summaries before raw L2. | Low for BBO/events, medium for summaries, extreme for raw L2. | High: sequence gaps, receive-time errors and fabricated backfill. | PREPARE versioned schemas and disabled capture specifications. | NO | Future prospective capture |
| Historical exchange metadata | Reduces survivorship and rule-history errors. | Both reports strongly support effective-time and availability-time metadata. | Medium archival effort. | High if current filters are backfilled historically. | ADOPT NOW as `exchange_symbol_metadata_v1` contract only. | NO collector | Future metadata archive |
| News/EventContext late fusion | May help event slices without making numerical prediction depend on unreliable historical text. | Reports strongly support separation; incremental alpha evidence is weak. | Medium/high licensing, deduplication and timestamp cost. | Critical publication/revision/retrospective-tag leakage. | PREPARE `event_context_v1` schema only. | NO | Phase 8+ optional sidecar |
| Neural cross-asset modeling | Could learn conditional market/peer effects across a changing universe. | MASTER/Set Transformer ideas are relevant but not locally validated. | High. | High peer contamination, masks and capacity overfit. | TEST AFTER PHASE 7 BASELINE; schema compatibility only now. | NO | Phase 8+ |
| Microstructure specialist | Could add orthogonal short-horizon information if prospective book/event data prove reliable. | Evidence transfers from other venues/tasks only indirectly. | High data and execution-model cost. | High sequence, queue, latency and selection bias. | PREPARE data contracts only. | NO | Phase 8+ specialist |
| Dense Transformer | Credible temporal/cross-asset challenger, not an assumed winner. | Reports recommend a 75–150M candidate but emphasize strong tree controls. | High GPU/trial cost. | High overlap and regime memorization. | PHASE 8+; do not implement now. | NO | Phase 8 |
| PatchTST-style patches | Efficient way to encode local windows, but channel independence is not the final cross-asset answer. | Mature generic forecasting evidence; task transfer is unproven. | Medium. | Medium boundary/partial-patch errors. | PREPARE compatible axes only. | NO | Phase 8 ablation |
| Set Transformer / MASTER ideas | Naturally handle changing eligible sets and cross-asset context. | Strong architecture fit, limited direct crypto-perpetual evidence. | Medium. | High if masks include future or ineligible assets. | PREPARE eligibility mask contract only. | NO | Phase 8 ablation |
| Model scaling | A scaling curve can test whether capacity pays; raw asset-minute count is not independent sample size. | Reports explicitly warn against assuming bigger is better. | Very high beyond tree/compact controls. | High trial multiplicity and memorization. | REJECT NOW. Predeclare stopping rules only. | NO | Phase 8+ only after signal proof |
| Ensemble/stacking | Diverse residuals may improve uncertainty and performance after individual models prove value. | Tree + neural stacking is conditionally supported; deep meta-models are not. | 2–5× model cost. | High if stacker inputs are not strictly OOF. | TEST AFTER each component independently qualifies; shallow OOF combiner only. | NO | Late Phase 8+ |

## Decision summary

- **ADOPT NOW:** versioned point-in-time schemas, strict 1m aggregation,
  fold-active ranking groups, interpretable TRAIN-fitted OOD, matched-comparison
  identity, trial declarations and prospective capture contracts.
- **PREPARE NOW / TEST LATER:** micro 1m context, competing risks, calibration,
  conformal coverage, CatBoost/XGBoost, OI/BBO/depth/liquidation capture and
  exchange metadata.
- **TEST AFTER PHASE 7 BASELINE:** all challenger training and every claim of
  incremental OOS value.
- **PHASE 8+:** neural temporal/cross-asset models, specialists, late fusion and
  stacking.
- **REJECT / NOT JUSTIFIED NOW:** full-universe 1m training, raw L2 at scale,
  MoE, very large models, automatic online learning, deep meta-models and any
  architecture chosen because it is fashionable.
