"""Isolated full-shape benchmark for the Phase 7 model-training hot path.

This command uses deterministic synthetic values with the canonical 20-symbol,
24-month row shape. It calls the production model code but never invokes the
Phase 7 pipeline, reads holdout data, or writes research checkpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.features import (
    ANCHOR_CONTEXT_COLUMNS,
    BASE_FEATURE_COLUMNS,
    COIN_CONTEXT_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
)
from crypto_ai.phase7.models import (
    Phase7ModelBundle,
    fit_architecture,
    prepare_architecture_inputs,
)
from crypto_ai.phase7.training import phase7_experiment_specs

A6_FEATURE_COLUMNS = (
    BASE_FEATURE_COLUMNS + COIN_CONTEXT_COLUMNS + ANCHOR_CONTEXT_COLUMNS + MARKET_CONTEXT_COLUMNS
)
TARGET_COLUMN = "raw_future_return"
FIVE_MINUTE_STEP_US = 300_000_000


def _table(
    symbols: list[str],
    rows_per_symbol: int,
    rng: np.random.Generator,
) -> pa.Table:
    chunks: dict[str, list[np.ndarray]] = {
        "symbol": [],
        "feature_time": [],
        **{name: [] for name in A6_FEATURE_COLUMNS},
    }
    for symbol_index, symbol in enumerate(symbols):
        values = rng.normal(0.0, 1.0, size=(rows_per_symbol, len(A6_FEATURE_COLUMNS)))
        for column in range(min(6, values.shape[1])):
            carry = 0.0
            for row in range(rows_per_symbol):
                carry = 0.98 * carry + values[row, column]
                values[row, column] = carry
        chunks["symbol"].append(np.full(rows_per_symbol, symbol, dtype=object))
        chunks["feature_time"].append(
            symbol_index * 10_000_000_000_000
            + np.arange(rows_per_symbol, dtype=np.int64) * FIVE_MINUTE_STEP_US
        )
        for column, name in enumerate(A6_FEATURE_COLUMNS):
            chunks[name].append(values[:, column].astype(np.float64))
    arrays = {name: np.concatenate(parts) for name, parts in chunks.items()}
    target = sum(0.5 * arrays[name] for name in A6_FEATURE_COLUMNS[:4])
    arrays[TARGET_COLUMN] = target + rng.normal(0.0, 1.5, size=len(target))
    return pa.table(arrays)


def _composition(specs: tuple[Any, ...], symbols: int, clusters: int) -> dict[str, Any]:
    by_architecture = Counter(spec.architecture for spec in specs)
    estimators_per_fold_view = (
        by_architecture["G0"]
        + by_architecture["C0"] * clusters
        + by_architecture["P0"] * symbols
        + by_architecture["H0"]
    )
    return {
        "specifications": len(specs),
        "by_architecture": dict(sorted(by_architecture.items())),
        "bundles": 16 * 2 * len(specs),
        "eligible_symbols": symbols,
        "estimators_per_fold_view": estimators_per_fold_view,
        "estimators_if_both_views_have_this_membership": 16 * 2 * estimators_per_fold_view,
        "absolute_30_symbol_ceiling": 16
        * 2
        * (
            by_architecture["G0"]
            + by_architecture["C0"] * clusters
            + by_architecture["P0"] * 30
            + by_architecture["H0"]
        ),
    }


def _prediction_sha256(model: Phase7ModelBundle, table: pa.Table) -> str:
    predicted, covered = model.predict(table)
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(predicted).view(np.uint8))
    digest.update(np.ascontiguousarray(covered).view(np.uint8))
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", type=int, default=20)
    parser.add_argument("--rows", type=int, default=210_240)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/phase7/research_v1.toml"),
    )
    args = parser.parse_args()
    if args.symbols < 1 or args.rows < 1 or args.threads < 1 or args.workers < 1:
        raise ValueError("symbols, rows, threads, and workers must be positive")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite benchmark output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = load_phase7_config(args.config)
    specs = phase7_experiment_specs(config)
    symbols = [f"SYM{index:02d}" for index in range(args.symbols)]
    validation_rows = max(args.rows // 4, 20_000)
    rng = np.random.default_rng(7)
    started = time.monotonic()
    train = _table(symbols, args.rows, rng)
    validation = _table(symbols, validation_rows, rng)
    calibration = _table(symbols, validation_rows, rng)
    build_seconds = time.monotonic() - started
    print(f"built tables in {build_seconds:.3f}s", flush=True)

    started = time.monotonic()
    prepared = prepare_architecture_inputs(
        train,
        validation,
        feature_columns=A6_FEATURE_COLUMNS,
        target_column=TARGET_COLUMN,
        eligibility_calibration_a=calibration,
    )
    preparation_seconds = time.monotonic() - started
    print(f"prepared shared arrays in {preparation_seconds:.3f}s", flush=True)

    mapping = {symbol: index % config.models.cluster_count for index, symbol in enumerate(symbols)}
    results: list[dict[str, Any]] = []
    reusable_global: Phase7ModelBundle | None = None
    for architecture in ("G0", "C0", "P0", "H0"):
        started = time.monotonic()
        model = fit_architecture(
            architecture,  # type: ignore[arg-type]
            train,
            validation,
            feature_columns=A6_FEATURE_COLUMNS,
            target_column=TARGET_COLUMN,
            config=config.models,
            model_threads=args.threads,
            estimator_workers=args.workers,
            cluster_mapping=mapping,
            symbol_balanced=True,
            hybrid_calibration=validation if architecture == "H0" else None,
            eligibility_calibration_a=calibration,
            prepared_inputs=prepared,
            reusable_global=reusable_global if architecture == "H0" else None,
        )
        elapsed = time.monotonic() - started
        if architecture == "G0":
            reusable_global = model
        result = {
            "architecture": architecture,
            "wall_seconds": elapsed,
            "estimator_count": len(model.estimators),
            "best_iterations": [
                int(estimator.best_iteration_)
                for estimator in model.estimators.values()
                if getattr(estimator, "best_iteration_", None) is not None
            ],
            "prediction_sha256": _prediction_sha256(model, validation),
            "fit_execution": model.metadata["fit_execution"],
        }
        results.append(result)
        print(
            f"{architecture}: {elapsed:.3f}s, {len(model.estimators)} estimators",
            flush=True,
        )

    usage = resource.getrusage(resource.RUSAGE_SELF)
    payload = {
        "classification": "ISOLATED_SYNTHETIC_FULL_SHAPE_BENCHMARK",
        "configuration_hash": config.configuration_hash,
        "host": {
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
        },
        "shape": {
            "symbols": args.symbols,
            "train_rows_per_symbol": args.rows,
            "validation_rows_per_symbol": validation_rows,
            "feature_count": len(A6_FEATURE_COLUMNS),
            "train_rows": train.num_rows,
            "validation_rows": validation.num_rows,
        },
        "execution": {
            "threads_per_estimator": args.threads,
            "estimator_workers": args.workers,
            "table_build_seconds": build_seconds,
            "shared_preparation_seconds": preparation_seconds,
            "user_cpu_seconds": usage.ru_utime,
            "system_cpu_seconds": usage.ru_stime,
            "maximum_rss_kib": usage.ru_maxrss,
        },
        "composition": _composition(specs, args.symbols, config.models.cluster_count),
        "architectures": results,
    }
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(f"wrote {output}", flush=True)


if __name__ == "__main__":
    main()
