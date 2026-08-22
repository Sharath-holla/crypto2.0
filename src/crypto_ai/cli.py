from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.config import load_binance_settings
from crypto_ai.context.commands import (
    collect_fear_greed,
    collect_open_interest_recent,
    collect_open_interest_snapshot,
    context_status,
    fear_greed_plan,
    open_interest_plan,
)
from crypto_ai.context.config import load_context_config
from crypto_ai.data.binance import BinanceArchiveClient, BinanceRestClient
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.models import ValidationStatus
from crypto_ai.data.quality.policy import load_quality_policy
from crypto_ai.data.quality.promotion import SilverPromoter
from crypto_ai.data.storage import file_sha256, read_candle_parquet
from crypto_ai.data.validation import validate_candles
from crypto_ai.logging import configure_logging
from crypto_ai.phase4.backtest import run_backtest_suite
from crypto_ai.phase4.config import (
    load_backtest_config,
    load_gold_v2_config,
)
from crypto_ai.phase4.gold import build_gold_v2
from crypto_ai.phase4.market_data import (
    DerivativesMarketDataClient,
    MarketDataKind,
    ingest_public_market_data,
)
from crypto_ai.phase4.model import train_main_model_v2
from crypto_ai.phase4_1.archive_market import ingest_archive_market_data
from crypto_ai.phase4_1.backtest import run_backtest_suite_v2_1
from crypto_ai.phase4_1.config import (
    load_backtest_v2_1_config,
    load_gold_v2_1_config,
)
from crypto_ai.phase4_1.gold import build_gold_v2_1
from crypto_ai.phase4_1.model import train_main_model_v2_1
from crypto_ai.phase5.config import load_hardening_config, load_walk_forward_config
from crypto_ai.phase5.engine import (
    compare_walk_forward_candidates,
    run_walk_forward,
)
from crypto_ai.phase5.hardening import (
    compare_hardened_candidates,
    run_hardened_walk_forward,
)
from crypto_ai.phase5.verification import verify_hardened_runs
from crypto_ai.phase6 import load_phase6_config, run_phase6_research
from crypto_ai.phase7 import (
    load_phase7_config,
    phase7_dry_run,
    phase7_plan,
    test_phase7_universe,
    validate_phase7_configuration,
)
from crypto_ai.research.config import (
    DatasetBuildConfig,
    load_dataset_config,
    load_experiment_config,
    load_feature_config,
    load_label_config,
)
from crypto_ai.research.experiment import comparison_text, load_experiment, train_experiment
from crypto_ai.research.gold import build_gold_dataset


def parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO-8601 datetime: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Datetime must include Z or an explicit UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-ai",
        description="Cryptocurrency data-quality and leakage-safe research tools",
    )
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download Binance klines")
    download.add_argument("--config", type=Path, default=Path("configs/data/binance.toml"))
    download.add_argument("--start", type=parse_datetime, required=True)
    download.add_argument("--end", type=parse_datetime, required=True)
    download.add_argument("--market", choices=["spot", "usdm"])
    download.add_argument("--symbol")
    download.add_argument("--interval")
    download.add_argument("--output-root", type=Path)
    download.add_argument("--request-limit", type=int)
    download.add_argument("--timeout-seconds", type=float)
    download.add_argument("--max-retries", type=int)
    download.add_argument("--retry-base-seconds", type=float)
    download.add_argument("--base-url")

    download_archive = subparsers.add_parser(
        "download-archive",
        help="Download checksum-verified Binance USD-M monthly kline archives",
    )
    download_archive.add_argument("--config", type=Path, default=Path("configs/data/binance.toml"))
    download_archive.add_argument("--start", type=parse_datetime, required=True)
    download_archive.add_argument("--end", type=parse_datetime, required=True)
    download_archive.add_argument("--symbol")
    download_archive.add_argument("--interval")
    download_archive.add_argument("--output-root", type=Path)
    download_archive.add_argument(
        "--raw-root", type=Path, default=Path("data/bronze/binance-public-data")
    )
    download_archive.add_argument("--timeout-seconds", type=float)
    download_archive.add_argument("--max-retries", type=int)
    download_archive.add_argument("--retry-base-seconds", type=float)
    download_archive.add_argument("--archive-base-url")

    validate = subparsers.add_parser("validate", help="Validate a candle Parquet file")
    validate.add_argument("path", type=Path)
    validate.add_argument("--interval", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect a candle Parquet file")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--limit", type=int, default=5)

    quality = subparsers.add_parser(
        "quality-report",
        help="Validate a Bronze manifest or existing candle partition",
    )
    quality_input = quality.add_mutually_exclusive_group(required=True)
    quality_input.add_argument("--manifest", type=Path)
    quality_input.add_argument("--path", type=Path)
    quality.add_argument(
        "--quality-config",
        type=Path,
        default=Path("configs/data_quality/default.toml"),
    )
    quality.add_argument("--output-root", type=Path, default=Path("data/quality"))
    quality.add_argument("--market", choices=["spot", "usdm"], default="usdm")
    quality.add_argument("--symbol", default="BTCUSDT")
    quality.add_argument("--interval", default="5m")
    quality.add_argument(
        "--source",
        help="Source identity (defaults to the selected Binance market)",
    )
    quality.add_argument("--start", type=parse_datetime)
    quality.add_argument("--end", type=parse_datetime)

    promote = subparsers.add_parser(
        "promote-silver",
        help="Validate a Bronze manifest and promote only data that passes the quality gate",
    )
    promote.add_argument("--manifest", type=Path, required=True)
    promote.add_argument(
        "--quality-config",
        type=Path,
        default=Path("configs/data_quality/default.toml"),
    )
    promote.add_argument("--quality-root", type=Path, default=Path("data/quality"))
    promote.add_argument("--silver-root", type=Path, default=Path("data/silver/binance"))
    promote.add_argument("--quarantine-root", type=Path, default=Path("data/quarantine"))

    build = subparsers.add_parser(
        "build-dataset",
        help="Build a deterministic leakage-safe Gold feature/label dataset",
    )
    build.add_argument("--config", type=Path)
    build.add_argument("--silver-manifest", type=Path)
    build.add_argument(
        "--label-config",
        type=Path,
        default=Path("configs/labels/forward_return_60m.toml"),
    )
    build.add_argument(
        "--feature-config",
        type=Path,
        default=Path("configs/features/baseline_v1.toml"),
    )
    build.add_argument("--output-root", type=Path)
    build.add_argument("--symbol")
    build.add_argument("--interval")
    build.add_argument("--start", type=parse_datetime)
    build.add_argument("--end", type=parse_datetime)

    train = subparsers.add_parser(
        "train",
        help="Train reproducible Phase 3 baselines on an existing Gold dataset",
    )
    train.add_argument("--dataset-manifest", type=Path, required=True)
    train.add_argument(
        "--config",
        type=Path,
        default=Path("configs/models/baseline_v1.toml"),
    )
    train.add_argument("--artifact-root", type=Path)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Inspect a completed Phase 3 experiment and model comparison",
    )
    evaluate.add_argument("--experiment", type=Path, required=True)
    evaluate.add_argument("--artifact-root", type=Path, default=Path("local_artifacts"))

    market_data = subparsers.add_parser(
        "download-market-data",
        help="Download and validate public Binance USD-M derivatives market data",
    )
    market_data.add_argument(
        "--kind",
        choices=[kind.value for kind in MarketDataKind],
        required=True,
    )
    market_data.add_argument("--start", type=parse_datetime, required=True)
    market_data.add_argument("--end", type=parse_datetime, required=True)
    market_data.add_argument("--symbol", default="BTCUSDT")
    market_data.add_argument("--interval", default="5m")
    market_data.add_argument("--config", type=Path, default=Path("configs/data/binance.toml"))
    market_data.add_argument("--output-root", type=Path, default=Path("data/market"))

    market_archive = subparsers.add_parser(
        "download-market-archive",
        help="Download checksum-verified public Binance mark/index/premium kline archives",
    )
    market_archive.add_argument(
        "--kind",
        choices=[
            MarketDataKind.MARK_KLINE.value,
            MarketDataKind.INDEX_KLINE.value,
            MarketDataKind.PREMIUM_KLINE.value,
        ],
        required=True,
    )
    market_archive.add_argument("--start", type=parse_datetime, required=True)
    market_archive.add_argument("--end", type=parse_datetime, required=True)
    market_archive.add_argument("--symbol", default="BTCUSDT")
    market_archive.add_argument("--interval", default="5m")
    market_archive.add_argument("--config", type=Path, default=Path("configs/data/binance.toml"))
    market_archive.add_argument("--output-root", type=Path, default=Path("data/market"))
    market_archive.add_argument(
        "--raw-root", type=Path, default=Path("data/bronze/binance-public-data")
    )

    build_v2 = subparsers.add_parser(
        "build-dataset-v2",
        help="Build immutable causally aligned Phase 4 Gold V2",
    )
    build_v2.add_argument("--config", type=Path, required=True)
    build_v2.add_argument(
        "--label-config",
        type=Path,
        default=Path("configs/labels/forward_return_60m.toml"),
    )

    train_v2 = subparsers.add_parser(
        "train-v2",
        help="Train Main Model V2 and time-safe feature-group ablations",
    )
    train_v2.add_argument("--dataset-manifest", type=Path, required=True)
    train_v2.add_argument("--config", type=Path, default=Path("configs/models/main_model_v2.toml"))
    train_v2.add_argument("--artifact-root", type=Path)

    build_v2_1 = subparsers.add_parser(
        "build-dataset-v2-1",
        help="Build immutable multi-year market_v2_1 Gold with coverage diagnostics",
    )
    build_v2_1.add_argument("--config", type=Path, required=True)
    build_v2_1.add_argument(
        "--label-config",
        type=Path,
        default=Path("configs/labels/forward_return_60m.toml"),
    )

    train_v2_1 = subparsers.add_parser(
        "train-v2-1",
        help="Run same-row Phase 4.1 long-history and derivatives-overlap ablations",
    )
    train_v2_1.add_argument("--core-dataset-manifest", type=Path, required=True)
    train_v2_1.add_argument("--derivatives-dataset-manifest", type=Path)
    train_v2_1.add_argument(
        "--config", type=Path, default=Path("configs/models/main_model_v2_1.toml")
    )
    train_v2_1.add_argument("--artifact-root", type=Path)

    backtest_v2_1 = subparsers.add_parser(
        "backtest-v2-1", help="Run OOS cost/funding/delay-stressed Phase 4.1 backtests"
    )
    backtest_v2_1.add_argument("--experiment", type=Path, required=True)
    backtest_v2_1.add_argument(
        "--config", type=Path, default=Path("configs/backtests/foundation_v2_1.toml")
    )
    backtest_v2_1.add_argument("--artifact-root", type=Path, default=Path("local_artifacts"))
    backtest_v2_1.add_argument("--funding-manifest", type=Path)
    backtest_v2_1.add_argument("--execution-1m-silver-manifest", type=Path)

    backtest = subparsers.add_parser(
        "backtest-v1",
        help="Run an OOS-only cost-aware Phase 4 backtest suite",
    )
    backtest.add_argument("--experiment", type=Path, required=True)
    backtest.add_argument(
        "--config", type=Path, default=Path("configs/backtests/foundation_v1.toml")
    )
    backtest.add_argument("--artifact-root", type=Path, default=Path("local_artifacts"))
    backtest.add_argument("--funding-manifest", type=Path)

    walk_forward = subparsers.add_parser(
        "walk-forward",
        help="Run immutable Phase 5 retrospective walk-forward validation",
    )
    walk_forward.add_argument("--config", type=Path, required=True)
    walk_forward.add_argument("--plan", action="store_true")
    walk_forward.add_argument("--resume", action="store_true")

    harden_walk_forward = subparsers.add_parser(
        "harden-walk-forward",
        help="Run versioned Phase 5.1 post-processing from immutable Phase 5 artifacts",
    )
    harden_walk_forward.add_argument("--config", type=Path, required=True)
    harden_walk_forward.add_argument("--resume", action="store_true")

    walk_forward_report = subparsers.add_parser(
        "walk-forward-report", help="Print a completed Phase 5 summary"
    )
    walk_forward_report.add_argument("--summary", type=Path, required=True)

    compare_candidates = subparsers.add_parser(
        "compare-candidates",
        help="Compare completed primary and derivatives Phase 5 candidate runs",
    )
    compare_candidates.add_argument("--primary-summary", type=Path, required=True)
    compare_candidates.add_argument("--derivatives-summary", type=Path, required=True)
    compare_candidates.add_argument("--output", type=Path)

    compare_hardened = subparsers.add_parser(
        "compare-hardened-candidates",
        help="Compare completed Phase 5.1 primary and derivatives results",
    )
    compare_hardened.add_argument("--primary-summary", type=Path, required=True)
    compare_hardened.add_argument("--derivatives-summary", type=Path, required=True)
    compare_hardened.add_argument("--output", type=Path)

    verify_hardened = subparsers.add_parser(
        "verify-hardened",
        help="Independently verify completed Phase 5.1 artifacts and v1 lineage",
    )
    verify_hardened.add_argument("--primary-summary", type=Path, required=True)
    verify_hardened.add_argument("--derivatives-summary", type=Path, required=True)
    verify_hardened.add_argument("--output", type=Path)
    phase6 = subparsers.add_parser(
        "phase6-research", help="Run isolated retrospective Phase 6 feature/target research"
    )
    phase6.add_argument("--config", type=Path, required=True)
    phase7 = subparsers.add_parser(
        "phase7-research",
        help="Plan, validate, or run survivorship-safe Phase 7 multi-asset research",
    )
    phase7.add_argument(
        "--config",
        type=Path,
        default=Path("configs/phase7/research_v1.toml"),
    )
    local_action = phase7.add_mutually_exclusive_group()
    local_action.add_argument("--plan", action="store_true")
    local_action.add_argument("--validate-config", action="store_true")
    local_action.add_argument("--dry-run", action="store_true")
    local_action.add_argument("--test-universe", action="store_true")
    local_action.add_argument(
        "--stage",
        choices=["registry", "universe", "data", "gold", "train", "report"],
    )
    phase7.add_argument("--resume", action="store_true")

    context = subparsers.add_parser(
        "context",
        help="Inspect or collect training-disabled public context datasets",
    )
    context_actions = context.add_subparsers(dest="context_command", required=True)
    context_status_parser = context_actions.add_parser(
        "status", help="Show provider and local context-dataset status without network access"
    )
    context_status_parser.add_argument(
        "--config", type=Path, default=Path("configs/context/default.toml")
    )
    fear_greed = context_actions.add_parser(
        "fear-greed", help="Plan or fetch Alternative.me Fear & Greed history"
    )
    fear_greed.add_argument("action", nargs="?", choices=["fetch"])
    fear_greed.add_argument("--plan", action="store_true")
    fear_greed.add_argument("--force-refresh", action="store_true")
    fear_greed.add_argument("--config", type=Path, default=Path("configs/context/default.toml"))
    open_interest = context_actions.add_parser(
        "oi", help="Plan or collect public Binance USD-M open interest"
    )
    open_interest.add_argument("action", nargs="?", choices=["recent", "snapshot"])
    open_interest.add_argument("--plan", action="store_true")
    open_interest.add_argument("--symbol", default="BTCUSDT")
    open_interest.add_argument("--start", type=parse_datetime)
    open_interest.add_argument("--end", type=parse_datetime)
    open_interest.add_argument("--config", type=Path, default=Path("configs/context/default.toml"))
    return parser


def _download(args: argparse.Namespace) -> int:
    overrides = {
        "market": args.market,
        "symbol": args.symbol,
        "interval": args.interval,
        "output_root": args.output_root,
        "request_limit": args.request_limit,
        "timeout_seconds": args.timeout_seconds,
        "max_retries": args.max_retries,
        "retry_base_seconds": args.retry_base_seconds,
        "base_url": args.base_url,
    }
    settings = load_binance_settings(args.config, overrides)
    with BinanceRestClient(settings) as client:
        manifest_path = HistoricalDownloader(settings, client).download(
            DownloadRequest(start=args.start, end=args.end)
        )
    manifest = read_manifest(manifest_path)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "status": manifest["status"] if manifest else "unknown",
                "row_count": manifest["row_count"] if manifest else None,
            },
            sort_keys=True,
        )
    )
    return 0 if manifest and manifest["status"] == "completed" else 2


def _download_archive(args: argparse.Namespace) -> int:
    settings = load_binance_settings(
        args.config,
        {
            "market": "usdm",
            "symbol": args.symbol,
            "interval": args.interval,
            "output_root": args.output_root,
            "timeout_seconds": args.timeout_seconds,
            "max_retries": args.max_retries,
            "retry_base_seconds": args.retry_base_seconds,
        },
    )
    with BinanceRestClient(settings) as metadata_client:
        client_options: dict[str, Any] = {
            "raw_root": args.raw_root,
            "metadata_client": metadata_client,
            "timeout_seconds": settings.timeout_seconds,
            "max_retries": settings.max_retries,
            "retry_base_seconds": settings.retry_base_seconds,
        }
        if args.archive_base_url is not None:
            client_options["base_url"] = args.archive_base_url
        with BinanceArchiveClient(**client_options) as archive_client:
            manifest_path = HistoricalDownloader(settings, archive_client).download(
                DownloadRequest(start=args.start, end=args.end)
            )
    manifest = read_manifest(manifest_path)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "source": manifest["source"] if manifest else None,
                "status": manifest["status"] if manifest else "unknown",
                "row_count": manifest["row_count"] if manifest else None,
            },
            sort_keys=True,
        )
    )
    return 0 if manifest and manifest["status"] == "completed" else 2


def _validate(args: argparse.Namespace) -> int:
    table = read_candle_parquet(args.path)
    report = validate_candles(table, args.interval)
    payload = report.to_dict()
    payload["file"] = str(args.path)
    payload["sha256"] = file_sha256(args.path)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if report.is_valid else 2


def _inspect(args: argparse.Namespace) -> int:
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    table = read_candle_parquet(args.path)
    metadata = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in (table.schema.metadata or {}).items()
    }
    payload: dict[str, Any] = {
        "file": str(args.path),
        "row_count": table.num_rows,
        "schema": str(table.schema),
        "metadata": metadata,
        "rows": table.slice(0, args.limit).to_pylist(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


def _quality_report(args: argparse.Namespace) -> int:
    policy = load_quality_policy(args.quality_config)
    engine = QualityEngine(policy)
    if args.manifest is not None:
        report = engine.validate_manifest(args.manifest)
    else:
        source = args.source or (
            "binance_spot_rest" if args.market == "spot" else "binance_usdm_futures_rest"
        )
        report = engine.validate_file(
            args.path,
            symbol=args.symbol,
            interval=args.interval,
            source=source,
            market=args.market,
            range_start=args.start,
            range_end=args.end,
        )
    report_path = engine.write_report(report, args.output_root)
    print(report.human_summary())
    print(
        json.dumps(
            {
                "report": str(report_path),
                "report_id": report.report_id,
                "dataset_version": report.dataset_version,
                "overall_status": report.overall_status.value,
            },
            sort_keys=True,
        )
    )
    return 0 if report.overall_status is not ValidationStatus.FAIL else 2


def _promote_silver(args: argparse.Namespace) -> int:
    policy = load_quality_policy(args.quality_config)
    engine = QualityEngine(policy)
    report = engine.validate_manifest(args.manifest)
    report_path = engine.write_report(report, args.quality_root)
    result = SilverPromoter(policy).promote(
        args.manifest,
        report,
        silver_root=args.silver_root,
        quarantine_root=args.quarantine_root,
    )
    print(
        json.dumps(
            {
                "promoted": result.promoted,
                "status": result.status,
                "validation_report": str(report_path),
                "validation_report_id": result.validation_report_id,
                "silver_dataset_version": result.silver_dataset_version,
                "promotion_manifest": (
                    str(result.promotion_manifest) if result.promotion_manifest else None
                ),
                "quarantine_record": (
                    str(result.quarantine_record) if result.quarantine_record else None
                ),
                "output_files": [str(path) for path in result.output_files],
                "exact_duplicates_removed": result.exact_duplicates_removed,
            },
            sort_keys=True,
        )
    )
    return 0 if result.promoted else 2


def _build_dataset(args: argparse.Namespace) -> int:
    if args.config is not None:
        dataset_config = load_dataset_config(args.config)
    elif args.silver_manifest is not None:
        dataset_config = DatasetBuildConfig(silver_manifest=args.silver_manifest)
    else:
        raise ValueError("build-dataset requires --config or --silver-manifest")
    overrides = {
        "silver_manifest": args.silver_manifest,
        "output_root": args.output_root,
        "symbol": args.symbol,
        "interval": args.interval,
        "start_time": args.start,
        "end_time": args.end,
    }
    values = dataset_config.model_dump()
    values.update({key: value for key, value in overrides.items() if value is not None})
    dataset_config = DatasetBuildConfig.model_validate(values)
    feature_config = load_feature_config(args.feature_config)
    label_config = load_label_config(args.label_config)
    result = build_gold_dataset(dataset_config, feature_config, label_config)
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "dataset": str(result.dataset_path),
                "manifest": str(result.manifest_path),
                "source_silver_version": result.source_silver_version,
                "row_count": result.row_count,
                "feature_count": len(result.feature_columns),
                "target": result.target_column,
                "reused": result.reused,
                "summary": result.summary,
            },
            sort_keys=True,
        )
    )
    return 0


def _train(args: argparse.Namespace) -> int:
    config = load_experiment_config(args.config)
    result = train_experiment(
        args.dataset_manifest,
        config,
        artifact_root=args.artifact_root,
    )
    root = (args.artifact_root or config.artifact_root).resolve()
    experiment_path = root / "experiments" / result["experiment_id"] / "experiment.json"
    print(comparison_text(result))
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "experiment": str(experiment_path),
                "status": result["status"],
                "models": list(result["models"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    result = load_experiment(args.experiment, artifact_root=args.artifact_root)
    print(comparison_text(result))
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "dataset_version": result["dataset_version"],
                "models": list(result["models"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _download_market_data(args: argparse.Namespace) -> int:
    settings = load_binance_settings(
        args.config,
        {
            "market": "usdm",
            "symbol": args.symbol,
            "interval": args.interval,
        },
    )
    kind = MarketDataKind(args.kind)
    with BinanceRestClient(settings) as client:
        table = DerivativesMarketDataClient(client.get_public_json).fetch(
            kind,
            symbol=settings.symbol,
            start=args.start,
            end=args.end,
            interval=args.interval,
        )
    manifest = ingest_public_market_data(
        table,
        kind=kind,
        symbol=settings.symbol,
        interval=None if kind is MarketDataKind.FUNDING else args.interval,
        output_root=args.output_root,
        request_start=args.start,
        request_end=args.end,
    )
    print(json.dumps({"manifest": str(manifest), "kind": kind.value, "rows": table.num_rows}))
    return 0


def _download_market_archive(args: argparse.Namespace) -> int:
    settings = load_binance_settings(
        args.config,
        {"market": "usdm", "symbol": args.symbol, "interval": args.interval},
    )
    with (
        BinanceRestClient(settings) as metadata_client,
        BinanceArchiveClient(
            raw_root=args.raw_root,
            metadata_client=metadata_client,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            retry_base_seconds=settings.retry_base_seconds,
        ) as archive_client,
    ):
        manifest = ingest_archive_market_data(
            archive_client,
            kind=MarketDataKind(args.kind),
            symbol=settings.symbol,
            interval=settings.interval,
            start=args.start,
            end=args.end,
            output_root=args.output_root,
            gap_fill_request_json=metadata_client.get_public_json,
        )
    payload = read_manifest(manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "kind": args.kind,
                "rows": payload.get("row_count") if payload else None,
                "coverage": payload.get("coverage") if payload else None,
            },
            sort_keys=True,
        )
    )
    return 0


def _build_dataset_v2(args: argparse.Namespace) -> int:
    result = build_gold_v2(
        load_gold_v2_config(args.config),
        load_label_config(args.label_config),
    )
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "dataset": str(result.dataset_path),
                "manifest": str(result.manifest_path),
                "row_count": result.row_count,
                "feature_count": len(result.feature_columns),
                "feature_groups": list(result.feature_groups),
                "reused": result.reused,
            },
            sort_keys=True,
        )
    )
    return 0


def _train_v2(args: argparse.Namespace) -> int:
    result = train_main_model_v2(
        args.dataset_manifest,
        load_experiment_config(args.config),
        artifact_root=args.artifact_root,
    )
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "selected_model": result["selected_model"],
                "ablations": list(result["ablations"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _build_dataset_v2_1(args: argparse.Namespace) -> int:
    result = build_gold_v2_1(
        load_gold_v2_1_config(args.config), load_label_config(args.label_config)
    )
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "dataset": str(result.dataset_path),
                "manifest": str(result.manifest_path),
                "row_count": result.row_count,
                "feature_count": len(result.feature_columns),
                "feature_groups": list(result.feature_groups),
                "reused": result.reused,
            },
            sort_keys=True,
        )
    )
    return 0


def _train_v2_1(args: argparse.Namespace) -> int:
    result = train_main_model_v2_1(
        args.core_dataset_manifest,
        load_experiment_config(args.config),
        derivatives_gold_manifest=args.derivatives_dataset_manifest,
        artifact_root=args.artifact_root,
    )
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "families": list(result["families"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _backtest_v2_1(args: argparse.Namespace) -> int:
    result = run_backtest_suite_v2_1(
        args.experiment,
        load_backtest_v2_1_config(args.config),
        artifact_root=args.artifact_root,
        funding_manifest=args.funding_manifest,
        execution_1m_silver_manifest=args.execution_1m_silver_manifest,
    )
    print(
        json.dumps(
            {
                "backtest_id": result["backtest_id"],
                "status": result["status"],
                "family": result["family"],
                "strategies": list(result["strategies"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _backtest_v1(args: argparse.Namespace) -> int:
    result = run_backtest_suite(
        args.experiment,
        load_backtest_config(args.config),
        artifact_root=args.artifact_root,
        funding_manifest=args.funding_manifest,
    )
    print(
        json.dumps(
            {
                "backtest_id": result["backtest_id"],
                "status": result["status"],
                "strategies": list(result["strategies"]),
            },
            sort_keys=True,
        )
    )
    return 0


def _walk_forward(args: argparse.Namespace) -> int:
    result = run_walk_forward(
        load_walk_forward_config(args.config),
        resume=args.resume,
        plan_only=args.plan,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _harden_walk_forward(args: argparse.Namespace) -> int:
    result = run_hardened_walk_forward(
        load_hardening_config(args.config),
        resume=args.resume,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _walk_forward_report(args: argparse.Namespace) -> int:
    result = read_manifest(args.summary.resolve())
    if result is None or result.get("status") != "complete":
        raise ValueError("a completed walk-forward summary is required")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _compare_candidates(args: argparse.Namespace) -> int:
    result = compare_walk_forward_candidates(
        args.primary_summary,
        args.derivatives_summary,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _compare_hardened_candidates(args: argparse.Namespace) -> int:
    result = compare_hardened_candidates(
        args.primary_summary,
        args.derivatives_summary,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def _verify_hardened(args: argparse.Namespace) -> int:
    result = verify_hardened_runs(
        args.primary_summary,
        args.derivatives_summary,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(args.log_level)
    if args.command == "download":
        return _download(args)
    if args.command == "download-archive":
        return _download_archive(args)
    if args.command == "validate":
        return _validate(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "quality-report":
        return _quality_report(args)
    if args.command == "promote-silver":
        return _promote_silver(args)
    if args.command == "build-dataset":
        return _build_dataset(args)
    if args.command == "train":
        return _train(args)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "download-market-data":
        return _download_market_data(args)
    if args.command == "download-market-archive":
        return _download_market_archive(args)
    if args.command == "build-dataset-v2":
        return _build_dataset_v2(args)
    if args.command == "train-v2":
        return _train_v2(args)
    if args.command == "build-dataset-v2-1":
        return _build_dataset_v2_1(args)
    if args.command == "train-v2-1":
        return _train_v2_1(args)
    if args.command == "backtest-v2-1":
        return _backtest_v2_1(args)
    if args.command == "backtest-v1":
        return _backtest_v1(args)
    if args.command == "walk-forward":
        return _walk_forward(args)
    if args.command == "harden-walk-forward":
        return _harden_walk_forward(args)
    if args.command == "walk-forward-report":
        return _walk_forward_report(args)
    if args.command == "compare-candidates":
        return _compare_candidates(args)
    if args.command == "compare-hardened-candidates":
        return _compare_hardened_candidates(args)
    if args.command == "verify-hardened":
        return _verify_hardened(args)
    if args.command == "phase6-research":
        result = run_phase6_research(load_phase6_config(args.config))
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "phase7-research":
        config = load_phase7_config(args.config)
        if args.plan:
            result = phase7_plan(config)
        elif args.validate_config:
            result = validate_phase7_configuration(config)
        elif args.dry_run:
            result = phase7_dry_run(config)
        elif args.test_universe:
            result = test_phase7_universe(config)
        else:
            from crypto_ai.phase7.pipeline import run_phase7_cloud

            result = run_phase7_cloud(config, stage=args.stage, resume=args.resume)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "context":
        config = load_context_config(args.config)
        if args.context_command == "status":
            result = context_status(config)
        elif args.context_command == "fear-greed":
            if args.plan:
                result = fear_greed_plan(config)
            elif args.action == "fetch":
                result = collect_fear_greed(config, force_refresh=args.force_refresh)
            else:
                raise ValueError("context fear-greed requires --plan or the fetch action")
        elif args.context_command == "oi":
            if args.plan:
                result = open_interest_plan(config, symbol=args.symbol)
            elif args.action == "recent":
                result = collect_open_interest_recent(
                    config,
                    symbol=args.symbol,
                    start=args.start,
                    end=args.end,
                )
            elif args.action == "snapshot":
                result = collect_open_interest_snapshot(config, symbol=args.symbol)
            else:
                raise ValueError("context oi requires --plan, recent, or snapshot")
        else:  # pragma: no cover - argparse requires a known context command
            raise AssertionError(f"Unhandled context command: {args.context_command}")
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
