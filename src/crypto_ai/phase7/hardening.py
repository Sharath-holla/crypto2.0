"""Phase 7B hardening helpers (written by Claude, 2026-11-02; additive, config-driven).

Everything here is opt-in or purely additive: defaults keep the existing training behaviour,
and no function reads TEST rows for selection. Settings live in this module's
``HardeningConfig`` (optionally overridden by a TOML file named by ``PHASE7_HARDENING_CONFIG``)
rather than in the frozen Phase 7 config, because new keys there would change the frozen config
hash and invalidate every prepared cache.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.result_integrity import (
    DESCRIPTIVE_ONLY,
    DEVELOPMENT_METRIC,
    NOT_APPLICABLE,
    NOT_INDEPENDENT,
    SELECTION_METRIC,
    reject_duplicates,
    validate_result_set,
)
from crypto_ai.phase7.selection_chronology import DESCRIPTIVE_RANKING

CONFIG_ENV = "PHASE7_HARDENING_CONFIG"
RESULTS_FILENAME = "phase7b_results.csv"


class FitAbortedError(RuntimeError):
    """A fit was stopped by a configured abort rule (validation worse than the zero baseline)."""


@dataclass(frozen=True)
class HardeningConfig:
    # live console
    console_table: bool = True  # one-line table every PHASE7_METRICS_EVERY rounds
    console_precision_recall: bool = True  # fixed-threshold, validation-only precision/recall
    fixed_threshold_bps: float = 5.0  # |move| in bps that counts as a signal / a real move
    metric_max_rows: int = 1_000_000  # strided subsample cap for the live P/R computation
    # baselines
    baseline_ridge_alpha: float = 1.0
    baseline_max_rows: int = 500_000  # strided subsample of TRAIN rows for the Ridge baseline
    # abort rules (all OFF by default)
    abort_after_worse_checks: int = 0  # N consecutive checks with val RMSE > zero baseline; 0=off
    stop_file_name: str = "STOP_PHASE7"  # create this file in the run directory to stop cleanly
    fold_gate_folds: int = 0  # after folds 1..N stop if no spec beats the baseline; 0=off
    # pilot mode (both must be set to take effect)
    pilot_horizon_minutes: int = 0
    pilot_target_type: str = ""
    # success criteria, written down BEFORE training (placeholders: the owner must confirm)
    success_min_net_positive_folds: int = 10  # of the 16 folds
    success_min_beats_baseline_folds: int = 10
    success_alpha: float = 0.05
    multiple_testing_correction: str = "bonferroni"


def load_hardening_config(path: Path | None = None) -> HardeningConfig:
    """Defaults, optionally overridden by a TOML file (unknown keys are rejected)."""

    chosen = path or (Path(os.environ[CONFIG_ENV]) if os.environ.get(CONFIG_ENV) else None)
    if chosen is None:
        return HardeningConfig()
    data = tomllib.loads(Path(chosen).read_text(encoding="utf-8"))
    data = data.get("hardening", data)
    known = {item.name for item in fields(HardeningConfig)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(f"unknown hardening config keys: {unknown}")
    return HardeningConfig(**data)


@lru_cache(maxsize=1)
def _cached_config(env_value: str | None) -> HardeningConfig:
    return load_hardening_config()


def current_config() -> HardeningConfig:
    """Config for the running process (cached per value of PHASE7_HARDENING_CONFIG)."""

    return _cached_config(os.environ.get(CONFIG_ENV))


# ---------------------------------------------------------------- live metrics (train/val only)
def _stride(count: int, limit: int) -> int:
    return max(1, math.ceil(count / max(1, limit)))


def fixed_threshold_precision_recall(
    actual: np.ndarray, predicted: np.ndarray, threshold_bps: float, *, max_rows: int = 1_000_000
) -> dict[str, float | int | None]:
    """Fixed-threshold, validation/train diagnostics (NOT the Cal-B trading policy).

    A *signal* is |prediction| >= threshold; a *real move* is |actual| >= threshold. A signal is a
    true positive when the predicted sign matches the actual sign on a real move.
    """

    step = _stride(len(actual), max_rows)
    a = np.asarray(actual, dtype=np.float64)[::step]
    p = np.asarray(predicted, dtype=np.float64)[::step]
    limit = threshold_bps / 10_000.0
    signal = np.abs(p) >= limit
    move = np.abs(a) >= limit
    hit = signal & move & (np.sign(p) == np.sign(a))
    signals, moves, hits = int(signal.sum()), int(move.sum()), int(hit.sum())
    precision = hits / signals if signals else None
    recall = hits / moves if moves else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "signals": signals,
        "real_moves": moves,
        "true_positives": hits,
        "row_stride": step,
    }


_LATEST_FIT: dict[str, Any] = {}


def record_latest_fit(snapshot: Mapping[str, Any]) -> None:
    _LATEST_FIT.clear()
    _LATEST_FIT.update(snapshot)


def latest_fit_snapshot() -> dict[str, Any]:
    """Last validation metrics seen by the live observer (used by the heartbeat line)."""

    return dict(_LATEST_FIT)


def trend_flag(previous: float | None, current: float, *, tolerance: float = 0.001) -> str:
    """'↓ better' / '↑ worse' / '= flat' for an error metric (lower is better)."""

    if previous is None or previous == 0:
        return "= flat"
    change = (current - previous) / abs(previous)
    if change < -tolerance:
        return "↓ better"
    if change > tolerance:
        return "↑ worse"
    return "= flat"


def _short(value: Any) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    return f"{value:.2e}" if abs(value) < 1e-2 and value != 0 else f"{value:.4f}"


def process_stats(path: str = ".") -> str:
    """Peak process RSS and free disk for the console line (best effort, never raises)."""

    # CHANGED BY CLAUDE (2026-11-06, final hardening): monitoring extras requested by the owner.
    try:
        import resource
        import shutil
        import sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is bytes on macOS and KiB on Linux.
        rss_gib = peak / (1024**3 if sys.platform == "darwin" else 1024**2)
        free_gib = shutil.disk_usage(path).free / 1024**3
        return f"peak RSS {rss_gib:.1f} GiB | free disk {free_gib:.0f} GiB"
    except Exception:  # monitoring must never break a fit
        return "RSS/disk n/a"


def console_line(
    label: str,
    iteration: int,
    round_limit: int,
    metrics: Mapping[str, Mapping[str, float]],
    flag: str,
    extra: str = "",
) -> str:
    train, val = metrics.get("train", {}), metrics.get("validation", {})
    # CHANGED BY CLAUDE (2026-11-06): optional ``extra`` suffix (best val RMSE, rounds since
    # improvement, elapsed, RSS, disk). Old behaviour is unchanged when ``extra`` is empty.
    return (
        f"[fit {label}] round {iteration:>4}/{round_limit} | "
        f"train L2 {_short(train.get('l2'))} MAE {_short(train.get('mae'))} "
        f"RMSE {_short(train.get('rmse'))} | "
        f"val L2 {_short(val.get('l2'))} MAE {_short(val.get('mae'))} "
        f"RMSE {_short(val.get('rmse'))} dir {_short(val.get('directional_accuracy'))} "
        f"P {_short(val.get('fixed_precision'))} R {_short(val.get('fixed_recall'))} "
        f"(fixed-threshold, validation only) | val RMSE {flag}" + (f" | {extra}" if extra else "")
    )


# ---------------------------------------------------------------- baselines (validation only)
def _ridge_predict(
    train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray, *, alpha: float, max_rows: int
) -> np.ndarray:
    step = _stride(len(train_y), max_rows)
    x = np.asarray(train_x[::step], dtype=np.float64)
    y = np.asarray(train_y[::step], dtype=np.float64)
    # CHANGED BY CLAUDE (2026-11-05, Phase 7C finding N-01): the original used plain mean/std, so
    # ONE NaN
    # feature made every weight NaN and the Ridge baseline score NaN. Missing values are now ignored
    # when standardising and then set to 0 (= the training mean). Clean data gives the same result.
    # OLD CODE (kept for the record):
    #   mean, scale = x.mean(axis=0), x.std(axis=0)
    #   scale[scale == 0] = 1.0
    #   z = (x - mean) / scale
    finite_x = np.isfinite(x)
    counts = np.maximum(finite_x.sum(axis=0), 1)
    safe_x = np.where(finite_x, x, 0.0)
    mean = safe_x.sum(axis=0) / counts
    variance = (np.where(finite_x, x - mean, 0.0) ** 2).sum(axis=0) / counts
    scale = np.sqrt(variance)
    scale[scale == 0] = 1.0
    z = np.where(finite_x, (x - mean) / scale, 0.0)
    keep = np.isfinite(y)
    z, y = z[keep], y[keep]
    y_mean = y.mean()
    gram = z.T @ z + alpha * np.eye(z.shape[1])
    weights = np.linalg.solve(gram, z.T @ (y - y_mean))
    test = np.asarray(test_x, dtype=np.float64)
    test_z = np.where(np.isfinite(test), (test - mean) / scale, 0.0)
    return test_z @ weights + y_mean


def _delta(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else float(left) - float(right)


def _errors(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    residual = predicted - actual
    return float(np.mean(np.abs(residual))), float(np.sqrt(np.mean(residual * residual)))


# CHANGED BY CLAUDE (2026-11-06, closure): cross-sectional IC and a no-information baseline.
XS_IC_MIN_SYMBOLS = 5  # a per-timestamp rank correlation over fewer symbols is noise


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    sorted_values = values[order]
    start = 0
    while start < len(values):
        stop = start
        while stop + 1 < len(values) and sorted_values[stop + 1] == sorted_values[start]:
            stop += 1
        ranks[order[start : stop + 1]] = (start + stop) / 2.0 + 1.0
        start = stop + 1
    return ranks


def cross_sectional_ic(
    times: np.ndarray,
    predicted: np.ndarray,
    actual: np.ndarray,
    *,
    min_symbols: int = XS_IC_MIN_SYMBOLS,
) -> dict[str, Any]:
    """Mean per-timestamp Spearman IC between predictions and realised targets.

    Each timestamp is ranked on its own (only rows sharing a timestamp are compared), so
    time-series level or trend cannot contribute. Timestamps with fewer than ``min_symbols`` rows
    or a constant side are skipped and counted.
    """

    t = np.asarray(times).astype(np.int64)
    p = np.asarray(predicted, dtype=np.float64)
    a = np.asarray(actual, dtype=np.float64)
    if not (len(t) == len(p) == len(a)):
        raise ValueError("cross-sectional IC inputs must be aligned")
    order = np.argsort(t, kind="mergesort")
    t, p, a = t[order], p[order], a[order]
    boundaries = np.flatnonzero(np.diff(t)) + 1
    values: list[float] = []
    skipped = 0
    for rows in np.split(np.arange(len(t)), boundaries):
        if len(rows) < min_symbols:
            skipped += 1
            continue
        rp, ra = _average_ranks(p[rows]), _average_ranks(a[rows])
        if np.ptp(rp) == 0 or np.ptp(ra) == 0:
            skipped += 1
            continue
        values.append(float(np.corrcoef(rp, ra)[0, 1]))
    return {
        "mean_xs_spearman_ic": float(np.mean(values)) if values else None,
        "std_xs_spearman_ic": float(np.std(values, ddof=1)) if len(values) > 1 else None,
        "timestamps_scored": len(values),
        "timestamps_skipped": skipped,
        "min_symbols": min_symbols,
    }


def score_baselines(
    train_x: np.ndarray,
    train_y: np.ndarray,
    validation_x: np.ndarray,
    validation_y: np.ndarray,
    model_validation_predictions: np.ndarray,
    covered: np.ndarray,
    *,
    config: HardeningConfig | None = None,
    validation_times: np.ndarray | None = None,
) -> dict[str, Any]:
    """Score zero-return, TRAIN-mean, Ridge and the model on the SAME covered validation rows.

    ``validation_times`` (aligned with ``validation_y``) enables the cross-sectional IC.
    """

    cfg = config or current_config()
    mask = np.asarray(covered, dtype=bool)
    y = np.asarray(validation_y, dtype=np.float64)[mask]
    model = np.asarray(model_validation_predictions, dtype=np.float64)[mask]
    zero_mae, zero_rmse = _errors(y, np.zeros_like(y))
    model_mae, model_rmse = _errors(y, model)
    result: dict[str, Any] = {
        # CHANGED BY CLAUDE (2026-11-06, IA-16): contract = same eligible rows, same target, same
        # fold, same validation role for model, zero and Ridge; Ridge sees TRAIN features only.
        # Metric class: DEVELOPMENT_METRIC (descriptive baseline, not a selection baseline).
        "baseline_contract_version": BASELINE_CONTRACT_VERSION,
        "metric_class": DEVELOPMENT_METRIC,
        "scope": "VALIDATION_ONLY",
        "validation_rows_scored": int(mask.sum()),
        "zero_return": {"mae": zero_mae, "rmse": zero_rmse},
        "lightgbm": {"mae": model_mae, "rmse": model_rmse},
        "lightgbm_skill_vs_zero": (1.0 - model_rmse / zero_rmse) if zero_rmse > 0 else None,
        "lightgbm_beats_zero": bool(model_rmse < zero_rmse),
    }
    # CHANGED BY CLAUDE (2026-11-06, final hardening): the same VALIDATION rows are also scored with
    # directional accuracy (non-zero actuals), Pearson and Spearman for the model (and Ridge below),
    # plus deltas vs each baseline. Cross-sectional IC needs timestamps and is NOT computed here.
    from crypto_ai.research.metrics import regression_metrics

    keep = ("mae", "rmse", "directional_accuracy_nonzero", "pearson_ic", "spearman_ic")
    full_model = regression_metrics(y, model)
    result["lightgbm"].update({name: full_model.get(name) for name in keep[2:]})
    result["zero_return"]["directional_accuracy_nonzero"] = None  # a constant 0 has no direction
    result["zero_return"]["pearson_ic"] = None
    result["zero_return"]["spearman_ic"] = None
    result["delta_vs_zero"] = {
        "mae": model_mae - zero_mae,  # negative = model better
        "rmse": model_rmse - zero_rmse,
    }
    # CHANGED BY CLAUDE (2026-11-06, closure): no-information TRAIN-mean baseline (constant, same
    # rows, TRAIN targets only - no information beyond what the model already receives).
    finite_train = np.asarray(train_y, dtype=np.float64)
    finite_train = finite_train[np.isfinite(finite_train)]
    if len(finite_train):
        mean_mae, mean_rmse = _errors(y, np.full_like(y, float(finite_train.mean())))
        result["train_mean"] = {"mae": mean_mae, "rmse": mean_rmse}
        result["lightgbm_beats_train_mean"] = bool(model_rmse < mean_rmse)
    xs_times = None
    if validation_times is not None:
        xs_times = np.asarray(validation_times)
        if len(xs_times) != len(validation_y):
            raise ValueError("validation_times must align with validation_y")
        xs_times = xs_times[mask]
        result["lightgbm"]["cross_sectional_ic"] = cross_sectional_ic(xs_times, model, y)
    else:
        result["lightgbm"]["cross_sectional_ic"] = {"status": "NOT_COMPUTED_NO_TIMESTAMPS"}
    if len(validation_x) == len(validation_y) and len(train_x) == len(train_y) and len(train_y):
        ridge = _ridge_predict(
            train_x,
            train_y,
            np.asarray(validation_x)[mask],
            alpha=cfg.baseline_ridge_alpha,
            max_rows=cfg.baseline_max_rows,
        )
        ridge_mae, ridge_rmse = _errors(y, ridge)
        result["ridge"] = {"mae": ridge_mae, "rmse": ridge_rmse, "alpha": cfg.baseline_ridge_alpha}
        full_ridge = regression_metrics(y, ridge)
        result["ridge"].update({name: full_ridge.get(name) for name in keep[2:]})
        result["delta_vs_ridge"] = {
            "mae": model_mae - ridge_mae,
            "rmse": model_rmse - ridge_rmse,
            "directional_accuracy_nonzero": _delta(
                result["lightgbm"].get("directional_accuracy_nonzero"),
                full_ridge.get("directional_accuracy_nonzero"),
            ),
            "spearman_ic": _delta(
                result["lightgbm"].get("spearman_ic"), full_ridge.get("spearman_ic")
            ),
        }
        result["lightgbm_beats_ridge"] = bool(model_rmse < ridge_rmse)
        if xs_times is not None:
            result["ridge"]["cross_sectional_ic"] = cross_sectional_ic(xs_times, ridge, y)
    else:
        result["ridge"] = {"status": "SKIPPED_MISALIGNED_OR_EMPTY"}
        result["lightgbm_beats_ridge"] = None
    return result


# ---------------------------------------------------------------- decision + trading metrics
def _side_scores(signal: np.ndarray, positive: np.ndarray) -> dict[str, Any]:
    tp = int((signal & positive).sum())
    fp = int((signal & ~positive).sum())
    fn = int((~signal & positive).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return {
        "signals": tp + fp,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def decision_metrics(
    symbols: Sequence[str],
    actual: np.ndarray,
    predicted: np.ndarray,
    *,
    threshold_bps_by_symbol: Mapping[str, float | None],
    cost_bps_by_symbol: Mapping[str, float],
) -> dict[str, Any]:
    """LONG / SHORT / NO_TRADE signals from Cal-B thresholds, scored per side.

    A LONG signal fires when predicted return * 1e4 >= round-trip cost + the Cal-B threshold
    (SHORT mirrors it). A LONG is *correct* (positive) when the actual return beat the cost.
    Signals are counted BEFORE the non-overlap execution filter, so they are signal-level, not
    trade-level, scores. Thresholds come from Cal-B only; nothing here is tuned on TEST.
    """

    names = np.asarray([str(item) for item in symbols], dtype=object)
    a = np.asarray(actual, dtype=np.float64)
    p = np.asarray(predicted, dtype=np.float64)
    finite = np.isfinite(a) & np.isfinite(p)
    hurdle = np.full(len(a), np.inf)
    cost = np.zeros(len(a))
    for symbol in set(names.tolist()):
        picked = names == symbol
        threshold = threshold_bps_by_symbol.get(symbol)
        cost[picked] = float(cost_bps_by_symbol[symbol])
        if threshold is not None:
            hurdle[picked] = cost[picked] + float(threshold)
    long_signal = finite & (p * 10_000 >= hurdle)
    short_signal = finite & (-p * 10_000 >= hurdle)
    long_positive = finite & (a * 10_000 > cost)
    short_positive = finite & (-a * 10_000 > cost)
    return {
        "scope": "TEST_SIGNAL_LEVEL_FROZEN_CAL_B_THRESHOLDS",
        "rows": int(finite.sum()),
        "long": _side_scores(long_signal, long_positive),
        "short": _side_scores(short_signal, short_positive),
        "no_trade_signals": int((finite & ~long_signal & ~short_signal).sum()),
    }


# CHANGED BY CLAUDE (2026-11-06, closure): the economic-status contract. Nothing produced by the
# current pipeline may be read as tradable profitability: funding is not modelled, costs are static
# scenarios (not measured slippage), entries use a reference price, and no equity curve exists.
ECONOMIC_STATUS: dict[str, str] = {
    "metric_scope": "TRADE_LEVEL_PROXY_NOT_PORTFOLIO",
    "portfolio_sharpe": "NOT_AVAILABLE",
    "portfolio_max_drawdown": "NOT_AVAILABLE",
    "portfolio_calmar": "NOT_AVAILABLE",
    "funding_model_status": "NOT_MODELLED",
    "cost_model_label": "STATIC_COST_STRESS",
    "entry_price_label": "REFERENCE_EXECUTION_PRICE",
    "economic_status": "REGRESSION_PLUMBING_ONLY_NO_TRADABILITY_CLAIM",
}


def require_no_tradability_claim(payload: Mapping[str, Any]) -> None:
    """Fail qualification if a payload claims profitability while funding is NOT_MODELLED."""

    claims = [
        key
        for key in ("tradable_profitability", "profitability_confirmed", "edge_confirmed")
        if payload.get(key) not in (None, False, "NOT_CLAIMED")
    ]
    if claims and payload.get("funding_model_status", "NOT_MODELLED") == "NOT_MODELLED":
        raise ValueError(f"TRADABILITY_CLAIM_WITHOUT_FUNDING_MODEL: {claims}")


def trading_metrics(
    trades: pa.Table, tier_costs: Mapping[str, Mapping[str, float]]
) -> dict[str, Any]:
    """Profit factor, per-trade Sharpe, max drawdown and cost split from the trades table.

    Fees and slippage ARE applied inside ``net_return`` (via ``base_cost_bps``). Funding is NOT
    modelled anywhere in the pipeline, so it is reported as NOT_MODELLED rather than invented.
    ``tier_costs[tier]`` = {"fee_bps": ..., "spread_bps": ..., "slippage_bps": ...} round trip.
    Sharpe is the per-trade mean/std (not annualized); drawdown is on cumulative additive net
    return ordered by exit time.
    """

    empty = {
        "trades": 0,
        "win_rate": None,
        "net_return_sum": 0.0,
        "expectancy": None,
        "profit_factor": None,
        "sharpe_per_trade": None,
        # CHANGED BY CLAUDE (2026-11-06, closure): was "max_drawdown". A drawdown of the
        # cumulative sum of independent trade returns is NOT a portfolio drawdown.
        "trade_drawdown_proxy": None,
        "fees_return_sum": 0.0,
        "spread_return_sum": 0.0,
        "slippage_return_sum": 0.0,
        "funding": "NOT_MODELLED",
        **ECONOMIC_STATUS,
    }
    if trades.num_rows == 0:
        return empty
    net = np.asarray(trades.column("net_return").to_pylist(), dtype=np.float64)
    exits = trades.column("exit_time").combine_chunks().cast(pa.int64()).to_numpy()
    tiers = trades.column("liquidity_tier").to_pylist()
    wins, losses = float(net[net > 0].sum()), float(-net[net < 0].sum())
    ordered = net[np.argsort(exits, kind="stable")]
    cumulative = np.cumsum(ordered)
    drawdown = float(np.max(np.maximum.accumulate(np.maximum(cumulative, 0.0)) - cumulative))
    spread = np.std(net, ddof=1) if len(net) > 1 else 0.0
    decided = int((net > 0).sum() + (net < 0).sum())
    return {
        "trades": int(trades.num_rows),
        "win_rate": float((net > 0).sum() / decided) if decided else None,
        "net_return_sum": float(net.sum()),
        "expectancy": float(net.mean()),
        "profit_factor": (wins / losses) if losses > 0 else None,
        "sharpe_per_trade": float(np.mean(net) / spread) if spread > 0 else None,
        "trade_drawdown_proxy": drawdown,  # OLD CODE (kept): "max_drawdown": drawdown,
        "fees_return_sum": float(sum(tier_costs[t]["fee_bps"] for t in tiers) / 10_000),
        "spread_return_sum": float(sum(tier_costs[t]["spread_bps"] for t in tiers) / 10_000),
        "slippage_return_sum": float(sum(tier_costs[t]["slippage_bps"] for t in tiers) / 10_000),
        "funding": "NOT_MODELLED",
        **ECONOMIC_STATUS,
    }


def tier_cost_breakdown(costs: Any) -> dict[str, dict[str, float]]:
    """Round-trip fee / spread / slippage bps per liquidity tier from a CostConfig."""

    return {
        tier: {
            "fee_bps": 2.0 * item.taker_fee_bps_per_side,
            "spread_bps": float(item.spread_bps_round_trip),
            "slippage_bps": 2.0 * item.slippage_bps_per_side,
        }
        for tier, item in (
            ("HIGH_LIQUIDITY", costs.high_liquidity),
            ("MEDIUM_LIQUIDITY", costs.medium_liquidity),
            ("LOWER_LIQUIDITY", costs.lower_liquidity),
        )
    }


def console_fields(decision: Mapping[str, Any], trading: Mapping[str, Any]) -> dict[str, Any]:
    """Values for the fold report fields that were hard-coded to ``None`` (pooled over sides)."""

    long_side, short_side = decision["long"], decision["short"]
    tp = long_side["true_positives"] + short_side["true_positives"]
    fp = long_side["false_positives"] + short_side["false_positives"]
    fn = long_side["false_negatives"] + short_side["false_negatives"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "no_trade_signals": decision["no_trade_signals"],
        "profit_factor": trading.get("profit_factor"),
        "sharpe": trading.get("sharpe_per_trade"),
        # OLD CODE (kept): "max_drawdown": trading.get("max_drawdown"),
        "max_drawdown": trading.get("trade_drawdown_proxy"),  # shown as a PROXY label in the UI
        "fees": trading.get("fees_return_sum"),
        "slippage": trading.get("slippage_return_sum"),
        "funding": trading.get("funding"),
    }


# ---------------------------------------------------------------- run control
def stop_requested(run_directory: Path, config: HardeningConfig | None = None) -> bool:
    cfg = config or current_config()
    return bool(cfg.stop_file_name) and (run_directory / cfg.stop_file_name).exists()


def apply_pilot_filter(
    specs: Sequence[Any], config: HardeningConfig | None = None
) -> tuple[Any, ...]:
    """Keep one horizon x one target type when pilot mode is configured; else return specs."""

    cfg = config or current_config()
    if not (cfg.pilot_horizon_minutes and cfg.pilot_target_type):
        return tuple(specs)
    kept = tuple(
        spec
        for spec in specs
        if spec.horizon_minutes == cfg.pilot_horizon_minutes
        and spec.target_type == cfg.pilot_target_type
    )
    if not kept:
        raise ValueError("pilot filter matches no experiment specification")
    return kept


def fold_gate_failed(
    fold_reports: Iterable[Mapping[str, Any]],
    fold_position: int,
    config: HardeningConfig | None = None,
) -> bool:
    """True when folds 1..N are gated and NO completed spec beat the zero baseline on validation."""

    cfg = config or current_config()
    if not cfg.fold_gate_folds or fold_position > cfg.fold_gate_folds:
        return False
    scored = [
        (item.get("phase7b") or {}).get("baselines", {}).get("lightgbm_beats_zero")
        for item in fold_reports
        if item.get("status") == "COMPLETE"
    ]
    scored = [value for value in scored if value is not None]
    return bool(scored) and not any(scored)


# ---------------------------------------------------------------- results table
RESULT_COLUMNS = (
    "fold_id", "spec", "horizon_minutes", "target_type", "architecture",
    "train_rows", "validation_rows", "calibration_a_rows", "calibration_b_rows", "test_rows",
    "zero_val_rmse", "ridge_val_rmse", "lightgbm_val_rmse", "lightgbm_skill_vs_zero",
    "beats_zero", "beats_ridge",
    "calibration_method", "calibration_selection_source",
    "long_precision", "long_recall", "long_f1", "short_precision", "short_recall", "short_f1",
    "no_trade_signals",
    "trades", "win_rate", "net_return_sum", "expectancy", "profit_factor", "sharpe_per_trade",
    "trade_drawdown_proxy", "fees_return_sum", "spread_return_sum", "slippage_return_sum",
    "funding",
    "test_used_for_selection",
    # CHANGED BY CLAUDE (2026-11-06, final hardening): provenance + extra validation metrics.
    "run_id", "status", "configuration_hash", "code_version", "gold_dataset_id",
    "lightgbm_val_dir_acc_nonzero", "lightgbm_val_pearson", "lightgbm_val_spearman",
    "delta_rmse_vs_zero", "delta_rmse_vs_ridge", "delta_dir_acc_vs_ridge",
    "delta_spearman_vs_ridge",
    "seed", "feature_set", "backend", "scientific_code_identity", "hardening_identity",
    "baseline_contract_version",
    "portfolio_sharpe", "portfolio_max_drawdown", "funding_model_status", "cost_model_label",
    "entry_price_label", "economic_status",
)  # fmt: skip


def append_result_row(directory: Path, row: Mapping[str, Any]) -> Path:
    """Append one (fold, spec) row to the run's single results table (CSV)."""

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / RESULTS_FILENAME
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({name: row.get(name) for name in RESULT_COLUMNS})
        stream.flush()
        os.fsync(stream.fileno())
    return path


def results_row_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a COMPLETE fold/spec report (with its ``phase7b`` block) into one table row."""

    extra = report.get("phase7b") or {}
    base = extra.get("baselines", {})
    decision = extra.get("decision", {})
    trading = extra.get("trading", {})
    spec = report.get("spec", {})
    rows = report.get("segment_rows", {})
    selected = (report.get("calibration") or {}).get("selected", {})
    return {
        "fold_id": report.get("fold_id"),
        "spec": spec.get("name"),
        "horizon_minutes": spec.get("horizon_minutes"),
        "target_type": spec.get("target_type"),
        "architecture": spec.get("architecture"),
        "train_rows": rows.get("train"),
        "validation_rows": rows.get("validation"),
        "calibration_a_rows": rows.get("calibration_a"),
        "calibration_b_rows": rows.get("calibration_b"),
        "test_rows": rows.get("test"),
        "zero_val_rmse": base.get("zero_return", {}).get("rmse"),
        "ridge_val_rmse": base.get("ridge", {}).get("rmse"),
        "lightgbm_val_rmse": base.get("lightgbm", {}).get("rmse"),
        "lightgbm_skill_vs_zero": base.get("lightgbm_skill_vs_zero"),
        "beats_zero": base.get("lightgbm_beats_zero"),
        "beats_ridge": base.get("lightgbm_beats_ridge"),
        "calibration_method": selected.get("method"),
        "calibration_selection_source": (report.get("calibration") or {}).get("selection_source"),
        "long_precision": decision.get("long", {}).get("precision"),
        "long_recall": decision.get("long", {}).get("recall"),
        "long_f1": decision.get("long", {}).get("f1"),
        "short_precision": decision.get("short", {}).get("precision"),
        "short_recall": decision.get("short", {}).get("recall"),
        "short_f1": decision.get("short", {}).get("f1"),
        "no_trade_signals": decision.get("no_trade_signals"),
        "trades": trading.get("trades"),
        "win_rate": trading.get("win_rate"),
        "net_return_sum": trading.get("net_return_sum"),
        "expectancy": trading.get("expectancy"),
        "profit_factor": trading.get("profit_factor"),
        "sharpe_per_trade": trading.get("sharpe_per_trade"),
        "trade_drawdown_proxy": trading.get("trade_drawdown_proxy"),
        # OLD CODE (kept): "max_drawdown": trading.get("max_drawdown"),
        "fees_return_sum": trading.get("fees_return_sum"),
        "spread_return_sum": trading.get("spread_return_sum"),
        "slippage_return_sum": trading.get("slippage_return_sum"),
        "funding": trading.get("funding"),
        "portfolio_sharpe": trading.get("portfolio_sharpe"),
        "portfolio_max_drawdown": trading.get("portfolio_max_drawdown"),
        "funding_model_status": trading.get("funding_model_status"),
        "cost_model_label": trading.get("cost_model_label"),
        "entry_price_label": trading.get("entry_price_label"),
        "economic_status": trading.get("economic_status"),
        "test_used_for_selection": report.get("test_used_for_selection"),
        # CHANGED BY CLAUDE (2026-11-06, final hardening): provenance + extra validation metrics.
        "run_id": (report.get("execution_context") or {}).get("run_identity"),
        "status": report.get("status"),
        "configuration_hash": (report.get("checkpoint_identity") or {}).get("configuration_hash"),
        "code_version": (report.get("checkpoint_identity") or {}).get("code_version"),
        "gold_dataset_id": (report.get("checkpoint_identity") or {}).get("gold_dataset_id"),
        "lightgbm_val_dir_acc_nonzero": base.get("lightgbm", {}).get(
            "directional_accuracy_nonzero"
        ),
        "lightgbm_val_pearson": base.get("lightgbm", {}).get("pearson_ic"),
        "lightgbm_val_spearman": base.get("lightgbm", {}).get("spearman_ic"),
        "delta_rmse_vs_zero": (base.get("delta_vs_zero") or {}).get("rmse"),
        "delta_rmse_vs_ridge": (base.get("delta_vs_ridge") or {}).get("rmse"),
        "delta_dir_acc_vs_ridge": (base.get("delta_vs_ridge") or {}).get(
            "directional_accuracy_nonzero"
        ),
        "delta_spearman_vs_ridge": (base.get("delta_vs_ridge") or {}).get("spearman_ic"),
        # CHANGED BY CLAUDE (2026-11-06, IA-02/IA-04): canonical identity fields.
        "seed": (report.get("model") or {}).get("seed"),
        "feature_set": spec.get("feature_group"),
        "backend": (report.get("model") or {}).get("compute_backend"),
        "scientific_code_identity": (
            (report.get("checkpoint_identity") or {}).get("training_source_identity") or {}
        ).get("manifest_sha256"),
        "hardening_identity": (extra.get("experiment_control_identity") or {}).get(
            "manifest_sha256"
        ),
        "baseline_contract_version": base.get("baseline_contract_version"),
    }


# ---------------------------------------------------------------- success criteria
# CHANGED BY CLAUDE (2026-11-06, closure): v2 adds the TRAIN-mean baseline and the cross-sectional
# IC on the same rows; nothing else changes. OLD VALUE:
# BASELINE_CONTRACT_VERSION = "baseline_contract_v1_same_rows_same_target_fixed_ridge_validation"
BASELINE_CONTRACT_VERSION = "baseline_contract_v2_same_rows_same_target_fixed_ridge_xs_ic"


def _per_spec_skill(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    by_spec: dict[str, list[float]] = {}
    for row in rows:
        skill = row.get("lightgbm_skill_vs_zero")
        if skill not in (None, ""):
            by_spec.setdefault(str(row["spec"]), []).append(float(skill))
    return by_spec


def _descriptive_items(by_spec: Mapping[str, Sequence[float]]) -> list[dict[str, Any]]:
    items = []
    for spec, skills in by_spec.items():
        values = np.asarray(skills, dtype=np.float64)
        items.append(
            {
                "spec": spec,
                "folds_scored": int(len(values)),
                "mean_validation_skill_vs_zero": float(values.mean()),
                "median_validation_skill_vs_zero": float(np.median(values)),
                "worst_fold_skill": float(values.min()),
                "std_across_folds": float(values.std(ddof=1)) if len(values) > 1 else None,
                "fraction_folds_positive": float((values > 0).mean()),
            }
        )
    items.sort(key=lambda item: item["mean_validation_skill_vs_zero"], reverse=True)
    return items


def descriptive_ranking(
    rows: Sequence[Mapping[str, Any]], config: HardeningConfig | None = None
) -> dict[str, Any]:
    """DESCRIPTIVE ranking of specs by validation skill. It is NOT evidence of an edge.

    CHANGED BY CLAUDE (2026-11-06, finding IA-01/IA-02). The old helper returned one-sided t-test
    p-values and a Bonferroni "significant" flag computed from VALIDATION rows, the same rows that
    stop each estimator early, and it counted duplicate CSV rows as extra folds. Both claims were
    invalid, so: duplicates are rejected, no p-value is produced, and the output says why.
    OLD CODE: ``rank_specs_with_correction`` (removed; see git history before this commit).
    """

    ordered = reject_duplicates(rows)
    by_spec = _per_spec_skill(ordered)
    return {
        "ranking_kind": DESCRIPTIVE_RANKING,
        "metric_class": DEVELOPMENT_METRIC,
        "inference_status": NOT_INDEPENDENT,
        "p_values": NOT_APPLICABLE,
        "reason": (
            "Validation rows also stop each estimator early and rolling folds reuse earlier TEST "
            "months as later validation, so no p-value or 'significant' flag is valid here."
        ),
        "ranking_basis": "VALIDATION_ONLY",
        "specs_tried": len(by_spec),
        "spec_fold_pairs_tried": sum(len(v) for v in by_spec.values()),
        "folds_seen": len({str(r.get("fold_id")) for r in ordered}),
        "ranking": _descriptive_items(by_spec),
    }


# Backward-compatible name. It now returns the DESCRIPTIVE ranking only (no p-values).
rank_specs_with_correction = descriptive_ranking


def selection_eligible_ranking(
    rows: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    *,
    expected_fold_ids: Sequence[str],
) -> dict[str, Any]:
    """SELECTION_ELIGIBLE ranking: unique canonical results on DEVELOPMENT folds of a frozen
    protocol only. It may choose a spec; it still cannot certify an edge (inference
    NOT_INDEPENDENT).
    """

    from crypto_ai.phase7.selection_chronology import (
        SELECTION_ELIGIBLE_RANKING,
        assert_rows_selection_eligible,
    )

    validated = validate_result_set(rows, expected_fold_ids=expected_fold_ids)
    assert_rows_selection_eligible(validated, protocol)
    return {
        "ranking_kind": SELECTION_ELIGIBLE_RANKING,
        "metric_class": SELECTION_METRIC,
        "inference_status": NOT_INDEPENDENT,
        "protocol_sha256": protocol["protocol_sha256"],
        "selection_policy_version": protocol["selection_policy_version"],
        "ranking": _descriptive_items(_per_spec_skill(validated)),
        "independent_evaluation": "REQUIRES the protocol's evaluation folds, run after selection",
    }


def evaluate_success(
    rows: Sequence[Mapping[str, Any]],
    config: HardeningConfig | None = None,
    *,
    expected_fold_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Count folds against the written criteria. DESCRIPTIVE only; duplicates are rejected.

    CHANGED BY CLAUDE (2026-11-06, finding IA-02): the old version counted every row, so ten copies
    of one fold satisfied "10 folds". It now validates the result set first and renames the verdict
    ``descriptive_criteria_met`` so it cannot be quoted as a pass of the independent success
    protocol.
    """

    cfg = config or current_config()
    if expected_fold_ids is not None:
        ordered = validate_result_set(
            rows, expected_fold_ids=expected_fold_ids, strict_identity=False
        )
    else:
        ordered = reject_duplicates(rows)
    per_spec: dict[str, dict[str, int]] = {}
    for row in ordered:
        entry = per_spec.setdefault(str(row["spec"]), {"net_positive": 0, "beats": 0, "folds": 0})
        entry["folds"] += 1
        net = row.get("net_return_sum")
        entry["net_positive"] += int(net not in (None, "") and float(net) > 0)
        entry["beats"] += int(str(row.get("beats_zero")) == "True")
    verdicts = {
        spec: {
            **counts,
            "descriptive_criteria_met": counts["net_positive"] >= cfg.success_min_net_positive_folds
            and counts["beats"] >= cfg.success_min_beats_baseline_folds,
        }
        for spec, counts in sorted(per_spec.items())
    }
    return {
        "status": DESCRIPTIVE_ONLY,
        "inference_status": NOT_INDEPENDENT,
        "qualifies_as_independent_evidence": False,
        "why_not": (
            "Validation 'beats_zero' is a development metric; fold TEST months are reused as later "
            "validation; costs exclude funding. Use the frozen selection protocol and the "
            "independent evaluation folds (docs/research/PHASE7_SUCCESS_CRITERIA_V1.md)."
        ),
        "criteria": {
            "min_net_positive_folds": cfg.success_min_net_positive_folds,
            "min_beats_baseline_folds": cfg.success_min_beats_baseline_folds,
        },
        "specs": verdicts,
        "any_spec_meets_descriptive_criteria": any(
            item["descriptive_criteria_met"] for item in verdicts.values()
        ),
    }


def read_results_table(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# ---------------------------------------------------------------- Silver check
def silver_status(data_root: Path) -> dict[str, Any]:
    """Is the Silver mirror present? Training from Gold only needs a warning, never a failure."""

    silver = data_root / "phase7" / "silver" / "binance"
    present = silver.is_dir() and any(silver.rglob("*.json")) and any(silver.rglob("*.parquet"))
    return {
        "silver_root": str(silver),
        "status": "PRESENT" if present else "ABSENT",
        "owner_decision": "PENDING: 'Silver restored' or 'Gold is source of truth'",
    }


class SilverMissingError(RuntimeError):
    """A Gold rebuild or audit needs Silver, which is not present in this environment."""


def require_silver(data_root: Path, operation: str) -> None:
    status = silver_status(data_root)
    if status["status"] != "PRESENT":
        raise SilverMissingError(
            f"{operation} needs Silver data, but none was found under {status['silver_root']}. "
            "Training from existing Gold works without it; rebuilding or auditing Gold does not. "
            "Restore Silver first, or record that Gold is the source of truth."
        )


def main() -> int:
    """Summarise a finished run: ``python -m crypto_ai.phase7.hardening <phase7b_results.csv>``."""

    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    rows = read_results_table(args.results)
    report = {
        "config": asdict(current_config()),
        "ranking": descriptive_ranking(rows),
        "success": evaluate_success(rows),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
