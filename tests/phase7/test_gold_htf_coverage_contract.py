from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.phase7 import pipeline
from crypto_ai.phase7.acquisition import (
    AcquisitionPaths,
    QualityGateRejected,
    _promote_candles,
    load_candle_family,
)
from crypto_ai.phase7.features import _asof_higher_context, build_higher_timeframe_context
from tests.phase7.test_archive_missing_reconciliation import START, _archive, _config

DAY = timedelta(days=1)


def _silver(tmp_path: Path) -> Path:
    config = _config(tmp_path)
    manifest, _, _ = _archive(tmp_path, missing=())
    return _promote_candles(config, AcquisitionPaths.from_config(config), manifest)


def test_a_entire_gold_chunk_before_validated_htf_availability_is_absent(
    tmp_path: Path,
) -> None:
    silver = _silver(tmp_path)

    table = load_candle_family(
        {"TESTUSDT": str(silver)},
        interval="1d",
        start=START - 2 * DAY,
        end=START,
        allow_preavailability_absence=True,
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
        allow_preavailability_absence=True,
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
        allow_preavailability_absence=True,
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
            allow_preavailability_absence=True,
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
        allow_preavailability_absence=True,
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
            allow_preavailability_absence=True,
        )


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
