from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.research.config import DatasetBuildConfig, FeatureConfig, LabelConfig, SplitConfig
from crypto_ai.research.gold import build_gold_dataset, read_gold_dataset
from crypto_ai.research.metrics import (
    distribution_summary,
    feature_distribution,
    prediction_buckets,
    regression_metrics,
)
from crypto_ai.research.split import chronological_purged_split
from tests.research_helpers import make_research_candles, write_silver_dataset


def _build(tmp_path: Path, count: int = 300):
    manifest_path, silver_path = write_silver_dataset(tmp_path, make_research_candles(count))
    result = build_gold_dataset(
        DatasetBuildConfig(
            silver_manifest=manifest_path,
            output_root=tmp_path / "gold",
        ),
        FeatureConfig(),
        LabelConfig(),
    )
    return result, silver_path


def test_gold_dataset_is_immutable_lineage_complete_and_idempotent(tmp_path: Path) -> None:
    manifest_path, silver_path = write_silver_dataset(tmp_path, make_research_candles(200))
    silver_hash = file_sha256(silver_path)
    config = DatasetBuildConfig(
        silver_manifest=manifest_path,
        output_root=tmp_path / "gold",
    )

    first = build_gold_dataset(config, FeatureConfig(), LabelConfig())
    second = build_gold_dataset(config, FeatureConfig(), LabelConfig())
    table, manifest = read_gold_dataset(first.manifest_path)

    assert first.row_count == 138
    assert second.reused
    assert second.dataset_version == first.dataset_version
    assert second.dataset_path == first.dataset_path
    assert file_sha256(silver_path) == silver_hash
    assert table.num_rows == 138
    assert manifest["source_silver_version"] == "silver-test-v1"
    assert manifest["source_bronze_dataset_version"] == "dataset-test-v1"
    assert manifest["validation_report_id"] == "quality-test-v1"
    assert manifest["feature_count"] == 13
    assert manifest["target_column"] == "future_return_60m"
    assert manifest["build_summary"]["rows_removed_feature_warmup"] == 49
    assert manifest["build_summary"]["label_reason_counts"]["insufficient_future"] == 13
    assert manifest["constant_features"] == []
    feature_times = table.column("feature_time").cast(pa.int64()).to_numpy()
    assert np.all(np.diff(feature_times) > 0)


def test_gold_dataset_reports_gap_invalidated_labels(tmp_path: Path) -> None:
    manifest_path, _ = write_silver_dataset(tmp_path, make_research_candles(220, gap_index=150))
    result = build_gold_dataset(
        DatasetBuildConfig(
            silver_manifest=manifest_path,
            output_root=tmp_path / "gold",
        ),
        FeatureConfig(),
        LabelConfig(),
    )
    manifest = read_manifest(result.manifest_path)

    assert manifest is not None
    assert manifest["build_summary"]["label_reason_counts"]["gap_in_horizon"] > 0
    assert manifest["build_summary"]["rows_removed_feature_warmup"] > 49


def test_gold_builder_rejects_tiny_silver_sample_cleanly(tmp_path: Path) -> None:
    manifest_path, _ = write_silver_dataset(tmp_path, make_research_candles(12))

    with pytest.raises(ValueError, match="No usable Gold rows"):
        build_gold_dataset(
            DatasetBuildConfig(
                silver_manifest=manifest_path,
                output_root=tmp_path / "gold",
            ),
            FeatureConfig(),
            LabelConfig(),
        )


def test_temporal_split_is_chronological_and_purges_overlapping_labels(
    tmp_path: Path,
) -> None:
    result, _ = _build(tmp_path)
    table, _ = read_gold_dataset(result.manifest_path)
    split = chronological_purged_split(
        table,
        SplitConfig(minimum_rows_per_split=10),
    )
    train_feature = split.train.column("feature_time").cast(pa.int64()).to_numpy()
    train_end = split.train.column("label_end_time").cast(pa.int64()).to_numpy()
    validation_feature = split.validation.column("feature_time").cast(pa.int64()).to_numpy()
    validation_end = split.validation.column("label_end_time").cast(pa.int64()).to_numpy()
    test_feature = split.test.column("feature_time").cast(pa.int64()).to_numpy()

    assert np.all(np.diff(train_feature) > 0)
    assert train_feature[-1] < validation_feature[0] < test_feature[0]
    assert np.all(train_end < split.validation_start_us)
    assert np.all(validation_end < split.test_start_us)
    assert split.purged_train_rows == 12
    assert split.purged_validation_rows == 12
    metadata = split.metadata()
    assert metadata["validation_start"] == metadata["validation_period"]["start"]
    assert metadata["test_start"] == metadata["test_period"]["start"]


def test_split_rejects_bad_timestamp_semantics(tmp_path: Path) -> None:
    result, _ = _build(tmp_path)
    table, _ = read_gold_dataset(result.manifest_path)
    columns = table.to_pydict()
    columns["entry_time"][0] = columns["feature_time"][0]
    columns["label_end_time"][0] = columns["feature_time"][0]
    invalid = pa.Table.from_pydict(columns, schema=table.schema)

    with pytest.raises(ValueError, match="timestamp semantics"):
        chronological_purged_split(invalid, SplitConfig(minimum_rows_per_split=10))


def test_regression_metrics_match_known_values() -> None:
    actual = np.array([1.0, -1.0, 1.0, -1.0])
    predicted = np.array([0.5, -0.5, -0.5, -1.0])
    metrics = regression_metrics(actual, predicted)

    assert metrics["mae"] == pytest.approx(0.625)
    assert metrics["rmse"] == pytest.approx(np.sqrt(0.6875))
    assert metrics["directional_accuracy"] == pytest.approx(0.75)
    assert metrics["pearson_ic"] is not None
    assert metrics["spearman_ic"] is not None


def test_spearman_matches_known_rank_correlation() -> None:
    metrics = regression_metrics(
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array([1.0, 3.0, 2.0, 4.0]),
    )

    assert metrics["spearman_ic"] == pytest.approx(0.8)


def test_constant_predictions_have_undefined_correlations() -> None:
    metrics = regression_metrics(
        np.array([-1.0, 0.0, 1.0]),
        np.array([0.25, 0.25, 0.25]),
    )

    assert metrics["pearson_ic"] is None
    assert metrics["spearman_ic"] is None


def test_prediction_buckets_cover_each_observation_once() -> None:
    actual = np.arange(20, dtype=np.float64) - 10
    predicted = actual[::-1]
    buckets = prediction_buckets(actual, predicted)

    assert len(buckets) == 10
    assert sum(bucket["count"] for bucket in buckets) == 20
    assert buckets[0]["maximum_prediction"] <= buckets[-1]["minimum_prediction"]


def test_distribution_and_feature_summaries_report_sanity_fields() -> None:
    values = np.array([-0.01, -0.00005, 0.0, 0.00005, 0.02])
    target = distribution_summary(values, near_zero_threshold=0.0001)
    feature = feature_distribution(np.array([1.0, 1.0, np.nan, np.inf]))

    assert target["count"] == 5
    assert target["near_zero_percentage"] == pytest.approx(60.0)
    expected_percentiles = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    for key, expected in zip(
        ("p01", "p05", "p25", "p50", "p75", "p95", "p99"),
        expected_percentiles,
        strict=True,
    ):
        assert target["percentiles"][key] == pytest.approx(expected)
    assert feature["missing_count"] == 1
    assert feature["infinite_count"] == 1
    assert feature["constant"]
