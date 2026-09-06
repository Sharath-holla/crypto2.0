from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import write_immutable
from crypto_ai.phase7 import pipeline
from crypto_ai.phase7.acquisition import (
    AcquisitionPaths,
    QualityGateRejected,
    _promote_candles,
    load_candle_family,
)
from crypto_ai.phase7.config import FeatureConfig, TargetConfig
from crypto_ai.phase7.features import (
    _asof_higher_context,
    build_higher_timeframe_context,
    generate_multiasset_features,
)
from crypto_ai.phase7.registry import build_symbol_registry
from crypto_ai.phase7.targets import generate_multiasset_targets
from tests.factories import make_candle
from tests.phase7.test_archive_missing_reconciliation import START, _archive, _config

DAY = timedelta(days=1)


def _silver(tmp_path: Path) -> Path:
    config = _config(tmp_path)
    manifest, _, _ = _archive(tmp_path, missing=())
    return _promote_candles(config, AcquisitionPaths.from_config(config), manifest)


def _synthetic_silver(
    tmp_path: Path,
    *,
    symbol: str,
    interval: str,
    start: datetime,
    row_count: int,
) -> Path:
    interval_minutes = {"5m": 5, "12h": 720, "1d": 1_440}[interval]
    interval_delta = timedelta(minutes=interval_minutes)
    root = tmp_path / f"silver-{symbol}-{interval}"
    output = root / "dataset" / f"symbol={symbol}" / f"interval={interval}" / "part-test.parquet"
    checksum = write_immutable(
        output,
        candles_to_table(
            [
                make_candle(
                    index,
                    start=start,
                    interval_minutes=interval_minutes,
                    symbol=symbol,
                    source="binance_usdm_futures_archive",
                )
                for index in range(row_count)
            ]
        ),
        metadata={"symbol": symbol, "interval": interval, "market": "usdm"},
    )
    source = tmp_path / f"source-{symbol}-{interval}.json"
    write_manifest(
        source,
        {
            "symbol": symbol,
            "interval": interval,
            "start": start.isoformat(),
            "end": (start + row_count * interval_delta).isoformat(),
        },
    )
    silver = root / "manifests" / "silver.json"
    write_manifest(
        silver,
        {
            "symbol": symbol,
            "interval": interval,
            "quality_status": "PASS",
            "source_manifest": str(source.resolve()),
            "output_files": [
                {
                    "file": output.relative_to(root).as_posix(),
                    "sha256": checksum,
                }
            ],
        },
    )
    return silver


def _lifecycle_registry(start: datetime, end: datetime):
    research_cutoff = end + 2 * DAY
    return build_symbol_registry(
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                }
            ]
        },
        [
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": start,
                "last_market_data_time": research_cutoff - timedelta(minutes=5),
                "available_from": start,
                "available_intervals": ["5m", "12h", "1d"],
            },
            {
                "symbol": "HNTUSDT",
                "base_asset": "HNT",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": start,
                "last_market_data_time": end - timedelta(minutes=5),
                "available_from": start,
                "available_until": end,
                "available_intervals": ["5m", "12h", "1d"],
            },
        ],
        observed_at=end,
        research_cutoff=research_cutoff,
    )


def test_a_entire_gold_chunk_before_validated_htf_availability_is_absent(
    tmp_path: Path,
) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START - 2 * DAY,
        end=START,
        allow_lifecycle_absence=True,
    )

    assert table is None


def test_b_gold_chunk_crossing_first_htf_availability_loads_only_overlap(
    tmp_path: Path,
) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START - DAY,
        end=START + DAY,
        allow_lifecycle_absence=True,
    )

    assert table is not None
    assert table.num_rows == 1
    assert table.column("open_time")[0].as_py() == START


def test_c_gold_chunk_inside_validated_htf_availability_loads_normally(
    tmp_path: Path,
) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START + 2 * DAY,
        end=START + 4 * DAY,
        allow_lifecycle_absence=True,
    )

    assert table is not None
    assert table.num_rows == 2


def test_d_true_interior_htf_gap_fails_quality_promotion(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest, _, _ = _archive(tmp_path, missing=(3,))

    with pytest.raises(QualityGateRejected):
        _promote_candles(config, AcquisitionPaths.from_config(config), manifest)


def test_e_corrupt_htf_manifest_fails_closed(tmp_path: Path) -> None:
    silver = _silver(tmp_path)
    payload = json.loads(silver.read_text(encoding="utf-8"))
    payload["quality_status"] = "FAIL"
    silver.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Ineligible Silver manifest"):
        load_candle_family({"TESTUSDT": str(silver)}, interval="1d", start=START, end=START + DAY)


def test_f_unavailable_symbol_timeframe_is_not_silently_accepted() -> None:
    with pytest.raises(ValueError, match="No 1d candle tables"):
        load_candle_family(
            {},
            interval="1d",
            start=datetime(2020, 1, 1, tzinfo=UTC),
            end=datetime(2020, 2, 1, tzinfo=UTC),
            allow_lifecycle_absence=True,
        )


def test_g_normal_long_history_manifest_remains_unchanged(tmp_path: Path) -> None:
    silver = _silver(tmp_path)

    default = load_candle_family(
        {"TESTUSDT": str(silver)}, interval="1d", start=START, end=START + 8 * DAY
    )
    explicit = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START,
        end=START + 8 * DAY,
        allow_lifecycle_absence=True,
    )

    assert default is not None and explicit is not None
    assert default.equals(explicit)


def test_h_late_htf_first_row_cannot_leak_before_completed_candle(
    tmp_path: Path,
) -> None:
    silver = _silver(tmp_path)
    candles = load_candle_family(
        {"TESTUSDT": str(silver)}, interval="1d", start=START, end=START + 8 * DAY
    )
    assert candles is not None
    context = build_higher_timeframe_context(None, candles)
    assert context is not None
    availability = int((START + DAY).timestamp() * 1_000_000)

    values, _ = _asof_higher_context(
        np.asarray(["TESTUSDT", "TESTUSDT"], dtype=object),
        np.asarray([availability - 1, availability], dtype=np.int64),
        context,
    )

    assert np.isnan(values["htf_1d_range_pct"][0])
    assert np.isfinite(values["htf_1d_range_pct"][1])


def test_in_range_missing_output_file_is_not_lifecycle_absence(tmp_path: Path) -> None:
    silver = _silver(tmp_path)
    payload = read_manifest(silver)
    assert payload is not None
    output = silver.parent.parent / str(payload["output_files"][0]["file"])
    output.unlink()

    with pytest.raises(ValueError, match="Silver checksum mismatch"):
        load_candle_family(
            {"TESTUSDT": str(silver)},
            interval="1d",
            start=START,
            end=START + DAY,
            allow_lifecycle_absence=True,
        )


def test_partial_delisting_overlap_loads_only_validated_lifecycle_rows(tmp_path: Path) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START + 7 * DAY,
        end=START + 10 * DAY,
        allow_lifecycle_absence=True,
    )

    assert table is not None
    assert table.num_rows == 1
    assert table.column("open_time")[0].as_py() == START + 7 * DAY


def test_wholly_post_delisting_window_is_lifecycle_absence(tmp_path: Path) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START + 8 * DAY,
        end=START + 9 * DAY,
        allow_lifecycle_absence=True,
    )

    assert table is None


def test_outside_lifecycle_still_fails_without_explicit_contract(tmp_path: Path) -> None:
    silver = _silver(tmp_path)

    with pytest.raises(ValueError, match="lifecycle overlap"):
        load_candle_family(
            {"TESTUSDT": str(silver)},
            interval="1d",
            start=START + 8 * DAY,
            end=START + 9 * DAY,
        )


def test_corrupt_active_lifecycle_partition_fails_closed(tmp_path: Path) -> None:
    silver = _silver(tmp_path)
    payload = read_manifest(silver)
    assert payload is not None
    output = silver.parent.parent / str(payload["output_files"][0]["file"])
    output.write_bytes(b"corrupt parquet")

    with pytest.raises(ValueError, match="Silver checksum mismatch"):
        load_candle_family(
            {"TESTUSDT": str(silver)},
            interval="1d",
            start=START,
            end=START + DAY,
            allow_lifecycle_absence=True,
        )


def test_active_lifecycle_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    silver = _silver(tmp_path)
    payload = read_manifest(silver)
    assert payload is not None
    payload["output_files"][0]["sha256"] = "0" * 64
    write_manifest(silver, payload)

    with pytest.raises(ValueError, match="Silver checksum mismatch"):
        load_candle_family(
            {"TESTUSDT": str(silver)},
            interval="1d",
            start=START,
            end=START + DAY,
            allow_lifecycle_absence=True,
        )


@pytest.mark.parametrize(
    ("interval", "interval_delta"),
    [
        ("5m", timedelta(minutes=5)),
        ("12h", timedelta(hours=12)),
        ("1d", DAY),
    ],
)
def test_interval_lifecycle_end_is_half_open(
    tmp_path: Path,
    interval: str,
    interval_delta: timedelta,
) -> None:
    silver = _synthetic_silver(
        tmp_path,
        symbol="HNTUSDT",
        interval=interval,
        start=START,
        row_count=4,
    )
    lifecycle_end = START + 4 * interval_delta

    crossing = load_candle_family(
        {"HNTUSDT": str(silver)},
        interval=interval,
        start=lifecycle_end - interval_delta,
        end=lifecycle_end + interval_delta,
        allow_lifecycle_absence=True,
    )
    after = load_candle_family(
        {"HNTUSDT": str(silver)},
        interval=interval,
        start=lifecycle_end,
        end=lifecycle_end + interval_delta,
        allow_lifecycle_absence=True,
    )

    assert crossing is not None
    assert crossing.num_rows == 1
    assert crossing.column("open_time")[0].as_py() == lifecycle_end - interval_delta
    assert after is None


def test_post_delisting_symbol_does_not_block_active_symbol_family(tmp_path: Path) -> None:
    hnt = _synthetic_silver(
        tmp_path,
        symbol="HNTUSDT",
        interval="5m",
        start=START,
        row_count=4,
    )
    btc = _synthetic_silver(
        tmp_path,
        symbol="BTCUSDT",
        interval="5m",
        start=START,
        row_count=12,
    )

    table = load_candle_family(
        {"HNTUSDT": str(hnt), "BTCUSDT": str(btc)},
        interval="5m",
        start=START + timedelta(minutes=30),
        end=START + timedelta(minutes=45),
        allow_lifecycle_absence=True,
    )

    assert table is not None
    assert table.num_rows == 3
    assert set(table.column("symbol").to_pylist()) == {"BTCUSDT"}


def test_target_path_crossing_delisting_is_invalidated_without_synthetic_rows() -> None:
    lifecycle_end = START + timedelta(minutes=6 * 60)
    candles = candles_to_table(
        [
            make_candle(
                index,
                start=START,
                symbol="HNTUSDT",
                source="binance_usdm_futures_archive",
            )
            for index in range(72)
        ]
    )
    registry = _lifecycle_registry(START, lifecycle_end)
    features = generate_multiasset_features(
        candles,
        registry=registry,
        config=FeatureConfig(
            correlation_window_rows=12,
            liquidity_window_rows=12,
            volatility_window_rows=12,
            daily_volatility_rows=12,
            seven_day_volatility_rows=24,
            include_12h=False,
            include_1d=False,
            include_derivatives=False,
        ),
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=TargetConfig(),
        research_cutoff=lifecycle_end + DAY,
    ).table

    assert targets.num_rows
    assert max(targets.column("label_end_time").to_pylist()) < lifecycle_end
    assert max(targets.column("entry_time").to_pylist()) < lifecycle_end


def test_delisted_symbol_is_historical_but_excluded_from_later_market_context() -> None:
    lifecycle_end = START + timedelta(minutes=60)
    registry = _lifecycle_registry(START, lifecycle_end)
    candles = candles_to_table(
        [
            make_candle(index, start=START, symbol=symbol)
            for symbol in ("BTCUSDT", "HNTUSDT")
            for index in range(24)
        ]
    )
    features = generate_multiasset_features(
        candles,
        registry=registry,
        config=FeatureConfig(
            correlation_window_rows=12,
            liquidity_window_rows=12,
            volatility_window_rows=12,
            daily_volatility_rows=12,
            seven_day_volatility_rows=24,
            include_12h=False,
            include_1d=False,
            include_derivatives=False,
        ),
    )
    table = features.table
    symbols = np.asarray(table.column("symbol").to_pylist(), dtype=object)
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    end_us = int(lifecycle_end.timestamp() * 1_000_000)
    before = (symbols == "HNTUSDT") & (times < end_us)
    after = (symbols == "HNTUSDT") & (times >= end_us)

    assert np.any(before) and np.any(after)
    assert all("HNTUSDT" in features.market_membership[int(value)] for value in times[before])
    assert all("HNTUSDT" not in features.market_membership[int(value)] for value in times[after])
    assert all("BTCUSDT" in features.market_membership[int(value)] for value in times[after])
    listing_age = np.asarray(table.column("listing_age_days").to_pylist(), dtype=np.float64)
    assert np.all(np.isfinite(listing_age[before]))
    assert np.all(np.isnan(listing_age[after]))


def test_htf_context_expires_at_valid_until(tmp_path: Path) -> None:
    silver = _silver(tmp_path)
    candles = load_candle_family(
        {"TESTUSDT": str(silver)}, interval="1d", start=START, end=START + 8 * DAY
    )
    assert candles is not None
    context = build_higher_timeframe_context(None, candles)
    assert context is not None
    valid_until = int((START + 2 * DAY).timestamp() * 1_000_000)

    values, _ = _asof_higher_context(
        np.asarray(["TESTUSDT", "TESTUSDT"], dtype=object),
        np.asarray([valid_until - 1, valid_until], dtype=np.int64),
        context.slice(0, 1),
    )

    assert np.isfinite(values["htf_1d_range_pct"][0])
    assert np.isnan(values["htf_1d_range_pct"][1])


def test_gold_refuses_legacy_data_manifest_without_full_coverage_contract(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    with pytest.raises(ValueError, match="full causal candle-coverage contract"):
        pipeline._gold_chunk(
            config,
            object(),  # type: ignore[arg-type]
            {},
            START,
            START + DAY,
        )
