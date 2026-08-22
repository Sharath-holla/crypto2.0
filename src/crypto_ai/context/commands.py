from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_ai.context.alternative_me import (
    FEAR_GREED_AVAILABILITY_POLICY,
    FEAR_GREED_ENDPOINT,
    AlternativeMeFearGreedProvider,
)
from crypto_ai.context.base import RetryingPublicJsonClient
from crypto_ai.context.binance_open_interest import (
    OI_COVERAGE_LIMITATION,
    OI_CURRENT_ENDPOINT,
    OI_HISTORY_ENDPOINT,
    BinanceOpenInterestProvider,
)
from crypto_ai.context.config import ContextConfig
from crypto_ai.context.models import CollectionResult
from crypto_ai.context.storage import ContextStore


def _result_payload(result: CollectionResult) -> dict[str, Any]:
    return {
        "dataset_version": result.dataset_version,
        "dataset_path": str(result.dataset_path),
        "manifest_path": str(result.manifest_path),
        "raw_path": str(result.raw_path),
        "row_count": result.row_count,
        "duplicate_count": result.duplicate_count,
        "reused": result.reused,
        "network_scope": "PUBLIC_MARKET_DATA_ONLY",
        "training_enabled": False,
    }


def _latest_status(store: ContextStore) -> dict[str, Any] | None:
    latest = store.latest_manifest()
    if latest is None:
        return None
    path, manifest = latest
    return {
        "manifest": str(path),
        "dataset_version": manifest["dataset_version"],
        "row_count": manifest["row_count"],
        "actual_start": manifest["actual_start"],
        "actual_end": manifest["actual_end"],
        "training_eligibility": manifest["training_eligibility"],
        "training_eligible": manifest["training_eligible"],
    }


def context_status(config: ContextConfig) -> dict[str, Any]:
    fear_store = ContextStore(
        config.data_root,
        provider_id="alternative_me",
        dataset_name="history",
        key_columns=("scope", "provider_timestamp"),
    )
    oi_status: dict[str, Any] = {}
    period_minutes = {
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "1d": 1_440,
    }[config.open_interest.period]
    for symbol in config.open_interest.symbols:
        history_store = ContextStore(
            config.data_root,
            provider_id="binance_open_interest",
            dataset_name=f"recent_history/{symbol.lower()}/{config.open_interest.period}",
            key_columns=("symbol", "period", "provider_timestamp"),
            expected_step=timedelta(minutes=period_minutes),
        )
        snapshot_store = ContextStore(
            config.data_root,
            provider_id="binance_open_interest",
            dataset_name=f"forward_snapshots/{symbol.lower()}",
            key_columns=("symbol", "provider_timestamp"),
        )
        oi_status[symbol] = {
            "recent_history": _latest_status(history_store),
            "forward_snapshots": _latest_status(snapshot_store),
        }
    return {
        "status": "PASS",
        "configuration_hash": config.configuration_hash,
        "data_root": str(config.data_root.resolve()),
        "network_used": False,
        "phase7_baseline_context": "MARKET_DATA_ONLY",
        "research_cutoff_exclusive": config.research_cutoff.isoformat(),
        "july_2026_used": config.july_2026_used,
        "prospective_holdout_start": config.prospective_holdout_start.isoformat(),
        "prospective_holdout_used": config.prospective_holdout_used,
        "providers": {
            "alternative_me": {
                "status": "IMPLEMENTED",
                "training_enabled": config.alternative_me.training_enabled,
                "latest_dataset": _latest_status(fear_store),
            },
            "binance_open_interest": {
                "status": "IMPLEMENTED",
                "training_enabled": config.open_interest.training_enabled,
                "datasets": oi_status,
            },
            "cryptopanic": {"status": "NOT_IMPLEMENTED", "enabled": False},
            "arkham": {"status": "NOT_IMPLEMENTED", "enabled": False},
            "reddit": {"status": "NOT_IMPLEMENTED", "enabled": False},
        },
    }


def fear_greed_plan(config: ContextConfig) -> dict[str, Any]:
    return {
        "status": "PLAN_ONLY",
        "provider": "alternative_me",
        "endpoint": FEAR_GREED_ENDPOINT,
        "request_parameters": {"limit": 0, "format": "json"},
        "scope": "GLOBAL_MARKET_CONTEXT",
        "availability_policy": FEAR_GREED_AVAILABILITY_POLICY,
        "historical_training_eligible": False,
        "phase7_training_enabled": config.alternative_me.training_enabled,
        "network_used": False,
        "output_root": str((config.data_root / "alternative_me").resolve()),
    }


def open_interest_plan(
    config: ContextConfig,
    *,
    symbol: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    captured = (now or datetime.now(UTC)).astimezone(UTC)
    return {
        "status": "PLAN_ONLY",
        "provider": "binance_open_interest",
        "symbol": symbol.upper(),
        "period": config.open_interest.period,
        "current_endpoint": OI_CURRENT_ENDPOINT,
        "history_endpoint": OI_HISTORY_ENDPOINT,
        "default_recent_start": (
            captured - timedelta(days=config.open_interest.recent_history_days)
        ).isoformat(),
        "default_recent_end": captured.isoformat(),
        "official_coverage_limitation": OI_COVERAGE_LIMITATION,
        "training_eligibility": "FORWARD_ONLY",
        "phase7_training_enabled": config.open_interest.training_enabled,
        "network_used": False,
        "output_root": str((config.data_root / "binance_open_interest").resolve()),
    }


def collect_fear_greed(config: ContextConfig, *, force_refresh: bool = False) -> dict[str, Any]:
    store = ContextStore(
        config.data_root,
        provider_id="alternative_me",
        dataset_name="history",
        key_columns=("scope", "provider_timestamp"),
    )
    latest = store.latest_manifest()
    if latest is not None and not force_refresh:
        path, manifest = latest
        ingested_at = datetime.fromisoformat(str(manifest["ingested_at"])).astimezone(UTC)
        if datetime.now(UTC) - ingested_at <= timedelta(
            hours=config.alternative_me.cache_max_age_hours
        ):
            result = CollectionResult(
                dataset_version=str(manifest["dataset_version"]),
                dataset_path=Path(manifest["dataset_path"]),
                manifest_path=path,
                raw_path=Path(manifest["raw_path"]),
                row_count=int(manifest["row_count"]),
                duplicate_count=int(manifest.get("duplicate_count", 0)),
                reused=True,
            )
            return {**_result_payload(result), "network_used": False, "cache_status": "VALID"}
    config.assert_network_allowed()
    http = config.http
    with RetryingPublicJsonClient(
        config.alternative_me.base_url,
        timeout_seconds=http.timeout_seconds,
        max_retries=http.max_retries,
        retry_base_seconds=http.retry_base_seconds,
    ) as client:
        result = AlternativeMeFearGreedProvider(client.get_json).collect_history(
            store=store,
            config_hash=config.configuration_hash,
        )
    return {**_result_payload(result), "network_used": True, "cache_status": "REFRESHED"}


def collect_open_interest_recent(
    config: ContextConfig,
    *,
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    config.assert_network_allowed()
    captured = datetime.now(UTC)
    requested_end = (end or captured).astimezone(UTC)
    requested_start = (
        start or requested_end - timedelta(days=config.open_interest.recent_history_days)
    ).astimezone(UTC)
    period = config.open_interest.period
    minutes = {
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "1d": 1_440,
    }[period]
    store = ContextStore(
        config.data_root,
        provider_id="binance_open_interest",
        dataset_name=f"recent_history/{symbol.lower()}/{period}",
        key_columns=("symbol", "period", "provider_timestamp"),
        expected_step=timedelta(minutes=minutes),
    )
    http = config.http
    with RetryingPublicJsonClient(
        config.open_interest.base_url,
        timeout_seconds=http.timeout_seconds,
        max_retries=http.max_retries,
        retry_base_seconds=http.retry_base_seconds,
    ) as client:
        result = BinanceOpenInterestProvider(client.get_json).collect_recent_history(
            symbol=symbol,
            period=period,
            start=requested_start,
            end=requested_end,
            store=store,
            config_hash=config.configuration_hash,
            ingested_at=captured,
            limit=config.open_interest.history_limit,
            provider_history_days=config.open_interest.recent_history_days,
        )
    return {**_result_payload(result), "network_used": True}


def collect_open_interest_snapshot(config: ContextConfig, *, symbol: str) -> dict[str, Any]:
    config.assert_network_allowed()
    store = ContextStore(
        config.data_root,
        provider_id="binance_open_interest",
        dataset_name=f"forward_snapshots/{symbol.lower()}",
        key_columns=("symbol", "provider_timestamp"),
    )
    http = config.http
    with RetryingPublicJsonClient(
        config.open_interest.base_url,
        timeout_seconds=http.timeout_seconds,
        max_retries=http.max_retries,
        retry_base_seconds=http.retry_base_seconds,
    ) as client:
        result = BinanceOpenInterestProvider(client.get_json).collect_snapshot(
            symbol=symbol,
            store=store,
            config_hash=config.configuration_hash,
        )
    return {**_result_payload(result), "network_used": True}
