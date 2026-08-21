from __future__ import annotations

import json
from datetime import timedelta

from crypto_ai.phase4.features import FEATURE_V2_VERSION
from crypto_ai.phase4_1.config import GoldV2_1Config
from crypto_ai.phase4_1.gold import build_gold_v2_1, read_gold_v2_1
from crypto_ai.research.config import LabelConfig
from tests.research_helpers import make_research_candles, write_silver_dataset


def test_gold_v2_1_is_immutable_auditable_and_keeps_label_v1(tmp_path) -> None:
    candles = make_research_candles(4_500)
    silver_manifest, _ = write_silver_dataset(tmp_path, candles)
    config = GoldV2_1Config(
        silver_manifests=(silver_manifest,),
        dataset_family="core_long_history",
        start_time=candles[0].open_time,
        end_time=candles[-1].open_time + timedelta(minutes=5),
        output_root=tmp_path / "gold",
    )

    first = build_gold_v2_1(config, LabelConfig())
    second = build_gold_v2_1(config, LabelConfig())
    table, manifest = read_gold_v2_1(first.manifest_path)
    coverage = json.loads(
        (first.manifest_path.parent / "feature_coverage.json").read_text(encoding="utf-8")
    )
    target = json.loads(
        (first.manifest_path.parent / "target_analysis.json").read_text(encoding="utf-8")
    )

    assert second.reused is True
    assert first.dataset_version == second.dataset_version
    assert table.num_rows == manifest["row_count"]
    assert manifest["dataset_family"] == "core_long_history"
    assert manifest["feature_version"] == "2.1.0"
    assert manifest["feature_count"] == 52
    assert manifest["label_version"] == "1.0.0"
    assert manifest["label_config"]["entry_reference"] == "next_candle_open"
    assert manifest["research_cutoff_exclusive"] == config.end_time.isoformat()
    assert coverage["features"]["taker_buy_base_share"]["group"] == "taker_flow"
    assert coverage["groups"]["taker_flow"]["expected_rows"] == len(candles)
    assert coverage["groups"]["taker_flow"]["availability_start"] is not None
    assert coverage["groups"]["taker_flow"]["maximum_gap_minutes"] >= 0
    assert coverage["groups"]["taker_flow"]["source_dataset"].endswith("kline taker volumes")
    assert (
        coverage["unavailable_or_intentionally_excluded_groups"]["open_interest"][
            "coverage_percentage"
        ]
        == 0.0
    )
    assert target["overall"]["count"] == table.num_rows
    assert FEATURE_V2_VERSION == "2.0.0"
