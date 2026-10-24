"""Future quality evidence must not choose an earlier training population."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.config import stable_hash
from crypto_ai.phase7.features import (
    CROSS_SECTIONAL_SOURCE_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
    bind_fold_cross_sectional_context,
)
from crypto_ai.phase7.folds import (
    IneligibleFoldError,
    fit_train_only_clusters,
    fit_train_only_liquidity_tiers,
    slice_multiasset_fold,
)
from crypto_ai.phase7.models import prepare_architecture_inputs
from crypto_ai.phase7.universe import FoldActiveUniverse, select_fold_active_universe
from tests.phase7.test_causal_segment_quarantine import _gap
from tests.phase7.test_cold_start_universe import (
    NEW_EVIDENCE,
    _config,
    _core_context,
    _descriptor,
    _registry,
)

TRAIN_START = datetime(2024, 1, 1, tzinfo=UTC)
TRAIN_END = datetime(2024, 7, 1, tzinfo=UTC)
TEST_END = datetime(2025, 1, 1, tzinfo=UTC)


def _membership(gaps=(), *, view="EXPANDING", required_end=TEST_END):
    registry = _registry()
    config = _config()
    core, policy, descriptors = _core_context(registry, config)
    return select_fold_active_universe(
        registry,
        [*descriptors, _descriptor("NEWUSDT", TRAIN_END, NEW_EVIDENCE)],
        fold_id="gap-causality",
        train_end=TRAIN_END,
        core_universe=core,
        expansion_policy=policy,
        config=config,
        research_view=view,
        unusable_segments=gaps,
        required_start=TRAIN_START,
        required_end=required_end,
    )


@pytest.mark.parametrize("view", ["CORE", "EXPANDING"])
@pytest.mark.parametrize("symbol", ["BTCUSDT", "NEWUSDT"])
@pytest.mark.parametrize("offset_days", [-0.5, 0, 1, 60, 120])
def test_future_gap_within_same_fold_cannot_change_training_membership(
    tmp_path, view, symbol, offset_days
):
    gap = _gap(tmp_path, symbol=symbol, start=TRAIN_END + timedelta(days=offset_days))
    before = _membership(view=view)
    after = _membership((gap,), view=view)
    assert after.active_symbols == before.active_symbols
    assert after.membership_hash == before.membership_hash
    assert after.model_dump(mode="json") == before.model_dump(mode="json")


@pytest.mark.parametrize("symbol", ["BTCUSDT", "NEWUSDT"])
def test_completed_training_gap_still_rejects_corrupt_history(tmp_path, symbol):
    gap = _gap(tmp_path, symbol=symbol, start=TRAIN_END - timedelta(days=1))
    membership = _membership((gap,))
    assert symbol not in membership.active_symbols
    member = next(item for item in membership.members if item.symbol == symbol)
    assert member.quality_status == "INELIGIBLE_DATA_QUALITY"
    assert member.unusable_segments == (gap.partition,)


def test_gap_order_does_not_change_causal_identity(tmp_path):
    first = _gap(tmp_path, symbol="NEWUSDT", start=TRAIN_END - timedelta(days=4))
    second = _gap(tmp_path, symbol="NEWUSDT", start=TRAIN_END - timedelta(days=2))
    assert (
        _membership((first, second)).membership_hash == _membership((second, first)).membership_hash
    )


def test_empty_gap_intersection_is_empty(tmp_path):
    gap = _gap(tmp_path, start=TRAIN_END - timedelta(hours=12))
    assert not gap.intersects(TRAIN_END, TRAIN_END)


def test_extending_only_future_required_window_cannot_change_membership(tmp_path):
    gap = _gap(tmp_path, start=TRAIN_END + timedelta(days=120))
    assert (
        _membership((gap,), required_end=TRAIN_END).membership_hash
        == _membership((gap,), required_end=TEST_END).membership_hash
    )


def test_old_membership_artifacts_remain_readable_without_relabelling():
    current = _membership()
    assert current.gap_gate_policy == "TRAIN_HISTORY_ONLY_V2"
    legacy = current.model_dump(mode="json", exclude={"membership_hash", "gap_gate_policy"})
    legacy["membership_hash"] = stable_hash(legacy)
    restored = FoldActiveUniverse.model_validate(legacy)
    assert restored.gap_gate_policy == "FULL_FOLD_REQUIRED_RANGE_V1"
    assert restored.membership_hash == legacy["membership_hash"]
    assert restored.membership_hash != current.membership_hash


def test_duplicate_gap_evidence_cannot_change_membership_identity(tmp_path):
    gap = _gap(tmp_path, start=TRAIN_END - timedelta(days=2))
    assert _membership((gap,)).membership_hash == _membership((gap, gap)).membership_hash


def test_gap_before_required_training_window_is_not_a_current_exclusion(tmp_path):
    gap = _gap(tmp_path, start=TRAIN_START - timedelta(days=2))
    assert _membership((gap,)).membership_hash == _membership().membership_hash


@pytest.mark.parametrize(
    "gap_start",
    [
        TRAIN_END,
        datetime(2024, 8, 1, tzinfo=UTC),
        datetime(2024, 10, 2, tzinfo=UTC),
        datetime(2024, 11, 1, tzinfo=UTC),
    ],
)
def test_future_gap_does_not_change_actual_train_context_or_numpy_inputs(tmp_path, gap_start):
    # Artificial rows and tiny descriptor clusters only. No acquisition/Gold/LightGBM fit.
    symbols = ("BTCUSDT", "ETHUSDT", "NEWUSDT")
    segment_starts = [
        TRAIN_START,
        TRAIN_END,
        datetime(2024, 9, 1, tzinfo=UTC),
        datetime(2024, 10, 2, tzinfo=UTC),  # After the exact Oct-1-noon Cal-A/Cal-B midpoint.
        datetime(2024, 11, 1, tzinfo=UTC),
    ]
    rows = []
    for start in segment_starts:
        for step in range(20):
            time = start + timedelta(hours=3, minutes=5 * step)
            for index, symbol in enumerate(symbols):
                rows.append(
                    {
                        "symbol": symbol,
                        "feature_time": time,
                        "entry_time": time + timedelta(minutes=5),
                        "label_end_time": time + timedelta(minutes=65),
                        "horizon_minutes": 60,
                        "raw_future_return": 0.001 * (index + 1),
                        "f1": float(index + 1),
                        "return_5m": [0.01, -0.02, 0.005][index],
                        "realized_volatility_1h": 0.01,
                        "taker_flow_imbalance": 0.1,
                        "market_membership_hash": "PREVIEW",
                        **{name: 0.0 for name in MARKET_CONTEXT_COLUMNS},
                        **{name: float(index + 1) for name in CROSS_SECTIONAL_SOURCE_COLUMNS},
                        "trailing_liquidity_percentile": 0.0,
                        "trailing_volatility_percentile": 0.0,
                        "trade_intensity_percentile": 0.0,
                    }
                )
    table = pa.Table.from_pylist(rows)
    plan = FoldPlan(
        "gap-causality",
        0,
        TRAIN_START,
        TRAIN_END,
        TRAIN_END,
        segment_starts[2],
        segment_starts[2],
        segment_starts[4],
        segment_starts[4],
        TEST_END,
    )
    registry, config = _registry(), _config()
    core, policy, descriptors = _core_context(registry, config)
    arguments = dict(
        registry=registry,
        universe=core,
        expansion_policy=policy,
        research_view="EXPANDING",
        descriptors=[*descriptors, _descriptor("NEWUSDT", TRAIN_END, NEW_EVIDENCE)],
        universe_config=config,
        schedule=ScheduleConfig(embargo_minutes=120, minimum_rows_per_segment=1),
        holdout_start=datetime(2026, 8, 1, tzinfo=UTC),
        cluster_count=2,
        seed=42,
    )
    baseline = slice_multiasset_fold(table, plan, **arguments)
    gap = _gap(tmp_path, symbol="BTCUSDT", start=gap_start)
    membership = _membership((gap,))
    assert baseline.eligibility_manifest["fold_membership_hash"] == membership.membership_hash
    # Independently exercise the membership-dependent context and matrix path.
    # The full fold entrypoint below must still block known future corruption.
    filtered = table.filter(
        pa.array([s in membership.active_symbols for s in table["symbol"].to_pylist()])
    )
    context = bind_fold_cross_sectional_context(filtered)
    perturbed_train = context.filter(pa.compute.less(context["feature_time"], pa.scalar(TRAIN_END)))
    perturbed_validation = context.filter(
        pa.compute.and_(
            pa.compute.greater_equal(context["feature_time"], pa.scalar(TRAIN_END)),
            pa.compute.less(context["feature_time"], pa.scalar(segment_starts[2])),
        )
    )
    assert baseline.train.equals(perturbed_train)
    assert baseline.validation.equals(perturbed_validation)
    cluster_mapping, _ = fit_train_only_clusters(
        arguments["descriptors"],
        train_end=TRAIN_END,
        eligible_symbols=set(membership.active_symbols),
        cluster_count=2,
        seed=42,
    )
    assert baseline.cluster_mapping == cluster_mapping
    assert baseline.liquidity_tiers == fit_train_only_liquidity_tiers(
        arguments["descriptors"],
        train_end=TRAIN_END,
        eligible_symbols=set(membership.active_symbols),
    )
    columns = ("f1", "market_mean_return", "trailing_liquidity_percentile")
    prepared = [
        prepare_architecture_inputs(
            train, validation, feature_columns=columns, target_column="raw_future_return"
        )
        for train, validation in (
            (baseline.train, baseline.validation),
            (perturbed_train, perturbed_validation),
        )
    ]
    for name in ("train_x", "train_y", "train_symbols", "validation_x", "validation_y"):
        np.testing.assert_array_equal(getattr(prepared[0], name), getattr(prepared[1], name))
    with pytest.raises(ValueError, match="post-TRAIN data-quality gaps") as caught:
        slice_multiasset_fold(table, plan, unusable_segments=(gap,), **arguments)
    assert not isinstance(caught.value, IneligibleFoldError)
