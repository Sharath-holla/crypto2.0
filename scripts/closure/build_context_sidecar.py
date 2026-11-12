"""Build a feature-only sidecar from verified local Silver; no network or model fit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.context_sidecar import context_source_projection, write_sidecar
from crypto_ai.phase7.registry import read_registry
from crypto_ai.phase7.universe import read_universe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persistent-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--gold-validation", type=Path, required=True)
    parser.add_argument("--silver-validation", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase7/research_core20_primary_v1.toml")
    )
    args = parser.parse_args()
    for evidence in (args.gold_validation, args.silver_validation):
        if json.loads(evidence.read_text())["status"] != "PASS":
            raise ValueError("source verification must pass first")
    if json.loads(args.census.read_text())["verdict"] != "MATERIAL_LOSS_SIDECAR_REQUIRED":
        raise ValueError("a real census must require this sidecar")
    root, run = args.persistent_root.resolve(), args.run_root.resolve()
    output = args.output_root.resolve()
    if output.is_relative_to(root / "data") or (root / "data").is_relative_to(output):
        raise ValueError("sidecar output overlaps immutable data")
    data_path = run / "data/data_manifest.json"
    data = json.loads(data_path.read_text())
    gold = json.loads(args.gold_validation.read_text())
    gold_manifest = json.loads(Path(gold["manifest_path"]).read_text())
    if file_sha256(data_path) != gold_manifest["lineage"]["data_manifest_sha256"]:
        raise ValueError("Silver acquisition identity differs from Gold lineage")
    config = load_phase7_config(args.config)
    registry_path, universe_path = (
        run / "registry/symbol_registry.json",
        run / "universe/core_universe.json",
    )
    registry, universe = read_registry(registry_path), read_universe(universe_path)
    if (
        registry.registry_hash != gold_manifest["registry_hash"]
        or universe.universe_hash != gold_manifest["lineage"]["core_universe_hash"]
    ):
        raise ValueError("registry/universe differ from Gold")
    silver = root / "data/phase7/silver/binance"
    manifests = {
        s: silver / "manifests" / Path(p).name
        for s, p in data["candle_silver_manifests"]["5m"].items()
    }
    identity = {
        "gold_manifest_sha256": gold["manifest_sha256"],
        "registry_hash": registry.registry_hash,
        "universe_hash": universe.universe_hash,
        "research_universe_hash": gold_manifest["universe_hash"],
        "configuration_hash": config.configuration_hash,
        "registry_sha256": file_sha256(registry_path),
        "universe_sha256": file_sha256(universe_path),
        "data_manifest_sha256": file_sha256(data_path),
        "builder_sha256": file_sha256(Path(__file__)),
        "silver_validation_sha256": file_sha256(args.silver_validation),
        "silver_manifests": [
            {"symbol": s, "path": str(p), "sha256": file_sha256(p)}
            for s, p in sorted(manifests.items())
        ],
        "projection_contract": (
            "Six context inputs; producer helpers, contiguous segments, annual Gold lookback."
        ),
    }

    def parts():
        for symbol, manifest in sorted(manifests.items()):
            records = json.loads(manifest.read_text())["output_files"]
            start = config.data_start
            while start < config.research_cutoff:
                end = min(datetime(start.year + 1, 1, 1, tzinfo=UTC), config.research_cutoff)
                lower = max(
                    config.data_start,
                    start
                    - timedelta(
                        minutes=5
                        * max(
                            config.features.correlation_window_rows,
                            config.features.liquidity_window_rows,
                            config.features.volatility_window_rows,
                            config.features.seven_day_volatility_rows,
                        )
                    ),
                )
                tables = []
                for rec in records:
                    date = next(
                        p.split("=", 1)[1] for p in Path(rec["file"]).parts if p.startswith("date=")
                    )
                    if not lower.date() <= datetime.fromisoformat(date).date() <= end.date():
                        continue
                    path = silver / rec["file"]
                    if file_sha256(path) != rec["sha256"]:
                        raise ValueError(f"Silver checksum mismatch: {path}")
                    table = pq.ParquetFile(path).read(
                        columns=[
                            "symbol",
                            "open_time",
                            "close",
                            "quote_volume",
                            "trade_count",
                            "taker_buy_quote_volume",
                        ]
                    )
                    table = table.filter(
                        pc.and_(
                            pc.greater_equal(table["open_time"], lower),
                            pc.less(table["open_time"], end),
                        )
                    )
                    if table.num_rows:
                        tables.append(table)
                if tables:
                    projected = context_source_projection(pa.concat_tables(tables), config.features)
                    projected = projected.filter(
                        pc.and_(
                            pc.greater_equal(projected["feature_time"], start),
                            pc.less(projected["feature_time"], end),
                        )
                    )
                    print(symbol, start.year, projected.num_rows, flush=True)
                    yield projected
                start = end

    path = write_sidecar(output, parts(), identity)
    print(path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
