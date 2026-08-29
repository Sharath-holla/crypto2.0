from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan, calibration_split_time, slice_hardened_fold
from crypto_ai.phase7.config import Phase7Config, TargetConfig, load_phase7_config, stable_hash
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry
from crypto_ai.phase7.targets import generate_multiasset_targets

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/phase7/research_v1.toml"
CANONICAL_CONFIGURATION_HASH = "cc550337f1f4ee4654124bf6"


def _separator_config(separator: str) -> Phase7Config:
    base = load_phase7_config(CONFIG_PATH)

    def logical(value: str) -> str:
        return value.replace("/", separator)

    payload = base.model_dump(mode="python")
    payload["binance_config"] = logical("configs/data/binance.toml")
    payload["quality_config"] = logical("configs/data_quality/default.toml")
    payload["paths"] = {
        **base.paths.model_dump(mode="python"),
        "data_root": logical("data"),
        "artifact_root": logical("local_artifacts/phase7"),
        "gold_root": logical("data/gold/phase7"),
        "checkpoint_root": logical("local_artifacts/phase7/checkpoints"),
    }
    return Phase7Config.model_validate(payload)


def test_phase7_configuration_identity_is_cross_platform_and_canonical() -> None:
    windows = _separator_config("\\")
    posix = _separator_config("/")

    assert windows.configuration_identity_payload() == posix.configuration_identity_payload()
    assert windows.configuration_hash == posix.configuration_hash
    assert windows.configuration_hash == CANONICAL_CONFIGURATION_HASH


def test_configuration_identity_is_order_stable_and_path_semantic() -> None:
    config = load_phase7_config(CONFIG_PATH)
    payload = config.configuration_identity_payload()
    reversed_payload = dict(reversed(tuple(payload.items())))
    changed = config.model_copy(
        update={
            "paths": config.paths.model_copy(
                update={"artifact_root": Path("local_artifacts/phase7-other")}
            )
        }
    )

    assert stable_hash(payload) == stable_hash(reversed_payload)
    assert config.configuration_hash == CANONICAL_CONFIGURATION_HASH
    assert changed.configuration_hash != config.configuration_hash
    assert payload["required_intervals"] == ["5m", "12h", "1d"]
    assert payload["research_cutoff"] == "2026-07-01T00:00:00Z"
    assert payload["prospective_holdout_used"] is False
    assert payload["paths"]["cloud_storage_root"] is None
    assert payload["models"]["seed"] == 42


def test_target_v2_spans_are_measured_from_entry_for_every_horizon() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    features = generate_multiasset_features(
        candles,
        registry=synthetic_registry(),
        config=load_phase7_config(CONFIG_PATH).features.model_copy(
            update={
                "correlation_window_rows": 24,
                "liquidity_window_rows": 24,
                "volatility_window_rows": 24,
                "daily_volatility_rows": 24,
                "seven_day_volatility_rows": 48,
                "include_12h": False,
                "include_1d": False,
                "include_derivatives": False,
            }
        ),
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=TargetConfig(),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    ).table
    feature_times = targets.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    entry_times = targets.column("entry_time").combine_chunks().cast(pa.int64()).to_numpy()
    label_ends = targets.column("label_end_time").combine_chunks().cast(pa.int64()).to_numpy()
    horizons = np.asarray(targets.column("horizon_minutes").to_pylist(), dtype=np.int64)

    assert np.all(entry_times - feature_times == 5 * 60_000_000)
    for horizon in (15, 30, 60, 120):
        selected = horizons == horizon
        assert np.any(selected)
        assert np.all(label_ends[selected] - entry_times[selected] == horizon * 60_000_000)
        assert np.all(label_ends[selected] - feature_times[selected] == (horizon + 5) * 60_000_000)


def test_120m_embargo_and_actual_label_end_purge_protect_every_boundary() -> None:
    plan = FoldPlan(
        fold_id="boundary-proof",
        index=0,
        train_start=datetime(2020, 1, 1, tzinfo=UTC),
        train_end=datetime(2020, 2, 1, tzinfo=UTC),
        validation_start=datetime(2020, 2, 1, tzinfo=UTC),
        validation_end=datetime(2020, 3, 1, tzinfo=UTC),
        calibration_start=datetime(2020, 3, 1, tzinfo=UTC),
        calibration_end=datetime(2020, 4, 1, tzinfo=UTC),
        test_start=datetime(2020, 4, 1, tzinfo=UTC),
        test_end=datetime(2020, 5, 1, tzinfo=UTC),
    )
    split = calibration_split_time(plan)
    boundaries = (
        plan.validation_start,
        plan.calibration_start,
        split,
        plan.test_start,
    )
    offsets = (-130, -125, -120, -115, -5, 0, 5, 120, 125)
    feature_times = sorted(
        {boundary + timedelta(minutes=offset) for boundary in boundaries for offset in offsets}
    )
    table = pa.table(
        {
            "feature_time": pa.array(feature_times, type=pa.timestamp("us", tz="UTC")),
            "entry_time": pa.array(
                [value + timedelta(minutes=5) for value in feature_times],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "label_end_time": pa.array(
                [value + timedelta(minutes=125) for value in feature_times],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "horizon_minutes": [120] * len(feature_times),
        }
    )
    schedule = ScheduleConfig(
        train_months=1,
        validation_months=1,
        calibration_months=1,
        test_months=1,
        step_months=1,
        embargo_minutes=120,
        minimum_rows_per_segment=1,
    )
    result = slice_hardened_fold(
        table,
        plan,
        schedule,
        holdout_start=datetime(2020, 6, 1, tzinfo=UTC),
    )
    segments = (
        ("train", result.train, "validation", result.validation, plan.validation_start),
        (
            "validation",
            result.validation,
            "calibration_a",
            result.calibration_a,
            plan.calibration_start,
        ),
        ("calibration_a", result.calibration_a, "calibration_b", result.calibration_b, split),
        (
            "calibration_b",
            result.calibration_b,
            "test",
            result.release_test(frozen_identity="boundary-proof"),
            plan.test_start,
        ),
    )

    for earlier_name, earlier, later_name, later, boundary in segments:
        earlier_features = set(earlier.column("feature_time").to_pylist())
        earlier_label_ends = earlier.column("label_end_time").to_pylist()
        later_features = set(later.column("feature_time").to_pylist())

        assert boundary - timedelta(minutes=130) in earlier_features
        for offset in (-125, -120, -115, -5):
            assert boundary + timedelta(minutes=offset) not in earlier_features
        assert all(value < boundary for value in earlier_label_ends)
        assert boundary not in later_features
        assert boundary + timedelta(minutes=5) not in later_features
        assert boundary + timedelta(minutes=120) in later_features
        assert boundary + timedelta(minutes=125) in later_features
        assert min(later_features) >= boundary + timedelta(minutes=120)
        assert result.report["segments"][earlier_name]["purged"] == 4
        assert result.report["segments"][later_name]["embargoed"] == 2
