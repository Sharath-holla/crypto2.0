from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.checks import validate_partition
from crypto_ai.data.quality.models import ValidationContext, ValidationStatus
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import acquisition
from crypto_ai.phase7.acquisition import (
    AcquisitionPaths,
    QualityGateRejected,
    ReconciliationAttempt,
    _contiguous_partition_groups,
    _promote_causal_segments,
)
from crypto_ai.phase7.config import FeatureConfig, Phase7Config
from crypto_ai.phase7.features import (
    _asof_higher_context,
    build_higher_timeframe_context,
    generate_multiasset_features,
)
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry
from crypto_ai.phase7.segments import (
    AcquisitionOutcome,
    AcquisitionStatus,
    CandleFamilyAcquisition,
    CausalDataGap,
    ReconciliationStatus,
)
from crypto_ai.phase7.targets import generate_multiasset_targets
from crypto_ai.phase7.universe import select_fold_active_universe
from tests.factories import make_candle
from tests.phase7.test_cold_start_universe import (
    NEW_EVIDENCE,
    _core_context,
    _descriptor,
    _registry,
)
from tests.phase7.test_cold_start_universe import (
    _config as universe_config,
)

DAY = timedelta(days=1)
GAP_START = datetime(2024, 12, 1, tzinfo=UTC)
GAP_END = GAP_START + DAY


def _gap(
    tmp_path: Path,
    *,
    symbol: str = "NEWUSDT",
    start: datetime = GAP_START,
    interval: str = "1d",
) -> CausalDataGap:
    evidence: dict[str, Path] = {}
    for name in ("source", "quality", "quarantine", "rest", "comparison"):
        path = tmp_path / f"{symbol.lower()}-{name}.json"
        path.write_text(f'{{"evidence":"{name}"}}\n', encoding="utf-8")
        evidence[name] = path
    end = start + timedelta(milliseconds=86_400_000 if interval == "1d" else 300_000)
    return CausalDataGap(
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        partition=f"{int(start.timestamp() * 1000)}-{int(end.timestamp() * 1000)}",
        failed_checks=("taker_buy_base_exceeds_volume",),
        source_manifest=str(evidence["source"]),
        source_manifest_sha256=file_sha256(evidence["source"]),
        quality_report=str(evidence["quality"]),
        quality_report_sha256=file_sha256(evidence["quality"]),
        quarantine=str(evidence["quarantine"]),
        quarantine_sha256=file_sha256(evidence["quarantine"]),
        rest_manifest=str(evidence["rest"]),
        rest_manifest_sha256=file_sha256(evidence["rest"]),
        comparison_report=str(evidence["comparison"]),
        comparison_report_sha256=file_sha256(evidence["comparison"]),
        reconciliation_status=ReconciliationStatus.IDENTICAL_INVALID,
    )


def _fold_membership(
    tmp_path: Path,
    *,
    train_end: datetime,
    required_start: datetime,
    required_end: datetime,
    gap: CausalDataGap | None,
    history_days: float | None = None,
):
    registry = _registry()
    config = universe_config()
    core, policy, core_descriptors = _core_context(registry, config)
    descriptor = _descriptor("NEWUSDT", train_end, NEW_EVIDENCE)
    if history_days is not None:
        descriptor = descriptor.model_copy(update={"history_days": history_days})
    return select_fold_active_universe(
        registry,
        [*core_descriptors, descriptor],
        fold_id="causal-segment-test",
        train_end=train_end,
        core_universe=core,
        expansion_policy=policy,
        config=config,
        research_view="EXPANDING",
        unusable_segments=(() if gap is None else (gap,)),
        required_start=required_start,
        required_end=required_end,
    )


def _fake_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    strict: bool = False,
) -> CandleFamilyAcquisition:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = start + DAY
    records = []
    exchange = []
    for symbol in ("BADUSDT", "LATERUSDT"):
        exchange.append(
            {
                "symbol": symbol,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }
        )
        records.append(
            {
                "symbol": symbol,
                "first_market_data_time": start,
                "last_market_data_time": end - timedelta(minutes=5),
                "available_intervals": ["5m", "12h", "1d"],
            }
        )
    from crypto_ai.phase7.registry import build_symbol_registry

    registry = build_symbol_registry(
        {"symbols": exchange},
        records,
        observed_at=end,
        research_cutoff=end + DAY,
    )
    gap = _gap(tmp_path, symbol="BADUSDT", start=start)

    class FakeArchiveClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def inspect_interval_bounds(self, **_: object):
            return SimpleNamespace(first_open_time=start, end_exclusive=end)

    class FakeDownloader:
        def __init__(self, settings: object, *_: object) -> None:
            self.symbol = str(settings.symbol)  # type: ignore[attr-defined]

        def download(self, _request: object) -> Path:
            return tmp_path / f"{self.symbol}-bronze.json"

    monkeypatch.setattr(Phase7Config, "assert_cloud_execution_allowed", lambda _: None)
    monkeypatch.setattr(acquisition, "BinanceArchiveClient", FakeArchiveClient)
    monkeypatch.setattr(acquisition, "HistoricalDownloader", FakeDownloader)
    monkeypatch.setattr(
        acquisition,
        "_candle_settings",
        lambda *_args, symbol, **_kwargs: SimpleNamespace(
            symbol=symbol,
            timeout_seconds=1.0,
            max_retries=0,
            retry_base_seconds=0.0,
        ),
    )

    def promote(_config: object, _paths: object, manifest: Path) -> Path:
        if manifest.name.startswith("BADUSDT"):
            raise QualityGateRejected(
                manifest,
                SimpleNamespace(overall_status=ValidationStatus.FAIL),  # type: ignore[arg-type]
            )
        return tmp_path / f"{manifest.stem}-silver.json"

    monkeypatch.setattr(acquisition, "_promote_candles", promote)
    monkeypatch.setattr(
        acquisition,
        "_attempt_archive_reconciliation",
        lambda *_args: ReconciliationAttempt(
            segment_source_manifest=tmp_path / "BADUSDT-bronze.json",
            gaps=(gap,),
        ),
    )
    monkeypatch.setattr(
        acquisition,
        "_promote_causal_segments",
        lambda *_args: tmp_path / "BADUSDT-segmented-silver.json",
    )
    return acquisition.acquire_candle_family(
        Phase7Config(),
        registry,
        symbols=("BADUSDT", "LATERUSDT"),
        interval="1d",
        start=start,
        end=end,
        strict_symbols=frozenset({"BADUSDT"}) if strict else frozenset(),
    )


def test_01_structurally_impossible_row_remains_fail() -> None:
    start = datetime(2023, 11, 30, tzinfo=UTC)
    candle = replace(
        make_candle(start=start, interval_minutes=1_440, symbol="DYDXUSDT"),
        base_volume=Decimal("24048704.1"),
        taker_buy_base_volume=Decimal("27400442.6"),
    )
    result = validate_partition(
        candles_to_table([candle]),
        ValidationContext(
            symbol="DYDXUSDT",
            interval="1d",
            partition="1701302400000-1701388800000",
            range_start=start,
            range_end=start + DAY,
        ),
    )
    failed = {check.check_name for check in result.checks if check.status is ValidationStatus.FAIL}
    assert result.status is ValidationStatus.FAIL
    assert failed == {"taker_buy_base_exceeds_volume"}


def test_02_rejected_partition_cannot_enter_segmented_silver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = AcquisitionPaths.from_config(
        Phase7Config().model_copy(
            update={"paths": Phase7Config().paths.model_copy(update={"data_root": tmp_path})}
        )
    )
    start = datetime(2023, 11, 29, tzinfo=UTC)
    partitions = [
        {
            "partition_key": f"p{index}",
            "start": (start + index * DAY).isoformat(),
            "end": (start + (index + 1) * DAY).isoformat(),
            "status": "complete",
            "row_count": 1,
            "file": f"date={start.date().isoformat()}/p{index}.parquet",
        }
        for index in range(3)
    ]
    source = tmp_path / "source.json"
    write_manifest(
        source,
        {
            "source": "binance_public_archive",
            "market": "usdm",
            "symbol": "DYDXUSDT",
            "interval": "1d",
            "partitions": partitions,
        },
    )
    gap = _gap(tmp_path, symbol="DYDXUSDT", start=start + DAY)
    gap = gap.model_copy(
        update={
            "partition": "p1",
            "source_manifest": str(source),
            "source_manifest_sha256": file_sha256(source),
        }
    )
    promoted_partitions: list[tuple[str, ...]] = []

    def promote(_config: object, _paths: object, bronze: Path) -> Path:
        payload = read_manifest(bronze)
        assert payload is not None
        keys = tuple(str(item["partition_key"]) for item in payload["partitions"])
        promoted_partitions.append(keys)
        silver = paths.silver / "manifests" / f"silver-{len(promoted_partitions)}.json"
        write_manifest(
            silver,
            {"quality_status": "PASS", "validation_report_id": f"r{len(promoted_partitions)}"},
        )
        return silver

    monkeypatch.setattr(acquisition, "_promote_candles", promote)
    group_path = _promote_causal_segments(
        Phase7Config(),
        paths,
        ReconciliationAttempt(segment_source_manifest=source, gaps=(gap,)),
    )
    group = read_manifest(group_path)
    assert group is not None
    assert promoted_partitions == [("p0",), ("p2",)]
    assert group["corrupt_rows_promoted"] is False
    assert [segment["position"] for segment in group["segments"]] == [1, 2]


def test_03_corruption_evidence_hashes_are_stable(tmp_path: Path) -> None:
    gap = _gap(tmp_path)
    before = {
        path: file_sha256(Path(path))
        for path in (
            gap.source_manifest,
            gap.quality_report,
            gap.quarantine,
            gap.rest_manifest,
            gap.comparison_report,
        )
    }
    _ = gap.model_dump(mode="json")
    assert {path: file_sha256(Path(path)) for path in before} == before


def test_04_rejected_candidate_does_not_abort_later_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _fake_acquisition(tmp_path, monkeypatch)
    assert [item.symbol for item in result.outcomes] == ["BADUSDT", "LATERUSDT"]
    assert result.outcomes[1].status is AcquisitionStatus.VALID


def test_05_discovery_output_records_typed_rejected_segment(tmp_path: Path) -> None:
    gap = _gap(tmp_path)
    result = CandleFamilyAcquisition(
        (
            AcquisitionOutcome(
                symbol=gap.symbol,
                interval=gap.interval,
                status=AcquisitionStatus.QUALITY_REJECTED_SEGMENT,
                silver_manifest=str(tmp_path / "segment-group.json"),
                reason="identical structurally invalid archive and REST row",
                gaps=(gap,),
            ),
        )
    ).model_dump()
    assert result["outcomes"][0]["status"] == "QUALITY_REJECTED_SEGMENT"  # type: ignore[index]
    assert result["unusable_segments"][0]["failed_checks"] == [  # type: ignore[index]
        "taker_buy_base_exceeds_volume"
    ]


def test_06_fold_before_gap_is_not_disqualified(tmp_path: Path) -> None:
    gap = _gap(tmp_path)
    membership = _fold_membership(
        tmp_path,
        train_end=datetime(2024, 7, 1, tzinfo=UTC),
        required_start=datetime(2024, 1, 1, tzinfo=UTC),
        required_end=datetime(2024, 11, 1, tzinfo=UTC),
        gap=gap,
    )
    assert "NEWUSDT" in membership.active_symbols


def test_07_fold_crossing_gap_rejects_symbol(tmp_path: Path) -> None:
    gap = _gap(tmp_path)
    membership = _fold_membership(
        tmp_path,
        train_end=datetime(2024, 7, 1, tzinfo=UTC),
        required_start=datetime(2024, 1, 1, tzinfo=UTC),
        required_end=datetime(2025, 1, 1, tzinfo=UTC),
        gap=gap,
    )
    member = next(item for item in membership.members if item.symbol == "NEWUSDT")
    assert member.eligible is False
    assert member.quality_status == "INELIGIBLE_DATA_QUALITY"
    assert member.unusable_segments == (gap.partition,)


def test_08_later_reentry_reuses_minimum_history_rule(tmp_path: Path) -> None:
    gap = _gap(tmp_path, start=datetime(2024, 1, 1, tzinfo=UTC))
    common = {
        "tmp_path": tmp_path,
        "train_end": datetime(2025, 3, 1, tzinfo=UTC),
        "required_start": datetime(2024, 2, 1, tzinfo=UTC),
        "required_end": datetime(2025, 6, 1, tzinfo=UTC),
        "gap": gap,
    }
    insufficient = _fold_membership(**common, history_days=364.0)
    sufficient = _fold_membership(**common, history_days=365.0)
    assert "NEWUSDT" not in insufficient.active_symbols
    assert "NEWUSDT" in sufficient.active_symbols


def test_09_rolling_features_reset_at_gap() -> None:
    source = synthetic_candles(rows_per_symbol=80)
    symbols = np.asarray(source["symbol"].to_pylist(), dtype=object)
    btc = source.filter(pa.array(symbols == "BTCUSDT"))
    times = btc["open_time"].combine_chunks().cast(pa.int64()).to_numpy()
    removed = int(times[40])
    clean = btc.filter(pa.array(times != removed))
    result = generate_multiasset_features(
        clean,
        registry=synthetic_registry(),
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
    ).table
    feature_times = result["feature_time"].combine_chunks().cast(pa.int64()).to_numpy()
    first_after = int(np.flatnonzero(feature_times == removed + 10 * 60_000_000)[0])
    assert np.isnan(float(result["return_5m"][first_after].as_py()))
    assert np.isnan(float(result["ema20_distance_pct"][first_after].as_py()))


def test_10_targets_never_cross_missing_candle() -> None:
    source = synthetic_candles(rows_per_symbol=80)
    symbols = np.asarray(source["symbol"].to_pylist(), dtype=object)
    btc = source.filter(pa.array(symbols == "BTCUSDT"))
    times = btc["open_time"].combine_chunks().cast(pa.int64()).to_numpy()
    gap_time = int(times[40])
    clean = btc.filter(pa.array(times != gap_time))
    clean_times = clean["open_time"].combine_chunks().cast(pa.int64()).to_numpy()
    features = pa.table(
        {
            "symbol": ["BTCUSDT"] * clean.num_rows,
            "feature_time": pa.array(
                clean_times + 5 * 60_000_000, type=pa.timestamp("us", tz="UTC")
            ),
            "daily_volatility": [0.01] * clean.num_rows,
            "atr14_pct": [0.01] * clean.num_rows,
        }
    )
    targets = generate_multiasset_targets(
        clean,
        features,
        config=Phase7Config().targets,
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    ).table
    starts = targets["feature_time"].combine_chunks().cast(pa.int64()).to_numpy()
    ends = targets["label_end_time"].combine_chunks().cast(pa.int64()).to_numpy()
    assert not np.any((starts <= gap_time) & (ends >= gap_time))


def test_11_higher_timeframe_context_expires_at_gap() -> None:
    start = datetime(2023, 11, 28, tzinfo=UTC)
    candles = [
        make_candle(start=start + index * DAY, interval_minutes=1_440, symbol="DYDXUSDT")
        for index in (0, 1, 3, 4)
    ]
    context = build_higher_timeframe_context(None, candles_to_table(candles))
    assert context is not None
    probe = int((start + 3 * DAY).timestamp() * 1_000_000)
    values, names = _asof_higher_context(
        np.asarray(["DYDXUSDT"], dtype=object),
        np.asarray([probe], dtype=np.int64),
        context,
    )
    assert names
    assert all(np.isnan(column[0]) for column in values.values())


def test_12_removed_row_remains_explicit_segment_boundary() -> None:
    start = datetime(2023, 11, 29, tzinfo=UTC)
    records = [
        {
            "partition_key": f"p{index}",
            "start": (start + index * DAY).isoformat(),
            "end": (start + (index + 1) * DAY).isoformat(),
            "status": "complete",
            "row_count": 1,
            "file": f"p{index}.parquet",
        }
        for index in range(3)
    ]
    groups = _contiguous_partition_groups(records, {"p1"})
    assert [[item["partition_key"] for item in group] for group in groups] == [["p0"], ["p2"]]
    assert datetime.fromisoformat(groups[1][0]["start"]) > datetime.fromisoformat(
        groups[0][-1]["end"]
    )


@pytest.mark.parametrize(
    ("symbol", "start"),
    [
        ("ARBUSDT", datetime(2022, 5, 7, tzinfo=UTC)),
        ("RANDOMUSDT", datetime(2025, 2, 3, tzinfo=UTC)),
    ],
)
def test_13_policy_is_symbol_and_timestamp_agnostic(
    tmp_path: Path, symbol: str, start: datetime
) -> None:
    gap = _gap(tmp_path, symbol=symbol, start=start)
    assert gap.symbol == symbol
    assert gap.start == start
    assert gap.intersects(start, start + DAY)
    assert not gap.intersects(start - DAY, start)


def test_14_future_gap_does_not_change_earlier_membership_identity(tmp_path: Path) -> None:
    gap = _gap(tmp_path)
    kwargs = {
        "tmp_path": tmp_path,
        "train_end": datetime(2024, 7, 1, tzinfo=UTC),
        "required_start": datetime(2024, 1, 1, tzinfo=UTC),
        "required_end": datetime(2024, 11, 1, tzinfo=UTC),
    }
    baseline = _fold_membership(**kwargs, gap=None)
    with_future_gap = _fold_membership(**kwargs, gap=gap)
    assert with_future_gap.membership_hash == baseline.membership_hash
    assert with_future_gap.active_symbols == baseline.active_symbols


def test_15_later_valid_symbol_is_recorded_after_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _fake_acquisition(tmp_path, monkeypatch)
    assert result.manifests["BADUSDT"].endswith("BADUSDT-segmented-silver.json")
    assert result.manifests["LATERUSDT"].endswith("LATERUSDT-bronze-silver.json")
    assert len(result.gaps) == 1


def test_16_required_core_symbol_remains_hard_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(QualityGateRejected):
        _fake_acquisition(tmp_path, monkeypatch, strict=True)
